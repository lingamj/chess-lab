#!/usr/bin/env python3
"""Audit a dataset: statistics and per-sample validation."""
import pickle, sys
from collections import Counter
from move_helpers import index_to_move, move_to_str, NUM_MOVES

def audit(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    if isinstance(data, dict):
        positions = data['positions']
        values = data['values']
        policies = data['policies']
        game_starts = data.get('game_starts', [None]*len(positions))
        samples = list(zip(positions, policies, values, game_starts))
    elif isinstance(data, list):
        samples = []
        for item in data:
            board = item[0]
            idx = item[1]
            val = item[3]
            uci = item[2] if len(item) > 2 else None
            is_start = item[9] if len(item) >= 10 else None
            samples.append((board, idx, val, uci, is_start))
    else:
        print("Unsupported format")
        return

    stats = Counter()
    bad = 0
    for i, s in enumerate(samples):
        board, idx, val, uci, is_start = s[0], s[1], s[2], s[3] if len(s) > 3 else None, s[4] if len(s) > 4 else None
        if not isinstance(val, (int, float)):
            print(f"Non-numeric value at sample {i}")
            bad += 1
            continue
        if val < -1.0 or val > 1.0:
            print(f"Value out of range at sample {i}: {val}")
            bad += 1
        if not isinstance(idx, int):
            print(f"Non-integer policy index at sample {i}")
            bad += 1
            continue
        move = index_to_move(idx)
        if move is None or idx >= NUM_MOVES:
            print(f"Invalid policy index {idx} at sample {i}")
            bad += 1
            continue
        if move not in board.generate_legal_moves():
            print(f"Illegal move at sample {i}: {move}")
            bad += 1
        if uci is not None:
            expected_uci = move_to_str(move)
            if uci != expected_uci:
                print(f"UCI mismatch at sample {i}: stored={uci} expected={expected_uci}")
                bad += 1
        stats['total'] += 1
        stats['w_turn' if board.white_turn else 'b_turn'] += 1
        if val == 1.0: stats['win'] += 1
        elif val == -1.0: stats['loss'] += 1
        else: stats['draw'] += 1

    print(f"Samples: {stats['total']}")
    print(f"White to move: {stats['w_turn']}  Black to move: {stats['b_turn']}")
    print(f"Wins: {stats['win']}, Draws: {stats['draw']}, Losses: {stats['loss']}")
    if bad:
        print(f"Errors: {bad}")
        sys.exit(1)
    else:
        print("All samples valid.")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python dataset_audit.py <dataset.pkl>")
        sys.exit(1)
    audit(sys.argv[1])
