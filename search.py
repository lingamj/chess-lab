#!/usr/bin/env python3
"""Search engine – full NN evaluation with compact LRU NN cache.
   Incremental NN features are used (via nn.py / board.py).
   Quiescence search is active at depth zero.
   LMR re‑search depth corrected. Negative‑depth bug fixed (depth <= 0).
   Policy shape handled defensively (ravel).

   FIXES:
   - Quiescence no longer expands every checking move (removed _move_gives_check).
   - All evasions searched when in check (no pruning).
   - Captures capped to 16 best policy moves (when NOT in check).
   - Quiescence terminates on search-legal conditions, not a node cap.
   - Mate distance pruning added.
   - Timeout returns last fully completed depth (or 0); never -MATE.
   - Aspiration re‑search timeout preserves first valid score.
   - Completed depth correctly reported.
"""

import math, time, threading, itertools
from dataclasses import dataclass, replace
import numpy as np
from collections import OrderedDict
from board import ChessBoard, MATE, CHAR_TO_CODE
from move_helpers import move_to_str, str_to_move, move_to_index
from static_eval import combined_eval

MAX_DEPTH = 20
MATE_SCORE = 30000
MATE_PLY_BOUND = 1000  # Exclusive ply-distance bound for mate-score classification.
                      # A score at exactly the threshold (MATE_SCORE minus
                      # this bound) is excluded by the strict '>' comparison;
                      # matches the '> 29000' threshold in web_control.py
                      # and frontend/js/analysis.js.
TT_MAX = 500000
NN_CACHE_MAX = 50000
NN_SCALE = 800
TOP_POLICY_N = 32
CURRENT_TT_VERSION = 2
SEARCH_SEMANTIC_VERSION = 1  # bump on any change to search semantics
PV_MAX = 1024  # defensive PV extraction bound; not a search-depth limit
MAX_Q_DEPTH = 6  # qsearch depth cap, relative to qsearch entry
DELTA_MARGIN = 200  # centipawn safety margin for delta pruning
_PIECE_CP = {'P':100,'N':320,'B':330,'R':500,'Q':900,'K':0}

# P5.15C I5: only these source_type values may be treated as
# authoritative at the root or written to the TT as exact.
# quiescence and heuristic results are never authoritative.
AUTHORITATIVE_ROOT_SOURCES = frozenset({"search", "terminal"})

class SearchTimeout(Exception):
    pass


@dataclass
class SearchResult:
    score: float
    bound: str
    valid: bool
    source_type: str
    source_depth: int | None
    move: object | None = None

    def __post_init__(self):
        # bound is always one of the four engine states.
        # "invalid" is an internal/result-state sentinel and is permitted
        # only when valid is False.
        if self.bound not in ("exact", "lower", "upper", "invalid"):
            raise ValueError(
                f"invalid SearchResult bound: {self.bound!r}"
            )
        if self.valid and self.bound == "invalid":
            raise ValueError(
                "valid=True requires bound to be exact, lower, or upper"
            )
        # source_depth is required as a field, but None is legitimate.
        # Missing source_depth is therefore structurally impossible in
        # a SearchResult; None means "this result has no fixed depth
        # provenance" (for example terminal or quiescence).
        if not isinstance(self.source_type, str) or not self.source_type:
            raise ValueError("source_type must be a non-empty string")

