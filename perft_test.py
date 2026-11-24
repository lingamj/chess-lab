#!/usr/bin/env python3
"""Perft validation for the starting position."""
from board import ChessBoard
from move_helpers import perft

EXPECTED = {1:20, 2:400, 3:8902, 4:197281, 5:4865609}

board = ChessBoard()
print("Starting position perft:")
for depth, expected in EXPECTED.items():
    nodes = perft(board, depth)
    status = "✓" if nodes == expected else f"✗ (expected {expected})"
    print(f"  depth {depth}: {nodes} {status}")
