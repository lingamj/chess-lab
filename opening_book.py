#!/usr/bin/env python3
"""Simple PolyGlot opening book reader."""

import struct, os, random

class OpeningBook:
    def __init__(self, book_path=None):
        self.book_path = book_path or os.path.expanduser('~/chess_ai/book.bin')
        self.entries = []
        if os.path.exists(self.book_path):
            self._load()

    def _load(self):
        with open(self.book_path, 'rb') as f:
            while True:
                entry = f.read(16)
                if not entry:
                    break
                key, move, weight, learn = struct.unpack('>QHHI', entry)
                self.entries.append((key, move, weight))

    def lookup(self, hash_key):
        """Return a random move weighted by popularity."""
        candidates = [(m, w) for k, m, w in self.entries if k == hash_key]
        if not candidates:
            return None
        total = sum(w for _, w in candidates)
        r = random.randint(0, total - 1) if total > 0 else 0
        accum = 0
        for move, weight in candidates:
            accum += weight
            if r < accum:
                return self._decode_move(move)
        return None

    def _decode_move(self, move):
        """Convert PolyGlot move to internal format."""
        to_file = move & 0x7
        to_row = (move >> 3) & 0x7
        from_file = (move >> 6) & 0x7
        from_row = (move >> 9) & 0x7
        promo = (move >> 12) & 0x7
        promo_piece = {0: None, 1: 'N', 2: 'B', 3: 'R', 4: 'Q'}.get(promo, None)
        return (from_row, from_file, to_row, to_file) + ((promo_piece,) if promo_piece else ())
