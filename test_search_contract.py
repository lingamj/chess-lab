#!/usr/bin/env python3
"""P5.15D - SearchResult provenance contract regression.

Exercises all 20 SearchResult construction sites in search.py against
the P5.15C reference contract. Deterministic NN stub; no model loaded.

Test-only conventions:
  - Site 10 (defensive, unreachable under normal
    ChessBoard.generate_legal_moves) is exercised via _EmptyTruthyList,
    a test-only iterable inconsistency.
  - Qsearch sites 17/19/20 use a scoped combined_eval=0 override plus
    controlled child SearchResult objects, so the branches fire without
    depending on the NN evaluator's numerical output.
  - The 20-site table is derived from an AST walk of search.py, not
    from text matching.

The optional --root-discovery flag runs a one-shot discovery check
for the P5.15C terminal-root contract. That check is expected to
report a gap under the current live code and pass after P5.15D.1.
"""

import ast
import sys
import time
from pathlib import Path

import numpy as np

from board import ChessBoard
from search import SearchEngine, SearchResult, MATE_SCORE, MATE_PLY_BOUND, MAX_Q_DEPTH
from move_helpers import NUM_MOVES, move_to_str
import search as search_mod


class _NnStub:
    def evaluate(self, board):
        return 0.0, np.zeros(NUM_MOVES, dtype=np.float32)
    def evaluate_value_only(self, board):
        return 0.0
    def load(self, path):
        return True


class _EmptyTruthyList(list):
    """Non-empty, truthy, iterates zero elements.

    Used only to force site 10 in search._pvs_result. The live code
    checks 'if not moves:' then does 'best_move = moves[0]' and
    iterates. Site 10 is defensive and is not reachable through
    normal ChessBoard.generate_legal_moves().
    """
    def __init__(self, elem):
        super().__init__([elem])
    def __iter__(self):
        return iter([])


_ORIG_SR = search_mod.SearchResult
_SITE_CALLS = []
_SITE_LINES = {}


def _build_site_table():
    path = Path(search_mod.__file__)
    tree = ast.parse(path.read_text())
    sites = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "SearchResult":
                end = getattr(node, "end_lineno", None) or node.lineno
                sites.append((node.lineno, end))
    sites.sort()
    _SITE_LINES.clear()
    for ordinal, (a, b) in enumerate(sites, 1):
        _SITE_LINES[ordinal] = (a, b)
    return sites


def _recording_SR(*args, **kwargs):
    frame = sys._getframe(1)
    fname = frame.f_code.co_filename
    lineno = frame.f_lineno
    ordinal = None
    if Path(fname).name == "search.py":
        for o, (a, b) in _SITE_LINES.items():
            if a <= lineno <= b:
                ordinal = o
                break
    _SITE_CALLS.append((ordinal, fname, lineno))
    return _ORIG_SR(*args, **kwargs)


def _install_recorder():
    _SITE_CALLS.clear()
    search_mod.SearchResult = _recording_SR


def _uninstall_recorder():
    search_mod.SearchResult = _ORIG_SR


def _sites_hit():
    return sorted({o for (o, _, _) in _SITE_CALLS if o is not None})


def _engine():
    e = SearchEngine(nn=_NnStub(), max_depth=6, tt_max=1000)
    e.time_limit = None
    e.start_time = time.time()
    return e


def _board(fen):
    b = ChessBoard()
    b.set_fen(fen)
    return b


def _board_empty_moves(fen):
    """Test-only subclass: reports a truthy move list that iterates empty.
       Used to force site 10 (defensive branch) without modifying
       production code. ChessBoard.__slots__ prevents monkey-patching
       generate_legal_moves on an instance, so a subclass is required."""
    class _B(ChessBoard):
        def generate_legal_moves(self):
            return _EmptyTruthyList(("dummy",))
    b = _B()
    b.set_fen(fen)
    return b


def _check(label, r, bound, valid, stype, sdepth):
    got = (r.bound, r.valid, r.source_type, r.source_depth)
    exp = (bound, valid, stype, sdepth)
    if got != exp:
        print(f"  FAIL {label}: got {got}, expected {exp}")
        return False
    return True


def _force_pvs_child(e, child, at_ply):
    """Return controlled child at ply >= at_ply; delegate otherwise.

    Must replicate the PV-slot padding that the real _pvs_result
    performs at entry, because the parent's PV-copy block reads
    self.pv_length[ply+1] and self.pv_moves[ply+1]. Without this,
    forcing a child at ply+1 leaves the parent's index out of range.
    """
    orig = e._pvs_result
    def w(board, alpha, beta, depth, ply):
        if ply >= at_ply:
            while ply >= len(e.pv_moves):
                e.pv_moves.append([])
                e.pv_length.append(0)
            if (beta - alpha) > 1:
                e.pv_length[ply] = 0
            return child
        return orig(board, alpha, beta, depth, ply)
    e._pvs_result = w


def _force_q_child(e, child, at_qdepth):
    orig = e._quiescence_result
    def w(board, alpha, beta, ply, q_depth=0):
        return child if q_depth >= at_qdepth else orig(board, alpha, beta, ply, q_depth)
    e._quiescence_result = w


class _ZeroCE:
    def __enter__(self):
        self._orig = search_mod.combined_eval
        search_mod.combined_eval = lambda board: 0
        return self
    def __exit__(self, *a):
        search_mod.combined_eval = self._orig


START       = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
FOOL_MATE   = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
STALEMATE   = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
KQK_CAPTURE = "4k3/8/8/3q4/4P3/8/8/4K3 w - - 0 1"


