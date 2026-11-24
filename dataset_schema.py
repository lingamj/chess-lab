#!/usr/bin/env python3
"""Single source of truth for the training dataset format.
   Structural, semantic, and content validation.
   Callers must pass NUM_MOVES (from move_helpers) to avoid circular imports.
"""

import numbers
from board import ChessBoard

FORMAT_VERSION = 2
SUPPORTED_VERSIONS = {2}

FIELDS = (
    "positions",
    "policies",
    "values",
    "move_uci",
    "source",
    "white_elo",
    "black_elo",
    "opening",
    "date",
    "game_ids",
    "game_starts",
)

VALID_SOURCES = {0, 1, 2}

def _is_valid_uci(s):
    if not isinstance(s, str):
        return False
    if len(s) not in (4, 5):
        return False
    if not ('a' <= s[0] <= 'h' and '1' <= s[1] <= '8' and 'a' <= s[2] <= 'h' and '1' <= s[3] <= '8'):
        return False
    if len(s) == 5 and s[4] not in 'qrbnQRBN':
        return False
    return True

def validate_integrity(data, num_moves):
    ver = data.get("format_version")
    if ver not in SUPPORTED_VERSIONS:
        raise ValueError(f"Unsupported format_version {ver}. Supported: {SUPPORTED_VERSIONS}")

    for f in FIELDS:
        if f not in data:
            raise KeyError(f"Missing field '{f}'")
        if not isinstance(data[f], list):
            raise TypeError(f"Field '{f}' must be a list")

    n = len(data["positions"])
    for f in FIELDS:
        if len(data[f]) != n:
            raise ValueError(f"Length mismatch: positions has {n}, {f} has {len(data[f])}")

    if not all(isinstance(p, ChessBoard) for p in data["positions"]):
        raise TypeError("All positions must be ChessBoard instances")

    if not all(isinstance(idx, numbers.Integral) and 0 <= idx < num_moves for idx in data["policies"]):
        raise TypeError(f"Field 'policies' must contain integers in [0, {num_moves})")

    if not all(isinstance(v, numbers.Real) for v in data["values"]):
        raise TypeError("Field 'values' must contain real numbers")
    for v in data["values"]:
        if not (-1.0 <= float(v) <= 1.0):
            raise ValueError(f"Value {v} outside [-1, 1]")

    if not all(_is_valid_uci(u) for u in data["move_uci"]):
        raise ValueError("Field 'move_uci' contains malformed UCI strings")

    if not all(isinstance(s, numbers.Integral) and s in VALID_SOURCES for s in data["source"]):
        raise TypeError(f"Field 'source' must be one of {VALID_SOURCES}")

    for meta_field in ("white_elo", "black_elo", "opening", "date"):
        if not all(isinstance(x, str) for x in data[meta_field]):
            raise TypeError(f"Field '{meta_field}' must contain only strings")

    if not all(isinstance(b, bool) for b in data["game_starts"]):
        raise TypeError("Field 'game_starts' must contain only booleans")

    if not all(isinstance(g, numbers.Integral) for g in data["game_ids"]):
        raise TypeError("Field 'game_ids' must contain integers")

    seen_ids = {}
    for i, (gid, is_start) in enumerate(zip(data["game_ids"], data["game_starts"])):
        if gid not in seen_ids:
            if not is_start:
                raise RuntimeError(f"game_id {gid} first sample (index {i}) must have game_start=True")
            seen_ids[gid] = i
        else:
            if is_start:
                raise RuntimeError(f"game_id {gid} has multiple game_start=True (indices {seen_ids[gid]} and {i})")

    for prev, cur in zip(data["game_ids"], data["game_ids"][1:]):
        if cur < prev:
            raise RuntimeError(f"game_ids not monotonic: {prev} then {cur}")
