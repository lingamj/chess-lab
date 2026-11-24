#!/usr/bin/env python3
"""Verify training_data.pkl format before training."""

import pickle, os, sys
from move_helpers import NUM_MOVES

def verify():
    data_file = "training_data.pkl"
    if not os.path.exists(data_file):
        print(f"❌ {data_file} not found.")
        return False

    with open(data_file, "rb") as f:
        data = pickle.load(f)

    if not data:
        print("❌ Data is empty.")
        return False

    print(f"✅ Loaded {len(data)} samples.")

    for i, sample in enumerate(data[:5]):
        if len(sample) != 9:
            print(f"❌ Sample {i} has {len(sample)} fields, expected 9.")
            return False

        board, policy_idx, move_uci, value, source, white_elo, black_elo, opening, date = sample

        if not hasattr(board, "generate_legal_moves"):
            print(f"❌ Sample {i}: 'board' is not a ChessBoard object.")
            return False

        if not isinstance(policy_idx, int) or not (0 <= policy_idx < NUM_MOVES):
            print(f"❌ Sample {i}: policy_idx {policy_idx} out of range.")
            return False

        if not isinstance(value, (int, float)) or value < -1.0 or value > 1.0:
            print(f"❌ Sample {i}: value {value} out of expected range.")
            return False

        if not isinstance(move_uci, str) or len(move_uci) < 4:
            print(f"❌ Sample {i}: move_uci '{move_uci}' invalid.")
            return False

        if not isinstance(source, int):
            print(f"❌ Sample {i}: source is not int.")
            return False

        print(f"✅ Sample {i}: board OK, policy_idx={policy_idx}, value={value}, uci={move_uci}, source={source}")

    print("✅ All samples checked successfully.")
    return True

if __name__ == "__main__":
    sys.exit(0 if verify() else 1)
