#!/usr/bin/env python3
"""Train the dual‑head neural network (passes one‑hot policies to nn.train()).
   Supports:
     - Dict format (V2): {'positions':..., 'values':..., 'policies':...}
     - List of 9‑tuples (legacy training_data.pkl)
   Resumes from the output model if it exists.
   Saves the model only after a successful training run.
   Activates the new model (copies master → active) only after successful training.
"""

import sys, os, pickle, signal
import numpy as np
from nn import DualNet
from move_helpers import NUM_MOVES, move_to_index

def load_dataset(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)

    if isinstance(data, dict):
        required = {'positions', 'values', 'policies'}
        missing = required - data.keys()
        if missing:
            raise KeyError(f"Dataset missing keys: {sorted(missing)}")
        positions = data['positions']
        values = data['values']
        policies = data['policies']
    elif isinstance(data, (list, tuple)):
        if len(data) == 0:
            return [], [], []
        first = data[0]
        if isinstance(first, tuple) and len(first) >= 4:
            positions = [x[0] for x in data]
            policies  = [x[1] for x in data]
            values    = [x[3] for x in data]
        else:
            raise ValueError("Unsupported dataset format.")
    else:
        raise ValueError("Dataset must be a dict or a list of tuples.")

    if not (len(positions) == len(values) == len(policies)):
        raise ValueError(f"Length mismatch: positions={len(positions)}, values={len(values)}, policies={len(policies)}")

    if not all(isinstance(v, (int, float, np.floating, np.integer)) for v in values):
        raise ValueError("All value targets must be numeric.")
    for v in values:
        if v < -1.0 or v > 1.0:
            raise ValueError(f"Value {v} outside [-1,1]")

    valid = [(p, v, pol) for p, v, pol in zip(positions, values, policies)
             if isinstance(pol, (int, np.integer)) and 0 <= pol < NUM_MOVES]
    if len(valid) < len(positions):
        print(f"Filtered out {len(positions) - len(valid)} invalid policy indices.")
    positions, values, policies = zip(*valid) if valid else ([], [], [])
    return list(positions), list(values), list(policies)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 train.py <dataset.pkl> [epochs] [lr] [batch_size] [output_model]")
        sys.exit(1)

    path = sys.argv[1]
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    lr = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
    batch_size = int(sys.argv[4]) if len(sys.argv) > 4 else 512
    output_model = sys.argv[5] if len(sys.argv) > 5 else 'chess_nn_master.pkl'

    print("Loading dataset...")
    positions, values, policies = load_dataset(path)
    if not positions:
        print("No valid positions. Exiting.")
        return False


    net = DualNet()
    if os.path.exists(output_model):
        print(f"Resuming from {output_model}")
        net.load(output_model)
    else:
        print("Starting from scratch.")

    print(f"Training on {len(positions)} samples, epochs={epochs}, lr={lr}, batch={batch_size}...")

    def save_model():
        net.save(output_model)
        print(f"Model saved to {output_model}")

    def handler(sig, frame):
        print("\nStopping (model NOT saved).")
        sys.exit(1)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    training_ok = False
    try:
        net.train(positions, values, policies, epochs=epochs, lr=lr, batch_size=batch_size)
        training_ok = True
    except Exception as e:
        print(f"Training error: {e}")
    else:
        save_model()

    return training_ok


if __name__ == "__main__":
    ok = main()
    # Auto‑activate the new model only after successful training
    if ok:
        import os, shutil, time
        if os.path.exists("chess_nn_master.pkl"):
            if os.path.exists("chess_nn.pkl"):
                backup_name = f"chess_nn_backup_{time.strftime('%Y%m%d_%H%M%S')}.pkl"
                shutil.copy2("chess_nn.pkl", backup_name)
                print(f"Previous model saved as {backup_name}")
            shutil.copy2("chess_nn_master.pkl", "chess_nn.pkl")
            print("New model activated.")