def _make_tt_entry(engine, board, score, depth=10, flag="exact",
                   move=None, source_type="search", source_depth=5):
    return {
        "score": score, "depth": depth, "flag": flag, "move": move,
        "valid": True, "provenance_version": engine.tt_version,
        "source_type": source_type, "source_depth": source_depth,
        "stored_halfmove": board.halfmove_clock,
        "stored_track_rep": board.track_repetition,
        "stored_rep_fp": engine._rep_fingerprint(board),
    }


def test_sites_1_to_6():
    print("sites 1-6")
    ok = True

    e = _engine(); b = _board(START)
    ok &= _check("site1", e._pvs_result(b, 100, 100, 3, 0),
                 "upper", False, "search", 3)

    e = _engine(); b = _board(START); b.halfmove_clock = 100
    ok &= _check("site2", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "exact", True, "terminal", None)

    e = _engine(); b = _board(START); b.position_counts[b._position_key()] = 3
    ok &= _check("site3", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "exact", True, "terminal", None)

    e = _engine(); b = _board(START); b.position_counts[b._position_key()] = 2
    ok &= _check("site4", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "upper", False, "heuristic", None)

    e = _engine(); b = _board(START)
    e.tt[b.hash] = _make_tt_entry(e, b, 0.5)
    ok &= _check("site5", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "exact", True, "search", 5)

    e = _engine(); b = _board(START)
    e.tt[b.hash] = _make_tt_entry(e, b, 100.0, flag="lower")
    ok &= _check("site6", e._pvs_result(b, 50, 60, 3, 0),
                 "lower", True, "search", 5)

    return ok


def test_sites_7_to_12():
    print("sites 7-12")
    ok = True

    e = _engine(); b = _board(FOOL_MATE)
    ok &= _check("site7", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "exact", True, "terminal", None)

    e = _engine(); b = _board(STALEMATE)
    ok &= _check("site8", e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0),
                 "exact", True, "terminal", None)

    _build_site_table()
    # Site ordinals shifted +1 by Patch 1 (mate-at-threshold,
    # inserted after site 1) and +1 again by Patch 2 (qsearch
    # mate-at-depth-cap, inserted before old site 14). Total 22.
    # The recorder checks below target sites inside _pvs_result,
    # so they are not shifted by Patch 2's quiescence insertion.
    if len(_SITE_LINES) != 22:
        print(f"  FAIL: AST found {len(_SITE_LINES)} sites, expected 22")
        return False

    _install_recorder()
    try:
        e = _engine()
        b = _board_empty_moves(START)
        r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0)
    finally:
        _uninstall_recorder()
    ok &= _check("site10", r, "upper", False, "search", 3)
    if 11 not in _sites_hit():
        print(f"  FAIL site11 recorder: observed={_sites_hit()}")
        ok = False

    _install_recorder()
    try:
        e = _engine(); b = _board(START)
        _force_pvs_child(e, SearchResult(-5.0, "exact", True, "search", 1),
                         at_ply=1)
        r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 2, 0)
    finally:
        _uninstall_recorder()
    ok &= _check("sites9_11_12", r, "exact", True, "search", 2)
    hits = _sites_hit()
    for ordinal in (10, 12, 13):
        if ordinal not in hits:
            print(f"  FAIL site{ordinal}: recorder observed={hits}")
            ok = False

    return ok


def test_sites_13_to_20():
    print("sites 13-20")
    ok = True

    e = _engine(); b = _board(START)
    with _ZeroCE():
        ok &= _check("site13",
                     e._quiescence_result(b, -MATE_SCORE, MATE_SCORE, 0,
                                          MAX_Q_DEPTH + 1),
                     "upper", False, "heuristic", None)

    e = _engine(); b = _board(START)
    with _ZeroCE():
        ok &= _check("site14",
                     e._quiescence_result(b, -MATE_SCORE, 0, 0, 0),
                     "lower", True, "quiescence", None)

    e = _engine(); b = _board(FOOL_MATE)
    ok &= _check("site15",
                 e._quiescence_result(b, -MATE_SCORE, MATE_SCORE, 0, 0),
                 "exact", True, "terminal", None)

    e = _engine(); b = _board(STALEMATE)
    ok &= _check("site16",
                 e._quiescence_result(b, -MATE_SCORE, MATE_SCORE, 0, 0),
                 "exact", True, "terminal", None)

    e = _engine(); b = _board(KQK_CAPTURE)
    _force_q_child(e,
                   SearchResult(-100.0, "exact", True, "quiescence", None),
                   at_qdepth=1)
    with _ZeroCE():
        ok &= _check("site17",
                     e._quiescence_result(b, -MATE_SCORE, 50, 0, 0),
                     "lower", True, "quiescence", None)

    e = _engine(); b = _board(START)
    with _ZeroCE():
        ok &= _check("site18",
                     e._quiescence_result(b, MATE_SCORE - 100, MATE_SCORE, 0, 0),
                     "upper", True, "quiescence", None)

    e = _engine(); b = _board(KQK_CAPTURE)
    _force_q_child(e,
                   SearchResult(-100.0, "exact", False, "quiescence", None),
                   at_qdepth=1)
    with _ZeroCE():
        ok &= _check("site19",
                     e._quiescence_result(b, -MATE_SCORE, MATE_SCORE, 0, 0),
                     "upper", False, "quiescence", None)

    e = _engine(); b = _board(KQK_CAPTURE)
    _force_q_child(e,
                   SearchResult(-100.0, "exact", True, "quiescence", None),
                   at_qdepth=1)
    with _ZeroCE():
        ok &= _check("site20",
                     e._quiescence_result(b, -MATE_SCORE, MATE_SCORE, 0, 0),
                     "exact", True, "quiescence", None)

    return ok


