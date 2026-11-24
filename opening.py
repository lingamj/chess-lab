#!/usr/bin/env python3
"""Opening tree – with cached tree and id map for O(1) lookups.
   Thread‑safe loading with locks.
"""

import os
import pickle
import gzip
import threading
import chess

def normalize_position_key(fen):
    """Return a position key that ignores irrelevant en passant rights.

    Key = board + side to move + castling rights + en passant square only
    when a legal en passant capture exists. Halfmove/fullmove are ignored.
    """
    try:
        board = chess.Board(fen)
    except Exception:
        parts = fen.split()
        return " ".join(parts[:4]) if len(parts) >= 4 else fen

    ep = "-"
    if board.ep_square is not None:
        try:
            if board.has_legal_en_passant():
                ep = chess.square_name(board.ep_square)
        except Exception:
            ep = chess.square_name(board.ep_square)

    return (
        board.board_fen()
        + " "
        + ("w" if board.turn == chess.WHITE else "b")
        + " "
        + board.castling_xfen()
        + " "
        + ep
    )

def _canonicalize_fen(fen):
    """Normalize FEN for tree identity, ignoring irrelevant en passant."""
    return normalize_position_key(fen)

from functools import lru_cache

HOME = os.path.expanduser("~")
CHESS_DIR = os.path.join(HOME, "chess_ai")
TREE_FILE = os.path.join(CHESS_DIR, "opening_tree.pkl.gz")
EXAMPLES_FILE = os.path.join(CHESS_DIR, "game_examples.pkl.gz")

_tree = None
_id_to_fen = None
_examples = None
_tree_lock = threading.Lock()
_examples_lock = threading.Lock()

def load_tree():
    """Load the opening tree and id‑to‑FEN mapping. Thread‑safe."""
    global _tree, _id_to_fen
    if _tree is not None:
        return _tree
    with _tree_lock:
        # Double‑check after acquiring the lock
        if _tree is not None:
            return _tree
        if os.path.exists(TREE_FILE):
            try:
                with gzip.open(TREE_FILE, 'rb') as f:
                    _tree = pickle.load(f)
                _id_to_fen = {data['id']: fen for fen, data in _tree.items()}
            except (OSError, pickle.PickleError) as e:
                print(f"WARNING: Failed to load opening tree: {e}")
                _tree = {}
                _id_to_fen = {}
        else:
            _tree = {}
            _id_to_fen = {}
        return _tree

def get_fen_id(fen):
    tree = load_tree()
    pos = tree.get(_canonicalize_fen(fen))
    return pos['id'] if pos else None

def get_fen_from_id(fid):
    tree = load_tree()  # ensures _id_to_fen is built
    return _id_to_fen.get(fid) if _id_to_fen else None

def load_examples():
    """Load example games. Thread‑safe."""
    global _examples
    if _examples is not None:
        return _examples
    with _examples_lock:
        if _examples is not None:
            return _examples
        if os.path.exists(EXAMPLES_FILE):
            try:
                with gzip.open(EXAMPLES_FILE, 'rb') as f:
                    _examples = pickle.load(f)
            except (OSError, pickle.PickleError) as e:
                print(f"WARNING: Failed to load examples: {e}")
                _examples = {}
        else:
            _examples = {}
        return _examples

@lru_cache(maxsize=50000)
def get_moves_cached(fen):
    """Return cached move data for a FEN. Returns tuple of move tuples."""
    tree = load_tree()
    pos = tree.get(_canonicalize_fen(fen))
    if not pos:
        return ()
    total = pos.get('total_games', 0)
    moves = []
    for uci, stats in pos['moves'].items():
        games = stats.get('games', 0)
        if games == 0:
            continue
        results = stats.get('results', (0, 0, 0))
        w, d, b = results[0], results[1], results[2]
        _mwr = stats.get('my_white_results', [0, 0, 0])
        _mbr = stats.get('my_black_results', [0, 0, 0])

        moves.append((
            uci,
            stats.get('san', uci),        # fallback to UCI if SAN missing
            games,
            stats.get('popularity', 0),
            round(w / games * 100, 1) if games else 0,
            round(d / games * 100, 1) if games else 0,
            round(b / games * 100, 1) if games else 0,
            stats.get('avg_elo', 0),
            stats.get('positions', games),
            stats.get('my_white_games', 0),
            stats.get('my_black_games', 0),
            _mwr[0], _mwr[1], _mwr[2],
            _mbr[0], _mbr[1], _mbr[2],
            stats.get('my_white_avg_elo', 0),
            stats.get('my_black_avg_elo', 0),
        ))
    moves.sort(key=lambda x: (-x[2], -x[7]))
    return tuple(moves)

def get_moves(fen):
    """Return move data as a list of dicts for JSON serialization."""
    return [
        {
            'uci': m[0],
            'san': m[1],
            'games': m[2],
            'popularity': m[3],
            'win_pct': m[4],
            'draw_pct': m[5],
            'loss_pct': m[6],
            'avg_elo': m[7],
            'positions': m[8],
            'my_white_games': m[9],
            'my_black_games': m[10],
            'my_white_w': m[11],
            'my_white_d': m[12],
            'my_white_b': m[13],
            'my_black_w': m[14],
            'my_black_d': m[15],
            'my_black_b': m[16],
            'my_white_avg_elo': m[17],
            'my_black_avg_elo': m[18]
        }
        for m in get_moves_cached(fen)
    ]

@lru_cache(maxsize=100000)
def get_examples_cached(fen, uci):
    """Return cached example games for a FEN and move UCI."""
    examples = load_examples()
    tree = load_tree()
    pos = tree.get(_canonicalize_fen(fen))
    if not pos:
        return ()
    fen_id = pos.get('id')
    if fen_id is None:
        return ()
    data = examples.get((fen_id, uci), [])
    return tuple(
        (x.get('white', '?'), x.get('black', '?'), x.get('date', ''),
         x.get('result', '*'), x.get('elo', 0))
        for x in data
    )

def get_examples(fen, uci):
    """Return example games as a list of dicts."""
    return [
        {'white': x[0], 'black': x[1], 'date': x[2], 'result': x[3], 'elo': x[4]}
        for x in get_examples_cached(fen, uci)
    ]

def get_eco(fen):
    """Return ECO code and opening name for a FEN."""
    tree = load_tree()
    pos = tree.get(_canonicalize_fen(fen))
    if pos:
        return {
            'eco': pos.get('eco', 'A00'),
            'name': pos.get('opening', 'Unclassified')
        }
    return {'eco': 'A00', 'name': 'Unclassified'}
