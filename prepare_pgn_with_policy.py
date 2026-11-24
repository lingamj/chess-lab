#!/usr/bin/env python3
"""
Convert PGN to training data (versioned dict format).
Output dict:
{
  "format_version": 2,
  "positions": [...],
  "policies": [...],
  "values": [...],
  "source": [...],
  "white_elo": [...],
  "black_elo": [...],
  "opening": [...],
  "date": [...],
  "game_ids": [...],
  "game_starts": [...]
}
Append mode supported.
"""

import sys, os, pickle, chess, chess.pgn
from board import ChessBoard
from move_helpers import move_to_index
from dataset_schema import FORMAT_VERSION, FIELDS, validate_integrity

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

def pgn_to_data(pgn_file_path, max_games=5000, source=0, append=True):
    outfile = "training_data.pkl"
    existing = None
    if append and os.path.exists(outfile):
        with open(outfile, "rb") as f:
            existing = pickle.load(f)
        if not isinstance(existing, dict) or existing.get("format_version") != FORMAT_VERSION:
            print("Old dataset format detected; starting fresh.")
            existing = None

    new_data = {f: [] for f in FIELDS}
    game_id = 0
    if existing:
        game_id = max(existing["game_ids"]) + 1 if existing["game_ids"] else 0

    with open(pgn_file_path, "r", encoding="utf-8", errors="ignore") as f:
        game_count = 0
        while game_count < max_games:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            result = game.headers.get("Result", "*")
            white_result = 1.0 if result == "1-0" else (-1.0 if result == "0-1" else 0.0)

            white_elo = game.headers.get("WhiteElo", "")
            black_elo = game.headers.get("BlackElo", "")
            opening = game.headers.get("Opening", "")
            date = game.headers.get("Date", "")
            board = chess.Board()
            first_move = True
            for move in game.mainline_moves():
                cb = ChessBoard()
                cb.set_fen(board.fen())
                value = white_result if white_result == 0.0 else (white_result if cb.white_turn else -white_result)

                engine_move = move_to_engine_move(move)
                policy_idx = move_to_index(engine_move)
                move_uci = move.uci()
                if policy_idx >= 0:
                    new_data["positions"].append(cb)
                    new_data["policies"].append(policy_idx)
                    new_data["values"].append(value)
                    new_data["move_uci"].append(move_uci)
                    new_data["source"].append(source)
                    new_data["white_elo"].append(white_elo)
                    new_data["black_elo"].append(black_elo)
                    new_data["opening"].append(opening)
                    new_data["date"].append(date)
                    new_data["game_ids"].append(game_id)
                    new_data["game_starts"].append(first_move)
                    first_move = False
                board.push(move)
            game_id += 1
            game_count += 1

    if existing:
        for f in FIELDS:
            existing[f].extend(new_data[f])
        combined = existing
    else:
        combined = new_data

    combined["format_version"] = FORMAT_VERSION
    from move_helpers import NUM_MOVES
    validate_integrity(combined, NUM_MOVES)

    with open(outfile, "wb") as f:
        pickle.dump(combined, f)
    print(f"Dataset saved: {outfile} ({len(combined['positions'])} positions, version {FORMAT_VERSION}).")
    return combined

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prepare_pgn_with_policy.py <your_pgn_file.pgn> [source] [append]")
        print("source: 0=your games, 1=self-play, 2=Stockfish (default 0)")
        print("append: 1 to append, 0 to overwrite (default 1)")
        sys.exit(1)
    pgn_file = sys.argv[1]
    source = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    append = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    pgn_to_data(pgn_file, max_games=5000, source=source, append=bool(append))