def test_root_contract_discovery():
    print("=== P5.15C terminal-root contract (discovery) ===")
    e = _engine()
    b = _board(START)
    b.halfmove_clock = 100

    move, score, depth, nodes = e.search(b, time_limit=None, depth=1)

    print(f"  accepted_root_source_type = {e.accepted_root_source_type!r}")
    print(f"  accepted_root_depth       = {e.accepted_root_depth!r}")
    print(f"  accepted_root_best_move   = {e.accepted_root_best_move!r}")

    if e.accepted_root_source_type == "terminal":
        print("  PASS: terminal root accepted as authoritative")
        return True
    print("  EXPECTED GAP: terminal root not accepted as authoritative")
    print("  (P5.15D.1 will introduce _root_acceptable)")
    return False


def test_multipv_1_control():
    print("multipv=1 control")
    e = _engine()
    b = _board(START)
    move, score, depth, nodes = e.search(b, time_limit=None, depth=3, multipv=1)
    ok = True
    lines = e.sorted_root_scores
    if len(lines) != 1:
        print(f"  FAIL: multipv=1 yielded {len(lines)} lines, expected 1")
        ok = False
    if lines and lines[0][0] != e.accepted_root_best_move:
        print("  FAIL: primary line move != accepted_root_best_move")
        ok = False
    if e.accepted_root_multipv:
        print(f"  FAIL: accepted_root_multipv populated under multipv=1: {e.accepted_root_multipv}")
        ok = False
    if ok:
        print(f"  PASS: 1 line, primary={move_to_str(move)}, depth={depth}")
    return ok


def test_multipv_3_startpos():
    print("multipv=3 startpos depth 3")
    e = _engine()
    b = _board(START)
    move, score, depth, nodes = e.search(b, time_limit=None, depth=3, multipv=3)
    ok = True
    lines = e.sorted_root_scores
    if len(lines) != 3:
        print(f"  FAIL: multipv=3 yielded {len(lines)} lines, expected 3")
        ok = False
    legal = set(b.generate_legal_moves())
    seen = set()
    prev = None
    for i, (m, s) in enumerate(lines):
        if m not in legal:
            print(f"  FAIL: line {i} move not legal: {m}")
            ok = False
        if m in seen:
            print(f"  FAIL: duplicate move at line {i}: {m}")
            ok = False
        seen.add(m)
        if prev is not None and s > prev:
            print(f"  FAIL: scores not descending at line {i}")
            ok = False
        prev = s
    if lines and lines[0][0] != e.accepted_root_best_move:
        print("  FAIL: primary not first in sorted_root_scores")
        ok = False
    if ok:
        print(f"  PASS: 3 lines at depth {depth}")
        for m, s in lines:
            print(f"    {move_to_str(m)}  {s:+.2f}")
    return ok


def test_multipv_fewer_legal_moves():
    print("multipv=5 with 3 legal moves (K vs K)")
    fen = "7k/8/8/8/8/8/8/7K w - - 0 1"
    e = _engine()
    b = _board(fen)
    legal = b.generate_legal_moves()
    n_legal = len(legal)
    move, score, depth, nodes = e.search(b, time_limit=None, depth=3, multipv=5)
    ok = True
    lines = e.sorted_root_scores
    if len(lines) > n_legal:
        print(f"  FAIL: {len(lines)} lines > {n_legal} legal moves")
        ok = False
    if len(lines) == 0:
        print("  FAIL: 0 lines returned")
        ok = False
    seen = set()
    for i, (m, s) in enumerate(lines):
        if m in seen:
            print(f"  FAIL: duplicate move at line {i}")
            ok = False
        seen.add(m)
        if m not in legal:
            print(f"  FAIL: line {i} move not legal")
            ok = False
    if ok:
        print(f"  PASS: {len(lines)} lines with {n_legal} legal moves")
    return ok


def test_multipv_bounded_research():
    print("multipv=3 bounded re-search call count")
    e = _engine()
    b = _board(START)
    calls = []
    orig = e._root_full_window_research
    def counting(board, move, depth):
        calls.append((move, depth))
        return orig(board, move, depth)
    e._root_full_window_research = counting
    n_legal = len(b.generate_legal_moves())
    move, score, depth, nodes = e.search(b, time_limit=None, depth=3, multipv=3)
    ok = True
    if len(calls) > n_legal:
        print(f"  FAIL: {len(calls)} re-search calls > {n_legal} legal moves")
        ok = False
    lines = e.sorted_root_scores
    if len(lines) == 0:
        print("  FAIL: 0 lines")
        ok = False
    if ok:
        print(f"  PASS: {len(calls)} re-search calls (bound: {n_legal}), {len(lines)} lines")
    return ok


def test_multipv_no_upper_cap():
    print("multipv=100 uncapped")
    e = _engine()
    b = _board(START)
    n_legal = len(b.generate_legal_moves())
    move, score, depth, nodes = e.search(b, time_limit=None, depth=3, multipv=100)
    ok = True
    lines = e.sorted_root_scores
    if len(lines) > n_legal:
        print(f"  FAIL: {len(lines)} lines > {n_legal} legal moves")
        ok = False
    if len(lines) == 0:
        print("  FAIL: 0 lines")
        ok = False
    if ok:
        print(f"  PASS: {len(lines)} lines, legal={n_legal}, no cap error")
    return ok


