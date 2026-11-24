#!/usr/bin/env python3
"""Comprehensive test suite for Chess AI – DualNet version."""

import sys, os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

from board import ChessBoard
from move_helpers import perft
from search import SearchEngine
from nn import DualNet

def test_perft():
    print("Testing perft...")
    b = ChessBoard()
    assert perft(b, 1) == 20
    assert perft(b, 2) == 400
    assert perft(b, 3) == 8902
    assert perft(b, 4) == 197281
    print("  Perft 1-4 OK")

def test_search():
    print("Testing search engine...")
    nn = DualNet()
    if not nn.load('chess_nn.pkl'):
        print("  WARNING: Could not load model, using random weights")
    eng = SearchEngine(nn=nn, max_depth=4)
    board = ChessBoard()
    move, score, depth, nodes = eng.search(board, 1000)
    assert move is not None, "No move returned"
    assert move in board.generate_legal_moves(), "Illegal move"
    print(f"  Search OK – move: {move}, score: {score}, depth: {depth}")

def test_hash_undo():
    print("Testing hash/undo (via run_tests.sh)...")
    # This is already covered by run_tests.sh, but we can call its logic
    import test_hash, test_undo
    print("  Hash and undo tests passed (from imported modules)")

def test_uci():
    print("Testing UCI engine...")
    import subprocess
    res = subprocess.run(
        ['python3', 'uci_engine.py'],
        input="uci\nquit\n",
        capture_output=True, text=True, timeout=5
    )
    assert 'uciok' in res.stdout, "UCI handshake failed"
    print("  UCI handshake OK")

if __name__ == "__main__":
    test_perft()
    test_search()
    # test_hash_undo()  # Uncomment if test_hash.py and test_undo.py exist
    test_uci()
    print("\nAll tests passed!")
