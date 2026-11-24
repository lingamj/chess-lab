#!/usr/bin/env python3
"""
Match your engine against Stockfish.
Usage: python match_vs_stockfish.py --model distilled_nn.pkl --games 20 --sims 100 --stockfish-level 8
"""

import argparse
import time
import math
import chess
import chess.engine
from board import ChessBoard
from nn import DualNet
from mcts import MCTS

def play_game(engine_nn, stockfish_engine, sims=100, engine_white=True, stockfish_time=0.1):
    """Play one game between engine and Stockfish."""
    board = chess.Board()
    move_count = 0

    while not board.is_game_over() and move_count < 200:
        if board.turn == chess.WHITE:
            if engine_white:
                # Engine move
                cb = ChessBoard()
                cb.set_fen(board.fen())
                mcts = MCTS(engine_nn, num_simulations=sims)
                policy = mcts.search(cb, temperature=0.0)
                move = max(policy.items(), key=lambda x: x[1])[0]
                fr, fc, tr, tc = move[0], move[1], move[2], move[3]
                from_sq = (7 - fr) * 8 + fc
                to_sq = (7 - tr) * 8 + tc
                promo = move[4] if len(move) > 4 else None
                if promo:
                    promo_map = {'Q': chess.QUEEN, 'R': chess.ROOK, 'B': chess.BISHOP, 'N': chess.KNIGHT}
                    move_uci = chess.Move(from_sq, to_sq, promotion=promo_map.get(promo))
                else:
                    move_uci = chess.Move(from_sq, to_sq)
                board.push(move_uci)
            else:
                # Stockfish move
                result_move = stockfish_engine.play(board, chess.engine.Limit(time=stockfish_time))
                board.push(result_move.move)  # <-- FIX: access .move
        else:
            if not engine_white:
                # Engine move (as black)
                cb = ChessBoard()
                cb.set_fen(board.fen())
                mcts = MCTS(engine_nn, num_simulations=sims)
                policy = mcts.search(cb, temperature=0.0)
                move = max(policy.items(), key=lambda x: x[1])[0]
                fr, fc, tr, tc = move[0], move[1], move[2], move[3]
                from_sq = (7 - fr) * 8 + fc
                to_sq = (7 - tr) * 8 + tc
                promo = move[4] if len(move) > 4 else None
                if promo:
                    promo_map = {'Q': chess.QUEEN, 'R': chess.ROOK, 'B': chess.BISHOP, 'N': chess.KNIGHT}
                    move_uci = chess.Move(from_sq, to_sq, promotion=promo_map.get(promo))
                else:
                    move_uci = chess.Move(from_sq, to_sq)
                board.push(move_uci)
            else:
                # Stockfish move
                result_move = stockfish_engine.play(board, chess.engine.Limit(time=stockfish_time))
                board.push(result_move.move)  # <-- FIX: access .move
        move_count += 1

    result = board.result()
    if engine_white:
        if result == "1-0":
            return "win"
        elif result == "0-1":
            return "loss"
        else:
            return "draw"
    else:
        if result == "1-0":
            return "loss"
        elif result == "0-1":
            return "win"
        else:
            return "draw"

def main():
    parser = argparse.ArgumentParser(description="Match your engine vs Stockfish")
    parser.add_argument('--model', default="distilled_nn.pkl", help='Path to your model')
    parser.add_argument('--games', type=int, default=20, help='Number of games')
    parser.add_argument('--sims', type=int, default=100, help='MCTS simulations per move')
    parser.add_argument('--stockfish-level', type=int, default=8, help='Stockfish strength level (1-20)')
    parser.add_argument('--stockfish-time', type=float, default=0.1, help='Seconds per move for Stockfish')
    args = parser.parse_args()

    nn = DualNet()
    if not nn.load(args.model):
        print(f"Failed to load model {args.model}")
        return

    engine = chess.engine.SimpleEngine.popen_uci("/data/data/com.termux/files/usr/bin/stockfish")
    if args.stockfish_level:
        engine.configure({"Skill Level": args.stockfish_level})

    wins = 0
    losses = 0
    draws = 0

    print(f"Playing {args.games} games against Stockfish (level {args.stockfish_level})...")
    for i in range(args.games):
        engine_white = (i % 2 == 0)
        result = play_game(nn, engine, sims=args.sims, engine_white=engine_white,
                           stockfish_time=args.stockfish_time)
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        else:
            draws += 1
        print(f"  Game {i+1}/{args.games}: {'Engine' if engine_white else 'Stockfish'} as white -> {result}")

    engine.quit()

    total = wins + losses + draws
    if total > 0:
        score = (wins + 0.5 * draws) / total
        elo_diff = -400 * math.log10((1 - score) / max(score, 0.001))
        print("\n" + "="*50)
        print("Match Results")
        print("="*50)
        print(f"Engine wins: {wins}")
        print(f"Engine losses: {losses}")
        print(f"Draws: {draws}")
        print(f"Engine score: {score*100:.1f}%")
        if elo_diff > 0:
            print(f"Engine is estimated to be +{elo_diff:.1f} Elo stronger than Stockfish level {args.stockfish_level}.")
        else:
            print(f"Engine is estimated to be {-elo_diff:.1f} Elo weaker than Stockfish level {args.stockfish_level}.")
        print("="*50)

if __name__ == "__main__":
    main()