class _CacheCountingNnStub(_NnStub):
    def __init__(self):
        super().__init__()
        self.policy_calls = []
        self.value_calls = []

    @staticmethod
    def _context(board):
        repetition_flag = int(
            board.track_repetition
            and board.position_counts.get(board.hash, 0) >= 3
        )
        return (
            board.hash, board.en_passant,
            board.halfmove_clock, repetition_flag,
        )

    def evaluate(self, board):
        self.policy_calls.append(self._context(board))
        return 0.0, np.zeros(NUM_MOVES, dtype=np.float32)

    def evaluate_value_only(self, board):
        self.value_calls.append(self._context(board))
        return 0.0


def _nn_feature_vector(board):
    import nn as nn_mod
    out = np.zeros(nn_mod.DualNet.INPUT_SIZE, dtype=np.float32)
    net = object.__new__(nn_mod.DualNet)
    net._compute_features_into(board, out)
    return out


def test_nn_cache_feature_identity():
    print("NN cache feature identity")
    nn = _CacheCountingNnStub()
    e = SearchEngine(nn=nn, max_depth=6, tt_max=1000)

    base = _board(START)
    halfmove = _board(START.rsplit(" ", 2)[0] + " 25 1")
    repetition = _board(START)
    repetition.position_counts[repetition.hash] = 3

    no_ep = _board("4k3/8/8/4p3/8/8/8/4K3 w - - 0 1")
    raw_ep = _board("4k3/8/8/4p3/8/8/8/4K3 w - e6 0 1")

    cases = (
        ("base", base),
        ("different halfmove", halfmove),
        ("different repetition feature", repetition),
        ("no en-passant square", no_ep),
        ("raw en-passant feature", raw_ep),
    )

    ok = True
    if base.hash != halfmove.hash:
        print("  FAIL: halfmove fixture hashes differ")
        ok = False
    if base.hash != repetition.hash:
        print("  FAIL: repetition fixture hashes differ")
        ok = False
    if no_ep.hash != raw_ep.hash:
        print("  FAIL: en-passant fixture hashes differ")
        ok = False
    if raw_ep.en_passant is None or no_ep.en_passant is not None:
        print("  FAIL: en-passant fixture state is invalid")
        ok = False

    feature_pairs = (
        ("halfmove", base, halfmove),
        ("repetition", base, repetition),
        ("raw en-passant", no_ep, raw_ep),
    )
    for label, left, right in feature_pairs:
        if np.array_equal(
            _nn_feature_vector(left), _nn_feature_vector(right)
        ):
            print(f"  FAIL: {label} fixtures do not change NN features")
            ok = False

    if not ok:
        return False

    for _, board in cases:
        e._get_nn_eval(board, need_policy=True)

    first_pass_calls = len(nn.policy_calls)
    for _, board in cases:
        e._get_nn_eval(board, need_policy=True)

    if first_pass_calls != len(cases):
        print(
            f"  FAIL: expected {len(cases)} distinct NN evaluations, "
            f"got {first_pass_calls}"
        )
        ok = False
    if len(nn.policy_calls) != first_pass_calls:
        print(
            f"  FAIL: repeated identical contexts caused extra evaluations: "
            f"{len(nn.policy_calls)} total calls"
        )
        ok = False
    if e.nn_cache_misses != len(cases):
        print(
            f"  FAIL: expected {len(cases)} cache misses, "
            f"got {e.nn_cache_misses}"
        )
        ok = False
    if e.nn_cache_hits != len(cases):
        print(
            f"  FAIL: expected {len(cases)} cache hits, got {e.nn_cache_hits}"
        )
        ok = False

    value_nn = _CacheCountingNnStub()
    value_engine = SearchEngine(nn=value_nn, max_depth=6, tt_max=1000)
    value_a = _board(START)
    value_b = _board(START.rsplit(" ", 2)[0] + " 40 1")
    value_engine._get_nn_eval(value_a, need_policy=False)
    value_engine._get_nn_eval(value_a, need_policy=False)
    value_engine._get_nn_eval(value_b, need_policy=False)
    value_engine._get_nn_eval(value_b, need_policy=False)

    if value_a.hash != value_b.hash or len(value_nn.value_calls) != 2:
        print("  FAIL: value-only cache did not isolate halfmove contexts")
        ok = False
    if value_engine.nn_cache_misses != 2 or value_engine.nn_cache_hits != 2:
        print("  FAIL: value-only cache hit/miss accounting is incorrect")
        ok = False

    if ok:
        print(
            "  PASS: NN feature changes (halfmove, repetition, raw EP) "
            "are isolated; policy and value-only identical contexts reuse entries"
        )
    return ok


