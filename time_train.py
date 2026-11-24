#!/usr/bin/env python3
"""Time‑limited training for DualNet. Trains as many epochs as possible within a given time."""

import sys, os, pickle, time
from nn import DualNet

def load_data(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)
    positions, values, policies = [], [], []
    for pos, val, pol in data:
        positions.append(pos)
        values.append(val)
        policies.append(pol)
    return positions, values, policies

def main():
    # Default: train for 1 hour (3600 seconds)
    max_time = int(sys.argv[1]) if len(sys.argv) > 1 else 3600

    dataset_files = [f for f in os.listdir('.') if f.startswith('training_data_') and f.endswith('.pkl')]
    if not dataset_files:
        print("No training data found.")
        sys.exit(1)

    print("Loading data...")
    all_pos, all_val, all_pol = [], [], []
    for fname in dataset_files:
        pos, val, pol = load_data(fname)
        all_pos.extend(pos)
        all_val.extend(val)
        all_pol.extend(pol)
    print(f"Samples: {len(all_pos)}")

    nn = DualNet()
    nn.load('chess_nn.pkl')  # start from existing weights

    start_time = time.time()
    epoch = 0
    while time.time() - start_time < max_time:
        nn.train(all_pos, all_val, all_pol, epochs=1, lr=0.001, batch_size=512)
        epoch += 1
        elapsed = time.time() - start_time
        print(f"Epoch {epoch} completed, elapsed {elapsed:.0f}s / {max_time}s")
        if elapsed >= max_time:
            break

    nn.save('chess_nn.pkl')
    print(f"Training finished after {epoch} epochs. Model saved.")

if __name__ == '__main__':
    main()
