#!/usr/bin/env python3
"""Repertoire Manager – fully encapsulated, thread‑safe, atomic, UTF‑8."""

import os
import json
import time
import threading
import copy
from opening import get_fen_id, get_fen_from_id
from board import ChessBoard
from move_helpers import str_to_move, move_to_san

HOME = os.path.expanduser("~")
CHESS_DIR = os.path.join(HOME, "chess_ai")
REPERTOIRE_FILE = os.path.join(CHESS_DIR, "repertoire.json")
JSON_INDENT = 2

_rep = None
_rep_lock = threading.RLock()

def _now():
    return time.time()

def _safe_interval_days(value):
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _create_default_repertoire():
    now = _now()
    return {
        "version": 2,
        "created": now,
        "updated": now,
        "positions": {}
    }

# ---------- Internal load/save ----------
def _load_repertoire():
    global _rep
    with _rep_lock:
        if _rep is not None:
            return _rep
        if os.path.exists(REPERTOIRE_FILE):
            try:
                with open(REPERTOIRE_FILE, 'r', encoding='utf-8') as f:
                    _rep = json.load(f)
                    _rep.setdefault("version", 2)
                    _rep.setdefault("created", _now())
                    _rep.setdefault("updated", _now())
                    _rep.setdefault("positions", {})
                return _rep
            except (json.JSONDecodeError, OSError):
                stamp = time.strftime("%Y%m%d_%H%M%S")
                backup = REPERTOIRE_FILE + ".broken." + stamp
                try:
                    os.replace(REPERTOIRE_FILE, backup)
                    print(f"Corrupted repertoire backed up to {backup}")
                except OSError:
                    pass
        _rep = _create_default_repertoire()
        return _rep

def _save_repertoire():
    global _rep
    with _rep_lock:
        if _rep is None:
            _load_repertoire()
        os.makedirs(CHESS_DIR, exist_ok=True)
        _rep["updated"] = _now()
        tmp = REPERTOIRE_FILE + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(_rep, f, indent=JSON_INDENT, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, REPERTOIRE_FILE)
        finally:
            # Clean up temporary file if it still exists
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

# ---------- Public aliases ----------
load_repertoire = _load_repertoire
save_repertoire = _save_repertoire

# ---------- Public API ----------
def get_entry_by_fen(fen):
    fen_id = get_fen_id(fen)
    if fen_id is None:
        return None
    with _rep_lock:
        rep = _load_repertoire()
        entry = rep["positions"].get(str(fen_id))
        return copy.deepcopy(entry) if entry is not None else None

def set_entry_by_fen(fen, data):
    if not isinstance(data, dict):
        raise ValueError("data must be a dictionary")
    fen_id = get_fen_id(fen)
    if fen_id is None:
        raise ValueError(f"FEN not found in opening tree: {fen}")
    data = copy.deepcopy(data)
    if "main_move" in data and "main_move_san" not in data:
        board = ChessBoard()
        board.set_fen(fen)
        move = str_to_move(data["main_move"])
        if move:
            data["main_move_san"] = move_to_san(move, board)
    with _rep_lock:
        rep = _load_repertoire()
        rep["positions"][str(fen_id)] = data
        _save_repertoire()

def delete_entry_by_fen(fen):
    fen_id = get_fen_id(fen)
    if fen_id is None:
        return
    with _rep_lock:
        rep = _load_repertoire()
        if str(fen_id) in rep["positions"]:
            del rep["positions"][str(fen_id)]
            _save_repertoire()

def get_all_entries():
    with _rep_lock:
        rep = _load_repertoire()
        entries = []
        for fid, entry in rep["positions"].items():
            try:
                fid_int = int(fid)
            except (TypeError, ValueError):
                continue
            fen = get_fen_from_id(fid_int)
            if fen:
                entries.append((fen, copy.deepcopy(entry)))
        return entries

def get_due_positions():
    with _rep_lock:
        rep = _load_repertoire()
        now = _now()
        due = []
        for fid, data in rep["positions"].items():
            try:
                fid_int = int(fid)
            except (TypeError, ValueError):
                continue
            last_reviewed = _safe_float(data.get("last_reviewed", 0))
            interval_days = _safe_interval_days(data.get("interval", 1))
            interval = interval_days * 86400
            if now - last_reviewed >= interval:
                entry = copy.deepcopy(data)
                entry["last_reviewed"] = last_reviewed
                due.append((fid_int, entry))
        # Sort by urgency: (now - last_reviewed) / interval (higher = more urgent)
        due.sort(
            key=lambda x: (now - x[1]["last_reviewed"]) /
                          (_safe_interval_days(x[1].get("interval", 1)) * 86400),
            reverse=True
        )
        return due

def normalize_move(move):
    if move is None:
        return ""
    move = str(move)
    return (
        move.strip()
        .lower()
        .replace("+", "")
        .replace("#", "")
        .replace("=", "")
        .replace(" ", "")
    )

def calculate_interval(correct, interval, easiness):
    if correct:
        if interval == 1:
            new_interval = 3
        elif interval < 7:
            new_interval = 7
        else:
            new_interval = int(round(interval * easiness))
        new_easiness = min(2.7, easiness + 0.1)
    else:
        new_interval = 1
        new_easiness = max(1.3, easiness - 0.2)
    return new_interval, new_easiness

def export_repertoire():
    with _rep_lock:
        rep = _load_repertoire()
        return {
            "version": 2,
            "exported": int(_now()),
            "positions": copy.deepcopy(rep["positions"])
        }

def reload_repertoire():
    global _rep
    with _rep_lock:
        _rep = None
        _load_repertoire()