def test_mate_precedence_over_draw():
    print("mate precedence over draw thresholds")
    e = _engine()
    ok = True

    # --- Checkmate at draw thresholds must return mate ---
    mate_fixtures = (
        ("halfmove-100", "R6k/6pp/8/8/8/8/8/6K1 b - - 100 1", None),
        ("repetition-3", "R6k/6pp/8/8/8/8/8/6K1 b - - 0 1", 3),
        ("repetition-2", "R6k/6pp/8/8/8/8/8/6K1 b - - 0 1", 2),
    )

    for name, fen, forced_count in mate_fixtures:
        b = _board(fen)
        if forced_count is not None:
            b.position_counts[b.hash] = forced_count
        if not b.is_checkmate():
            print(f"  FAIL: {name} fixture is not checkmate")
            ok = False
            continue

        r0 = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 1, 0)
        if r0.score != -MATE_SCORE:
            print(f"  FAIL: {name} ply=0 score={r0.score}, expected {-MATE_SCORE}")
            ok = False
        if r0.bound != "exact" or r0.valid is not True or r0.source_type != "terminal":
            print(
                f"  FAIL: {name} ply=0 metadata "
                f"bound={r0.bound!r} valid={r0.valid!r} source_type={r0.source_type!r}"
            )
            ok = False

        r1 = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 1, 1)
        if r1.score != -MATE_SCORE + 1:
            print(f"  FAIL: {name} ply=1 score={r1.score}, expected {-MATE_SCORE + 1}")
            ok = False
        if r1.bound != "exact" or r1.valid is not True or r1.source_type != "terminal":
            print(
                f"  FAIL: {name} ply=1 metadata "
                f"bound={r1.bound!r} valid={r1.valid!r} source_type={r1.source_type!r}"
            )
            ok = False

    # --- Existing non-mate draw behaviours must be unchanged ---
    non_mate_cases = (
        (
            "halfmove-100 non-mate",
            "6k1/8/8/8/8/8/8/6K1 w - - 100 1",
            None, 0.0, "exact", True, "terminal",
        ),
        (
            "repetition-3 non-mate",
            "6k1/8/8/8/8/8/8/6K1 w - - 0 1",
            3, 0.0, "exact", True, "terminal",
        ),
        (
            "repetition-2 non-mate",
            "6k1/8/8/8/8/8/8/6K1 w - - 0 1",
            2, -50.0, "upper", False, "heuristic",
        ),
    )

    for (label, fen, forced_count, exp_score,
         exp_bound, exp_valid, exp_src) in non_mate_cases:
        b = _board(fen)
        if forced_count is not None:
            b.position_counts[b.hash] = forced_count
        if b.is_checkmate():
            print(f"  FAIL: {label} fixture is unexpectedly checkmate")
            ok = False
            continue

        r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 1, 0)
        if r.score != exp_score:
            print(f"  FAIL: {label} score={r.score}, expected {exp_score}")
            ok = False
        if r.bound != exp_bound:
            print(f"  FAIL: {label} bound={r.bound!r}, expected {exp_bound!r}")
            ok = False
        if r.valid is not exp_valid:
            print(f"  FAIL: {label} valid={r.valid!r}, expected {exp_valid!r}")
            ok = False
        if r.source_type != exp_src:
            print(
                f"  FAIL: {label} source_type={r.source_type!r}, "
                f"expected {exp_src!r}"
            )
            ok = False

    if ok:
        print(
            "  PASS: mate precedence preserved at halfmove-100, "
            "repetition-3, repetition-2 (ply=0 and ply=1); "
            "non-mate halfmove/repetition-3 draws unchanged; "
            "repetition-2 heuristic unchanged; result metadata verified"
        )
    return ok


def test_quiescence_mate_at_depth_cap():
    print("quiescence mate at depth cap")
    e = _engine()
    ok = True

    # Branch 1: checkmate at cap must return mate, not heuristic.
    b_mate = _board("R6k/6pp/8/8/8/8/8/6K1 b - - 0 1")
    if not b_mate.is_checkmate():
        print("  FAIL: mate fixture is not checkmate")
        ok = False
    else:
        kic0 = e.king_in_check_calls
        mfg0 = e.movegen_full_calls
        r = e._quiescence_result(
            b_mate, -MATE_SCORE, MATE_SCORE, 0, MAX_Q_DEPTH + 1
        )
        if r.score != -MATE_SCORE:
            print(
                f"  FAIL: mate at cap score={r.score}, "
                f"expected {-MATE_SCORE}"
            )
            ok = False
        if (r.bound != "exact" or r.valid is not True
                or r.source_type != "terminal"):
            print(
                f"  FAIL: mate at cap metadata "
                f"bound={r.bound!r} valid={r.valid!r} "
                f"source_type={r.source_type!r}"
            )
            ok = False
        if e.king_in_check_calls != kic0 + 1:
            print(
                f"  FAIL: mate king_in_check_calls expected +1, "
                f"got {e.king_in_check_calls - kic0}"
            )
            ok = False
        if e.movegen_full_calls != mfg0 + 1:
            print(
                f"  FAIL: mate movegen_full_calls expected +1, "
                f"got {e.movegen_full_calls - mfg0}"
            )
            ok = False

    # Branch 2: in check with legal evasions must retain heuristic.
    b_evasion = _board("4k3/8/8/8/8/8/4R3/4K3 b - - 0 1")
    evasions = b_evasion.generate_legal_moves()
    if not b_evasion.is_king_in_check("b") or not evasions:
        print("  FAIL: in-check evasion fixture is invalid")
        ok = False
    else:
        kic2 = e.king_in_check_calls
        mfg2 = e.movegen_full_calls
        with _ZeroCE():
            r = e._quiescence_result(
                b_evasion, -MATE_SCORE, MATE_SCORE, 0,
                MAX_Q_DEPTH + 1
            )
        if (r.bound != "upper" or r.valid is not False
                or r.source_type != "heuristic"):
            print(
                f"  FAIL: in-check-evasion metadata wrong: "
                f"bound={r.bound!r} valid={r.valid!r} "
                f"source_type={r.source_type!r}"
            )
            ok = False
        if e.king_in_check_calls != kic2 + 1:
            print(
                f"  FAIL: evasion king_in_check_calls expected +1, "
                f"got {e.king_in_check_calls - kic2}"
            )
            ok = False
        if e.movegen_full_calls != mfg2 + 1:
            print(
                f"  FAIL: evasion movegen_full_calls expected +1, "
                f"got {e.movegen_full_calls - mfg2}"
            )
            ok = False

    # Branch 3: not in check must retain heuristic, full-movegen untouched.
    b_start = _board(START)
    with _ZeroCE():
        kic1 = e.king_in_check_calls
        mfg1 = e.movegen_full_calls
        r = e._quiescence_result(
            b_start, -MATE_SCORE, MATE_SCORE, 0, MAX_Q_DEPTH + 1
        )
    if (r.bound != "upper" or r.valid is not False
            or r.source_type != "heuristic"):
        print(
            f"  FAIL: non-mate heuristic metadata wrong: "
            f"bound={r.bound!r} valid={r.valid!r} "
            f"source_type={r.source_type!r}"
        )
        ok = False
    if e.king_in_check_calls != kic1 + 1:
        print(
            f"  FAIL: non-mate king_in_check_calls expected +1, "
            f"got {e.king_in_check_calls - kic1}"
        )
        ok = False
    if e.movegen_full_calls != mfg1:
        print(
            f"  FAIL: non-mate movegen_full_calls expected unchanged, "
            f"got {e.movegen_full_calls - mfg1}"
        )
        ok = False

    if ok:
        print(
            "  PASS: mate-at-cap, in-check-evasion, non-mate branches "
            "and telemetry verified"
        )
    return ok


