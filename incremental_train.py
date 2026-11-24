#!/usr/bin/env python3
"""Incremental trainer for DualNet – loads new data and fine‑tunes."""

import sys, os, pickle
from nn import DualNet

def load_new_data(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    positions, values, policies = [], [], []
    for pos, val, pol in data:
        positions.append(pos)
        values.append(val)
        policies.append(pol)
    return positions, values, policies

def main():
    new_data_file = sys.argv[1] if len(sys.argv) > 1 else 'training_data_merged.pkl'
    print(f"Loading {new_data_file}...")
    pos, val, pol = load_new_data(new_data_file)
    print(f"Samples: {len(pos)}")

    nn = DualNet()
    if not nn.load('chess_nn.pkl'):
        print("No existing model, starting from scratch.")
    nn.train(pos, val, pol, epochs=5, lr=0.0005, batch_size=512)   # lower LR for fine‑tuning
    nn.save('chess_nn.pkl')
    print("Incremental training complete.")

if __name__ == '__main__':
    main()
