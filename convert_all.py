#!/usr/bin/env python3
import sys, os, pickle, chess, chess.pgn
from board import ChessBoard
from move_helpers import move_to_index

PROMO_MAP = {chess.QUEEN:'Q', chess.ROOK:'R', chess.BISHOP:'B', chess.KNIGHT:'N'}

def square_to_engine_rf(square):
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    row = 7 - rank
    return row, file

def move_to_engine_move(move):
    fr, fc = square_to_engine_rf(move.from_square)
    tr, tc = square_to_engine_rf(move.to_square)
    promo = PROMO_MAP.get(move.promotion, None)
    return (fr, fc, tr, tc, promo)

def pgn_to_data(pgn_file_path, max_games=0, source=0, append=False):
    new_data = []
    with open(pgn_file_path, "r", encoding="utf-8", errors="ignore") as f:
        game_count = 0
        while True:
            if max_games and game_count >= max_games:
                break
            game = chess.pgn.read_game(f)
            if game is None:
                break
            result = game.headers.get("Result", "*")
            if result == "1-0": value = 1.0
            elif result == "0-1": value = -1.0
            else: value = 0.0
            white_elo = game.headers.get("WhiteElo", "")
            black_elo = game.headers.get("BlackElo", "")
            opening = game.headers.get("Opening", "")
            date = game.headers.get("Date", "")
            board = chess.Board()
            for move in game.mainline_moves():
                cb = ChessBoard()
                cb.set_fen(board.fen())
                engine_move = move_to_engine_move(move)
                policy_idx = move_to_index(engine_move)
                move_uci = move.uci()
                if policy_idx >= 0:
                    new_data.append((cb, policy_idx, move_uci, value, source,
                                     white_elo, black_elo, opening, date))
                board.push(move)
            game_count += 1
            if game_count % 100 == 0:
                print(f"Processed {game_count} games, positions: {len(new_data)}")
    outfile = "training_data.pkl"
    if append and os.path.exists(outfile):
        with open(outfile, "rb") as f:
            existing = pickle.load(f)
        combined = existing + new_data
        with open(outfile, "wb") as f:
            pickle.dump(combined, f)
        print(f"Appended {len(new_data)} positions. Total: {len(combined)}")
    else:
        with open(outfile, "wb") as f:
            pickle.dump(new_data, f)
        print(f"Created {outfile} with {len(new_data)} positions.")
    return new_data

if __name__ == "__main__":
    pgn_to_data("last_import.pgn", max_games=0, source=0, append=False)