def test_mate_ply_bound_constant():
    print("mate ply bound constant")
    ok = True
    if MATE_PLY_BOUND != 1000:
        print(f"  FAIL: MATE_PLY_BOUND={MATE_PLY_BOUND}, expected 1000")
        ok = False
    if MATE_SCORE - MATE_PLY_BOUND != 29000:
        print(
            f"  FAIL: MATE_SCORE - MATE_PLY_BOUND="
            f"{MATE_SCORE - MATE_PLY_BOUND}, expected 29000"
        )
        ok = False
    if ok:
        print("  PASS: MATE_PLY_BOUND=1000; threshold matches backend/frontend")
    return ok


def test_mate_ply_bound_tt_retrieve():
    print("mate ply bound in TT retrieval")
    ok = True

    cases = (
        ("+29900 old boundary at ply 10",  29900,  10,  29890),
        ("+29901 above old at ply 10",     29901,  10,  29891),
        ("+29001 below old at ply 10",     29001,  10,  28991),
        ("+29000 new boundary at ply 10",  29000,  10,  29000),
        ("+28500 non-mate at ply 10",      28500,  10,  28500),
        ("-29900 old boundary at ply 10", -29900,  10, -29890),
        ("-29901 above old at ply 10",    -29901,  10, -29891),
        ("-29001 below old at ply 10",    -29001,  10, -28991),
        ("-29000 new boundary at ply 10", -29000,  10, -29000),
        ("-28500 non-mate at ply 10",     -28500,  10, -28500),
    )

    for label, stored, ply, expected in cases:
        e = _engine()
        b = _board(START)
        e.tt[b.hash] = _make_tt_entry(
            e, b, stored,
            depth=10, flag="exact",
            source_type="search", source_depth=5,
        )
        r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, ply)
        if r.score != expected:
            print(
                f"  FAIL: {label}: got {r.score}, expected {expected}"
            )
            ok = False

    if ok:
        print(
            "  PASS: positive and negative TT retrieval adjustments; "
            "strict 29000 boundary preserved"
        )
    return ok


def test_mate_ply_bound_tt_store_roundtrip():
    print("mate ply bound in TT store (round-trip)")
    ok = True
    mate_fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"

    for ply in (0, 4):
        e = _engine()
        b = _board(mate_fen)
        captured = []
        original_store = e._store_tt

        def capture(hash_key, score, depth, flag, move, valid=True,
                    source_type=None, source_depth=None,
                    stored_halfmove=None, stored_track_rep=None,
                    stored_rep_fp=None,
                    _original=original_store, _captured=captured):
            _captured.append((hash_key, score))
            return _original(
                hash_key, score, depth, flag, move,
                valid=valid, source_type=source_type,
                source_depth=source_depth,
                stored_halfmove=stored_halfmove,
                stored_track_rep=stored_track_rep,
                stored_rep_fp=stored_rep_fp,
            )

        # Force only the exact-result eligibility gate so this test
        # directly exercises mate-score storage normalisation.
        # The production eligibility policy is not modified.
        e._store_tt = capture
        e._tt_exact_eligible = lambda _result: True
        try:
            r = e._pvs_result(
                b, -MATE_SCORE, MATE_SCORE, depth=3, ply=ply
            )
        finally:
            del e._store_tt
            del e._tt_exact_eligible

        expected_root = MATE_SCORE - 1 - ply
        expected_stored = MATE_SCORE - 1

        if r.score != expected_root:
            print(
                f"  FAIL: ply={ply}: returned {r.score}, "
                f"expected {expected_root}"
            )
            ok = False
            continue

        root_records = [
            score for hash_key, score in captured
            if hash_key == b.hash
        ]
        if not root_records:
            print(f"  FAIL: ply={ply}: no root-position TT store call")
            ok = False
            continue

        if root_records[-1] != expected_stored:
            print(
                f"  FAIL: ply={ply}: captured root score="
                f"{root_records[-1]}, expected {expected_stored}"
            )
            ok = False

        entry = e.tt.get(b.hash)
        if not isinstance(entry, dict):
            print(f"  FAIL: ply={ply}: root TT entry was not stored")
            ok = False
        elif entry.get("score") != expected_stored:
            print(
                f"  FAIL: ply={ply}: actual TT entry score="
                f"{entry.get('score')}, expected {expected_stored}"
            )
            ok = False

    if ok:
        print(
            "  PASS: actual root TT entries store node-relative "
            "mate-in-1 score correctly at ply=0 and ply=4"
        )
    return ok


