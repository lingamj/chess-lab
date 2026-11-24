#!/usr/bin/env python3
"""Engine vs Random – robust, uses current search API."""

import random, time, sys
from board import ChessBoard
from nn import DualNet
from search import SearchEngine, MATE_SCORE
from move_helpers import move_to_str, str_to_move

GAMES = 10
TIME_MS = 200        # 200 ms per move
DEPTH = 5            # search depth

def main():
    nn = DualNet()
    if not nn.load('chess_nn.pkl'):
        print("chess_nn.pkl not found")
        sys.exit(1)

    engine_wins = 0
    random_wins = 0
    draws = 0

    for game_num in range(GAMES):
        board = ChessBoard()
        engine = SearchEngine(nn=nn, max_depth=20, tt_max=100000)
        engine_plays_white = (game_num % 2 == 0)   # alternate colours

        while True:
            # Check game end
            if board.is_checkmate():
                if board.white_turn:
                    if engine_plays_white:
                        random_wins += 1
                    else:
                        engine_wins += 1
                else:
                    if engine_plays_white:
                        engine_wins += 1
                    else:
                        random_wins += 1
                break
            if board.is_draw() or board.halfmove_clock >= 100:
                draws += 1
                break

            legal_moves = board.generate_legal_moves()
            if not legal_moves:
                draws += 1
                break

            if (board.white_turn and engine_plays_white) or (not board.white_turn and not engine_plays_white):
                # Engine to move
                move, score, depth, nodes = engine.search(board, time_limit=TIME_MS, depth=DEPTH)
                if move is None or move not in legal_moves:
                    # fallback – pick a random legal move
                    move = random.choice(legal_moves)
            else:
                # Random to move
                move = random.choice(legal_moves)

            board.make_move(move)

        if (game_num + 1) % 2 == 0:
            print(f"  completed {game_num+1}/{GAMES} games...")

    print(f"\nEngine wins: {engine_wins}, Random wins: {random_wins}, Draws: {draws}")
    if engine_wins + random_wins + draws == 0:
        print("No games finished.")
    else:
        total = engine_wins + random_wins + draws
        print(f"Engine score: {engine_wins / total * 100:.1f}%")

if __name__ == '__main__':
    main()
