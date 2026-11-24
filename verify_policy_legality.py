#!/usr/bin/env python3
"""Verify every training sample: policy index -> move is legal, and UCI matches."""
import pickle, sys
from move_helpers import index_to_move, move_to_str

def verify(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    if not isinstance(data, list):
        print("Dataset is not a list of tuples. Skipping.")
        return
    bad = 0
    for i, item in enumerate(data):
        board = item[0]
        idx = item[1]
        stored_uci = item[2]
        move = index_to_move(idx)
        if move is None:
            print(f"  Bad index: sample {i}, idx={idx}")
            bad += 1
            continue
        if move not in board.generate_legal_moves():
            print(f"  Illegal move: sample {i}, idx={idx}, move={move}")
            bad += 1
            continue
        expected_uci = move_to_str(move)
        if expected_uci != stored_uci:
            print(f"  UCI mismatch: sample {i}, stored={stored_uci}, expected={expected_uci}")
            bad += 1
    if bad:
        print(f"FAILED: {bad} errors found.")
        sys.exit(1)
    else:
        print(f"OK: all {len(data)} samples have legal moves and correct UCI.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python verify_policy_legality.py <dataset.pkl>")
        sys.exit(1)
    verify(sys.argv[1])
