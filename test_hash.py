#!/usr/bin/env python3
"""Verify incremental Zobrist hash for every legal move in key positions."""

from board import ChessBoard

TEST_POSITIONS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "4k3/P7/8/8/8/8/7p/4K3 w - - 0 1",
    "k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
    "rnbq1k1r/pppp1ppp/4pn2/8/2BPP3/5N2/PPP2PPP/RNBQK2R b KQ - 2 4"
]

def test_hash_consistency():
    for fen in TEST_POSITIONS:
        board = ChessBoard()
        board.set_fen(fen)
        for move in board.generate_legal_moves():
            cpy = board.copy()
            cpy.make_move(move)
            if cpy.hash != cpy._compute_hash():
                print(f"FAIL: {fen}  move {move}")
                return False
    print("✓ All hash checks passed for all test positions.")
    return True

def test_hash_after_undo():
    for fen in TEST_POSITIONS:
        board = ChessBoard()
        board.set_fen(fen)
        original_hash = board.hash
        for move in board.generate_legal_moves():
            undo = board.make_move(move)
            if board.hash != board._compute_hash():
                print("FAIL after make")
                print(fen)
                print(move)
                return False
            board.undo_move(undo)
            if board.hash != original_hash:
                print("FAIL after undo")
                print(fen)
                print(move)
                print(original_hash)
                print(board.hash)
                return False
            if board.hash != board._compute_hash():
                print("FAIL recompute after undo")
                print(fen)
                print(move)
                return False
    print("✓ Hash undo tests passed.")
    return True

if __name__ == "__main__":
    if not test_hash_consistency():
        exit(1)
    if not test_hash_after_undo():
        exit(1)
    print("All hash tests passed.")
