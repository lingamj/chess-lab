#!/usr/bin/env python3
"""Syzygy tablebase probing via python‑chess – WDL-based, robust."""

import os, chess, chess.syzygy

class Tablebase:
    def __init__(self, path=None):
        self.path = path or os.path.expanduser('~/chess_ai/syzygy')
        self.tablebase = None
        if os.path.isdir(self.path):
            try:
                self.tablebase = chess.syzygy.open_tablebase(self.path)
            except:
                pass

    def probe(self, board):
        if not self.tablebase:
            return None, None
        fen = board.to_fen()
        try:
            chess_board = chess.Board(fen)
            n = chess_board.occupied.bit_count()
            if n > self.tablebase.max_pieces:
                return None, None

            best_move = None
            best_wdl = None
            best_dtz = None

            for move in board.generate_legal_moves():
                child = board.copy()
                child.make_move(move)
                child_fen = child.to_fen()
                child_board = chess.Board(child_fen)

                wdl = self.tablebase.probe_wdl(child_board)
                if wdl is None:
                    continue
                if wdl > 0:
                    score = -1
                elif wdl < 0:
                    score = 1
                else:
                    score = 0

                dtz = None
                try:
                    dtz = self.tablebase.probe_dtz(child_board)
                except:
                    pass

                if best_move is None:
                    best_move = move
                    best_wdl = score
                    best_dtz = dtz
                else:
                    if score > best_wdl:
                        best_move = move
                        best_wdl = score
                        best_dtz = dtz
                    elif score == best_wdl and dtz is not None:
                        if (best_dtz is None or abs(dtz) < abs(best_dtz)):
                            best_move = move
                            best_dtz = dtz

            if best_move is not None:
                return best_wdl, best_move
            return None, None
        except:
            return None, None
