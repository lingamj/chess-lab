#!/usr/bin/env python3
"""Verify dataset by replaying moves. Uses explicit 'game_start' flag if present."""
import pickle, sys
from board import ChessBoard
from move_helpers import index_to_move

def verify(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    if not data:
        return
    if isinstance(data, dict):
        positions = data['positions']
        policies = data['policies']
        game_starts = data.get('game_starts', [False]*len(positions))
        samples = list(zip(positions, policies, game_starts))
    elif isinstance(data, list):
        samples = []
        for item in data:
            board = item[0]
            idx = item[1]
            is_start = item[9] if len(item) >= 10 else False
            samples.append((board, idx, is_start))
    else:
        print("Unsupported format")
        return

    cur_board = None
    for i, (board, idx, is_start) in enumerate(samples):
        if is_start or cur_board is None:
            cur_board = board.copy()
        else:
            if not cur_board.equals(board):
                print(f"Board mismatch at sample {i} (not flagged as game start)")
                print(f"Expected: {cur_board.to_fen()}")
                print(f"Stored  : {board.to_fen()}")
                sys.exit(1)
        move = index_to_move(idx)
        if move is None or move not in cur_board.generate_legal_moves():
            print(f"Illegal move at sample {i}: idx={idx}")
            sys.exit(1)
        cur_board.make_move(move)
    print(f"OK: replayed {len(samples)} moves across multiple games without error.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python verify_sequence.py <dataset.pkl>")
        sys.exit(1)
    verify(sys.argv[1])