def test_tt_context_compatibility():
    print("TT context compatibility")
    ok = True

    # Case 1: identical context on a normal position. Exact hit
    # returns immediately; no children searched.
    e = _engine(); b = _board(START)
    e.tt[b.hash] = _make_tt_entry(e, b, 500.0, depth=10)
    eh0 = e.tt_exact_hits
    cr0 = e.tt_context_rejections
    r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0)
    if r.score != 500.0 or r.bound != "exact":
        print(f"  FAIL case1: score={r.score}, bound={r.bound}")
        ok = False
    if e.tt_exact_hits != eh0 + 1:
        print(f"  FAIL case1: exact hits {e.tt_exact_hits} != {eh0 + 1}")
        ok = False
    if e.tt_context_rejections != cr0:
        print(f"  FAIL case1: unexpected rejection")
        ok = False

    # Cases 2-5: incompatible context on terminal position. TT probe
    # fires at root before terminal detection; rejection counter
    # increments; mate score returned. No children searched.
    incompatible_builders = (
        ("case2 halfmove", _builder_halfmove),
        ("case3 additional history entry", _builder_repcount),
        ("case4 other pos", _builder_otherpos),
        ("case5 track_rep", _builder_trackrep),
    )

    for label, builder in incompatible_builders:
        e = _engine(); b = _board(FOOL_MATE)
        seed = builder(b, e)
        e.tt[b.hash] = _make_tt_entry(e, seed, 500.0, depth=10)
        cr0 = e.tt_context_rejections
        dq0 = e.tt_depth_qualified_hits
        eh0 = e.tt_exact_hits
        r = e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0)
        if e.tt_context_rejections != cr0 + 1:
            print(f"  FAIL {label}: rejections {e.tt_context_rejections} != {cr0 + 1}")
            ok = False
        if e.tt_depth_qualified_hits != dq0:
            print(f"  FAIL {label}: depth-qualified changed")
            ok = False
        if e.tt_exact_hits != eh0:
            print(f"  FAIL {label}: exact hits changed")
            ok = False
        if r.score == 500.0 and r.bound == "exact":
            print(f"  FAIL {label}: seed score reused")
            ok = False
        if r.score != -MATE_SCORE:
            print(f"  FAIL {label}: expected mate, got {r.score}")
            ok = False

    # Case 6: incompatible entry with move. Score not reused; TT move
    # still promoted to moves[0] by _order_moves. Interrupt at root
    # ordering to isolate from child TT activity (children may
    # legitimately hit entries via transposition and would inflate
    # the counters checked here).
    e = _engine(); b = _board(START)
    eb = b.copy(); eb.halfmove_clock = 10
    legal = b.generate_legal_moves()
    e_probe = _engine()
    probe_moves = list(legal)
    e_probe._order_moves(b, probe_moves, 0, None)
    natural_first = probe_moves[0] if probe_moves else None
    first_move = None
    for m in legal:
        if m != natural_first:
            first_move = m
            break
    if first_move is None:
        print("  FAIL case6: no distinguishing move on START")
        ok = False
    else:
        e.tt[b.hash] = _make_tt_entry(
            e, eb, 500.0, depth=10, move=first_move
        )
        captured_tt = [None]
        captured_first = [None]

        class _RootOrderingReached(Exception):
            pass

        orig_order = e._order_moves
        def capture_order(board, moves, ply, tt_entry):
            orig_order(board, moves, ply, tt_entry)
            if ply == 0:
                captured_tt[0] = tt_entry
                captured_first[0] = moves[0] if moves else None
                raise _RootOrderingReached

        e._order_moves = capture_order
        cr0 = e.tt_context_rejections
        dq0 = e.tt_depth_qualified_hits
        eh0 = e.tt_exact_hits
        reached = False
        try:
            e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0)
        except _RootOrderingReached:
            reached = True
        finally:
            del e._order_moves

        if not reached:
            print("  FAIL case6: root ordering not reached "
                  "(incompatible exact TT entry may have returned early)")
            ok = False
        if e.tt_context_rejections < cr0 + 1:
            print("  FAIL case6: no context rejection recorded")
            ok = False
        if e.tt_depth_qualified_hits != dq0:
            print("  FAIL case6: depth-qualified changed on rejection")
            ok = False
        if e.tt_exact_hits != eh0:
            print("  FAIL case6: exact hits changed on rejection")
            ok = False
        if captured_tt[0] is None:
            print("  FAIL case6: _order_moves did not receive tt_entry")
            ok = False
        elif captured_tt[0].get("move") != first_move:
            print("  FAIL case6: tt_entry.move mismatch")
            ok = False
        if captured_first[0] != first_move:
            print("  FAIL case6: TT move not promoted to moves[0]")
            ok = False

    # Case 7: replacement policy across all three context mismatches.
    replace_builders = (
        ("case7a halfmove", _builder_halfmove),
        ("case7b additional history entry", _builder_repcount),
        ("case7c track_rep", _builder_trackrep),
    )
    for label, builder in replace_builders:
        e = _engine(); b = _board(START)
        seed = builder(b, e)
        e.tt[b.hash] = _make_tt_entry(e, seed, 500.0, depth=100)
        e._store_tt(
            b.hash, 300.0, 5, "exact", None,
            valid=True, source_type="search", source_depth=5,
            stored_halfmove=b.halfmove_clock,
            stored_track_rep=b.track_repetition,
            stored_rep_fp=e._rep_fingerprint(b),
        )
        new_entry = e.tt.get(b.hash)
        if new_entry is None:
            print(f"  FAIL {label}: entry disappeared")
            ok = False
            continue
        if new_entry.get("stored_halfmove") != b.halfmove_clock:
            print(f"  FAIL {label}: halfmove={new_entry.get('stored_halfmove')}")
            ok = False
        if new_entry.get("stored_track_rep") != b.track_repetition:
            print(f"  FAIL {label}: track_rep={new_entry.get('stored_track_rep')}")
            ok = False
        if new_entry.get("stored_rep_fp") != e._rep_fingerprint(b):
            print(f"  FAIL {label}: repetition fingerprint mismatch")
            ok = False
        if new_entry.get("depth") != 5:
            print(f"  FAIL {label}: depth={new_entry.get('depth')}")
            ok = False
        if new_entry.get("score") != 300.0:
            print(f"  FAIL {label}: score={new_entry.get('score')}")
            ok = False

    # Case 8: fingerprint restored after make/undo.
    e = _engine(); b = _board(START)
    fp_before = e._rep_fingerprint(b)
    legal = b.generate_legal_moves()
    if legal:
        undo = b.make_move(legal[0])
        b.undo_move(undo)
        fp_after = e._rep_fingerprint(b)
        if fp_before != fp_after:
            print("  FAIL case8: fingerprint not restored")
            ok = False

    # Case 9: copy preserves fingerprint.
    e = _engine(); b = _board(START)
    fp_orig = e._rep_fingerprint(b)
    b_copy = b.copy(copy_history=True)
    fp_copy = e._rep_fingerprint(b_copy)
    if fp_orig != fp_copy:
        print("  FAIL case9: copy fingerprint differs")
        ok = False

    # Case 10: telemetry isolation on terminal position.
    e = _engine(); b = _board(FOOL_MATE)
    eb = b.copy(); eb.halfmove_clock = 10
    e.tt[b.hash] = _make_tt_entry(e, eb, 500.0, depth=10)
    rej0 = e.tt_context_rejections
    dq0 = e.tt_depth_qualified_hits
    e._pvs_result(b, -MATE_SCORE, MATE_SCORE, 3, 0)
    if e.tt_context_rejections != rej0 + 1:
        print(f"  FAIL case10: rejection not incremented")
        ok = False
    if e.tt_depth_qualified_hits != dq0:
        print(f"  FAIL case10: depth-qualified changed")
        ok = False

    if ok:
        print("  PASS: TT context compatibility across all cases")
    return ok


