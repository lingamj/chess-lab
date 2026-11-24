#!/usr/bin/env python3
"""Verify move->index->move is reversible for all legal moves."""
import random
from board import ChessBoard
from move_helpers import move_to_index, index_to_move, NUM_MOVES

FENS = [
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "4k3/P7/8/8/8/8/7p/4K3 w - - 0 1",
    "k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
    "rnbq1k1r/pppp1ppp/4pn2/8/2BPP3/5N2/PPP2PPP/RNBQK2R b KQ - 2 4",
    "8/8/8/8/8/4k3/8/R6K w - - 0 1",
    "8/8/8/8/8/3k4/6R1/7K w - - 0 1",
    "r7/8/8/8/8/8/8/R3K2k w Q - 0 1",
]

def test():
    for fen in FENS:
        board = ChessBoard()
        board.set_fen(fen)
        for move in board.generate_legal_moves():
            idx = move_to_index(move)
            if idx == -1:
                print(f"ERROR: legal move {move} not in index (FEN {fen})")
                return False
            recovered = index_to_move(idx)
            if recovered != move:
                print(f"Mismatch: {move} -> idx {idx} -> {recovered}")
                return False

    random.seed(42)
    for _ in range(5000):
        board = ChessBoard(track_repetition=False)
        board.set_fen(random.choice(FENS))
        for __ in range(random.randint(0, 20)):
            legals = board.generate_legal_moves()
            if not legals:
                break
            move = random.choice(legals)
            board.make_move(move, update_history=False)
        for move in board.generate_legal_moves():
            idx = move_to_index(move)
            if idx == -1:
                print(f"ERROR: legal move {move} not in index after random play")
                return False
            recovered = index_to_move(idx)
            if recovered != move:
                print(f"Mismatch: {move} -> idx {idx} -> {recovered}")
                return False
    print(f"✓ All legal moves correctly indexed and reversible ({NUM_MOVES} total indices).")
    return True

if __name__ == "__main__":
    if not test():
        exit(1)