class SearchEngine:
    def __init__(self, nn=None, max_depth=MAX_DEPTH, tt_max=TT_MAX):
        self.nn = nn
        self.max_depth = max_depth
        self.tt = OrderedDict()
        self.tt_max = tt_max
        self.nn_cache = OrderedDict()
        self.nodes = 0
        self.start_time = 0
        self.time_limit = 0
        self.alpha_beta_calls = 0
        self.current_depth = 0
        self.last_pv = []
        self.root_scores = {}
        self.sorted_root_scores = []
        self.accepted_root_best_move = None
        self.accepted_root_best_score = 0
        self.accepted_root_depth = 0
        self.accepted_root_scores = {}
        self.accepted_root_source_type = None
        self.accepted_root_source_depth = None
        self.accepted_root_multipv = {}
        self.root_move_candidates = {}
        self.tt_version = CURRENT_TT_VERSION
        self.killers = [[None, None] for _ in range(32)]
        self.history = {}
        self.stop_event = threading.Event()
        self.q_nodes = 0
        # Search telemetry counters. These are measurements only;
        # they must not influence search decisions. The definitions
        # and deliberate call-site exclusions are recorded in
        # docs/SEARCH_ALGORITHM.md in the telemetry section.
        # q_nodes retains its per-iteration meaning; total_q_nodes
        # accumulates across iterations of the current search call.
        # Hot-path make/undo and move-generation counts deliberately
        # exclude root-verification, MultiPV-helper and search()-
        # acceptance/fallback operations. The LMR exemption check
        # in _pvs_result is excluded to preserve its boolean chain.
        # capture_gives_check_calls counts delta-prune check tests
        # at the single call site in _quiescence_result; the
        # _capture_gives_check method is a staticmethod and cannot
        # safely increment instance state.
        self.tt_probes = 0
        self.tt_hits = 0
        self.tt_valid_hits = 0
        self.tt_depth_qualified_hits = 0
        self.tt_exact_hits = 0
        self.tt_cutoff_hits = 0
        self.tt_inserts = 0
        self.tt_replaces = 0
        self.tt_stale_replaces = 0
        self.tt_context_rejections = 0
        self.nn_policy_calls = 0
        self.nn_value_calls = 0
        self.nn_cache_hits = 0
        self.nn_cache_misses = 0
        self.make_move_calls = 0
        self.undo_move_calls = 0
        self.movegen_full_calls = 0
        self.movegen_capture_calls = 0
        self.king_in_check_calls = 0
        self.capture_gives_check_calls = 0
        self.move_order_calls = 0
        self.total_q_nodes = 0
        # Per-ply PV tracking. Reusable rows; no list allocation
        # on the hot path. pv_moves[ply] holds the move list for
        # the current best line at that ply; pv_length[ply] is
        # its valid prefix length.
        self.pv_moves = []
        self.pv_length = []
        # Per-iteration telemetry for this search() invocation.
        # Each entry is:
        #   (depth, elapsed_seconds, nodes_delta,
        #    q_nodes, alpha_beta_calls, bound, valid, accepted)
        # Reset at the start of every search() call.
        self.iteration_stats = []

    @staticmethod
    def _invert_bound(bound):
        if bound == "exact":
            return "exact"
        if bound == "lower":
            return "upper"
        if bound == "upper":
            return "lower"
        return "invalid"

    @staticmethod
    def _tt_exact_eligible(result):
        # P5.15C I5: positive source-set check. A heuristic or
        # otherwise-unlisted source must not become TT-exact even
        # if it returns bound="exact" and valid=True.
        return (
            result.valid
            and result.bound == "exact"
            and result.source_type in AUTHORITATIVE_ROOT_SOURCES
        )

    @staticmethod
    def _root_acceptable(result, iteration_move, legal_moves):
        # P5.15C I6 two-case root acceptance.
        # Case A (move-producing): valid exact authoritative
        #   source with a legal move.
        # Case B (terminal): valid exact "terminal" source with
        #   no move. Covers checkmate, stalemate, fifty-move,
        #   threefold.
        if not result.valid or result.bound != "exact":
            return False
        if result.source_type not in AUTHORITATIVE_ROOT_SOURCES:
            return False
        if iteration_move is None:
            return result.source_type == "terminal"
        return iteration_move in legal_moves

    def _root_full_window_research(self, board, move, depth):
        undo = board.make_move(move)
        try:
            child = self._pvs_result(
                board, -MATE_SCORE, MATE_SCORE, depth - 1, 1
            )
        finally:
            board.undo_move(undo)
        if not child.valid:
            return None
        if child.source_type not in AUTHORITATIVE_ROOT_SOURCES:
            return None
        if child.bound != "exact":
            return None
        return -child.score

    def _build_multipv_lines(self, board, depth, primary_move,
                             primary_score, multipv):
        legal = board.generate_legal_moves()
        if primary_move not in legal:
            return {primary_move: primary_score}

        candidates = self.root_move_candidates
        exact = {}
        bound_only = []

        for move in legal:
            if move == primary_move:
                continue
            cand = candidates.get(move)
            if (
                cand is not None
                and cand.valid
                and cand.bound == "exact"
                and cand.source_type in AUTHORITATIVE_ROOT_SOURCES
            ):
                exact[move] = cand.score
            else:
                priority = (
                    cand.score if cand is not None else float("-inf")
                )
                bound_only.append((priority, move))

        if len(exact) + 1 < multipv:
            bound_only.sort(key=lambda x: -x[0])
            for _, move in bound_only:
                if len(exact) + 1 >= multipv:
                    break
                if self._time_up():
                    break
                try:
                    score = self._root_full_window_research(
                        board, move, depth
                    )
                except SearchTimeout:
                    break
                if score is not None:
                    exact[move] = score

        ranked_secondaries = sorted(
            exact.items(), key=lambda x: -x[1]
        )
        lines = [(primary_move, primary_score)] + ranked_secondaries
        seen = set()
        deduped = []
        for move, score in lines:
            if move in seen:
                continue
            seen.add(move)
            deduped.append((move, score))
            if len(deduped) >= multipv:
                break
        return dict(deduped)

    def search(self, board, time_limit=3000, depth=None,
               on_accepted_iteration=None, unlimited=False,
               continue_from=None, multipv=1):
        self.start_time = time.time()
        self.time_limit = None if time_limit is None else time_limit / 1000.0

        if type(multipv) is not int or multipv < 1:
            raise ValueError(
                "multipv must be a positive int; got %r" % (multipv,)
            )

        if continue_from is None:
            start_depth = 1
        else:
            if type(continue_from) is not int or continue_from <= 0:
                raise ValueError(
                    "continue_from must be a positive int"
                )
            if continue_from != self.accepted_root_depth:
                raise ValueError(
                    "continue_from must equal accepted_root_depth "
                    f"({self.accepted_root_depth}); got {continue_from}"
                )
            start_depth = continue_from + 1

        if unlimited:
            depth_iter = itertools.count(start_depth)
        else:
            if depth is None:
                depth = self.max_depth
            depth_iter = range(start_depth, depth + 1)

        # Transient per-run counters always reset.
        self.nodes = 0
        self.q_nodes = 0
        self.current_depth = 0
        self.iteration_stats = []
        self.tt_probes = 0
        self.tt_hits = 0
        self.tt_valid_hits = 0
        self.tt_depth_qualified_hits = 0
        self.tt_exact_hits = 0
        self.tt_cutoff_hits = 0
        self.tt_inserts = 0
        self.tt_replaces = 0
        self.tt_stale_replaces = 0
        self.tt_context_rejections = 0
        self.nn_policy_calls = 0
        self.nn_value_calls = 0
        self.nn_cache_hits = 0
        self.nn_cache_misses = 0
        self.make_move_calls = 0
        self.undo_move_calls = 0
        self.movegen_full_calls = 0
        self.movegen_capture_calls = 0
        self.king_in_check_calls = 0
        self.capture_gives_check_calls = 0
        self.move_order_calls = 0
        self.total_q_nodes = 0
        # Reset PV table. It is rebuilt every iteration, but
        # clearing here guarantees a fresh search never sees a
        # stale line from a previous run.
        self.pv_moves = []
        self.pv_length = []

        if continue_from is None:
            # Fresh search: clear persistent search state.
            self.root_scores = {}
            self.sorted_root_scores = []
            self.last_pv = []
            self.accepted_root_best_move = None
            self.accepted_root_best_score = 0
            self.accepted_root_depth = 0
            self.accepted_root_scores = {}
            self.accepted_root_source_type = None
            self.accepted_root_source_depth = None
            self.accepted_root_multipv = {}
            self._clear_heuristics()

            best_move = None
            best_score = 0
            completed_depth = 0
        else:
            # Continuation: preserve TT, NN cache, heuristics,
            # accepted root, root_scores, sorted_root_scores, last_pv.
            best_move = self.accepted_root_best_move
            best_score = self.accepted_root_best_score
            completed_depth = self.accepted_root_depth

        try:
            for d in depth_iter:
                self.current_depth = d
                self.q_nodes = 0
                self.alpha_beta_calls = 0
                self.root_move_candidates = {}
                _iter_t0 = time.perf_counter()
                _iter_nodes0 = self.nodes

                if (d > 1 and abs(best_score) < MATE_SCORE - MATE_PLY_BOUND
                        and multipv == 1):
                    alpha = best_score - 50
                    beta = best_score + 50
                else:
                    alpha = -MATE_SCORE
                    beta = MATE_SCORE

                last_valid_score = best_score

                result = self._pvs_result(board, alpha, beta, d, 0)
                score = result.score

                if (
                    (result.valid and result.bound == "lower")
                    or score >= beta
                ):
                    try:
                        result = self._pvs_result(
                            board, -MATE_SCORE, MATE_SCORE, d, 0
                        )
                        score = result.score
                    except SearchTimeout:
                        score = last_valid_score
                        raise

                if (
                    (result.valid and result.bound == "upper")
                    or score <= alpha
                ):
                    try:
                        result = self._pvs_result(
                            board, -MATE_SCORE, MATE_SCORE, d, 0
                        )
                        score = result.score
                    except SearchTimeout:
                        score = last_valid_score
                        raise

                legal = board.generate_legal_moves()
                iteration_move = result.move

                accepted = self._root_acceptable(
                    result, iteration_move, legal
                )

                # P5.15I: verify a rejected mate-level root result
                # with a full-window re-search on a fresh, empty
                # TT. This prevents warm entries from tightening
                # the verifier's window. Restore the ongoing
                # search's TT immediately afterward. Promote only
                # an exact verified score match, then run the
                # original root-acceptance gate again.
                if (
                    not accepted
                    and iteration_move is not None
                    and iteration_move in legal
                    and result.source_type in AUTHORITATIVE_ROOT_SOURCES
                    and abs(result.score) > MATE_SCORE - MATE_PLY_BOUND
                ):
                    saved_tt = self.tt
                    self.tt = OrderedDict()
                    try:
                        try:
                            verified = self._root_full_window_research(
                                board, iteration_move, d
                            )
                        except SearchTimeout:
                            verified = None
                    finally:
                        self.tt = saved_tt
                    if verified is not None and verified == result.score:
                        # dataclasses.replace re-runs SearchResult
                        # validation without adding an AST site.
                        result = replace(
                            result,
                            score=verified,
                            bound="exact",
                            valid=True,
                            source_type="search",
                            source_depth=d,
                            move=iteration_move,
                        )
                        accepted = self._root_acceptable(
                            result, iteration_move, legal
                        )

                if accepted:
                    accepted_scores = {iteration_move: result.score}

                    self.accepted_root_best_move = iteration_move
                    self.accepted_root_best_score = result.score
                    self.accepted_root_depth = d
                    self.accepted_root_scores = accepted_scores
                    self.accepted_root_source_type = result.source_type
                    self.accepted_root_source_depth = result.source_depth

                    best_move = iteration_move
                    best_score = result.score
                    completed_depth = d

                    # Snapshot the PV for this accepted iteration.
                    # This is the authoritative PV until a later
                    # iteration is accepted; a partial timeout on
                    # the next iteration will not overwrite it.
                    pv_snapshot = self._extract_pv(board)
                    self.last_pv = pv_snapshot

                    if on_accepted_iteration is not None:
                        on_accepted_iteration(
                            d, iteration_move,
                            result.score, pv_snapshot
                        )

                    if multipv > 1:
                        try:
                            self.accepted_root_multipv = (
                                self._build_multipv_lines(
                                    board, d, iteration_move,
                                    result.score, multipv
                                )
                            )
                        except SearchTimeout:
                            pass
                else:
                    # No authoritative iteration accepted at this depth.
                    # Preserve the last accepted root state.
                    score = (
                        self.accepted_root_best_score
                        if self.accepted_root_depth > 0
                        else best_score
                    )
                    best_score = score
                    completed_depth = self.accepted_root_depth

                self.iteration_stats.append((
                    d,
                    time.perf_counter() - _iter_t0,
                    self.nodes - _iter_nodes0,
                    self.q_nodes,
                    self.alpha_beta_calls,
                    result.bound,
                    result.valid,
                    accepted,
                ))

                if self._time_up():
                    break

                if accepted and abs(result.score) > MATE_SCORE - MATE_PLY_BOUND:
                    if d >= (MATE_SCORE - abs(result.score)):
                        break

        except SearchTimeout:
            pass

        self.current_depth = completed_depth

        if self.accepted_root_depth > 0:
            best_move = self.accepted_root_best_move
            best_score = self.accepted_root_best_score

            legal = board.generate_legal_moves()

            if best_move is not None:
                if len(best_move) == 5 and best_move[4] is None:
                    best_move = best_move[:4]

                if best_move not in legal:
                    raise AssertionError(
                        "accepted_root_best_move is not legal"
                    )

                self.accepted_root_best_move = best_move

            # self.last_pv was snapshotted at the moment of the
            # last accepted iteration. It is not re-extracted
            # here, because a partial timeout iteration may have
            # overwritten the pv table since that snapshot.
            pv = self.last_pv

            if pv:
                if pv[0] != best_move:
                    raise AssertionError(
                        "PV first move disagrees with "
                        "accepted_root_best_move"
                    )
        else:
            # Emergency legacy fallback. Non-authoritative; must not
            # populate accepted_root_*.
            legal = board.generate_legal_moves()

            if best_move is not None:
                if len(best_move) == 5 and best_move[4] is None:
                    best_move = best_move[:4]

                if best_move not in legal:
                    best_move = legal[0] if legal else None

            if best_move is None and legal:
                best_move = legal[0]

            self.last_pv = self._extract_pv(board)

        if self.accepted_root_depth > 0:
            if multipv > 1 and self.accepted_root_multipv:
                self.sorted_root_scores = sorted(
                    self.accepted_root_multipv.items(),
                    key=lambda x: -x[1]
                )
            else:
                self.sorted_root_scores = sorted(
                    self.accepted_root_scores.items(),
                    key=lambda x: -x[1]
                )
        else:
            self.sorted_root_scores = sorted(
                self.root_scores.items(),
                key=lambda x: -x[1]
            )

        return (
            best_move,
            best_score,
            self.current_depth,
            self.nodes
        )

    def _time_up(self):
        if self.stop_event is not None and self.stop_event.is_set():
            return True
        if self.time_limit is None:
            return False
        return (time.time() - self.start_time) > self.time_limit

    def _clear_heuristics(self):
        self.killers = [[None, None] for _ in range(32)]
        self.history = {}
        self.q_nodes = 0
        self.total_q_nodes = 0

    def get_continuation_snapshot(self):
        return {
            'best_move': self.accepted_root_best_move,
            'best_score': self.accepted_root_best_score,
            'depth': self.accepted_root_depth,
            'scores': dict(self.accepted_root_scores),
            'source_type': self.accepted_root_source_type,
            'source_depth': self.accepted_root_source_depth,
            'pv': list(self.last_pv),
        }

    def restore_continuation_snapshot(self, snap):
        if not isinstance(snap, dict):
            raise ValueError("continuation snapshot must be a dict")
        required = ('best_move', 'best_score', 'depth', 'scores',
                    'source_type', 'source_depth', 'pv')
        missing = [k for k in required if k not in snap]
        if missing:
            raise ValueError(
                f"continuation snapshot missing keys: {missing}"
            )
        depth = snap['depth']
        if type(depth) is not int or depth <= 0:
            raise ValueError(
                "continuation snapshot depth must be a positive int"
            )
        best_score = snap['best_score']
        if not isinstance(best_score, (int, float)) or isinstance(best_score, bool):
            raise ValueError(
                "continuation snapshot best_score must be numeric"
            )
        scores = snap['scores']
        if not isinstance(scores, dict):
            raise ValueError(
                "continuation snapshot scores must be a dict"
            )
        pv = snap['pv']
        if not isinstance(pv, list):
            raise ValueError(
                "continuation snapshot pv must be a list"
            )
        self.accepted_root_best_move = snap['best_move']
        self.accepted_root_best_score = best_score
        self.accepted_root_depth = depth
        self.accepted_root_scores = dict(scores)
        self.accepted_root_source_type = snap['source_type']
        self.accepted_root_source_depth = snap['source_depth']
        self.last_pv = list(pv)
        # Persisted snapshots contain only the primary line.
        # Clear stale MultiPV data only when restoring a snapshot;
        # live HOT continuation remains unaffected.
        self.accepted_root_multipv = {}

    @staticmethod
    def _top_k_dict(arr, k):
        arr = np.asarray(arr).ravel()
        if len(arr) <= k:
            indices = np.argsort(arr)[::-1]
            return {int(i): float(arr[i]) for i in indices}
        idx = np.argpartition(arr, -k)[-k:]
        idx = idx[np.argsort(arr[idx])[::-1]]
        return {int(i): float(arr[i]) for i in idx}

    def _get_nn_eval(self, board, need_policy=True):
        # The NN feature vector contains state not represented by the
        # repetition/Zobrist hash: raw en-passant file, halfmove clock,
        # and the binary threefold-repetition feature.
        repetition_flag = int(
            board.track_repetition
            and board.position_counts.get(board.hash, 0) >= 3
        )
        key = (
            board.hash,
            board.en_passant,
            board.halfmove_clock,
            repetition_flag,
        )
        cached = self.nn_cache.get(key)
        if cached is not None:
            v, p = cached
            if p is not None or not need_policy:
                self.nn_cache_hits += 1
                self.nn_cache.move_to_end(key)
                return cached

        self.nn_cache_misses += 1
        if need_policy:
            self.nn_policy_calls += 1
            val, pol = self.nn.evaluate(board)
            pol = np.asarray(pol).ravel()
            top_dict = self._top_k_dict(pol, TOP_POLICY_N)
            entry = (val, top_dict)
        else:
            self.nn_value_calls += 1
            val = self.nn.evaluate_value_only(board)
            entry = (val, None)

        if len(self.nn_cache) >= NN_CACHE_MAX:
            self.nn_cache.popitem(last=False)
        self.nn_cache[key] = entry
        return entry

    def _pvs(self, board, alpha, beta, depth, ply):
        return self._pvs_result(board, alpha, beta, depth, ply).score

    def _pvs_result(self, board, alpha, beta, depth, ply):
        if self._time_up():
            raise SearchTimeout

        # PV slot: ensure this ply has a reusable row. Only full-
        # window nodes are on the PV path; null-window calls are
        # reconnaissance and cannot produce a PV move. Skipping
        # them eliminates the dominant PV-copy cost in PVS.
        is_pv_node = (beta - alpha) > 1
        while ply >= len(self.pv_moves):
            self.pv_moves.append([])
            self.pv_length.append(0)
        if is_pv_node:
            self.pv_length[ply] = 0

        alpha = max(alpha, -MATE_SCORE + ply)
        beta = min(beta, MATE_SCORE - ply)

        if alpha >= beta:
            return SearchResult(
                alpha, "upper", False, "search", depth
            )

        self.alpha_beta_calls += 1
        self.nodes += 1

        alpha_orig = alpha
        beta_orig = beta

        # A position that is checkmate at a draw threshold is still
        # checkmate. FIDE rules confirm: checkmate on the move that
        # triggers a draw threshold takes precedence. The count >= 2
        # heuristic also masks mate; gate it here as well.
        _mate_at_threshold = (
            board.halfmove_clock >= 100
            or (
                board.track_repetition
                and board.position_counts.get(
                    board._position_key(), 0
                ) >= 2
            )
        )

        if _mate_at_threshold and board.is_checkmate():
            return SearchResult(
                -MATE_SCORE + ply, "exact", True, "terminal", None
            )

        if board.halfmove_clock >= 100:
            return SearchResult(
                0.0, "exact", True, "terminal", None
            )

        if board.track_repetition:
            key = board._position_key()

            if board.position_counts.get(key, 0) >= 3:
                return SearchResult(
                    0.0, "exact", True, "terminal", None
                )

            if board.position_counts.get(key, 0) >= 2:
                return SearchResult(
                    -50.0, "upper", False, "heuristic", None
                )

        if depth <= 0:
            return self._quiescence_result(
                board, alpha, beta, ply, 0
            )

        self.tt_probes += 1
        raw_tt_entry = self.tt.get(board.hash)
        tt_entry = None

        if raw_tt_entry is not None:
            self.tt_hits += 1
            if all(
                k in raw_tt_entry
                for k in (
                    "provenance_version",
                    "valid",
                    "source_type",
                    "source_depth",
                    "depth",
                    "flag",
                    "score",
                    "stored_halfmove",
                    "stored_track_rep",
                    "stored_rep_fp",
                )
            ):
                if (
                    raw_tt_entry["provenance_version"] == self.tt_version
                    and raw_tt_entry["valid"] is True
                ):
                    tt_entry = raw_tt_entry
                    self.tt_valid_hits += 1

        if tt_entry is not None and tt_entry["depth"] >= depth:
            if self._tt_context_compatible(tt_entry, board):
                self.tt_depth_qualified_hits += 1
                score = tt_entry["score"]

                if abs(score) > MATE_SCORE - MATE_PLY_BOUND:
                    # Node-relative -> root-relative. Positive mate
                    # scores count down toward the mate; negative
                    # ones count up. Matches terminal -MATE_SCORE+ply.
                    score = score - ply if score > 0 else score + ply

                source_depth = tt_entry["source_depth"]
                flag = tt_entry["flag"]
                move = tt_entry.get("move")
                src_type = tt_entry["source_type"]

                tt_result = SearchResult(
                    score, flag, True, src_type, source_depth, move=move
                )

                if flag == "exact" and self._tt_exact_eligible(tt_result):
                    self.tt_exact_hits += 1
                    # Populate the PV slot with the TT move so an
                    # upper ply can extend by at least this move.
                    # Deeper reconstruction would require a full
                    # re-search, not worth the cost.
                    if move is not None:
                        row = self.pv_moves[ply]
                        row.clear()
                        row.append(move)
                        self.pv_length[ply] = 1
                    return tt_result

                if flag == "lower":
                    alpha = max(alpha, score)
                elif flag == "upper":
                    beta = min(beta, score)

                if alpha >= beta:
                    self.tt_cutoff_hits += 1
                    return SearchResult(
                        score, flag, True,
                        src_type, source_depth, move=move
                    )
            else:
                self.tt_context_rejections += 1

        self.movegen_full_calls += 1
        moves = board.generate_legal_moves()

        if not moves:
            self.king_in_check_calls += 1
            if board.is_king_in_check(
                "w" if board.white_turn else "b"
            ):
                return SearchResult(
                    -MATE_SCORE + ply,
                    "exact", True, "terminal", None
                )

            return SearchResult(
                0.0, "exact", True, "terminal", None
            )

        self.move_order_calls += 1
        self._order_moves(board, moves, ply, tt_entry)

        best_move = moves[0]
        best_score = -MATE_SCORE
        best_result = None
        cutoff = False
        best_child_source_depth = None

        for i, move in enumerate(moves):
            if self._time_up():
                raise SearchTimeout

            is_capture = (
                board.board[move[2]][move[3]] != "."
                or (len(move) > 4 and move[4] is not None)
                or (
                    board.en_passant is not None
                    and move[2] == board.en_passant[0]
                    and move[3] == board.en_passant[1]
                )
            )

            is_promotion = len(move) > 4 and move[4] is not None

            self.make_move_calls += 1
            undo = board.make_move(move)

            try:
                if (
                    i >= 6
                    and depth >= 3
                    and not is_capture
                    and not is_promotion
                    # P5.15I: checking moves are never LMR-reduced.
                    # make_move has run, so board.white_turn now
                    # reflects the opponent; castling rook movement
                    # is modeled. Short-circuit means the check test
                    # runs only for moves that would have been
                    # reduced anyway.
                    and not board.is_king_in_check(
                        'w' if board.white_turn else 'b'
                    )
                ):
                    reduction = 1 + (i - 3) // 6

                    child = self._pvs_result(
                        board,
                        -alpha - 1,
                        -alpha,
                        depth - 1 - reduction,
                        ply + 1
                    )

                    parent_score = -child.score
                    parent_bound = self._invert_bound(child.bound)

                    if parent_score > alpha:
                        child = self._pvs_result(
                            board,
                            -beta,
                            -alpha,
                            depth - 1,
                            ply + 1
                        )
                        parent_score = -child.score
                        parent_bound = self._invert_bound(
                            child.bound
                        )
                else:
                    if i == 0:
                        child = self._pvs_result(
                            board,
                            -beta,
                            -alpha,
                            depth - 1,
                            ply + 1
                        )
                    else:
                        child = self._pvs_result(
                            board,
                            -alpha - 1,
                            -alpha,
                            depth - 1,
                            ply + 1
                        )

                        if -child.score > alpha:
                            child = self._pvs_result(
                                board,
                                -beta,
                                -alpha,
                                depth - 1,
                                ply + 1
                            )

                    parent_score = -child.score
                    parent_bound = self._invert_bound(child.bound)

            finally:
                self.undo_move_calls += 1
                board.undo_move(undo)

            candidate = SearchResult(
                parent_score,
                parent_bound,
                child.valid,
                "search",
                depth
            )

            if ply == 0:
                self.root_move_candidates[move] = candidate

            if best_result is None or parent_score > best_score:
                best_score = parent_score
                best_move = move
                best_result = candidate
                best_child_source_depth = child.source_depth
                # PV: only tracked at full-window nodes. At
                # null-window nodes the child PV is not
                # meaningful (the child was a scout), so no
                # copying is done. This is the standard PVS
                # PV-extraction optimization and is what makes
                # recursive PV tracking affordable in Python.
                if is_pv_node:
                    row = self.pv_moves[ply]
                    row.clear()
                    row.append(move)
                    child_len = self.pv_length[ply + 1]
                    child_row = self.pv_moves[ply + 1]
                    for _k in range(child_len):
                        row.append(child_row[_k])
                    self.pv_length[ply] = 1 + child_len

            if parent_score > alpha:
                alpha = parent_score

            if alpha >= beta:
                if not is_capture and not is_promotion:
                    self._store_killer(ply, move)
                    self._update_history(move, depth)

                best_result = candidate
                best_child_source_depth = child.source_depth
                cutoff = True
                break

        if best_result is None:
            return SearchResult(
                best_score, "upper", False, "search", depth
            )

        if (
            best_result.valid
            and best_result.bound == "exact"
            and not cutoff
        ):
            if best_score <= alpha_orig:
                final_bound = "upper"
            elif best_score >= beta_orig:
                final_bound = "lower"
            else:
                final_bound = "exact"
            final_valid = True
        else:
            if cutoff:
                final_bound = "lower"
            elif best_result.bound == "upper":
                final_bound = "upper"
            elif best_result.bound == "lower":
                final_bound = "lower"
            else:
                final_bound = "upper"
            final_valid = best_result.valid

        source_type = "search"
        source_depth = depth

        if best_child_source_depth is not None:
            tt_depth = min(depth, best_child_source_depth + 1)
        else:
            tt_depth = depth

        stored_score = best_score

        if abs(best_score) > MATE_SCORE - MATE_PLY_BOUND:
            # Root-relative -> node-relative: add ply for a
            # mate we deliver, subtract ply for one received.
            stored_score = (
                best_score + ply if best_score > 0 else best_score - ply
            )

        if final_valid:
            gate_result = SearchResult(
                best_score,
                final_bound,
                final_valid,
                source_type,
                source_depth,
                move=best_move
            )

            if (
                final_bound != "exact"
                or self._tt_exact_eligible(gate_result)
            ):
                self._store_tt(
                    board.hash,
                    stored_score,
                    tt_depth,
                    final_bound,
                    best_move,
                    valid=True,
                    source_type=source_type,
                    source_depth=source_depth,
                    stored_halfmove=board.halfmove_clock,
                    stored_track_rep=board.track_repetition,
                    stored_rep_fp=self._rep_fingerprint(board),
                )

        if ply == 0 and final_valid:
            self.root_scores[best_move] = best_score

        return SearchResult(
            best_score,
            final_bound,
            final_valid,
            source_type,
            source_depth,
            move=best_move if ply == 0 else None
        )

    def _order_moves(self, board, moves, ply, tt_entry):
        if len(moves) <= 1:
            return
        policy_dict = {}
        if ply <= 2:
            _, policy_dict = self._get_nn_eval(board)
        def score(move):
            if tt_entry and tt_entry.get('move') == move:
                return 10_000_000
            target = board.board[move[2]][move[3]]
            if target != '.':
                attacker = board.board[move[0]][move[1]]
                gain = self._piece_value(target) - self._piece_value(attacker)
                if gain > 0:
                    return 1_000_000 + gain
            if ply < len(self.killers):
                if move == self.killers[ply][0]: return 500_000
                if move == self.killers[ply][1]: return 400_000
            hist = self.history.get(tuple(move), 0)
            if hist: return 200_000 + min(hist, 50_000)
            idx = move_to_index(move)
            prob = policy_dict.get(idx, 0)
            if prob: return int(prob * 100_000)
            return 0
        moves.sort(key=score, reverse=True)

    @staticmethod
    def _capture_gives_check(board, move):
        # Return True if playing `move` would leave the opponent's
        # king in check. Uses a cheap piece-code mutation view rather
        # than make_move + is_king_in_check + undo_move.
        fr, fc, tr, tc = move[:4]
        promo = move[4] if len(move) > 4 else None
        moving_white = board.white_turn
        attacker_color = 'w' if moving_white else 'b'
        opponent = 'b' if moving_white else 'w'
        king_sq = board._king_sq.get(opponent)
        if king_sq is None:
            return False
        kr, kc = king_sq
        pc = board._piece_code
        piece = board.board[fr][fc]
        src_idx = fr * 8 + fc
        dst_idx = tr * 8 + tc
        saved_src = pc[src_idx]
        saved_dst = pc[dst_idx]
        pc[src_idx] = 0
        ep_idx = -1
        saved_ep = 0
        if (piece.upper() == 'P' and fc != tc
                and board.board[tr][tc] == '.'
                and board.en_passant == (tr, tc)):
            ep_r = tr + (1 if moving_white else -1)
            ep_idx = ep_r * 8 + tc
            saved_ep = pc[ep_idx]
            pc[ep_idx] = 0
        if promo:
            landing = promo.upper() if moving_white else promo.lower()
        else:
            landing = piece
        pc[dst_idx] = CHAR_TO_CODE[landing]
        try:
            return board.is_square_attacked(kr, kc, attacker_color)
        finally:
            pc[src_idx] = saved_src
            pc[dst_idx] = saved_dst
            if ep_idx != -1:
                pc[ep_idx] = saved_ep

    @staticmethod
    def _piece_value(piece_char):
        if piece_char == '.': return 0
        return {'P':1,'N':2,'B':3,'R':4,'Q':5,'K':6}.get(piece_char.upper(), 0)

    def _store_killer(self, ply, move):
        while ply >= len(self.killers):
            self.killers.append([None, None])
        killers = self.killers[ply]
        if killers[0] != move: killers[1] = killers[0]; killers[0] = move

    def _update_history(self, move, depth):
        key = tuple(move)
        self.history[key] = self.history.get(key, 0) + depth * depth

    def _quiescence(self, board, alpha, beta, ply):
        return self._quiescence_result(board, alpha, beta, ply, 0).score

    def _quiescence_result(self, board, alpha, beta, ply, q_depth=0):
        if self._time_up():
            raise SearchTimeout

        self.q_nodes += 1
        self.total_q_nodes += 1


        if q_depth > MAX_Q_DEPTH:
            # A checkmate reached at the quiescence depth cap must
            # be reported as mate, not as a heuristic. Non-mate
            # positions (not in check, or in check with legal
            # evasions) still return the heuristic; this patch
            # does not extend the cap into check evasions. That
            # would be a separate check-extension policy with its
            # own tactical benchmarks.
            #
            # king_in_check_calls and movegen_full_calls are both
            # incremented here so telemetry reflects actual
            # operations. The increment-before-call convention
            # matches the normal quiescence path below.
            self.king_in_check_calls += 1
            in_check_at_cap = board.is_king_in_check(
                'w' if board.white_turn else 'b'
            )
            if in_check_at_cap:
                self.movegen_full_calls += 1
                if not board.generate_legal_moves():
                    return SearchResult(
                        -MATE_SCORE + ply,
                        "exact",
                        True,
                        "terminal",
                        None
                    )
            val, _ = self._get_nn_eval(board, need_policy=False)
            ce = combined_eval(board)
            if not board.white_turn:
                ce = -ce
            return SearchResult(
                ce + int(val * NN_SCALE),
                "upper",
                False,
                "heuristic",
                None
            )

        alpha_orig = alpha
        best_bound = None
        best_valid = True

        self.king_in_check_calls += 1
        in_check = board.is_king_in_check(
            'w' if board.white_turn else 'b'
        )

        if not in_check:
            val, _ = self._get_nn_eval(board, need_policy=False)
            ce = combined_eval(board)
            if not board.white_turn:
                ce = -ce
            stand_pat = ce + int(val * NN_SCALE)

            if stand_pat >= beta:
                return SearchResult(
                    beta, "lower", True, "quiescence", None
                )

            if stand_pat > alpha:
                alpha = stand_pat
                best_bound = "exact"

        if in_check:
            self.movegen_full_calls += 1
            q_moves = board.generate_legal_moves()
            if not q_moves:
                return SearchResult(
                    -MATE_SCORE + ply,
                    "exact",
                    True,
                    "terminal",
                    None
                )
        else:
            self.movegen_capture_calls += 1
            q_moves = board.generate_legal_captures()
            if not q_moves:
                if not board.has_any_legal_move():
                    return SearchResult(
                        0.0,
                        "exact",
                        True,
                        "terminal",
                        None
                    )

            if len(q_moves) > 1:
                def q_mvvlva(mv):
                    victim = board.board[mv[2]][mv[3]]
                    attacker = board.board[mv[0]][mv[1]]
                    return (self._piece_value(victim) * 10
                            - self._piece_value(attacker))

                q_moves.sort(key=q_mvvlva, reverse=True)
                q_moves = q_moves[:16]

        for move in q_moves:
            if not in_check:
                victim = board.board[move[2]][move[3]]
                victim_cp = _PIECE_CP.get(victim.upper(), 0)
                if len(move) > 4 and move[4] is not None:
                    promo_cp = _PIECE_CP.get(str(move[4]).upper(), 0)
                    gain_cp = victim_cp + promo_cp - 100
                else:
                    gain_cp = victim_cp
                if stand_pat + gain_cp + DELTA_MARGIN <= alpha:
                    # Do not prune a capture that gives check. The
                    # material-gain estimate ignores the opponent's
                    # restricted reply, so stand_pat is not a valid
                    # floor for these moves. The check test mutates
                    # the piece-code array directly; no make/undo.
                    self.capture_gives_check_calls += 1
                    if not self._capture_gives_check(board, move):
                        continue
            self.make_move_calls += 1
            undo = board.make_move(move)
            try:
                child = self._quiescence_result(
                    board, -beta, -alpha, ply + 1, q_depth + 1
                )
                score = -child.score
            finally:
                self.undo_move_calls += 1
                board.undo_move(undo)

            if score >= beta:
                return SearchResult(
                    beta,
                    "lower",
                    child.valid,
                    "quiescence",
                    None
                )

            if score > alpha:
                alpha = score
                best_bound = self._invert_bound(child.bound)
                best_valid = child.valid

        if best_bound is None:
            return SearchResult(
                alpha, "upper", True, "quiescence", None
            )

        if not best_valid:
            return SearchResult(
                alpha, "upper", False, "quiescence", None
            )

        return SearchResult(
            alpha, best_bound, True, "quiescence", None
        )

    def _rep_fingerprint(self, board):
        if not board.track_repetition:
            return None
        return hash(frozenset(board.position_counts.items()))

    def _tt_context_compatible(self, entry, board):
        if entry.get("stored_track_rep") != board.track_repetition:
            return False
        if entry.get("stored_halfmove") != board.halfmove_clock:
            return False
        if board.track_repetition:
            cur_fp = self._rep_fingerprint(board)
            if entry.get("stored_rep_fp") != cur_fp:
                return False
        return True

    def _store_tt(self, hash_key, score, depth, flag, move, valid=True,
                  source_type=None, source_depth=None,
                  stored_halfmove=None, stored_track_rep=None,
                  stored_rep_fp=None):
        if valid is not True:
            return

        if not isinstance(source_type, str) or not source_type:
            return

        entry = {
            "score": score,
            "depth": depth,
            "flag": flag,
            "move": move,
            "valid": True,
            "provenance_version": self.tt_version,
            "source_type": source_type,
            "source_depth": source_depth,
            "stored_halfmove": stored_halfmove,
            "stored_track_rep": stored_track_rep,
            "stored_rep_fp": stored_rep_fp,
        }

        old = self.tt.get(hash_key)

        replace = False

        if old is None:
            self.tt_inserts += 1
            replace = True
        elif (
            "provenance_version" not in old
            or old["provenance_version"] != self.tt_version
        ):
            self.tt_stale_replaces += 1
            replace = True
        elif (
            "source_type" not in old
            or "source_depth" not in old
            or "depth" not in old
            or "flag" not in old
            or "valid" not in old
            or "score" not in old
        ):
            replace = True
        elif old["valid"] is not True:
            replace = True
        elif old.get("stored_halfmove") != stored_halfmove:
            replace = True
        elif old.get("stored_track_rep") != stored_track_rep:
            replace = True
        elif (
            stored_track_rep
            and old.get("stored_rep_fp") != stored_rep_fp
        ):
            replace = True
        elif depth > old["depth"]:
            replace = True
        elif (
            depth == old["depth"]
            and flag == "exact"
            and old["flag"] != "exact"
        ):
            replace = True

        if replace:
            if old is not None:
                self.tt_replaces += 1
            self.tt[hash_key] = entry

        if len(self.tt) > self.tt_max:
            try:
                self.tt.popitem(last=False)
            except KeyError:
                pass

    def _extract_pv(self, board):
        # The PV is built during the search by _pvs_result and stored
        # in self.pv_moves / self.pv_length. Slot 0 holds the PV of
        # the last accepted iteration. No TT dependency; length
        # reflects the searched depth. `board` is unused; kept for
        # signature compatibility.
        if not self.pv_moves:
            return []
        if self.pv_length[0] <= 0:
            return []
        return list(self.pv_moves[0][:self.pv_length[0]])

    def get_pv(self):
        return self.last_pv
