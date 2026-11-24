#!/usr/bin/env python3
"""Universal memory‑safe trainer – handles 9‑tuple and themed dict formats."""

import sys, os, pickle, numpy as np
from nn import DualNet
from move_helpers import str_to_move, move_to_index

def value_from_score(score_cp):
    return max(-1.0, min(1.0, score_cp / 400.0))

def load_file(path):
    """Return lists of (board, value, policy_index) from any supported format."""
    with open(path, 'rb') as f:
        raw = pickle.load(f)

    boards, vals, idxs = [], [], []

    if isinstance(raw, dict) and 'positions' in raw:
        # Themed format: {'positions': [...], 'values': [...], 'policies': [...]}
        # Policies are already global move indices (int)
        for board, val, pol_idx in zip(raw['positions'], raw['values'], raw['policies']):
            try:
                v = value_from_score(val) if abs(val) > 2 else val  # raw score or already scaled
                boards.append(board)
                vals.append(v)
                idxs.append(pol_idx)
            except Exception:
                continue

    elif isinstance(raw, list) and len(raw) > 0 and hasattr(raw[0], '__len__') and len(raw[0]) >= 3:
        # 9‑tuple format: (board, score_cp, move_uci, ...)
        for item in raw:
            board_obj, score_cp, move_uci = item[0], item[1], item[2]
            try:
                move_tuple = str_to_move(move_uci)
                legal = board_obj.generate_legal_moves()
                if move_tuple not in legal:
                    continue
                idx = move_to_index(move_tuple)
                boards.append(board_obj)
                vals.append(value_from_score(score_cp))
                idxs.append(idx)
            except Exception:
                continue

    return boards, vals, idxs


def train_on_samples(nn, boards, values, indices, epochs=3, lr=0.0005, batch_size=128):
    """Train on a small chunk, then save."""
    N = len(boards)
    if N == 0:
        return
    pol = np.zeros((N, 20480), dtype=np.float32)
    for i, idx in enumerate(indices):
        pol[i, idx] = 1.0
    nn.train(boards, values, pol, epochs=epochs, lr=lr, batch_size=batch_size)
    nn.save('chess_nn.pkl')
    print(f"  chunk of {N} samples trained, model saved")


def process_file(nn, path, chunk_size=2000):
    print(f"Processing {path}...")
    boards, vals, idxs = load_file(path)
    total = len(boards)
    print(f"  {total} valid samples")

    for start in range(0, total, chunk_size):
        chunk_b = boards[start:start+chunk_size]
        chunk_v = vals[start:start+chunk_size]
        chunk_i = idxs[start:start+chunk_size]
        train_on_samples(nn, chunk_b, chunk_v, chunk_i, epochs=3, lr=0.0005, batch_size=128)

    print(f"  finished {path}")


def main():
    files = sorted([f for f in os.listdir('.') if f.startswith('training_data_') and f.endswith('.pkl')])
    if not files:
        print("No training_data_*.pkl found.")
        sys.exit(1)

    nn = DualNet()
    nn.load('chess_nn.pkl')

    for fname in files:
        try:
            process_file(nn, fname, chunk_size=2000)
        except Exception as e:
            print(f"  error on {fname}: {e}")

    print("Training complete.")


if __name__ == '__main__':
    main()