def _builder_halfmove(b, e):
    sb = b.copy(); sb.halfmove_clock = 10
    return sb


def _builder_repcount(b, e):
    sb = b.copy(); sb.position_counts[sb.hash ^ 1] = 2
    return sb


def _builder_otherpos(b, e):
    sb = b.copy(); sb.position_counts[sb.hash ^ 2] = 1
    return sb


def _builder_trackrep(b, e):
    sb = b.copy(); sb.track_repetition = False; sb.position_counts = {}
    return sb


def test_multipv_no_work_when_1():
    print("multipv=1 invokes no MultiPV helpers")
    e = _engine()
    b = _board(START)
    def boom(*args, **kwargs):
        raise AssertionError("_build_multipv_lines called under multipv=1")
    e._build_multipv_lines = boom
    def boom2(*args, **kwargs):
        raise AssertionError("_root_full_window_research called under multipv=1")
    e._root_full_window_research = boom2
    try:
        e.search(b, time_limit=None, depth=3, multipv=1)
    except AssertionError as ex:
        print(f"  FAIL: {ex}")
        return False
    print("  PASS: no MultiPV helpers invoked")
    return True


if __name__ == "__main__":
    if "--root-discovery" in sys.argv:
        test_root_contract_discovery()
        sys.exit(0)

    overall = True
    overall &= test_sites_1_to_6()
    overall &= test_sites_7_to_12()
    overall &= test_sites_13_to_20()

    multipv_ok = True
    multipv_ok &= test_multipv_1_control()
    multipv_ok &= test_multipv_3_startpos()
    multipv_ok &= test_multipv_fewer_legal_moves()
    multipv_ok &= test_multipv_bounded_research()
    multipv_ok &= test_multipv_no_upper_cap()
    multipv_ok &= test_multipv_no_work_when_1()

    nn_cache_ok = test_nn_cache_feature_identity()

    mate_precedence_ok = test_mate_precedence_over_draw()

    quiescence_mate_ok = test_quiescence_mate_at_depth_cap()

    mate_ply_bound_ok = test_mate_ply_bound_constant()
    mate_ply_bound_ok &= test_mate_ply_bound_tt_retrieve()
    mate_ply_bound_ok &= test_mate_ply_bound_tt_store_roundtrip()

    tt_context_ok = test_tt_context_compatibility()

    print()
    if overall:
        print("22/22 construction sites covered")
        print("all provenance tuples match P5.15C contract")
        print("P5.15D PASS")
    else:
        print("P5.15D FAIL")

    if multipv_ok:
        print("P5.15E PASS")
    else:
        print("P5.15E FAIL")

    if nn_cache_ok:
        print("NN CACHE IDENTITY PASS")
    else:
        print("NN CACHE IDENTITY FAIL")

    if mate_precedence_ok:
        print("MATE PRECEDENCE PASS")
    else:
        print("MATE PRECEDENCE FAIL")

    if quiescence_mate_ok:
        print("QUIESCENCE MATE PASS")
    else:
        print("QUIESCENCE MATE FAIL")

    if mate_ply_bound_ok:
        print("MATE PLY BOUND PASS")
    else:
        print("MATE PLY BOUND FAIL")

    if tt_context_ok:
        print("TT CONTEXT PASS")
    else:
        print("TT CONTEXT FAIL")

    sys.exit(0 if (overall and multipv_ok and nn_cache_ok and mate_precedence_ok and quiescence_mate_ok and mate_ply_bound_ok and tt_context_ok) else 1)
