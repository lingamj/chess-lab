#!/usr/bin/env python3
"""Permanent regression test: move-index table is 1-to-1."""
from move_helpers import MOVE_TO_INDEX, INDEX_TO_MOVE, NUM_MOVES
import sys

for idx in range(NUM_MOVES):
    move = INDEX_TO_MOVE[idx]
    back = MOVE_TO_INDEX.get(move, -1)
    if back != idx:
        print(f"ERROR: idx {idx} -> move {move} -> idx {back}")
        sys.exit(1)
print("✓ Move table is 1-to-1.")
