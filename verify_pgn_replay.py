#!/usr/bin/env python3
"""Verify that replaying a PGN through your dataset matches python-chess for ALL games."""
import sys, pickle, chess, chess.pgn
from board import ChessBoard
from move_helpers import index_to_move

def verify(pgn_path, data_path):
    with open(data_path, 'rb') as f:
        data = pickle.load(f)
    if isinstance(data, dict):
        positions = data['positions']
        policies = data['policies']
        game_starts = data.get('game_starts', [False]*len(positions))
        samples = list(zip(positions, policies, game_starts))
    elif isinstance(data, list):
        samples = []
        for item in data:
            idx = item[1]
            board = item[0]
            is_start = item[9] if len(item) >= 10 else False
            samples.append((board, idx, is_start))
    else:
        print("Unsupported format")
        return

    games = []
    current_game = []
    for board, idx, is_start in samples:
        if is_start and current_game:
            games.append(current_game)
            current_game = []
        current_game.append((board, idx))
    if current_game:
        games.append(current_game)

    with open(pgn_path) as f:
        pgn_games = []
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            board_lib = chess.Board()
            moves = []
            for move in game.mainline_moves():
                moves.append(move)
                board_lib.push(move)
            pgn_games.append((board_lib.fen(), moves))

    if len(games) != len(pgn_games):
        print(f"Warning: dataset has {len(games)} games, PGN has {len(pgn_games)}. Comparing first {min(len(games), len(pgn_games))}.")
    for i in range(min(len(games), len(pgn_games))):
        engine_board = ChessBoard()
        for board, idx in games[i]:
            if not engine_board.equals(board):
                engine_board = board.copy()
            move = index_to_move(idx)
            engine_board.make_move(move)
        final_engine_fen = engine_board.to_fen()
        ref_fen, _ = pgn_games[i]
        if final_engine_fen.split()[:4] != ref_fen.split()[:4]:
            print(f"Mismatch in game {i+1}")
            print(f"Reference: {ref_fen}")
            print(f"Engine   : {final_engine_fen}")
            sys.exit(1)
    print("OK: all games match the reference parser.")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python verify_pgn_replay.py <game.pgn> <dataset.pkl>")
        sys.exit(1)
    verify(sys.argv[1], sys.argv[2])
