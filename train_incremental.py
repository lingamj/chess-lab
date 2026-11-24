#!/usr/bin/env python3
"""Memory‑friendly incremental trainer – processes one .pkl at a time."""

import sys, os, pickle, numpy as np
from nn import DualNet
from move_helpers import str_to_move, move_to_index

def value_from_score(score_cp):
    return max(-1.0, min(1.0, score_cp / 400.0))

def load_and_convert(path):
    boards, values, indices = [], [], []
    with open(path, 'rb') as f:
        raw = pickle.load(f)
    for item in raw:
        board_obj, score_cp, move_uci = item[0], item[1], item[2]
        try:
            move_tuple = str_to_move(move_uci)
            legal = board_obj.generate_legal_moves()
            if move_tuple not in legal:
                continue
            idx = move_to_index(move_tuple)
            boards.append(board_obj)
            values.append(value_from_score(score_cp))
            indices.append(idx)
        except Exception:
            continue
    return boards, values, indices

def train_on_file(nn, path, epochs=5, lr=0.001, batch_size=128):
    print(f"Processing {path}...")
    boards, vals, idxs = load_and_convert(path)
    if not boards:
        print("  no valid samples, skipping")
        return
    N = len(boards)
    print(f"  {N} valid samples")
    # Build one‑hot policy matrix (only N x 20480, N is small per file)
    policy = np.zeros((N, 20480), dtype=np.float32)
    for i, idx in enumerate(idxs):
        policy[i, idx] = 1.0
    nn.train(boards, vals, policy, epochs=epochs, lr=lr, batch_size=batch_size)
    nn.save('chess_nn.pkl')
    print(f"  saved model after {path}")

def main():
    files = sorted([f for f in os.listdir('.') if f.startswith('training_data_') and f.endswith('.pkl')])
    if not files:
        print("No training_data_*.pkl found.")
        sys.exit(1)

    nn = DualNet()
    nn.load('chess_nn.pkl')

    # First do the files that already worked (they are large, contain real games)
    priority_files = [f for f in files if 'subset' in f or '5k' in f or '20k' in f or '2k' in f or '10k' in f]
    other_files = [f for f in files if f not in priority_files]

    for fname in priority_files + other_files:
        try:
            train_on_file(nn, fname, epochs=3, lr=0.0005, batch_size=128)
        except Exception as e:
            print(f"  error on {fname}: {e}")

    print("All done.")

if __name__ == '__main__':
    main()
