# SEARCH ALGORITHM

**Project:** Chess AI
**Updated:** 2026-09-11
**Applies to:** live `~/chess_ai/search.py` post-Patch-A

This document describes the search implementation in the active workspace.
It supersedes any earlier description of the search contract. Historical
search implementations are not authoritative.

---

## 1. Public interface

`SearchEngine.search(board, time_limit=3000, depth=None,
                     on_accepted_iteration=None, unlimited=False,
                     continue_from=None, multipv=1)`

Returns:

    (best_move, best_score, current_depth, nodes)

- `best_move` — a legal move tuple, or `None` if no move was found.
- `best_score` — score of the accepted authoritative iteration.
- `current_depth` — accepted authoritative depth when an iteration was
  accepted; otherwise the fallback reports no accepted depth.
- `nodes` — total nodes visited during this search.
- `multipv` — positive integer, default 1. Requests up to N exact
  authoritative root lines. No engine-imposed maximum; the number
  actually returned is bounded by legal root moves and by the search
  budget actually completed. Values below 1 or non-int raise
  `ValueError`. `multipv=1` is behaviorally equivalent to pre-P5.15E.

Compatibility wrappers retained for callers that still expect scalar returns:

- `_pvs(board, alpha, beta, depth, ply)` — returns scalar score.
- `_quiescence(board, alpha, beta, ply)` — returns scalar score.

Internal methods return `SearchResult` objects:

- `_pvs_result(...)` — returns `SearchResult`.
- `_quiescence_result(...)` — returns `SearchResult`.

---

## 2. SearchResult

A frozen dataclass used by the provenance-aware internal search paths.

Fields:

- `score: float`
- `bound: str` — one of `"exact"`, `"lower"`, `"upper"`, `"invalid"`.
- `valid: bool`
- `source_type: str` — non-empty provenance label. Current implementations use
  `"search"`, `"quiescence"`, `"terminal"`, and `"heuristic"`. TT hits reuse
  the stored entry's existing provenance rather than introducing a separate
  `"tt"` source type.
- `source_depth: int | None`
- `move: object | None = None`

Invariants enforced in `__post_init__`:

- `bound` must be one of the four allowed values.
- `valid=True` requires `bound` in `("exact", "lower", "upper")`.
- `source_type` must be a non-empty string. The set of values in current use
  is not enforced as an enum.
- `source_depth` is a required field; `None` is a legitimate value meaning
  "no fixed depth provenance" (terminal, quiescence).

---

## 3. Bound inversion

`_invert_bound(bound)`:

    exact  -> exact
    lower  -> upper
    upper  -> lower
    other  -> invalid

Used when the parent converts a child result through a negamax ply.

---

## 4. Transposition table

### 4.1 Schema

A valid entry written by `_store_tt` contains:

    {
        "score": float,
        "depth": int,           # coverage depth
        "flag": str,            # "exact" | "lower" | "upper"
        "move": tuple | None,
        "valid": True,
        "provenance_version": CURRENT_TT_VERSION,
        "source_type": str,
        "source_depth": int | None,
    }

`source_depth` is provenance metadata. `depth` is coverage. They are not
interchangeable.

### 4.2 Constants

- `CURRENT_TT_VERSION = 1`
- `TT_MAX = 500000`

### 4.3 Read gate

An entry is reusable for a search at depth `D` only if all required keys
are present AND:

- `provenance_version == self.tt_version`
- `valid is True`
- `entry["depth"] >= D`

Missing keys make the entry unusable. No fallback defaults are applied to
provenance fields. `move` is optional.

`_tt_exact_eligible(result)` returns `True` only when:

- `result.valid is True`
- `result.bound == "exact"`
- `result.source_type != "quiescence"`

### 4.4 Write rules (`_store_tt`)

Signature:

    _store_tt(hash_key, score, depth, flag, move,
              valid=True, source_type=None, source_depth=None)

Guards:

- `valid is not True` -> no write.
- `source_type` not a non-empty string -> no write.

Replacement order:

1. No existing entry -> store.
2. `provenance_version` missing or mismatched -> replace, regardless of depth.
3. Any required key missing on the existing entry -> replace.
4. `old["valid"] is not True` -> replace.
5. `depth > old["depth"]` -> replace.
6. `depth == old["depth"]` and new `flag == "exact"` and old flag is not -> replace.
7. Otherwise -> retain.

LRU eviction uses `popitem(last=False)` when the table exceeds `tt_max`.

`source_depth` is stored verbatim, including `None`.

---

## 5. Principal variation search (`_pvs_result`)

### 5.1 Early exits

- Time up -> raise `SearchTimeout`.
- `alpha >= beta` -> return `SearchResult(alpha, "upper", False, "search", depth)`.
- Fifty-move rule -> terminal draw, `bound="exact"`, `source_type="terminal"`.
- Threefold repetition -> terminal draw, `bound="exact"`, `source_type="terminal"`.
- Twofold repetition -> `-50.0`, `bound="upper"`, `valid=False`, `source_type="heuristic"`.
- `depth <= 0` -> delegate to `_quiescence_result`.
- No legal moves -> checkmate (`-MATE_SCORE + ply`) or stalemate (`0.0`),
  both `bound="exact"`, `source_type="terminal"`.

### 5.2 TT probe

Uses the read gate described in section 4.3. On an exact hit eligible for
reuse, returns immediately. On a lower/upper hit, narrows `alpha`/`beta`
and returns the bound if `alpha >= beta`.

### 5.3 Move ordering and LMR

`_order_moves(board, moves, ply, tt_entry)` ranks by:

1. TT move (highest).
2. Capture gain (MVV-LVA style).
3. Killer moves at this ply.
4. History heuristic.
5. NN policy index.

For `i >= 4`, `depth >= 3`, and non-capture non-promotion moves:

- Reduced-depth null-window search with `reduction = 1 + (i - 3) // 6`.
- If it raises alpha, a full-depth null-window re-search is performed.

For other moves:

- First move (`i == 0`): full-window PVS.
- Subsequent moves: null-window, then full-window re-search on alpha raise.

### 5.4 Parent bound composition

Each child's `bound` is inverted via `_invert_bound` before the parent
classifies its own result.

Parent final classification:

- If the establishing child was not exact/valid, or a cutoff occurred,
  the parent cannot be exact.
- If `best_score <= alpha_orig` -> `"upper"`.
- If `best_score >= beta_orig` -> `"lower"`.
- Otherwise -> `"exact"`.

### 5.5 TT coverage depth

`best_child_source_depth` tracks the source depth of the establishing child.
On the accepted best move or a cutoff move, it is updated to the child's
`source_depth`. Final coverage depth is:

    tt_depth = min(depth, best_child_source_depth + 1)
        if best_child_source_depth is not None
        else depth

Provenance `source_depth` returned by the node is `depth` (immediate
mechanism). Only `tt_depth` reflects child coverage.

### 5.6 Storage and return

If the final result is valid, `_store_tt` is called with `tt_depth` as
`depth` and `source_depth` as provenance. If the final `bound` is `"exact"`
but the result is not eligible under `_tt_exact_eligible`, the store is
skipped.

`root_scores[best_move] = best_score` is written only when `ply == 0` and
`final_valid` is True.

---

## 6. Quiescence search (`_quiescence_result`)

- `q_nodes > MAX_Q_NODES` -> NN fallback, `bound="upper"`, `valid=False`,
  `source_type="heuristic"`.
- `ply > 12` -> same fallback.
- Not in check: evaluate stand-pat. If `stand_pat >= beta` -> `"lower"`.
  If `stand_pat > alpha`, raise alpha and set `best_bound = "exact"`.
- In check: stand-pat is disabled; all evasions are searched.
- Otherwise: captures only, up to 16 highest-policy captures.
- Children are searched with `(-beta, -alpha, ply + 1)`.
- Cutoff (`score >= beta`): `bound="lower"`.
- Final classification:
  - `best_bound is None` -> `"upper"`, `valid=True`.
  - Not `best_valid` -> `"upper"`, `valid=False`.
  - Otherwise -> `best_bound`, `valid=True`.

**Option B policy.** Normal selective quiescence results use
`source_type="quiescence"`. Resource/ply-limit NN fallbacks use
`source_type="heuristic"` and are non-authoritative.
`_tt_exact_eligible` excludes `source_type="quiescence"`, so normal
quiescence results cannot become TT-exact entries. Invalid heuristic
fallbacks are not stored.

`_quiescence_result` never calls `_store_tt` and never writes the TT
directly.

---

## 7. PV extraction (`_extract_pv`)

Walks TT entries from the current position. At each step:

- Entry must be present and contain all required keys.
- `provenance_version == self.tt_version`.
- `valid is True`.
- `flag == "exact"`.
- `move` is not `None`.
- `move` is legal in the reconstructed position.

Stops on any violation. Cycle guard via `visited` set of hashes. Maximum
walk length is 20 plies.

Empty PV is diagnostic, not an error. Only a non-empty PV whose first
move disagrees with the accepted root move is a hard failure
(`AssertionError`).

Because the root TT entry can be replaced by a later non-exact entry at
the same position, an accepted exact root iteration does not guarantee a
non-empty PV. This is intentional.

The accepted root move remains authoritative even when PV extraction stops
because a later TT entry is non-exact or otherwise fails the PV validity
gate. PV extraction must not silently substitute the returned best move
for a failed TT-derived PV.

---

## 8. Root authority

`SearchEngine.search()` maintains six accepted-root fields. They describe
one accepted authoritative iteration and are updated only when:

- `result.valid is True`
- `result.bound == "exact"`
- the returned move is legal

Fields:

- `accepted_root_best_move`
- `accepted_root_best_score`
- `accepted_root_depth`
- `accepted_root_scores` (Option A: `{move: score}` only)
- `accepted_root_source_type`
- `accepted_root_source_depth`

The public return tuple is derived from these fields. `current_depth` is
`accepted_root_depth`, not the last attempted depth.

If no iteration is accepted, the engine falls back to the first legal
move with score 0. This fallback does not populate accepted-root fields
and does not trigger the PV assertion.

`root_scores` is diagnostic accumulation. `sorted_root_scores` reflects
`accepted_root_scores` when an iteration was accepted, otherwise
`root_scores`.

---

## 9. Constants

- `MAX_DEPTH = 20`
- `MATE_SCORE = 30000`
- `TT_MAX = 500000`
- `NN_CACHE_MAX = 500`
- `NN_SCALE = 800`
- `TOP_POLICY_N = 32`
- `MAX_Q_NODES = 500`
- `CURRENT_TT_VERSION = 1`

---

## 10. Open items

- Evaluator perspective/score contract — OPEN.
- NN value-head validation — OPEN, downstream of the evaluator contract.
- The leaf combination `combined_eval(board) + int(val * NN_SCALE)` mixes
  a White-perspective static evaluation with an unverified NN value head.
  This is under investigation and no fix has been applied.

---

## 11. Non-goals

- MultiPV is not implemented. `accepted_root_scores` holds a single entry.
- TT statistics caching is not implemented; the TT is per-engine-instance
  and is discarded after each search.
- No persistent search-state or history beyond `self.history` and
  `self.killers`, both reset per search.


---

## 2026-09-27 — Live-source reconciliation

The 2026-09-11 body of this document predates the live session,
continuation, unlimited-search, recursive-PV, and newer quiescence work
now present in `search.py`. Sections 1, 6, 7, 9, and 11 are contradicted
by live source in the ways described below. The historical body is
preserved as recorded and is not edited in place.

### §1 — Public interface (superseded)

Live `SearchEngine.search` signature:

    search(board, time_limit=3000, depth=None,
           on_accepted_iteration=None, unlimited=False,
           continue_from=None)

Additional parameters relative to the historical signature:

- `on_accepted_iteration` — optional callback fired once for each
  accepted authoritative root iteration with `(depth, move, score, pv)`.
- `unlimited` — when `True`, the iteration sequence is not bounded by
  `MAX_DEPTH`.
- `continue_from` — continuation entry point. It must be an `int`, must
  be greater than zero, and must equal the engine's current
  `accepted_root_depth`. On success, `start_depth = continue_from + 1`.

The public return tuple is unchanged:
`(best_move, best_score, current_depth, nodes)`.

### §6 — Quiescence search (superseded in part)

The historical §6 describes a node-count cap (`q_nodes > MAX_Q_NODES`).
Live source instead applies a qsearch-relative depth cap.

Live termination and pruning rules:

- `q_depth > MAX_Q_DEPTH` → NN fallback with an invalid heuristic
  `SearchResult`; `MAX_Q_DEPTH = 6`.
- No `ply > 12` termination condition exists in the live
  `_quiescence_result` implementation.
- Stand-pat is evaluated only when the side to move is not in check.
- In check, all legal evasions are searched; there is no capture-only
  restriction in that case.
- When not in check, `board.generate_legal_captures()` supplies q-moves.
- If more than one capture is available, captures are sorted by the
  live MVV-LVA score and capped with `q_moves[:16]`.
- Delta pruning uses:
  `stand_pat + gain_cp + DELTA_MARGIN <= alpha`.
  `DELTA_MARGIN = 200`.
- A capture that gives check is exempt from that delta-pruning decision.
  `_capture_gives_check()` uses direct piece-code mutation rather than
  `make_move` + king-check test + `undo_move`.

The historical phrase “up to 16 highest-policy captures” is therefore
incorrect for the current implementation. The qsearch ordering is
MVV-LVA; NN policy is used elsewhere for normal move ordering.

### §7 — PV extraction (superseded)

The historical §7 describes a TT walk with a cycle guard and a 20-ply
maximum. Live source does not perform TT-walk PV extraction.

The live `_extract_pv()` implementation returns the current recursive
PV prefix stored in `self.pv_moves[0]` / `self.pv_length[0]`:

    if not self.pv_moves:
        return []
    if self.pv_length[0] <= 0:
        return []
    return list(self.pv_moves[0][:self.pv_length[0]])

During search, `_pvs_result()` maintains reusable per-ply PV rows in
`pv_moves[ply]` and `pv_length[ply]`. Only full-window PV nodes
(`is_pv_node`) participate in recursive PV construction; null-window
scout nodes are not copied into the PV path.

When a root iteration is accepted, `search()` snapshots the current PV
into `last_pv`. A later partial/timeout iteration does not replace that
accepted-iteration snapshot. The previously described TT-walking
implementation is not the current PV mechanism.

### §9 — Constants (superseded)

Live constants from `search.py` are:

    MAX_DEPTH = 20
    MATE_SCORE = 30000
    TT_MAX = 500000
    NN_CACHE_MAX = 5000
    NN_SCALE = 800
    TOP_POLICY_N = 32
    CURRENT_TT_VERSION = 1
    SEARCH_SEMANTIC_VERSION = 1
    PV_MAX = 1024
    MAX_Q_DEPTH = 6
    DELTA_MARGIN = 200
    _PIECE_CP = {'P':100,'N':320,'B':330,'R':500,'Q':900,'K':0}

Differences from the historical §9:

- `NN_CACHE_MAX` is 5000, not 500.
- `MAX_Q_NODES = 500` is not a live search constant and is not the
  current qsearch termination mechanism.
- `SEARCH_SEMANTIC_VERSION` is now explicit in the live search source.
- `PV_MAX`, `MAX_Q_DEPTH`, and `DELTA_MARGIN` are live constants omitted
  from the historical section.

### §11 — Non-goals (superseded in part)

The historical §11 states that there is no persistent search-state or
history beyond `self.history` and `self.killers`, both reset per search.
That statement is no longer complete.

Live source exposes:

    get_continuation_snapshot()
    restore_continuation_snapshot(snap)

The continuation snapshot contains these seven fields:

    best_move
    best_score
    depth
    scores
    source_type
    source_depth
    pv

`restore_continuation_snapshot()` validates that the input is a dict;
requires all seven keys; requires `depth` to be a positive `int`;
requires numeric `best_score` while rejecting bool; requires `scores`
to be a dict; and requires `pv` to be a list.

The runtime TT and NN cache are not serialized into this snapshot.
They remain per-engine-instance state. HOT continuation can therefore
retain TT/NN-cache/heuristic state by retaining the same engine, while
WARM/COLD continuation restores the accepted semantic frontier and then
continues with a rebuilt engine where applicable.

This continuation mechanism is distinct from a future persistent,
position-keyed semantic analysis-history cache. That future subsystem
would allow a later visit to the same compatible position to reuse a
validated prior result without requiring the original live session.

### Unlimited selected-position analysis

`MAX_DEPTH` is the bounded-search default, not the ceiling for browser
deep analysis. Live iteration selection is:

    if unlimited:
        depth_iter = itertools.count(start_depth)
    else:
        if depth is None:
            depth = self.max_depth
        depth_iter = range(start_depth, depth + 1)

Therefore `unlimited=True` produces an unbounded iterative-deepening
sequence. The browser analysis path invokes the search with
`time_limit=None` and `unlimited=True`, so selected-position analysis
continues until cancellation or an exceptional termination condition.

### Cancellation and accepted-depth authority

`stop_event` is a `threading.Event` on the engine instance. `_time_up()`
checks the stop event first; only when no stop has been requested does it
evaluate an optional wall-clock time limit.

The live search checks `_time_up()`:

- at the top of `_pvs_result()`;
- at the top of `_quiescence_result()`; and
- after each completed iterative-deepening depth in `search()`.

When cancellation is observed, `SearchTimeout` is handled by `search()`
and the engine returns the last accepted authoritative root result.
A partially searched later iteration does not overwrite the previously
accepted root or its `last_pv` snapshot.

The web layer propagates cancellation to the session and the owning
engine's `stop_event`; only the current session reservation owner may
signal the session stop path (`_owns_session`).

### Status

Sections 1, 6, 7, 9, and 11 of the historical body are contradicted or
incomplete relative to live source in the ways documented above. This
section records the current live contract while preserving the
historical body as recorded.

### Cross-references

- `docs/ARCHITECTURE.md` — search architecture and session/job layer.
- `docs/API_REFERENCE.md` — current job/session route surface.
- `docs/AUDIT_STATUS.md` — current verified state and open engineering gates.


## 2026-10-11 — Search telemetry counters

### Purpose and scope

The instrumentation-only `search.py` build records selected search
operations so performance work can be directed by measurements rather
than assumptions. These counters do not choose moves or alter search
decisions.

Verified instrumented source SHA at this stage:

`fa0a23df31c7202f23498f78d53111477fccde07592394e7f2aeb8593f809df5`

### Counter semantics

- `tt_probes`: transposition-table lookup attempts at the instrumented
  PVS lookup site.
- `tt_hits`: raw lookups that found an entry, before provenance checks.
- `tt_valid_hits`: entries accepted by the current provenance/version
  checks.
- `tt_depth_qualified_hits`: valid entries whose stored depth meets the
  requested search depth.
- `tt_exact_hits`: depth-qualified exact results accepted by the
  existing `_tt_exact_eligible` contract.
- `tt_cutoff_hits`: accepted TT bounds that cause an alpha-beta cutoff.
- `tt_inserts`: writes that introduce a previously absent TT key.
- `tt_replaces`: writes that overwrite an existing TT key.
- `tt_stale_replaces`: replacements caused by missing or mismatched
  provenance version; this is a subset of `tt_replaces`.
- `nn_policy_calls`: fresh neural evaluations requesting policy output.
- `nn_value_calls`: fresh value-only neural evaluations.
- `nn_cache_hits`: usable cached NN results returned without fresh
  evaluation.
- `nn_cache_misses`: requests that require fresh NN evaluation because
  a usable cached result was unavailable.
- `make_move_calls` and `undo_move_calls`: instrumented make/undo
  operations in the PVS and quiescence loops. Root verification,
  MultiPV helper, and search acceptance/fallback operations are excluded.
- `movegen_full_calls`: instrumented full legal-move generation in PVS
  and in-check quiescence.
- `movegen_capture_calls`: instrumented legal-capture generation in
  quiescence.
- `king_in_check_calls`: instrumented PVS terminal checks and
  quiescence entry checks. The LMR exemption check is excluded.
- `capture_gives_check_calls`: tests performed at the quiescence
  delta-pruning call site to avoid pruning captures that give check.
  This is not a count of every low-level attack test.
- `move_order_calls`: calls to the instrumented PVS move-ordering site.
- `total_q_nodes`: cumulative quiescence-node entries during the current
  `search()` call.

### Quiescence counter contract

The pre-existing `q_nodes` field retains its per-iteration semantics:
it is reset by the iterative-deepening loop. `total_q_nodes` accumulates
quiescence-node entries across iterations of the current search call.

At the end of a search, the expected invariant is:

`total_q_nodes >= q_nodes`

These fields measure different scopes of quiescence work. Neither is
expected to be close to the main-search `nodes` count.

### Instrumentation exclusions and validation

These counters deliberately cover selected call sites rather than
claiming to count every invocation of the corresponding board operation.
The exclusions above must be preserved if instrumentation is moved.

The fixed-depth comparison against the recorded pre-telemetry baseline
passed all nine fixtures with exact matches for move, score, accepted
depth, nodes, and per-iteration `q_nodes`. The tested make/undo counts
balanced, and the P5.15D and P5.15E search-contract checks passed.

This establishes behavior neutrality for the tested fixtures; it does
not establish zero runtime overhead, a general strength improvement, or
correctness for every chess position.

### Next measurement gate

Measure wall-clock overhead separately using the same fixtures, model,
and settings. Then profile the relevant operations before choosing an
optimization. Any search-decision change must rerun tactical/mate tests,
the fixed benchmark suite, and the applicable search-contract tests.


---

## 2026-11-10 — Live-source reconciliation (Patches 1, 2, 3, 4A, P5.15I, P5.15J)

This section records the Patches 1, 2, 3, 4A, P5.15I and P5.15J changes reflected in live `search.py` at SHA-256 `fee2145a1035b7a56db669ef549a27cabb46d8496b457f46203aaea179fad93c`. It supersedes specific claims in §§ 4.1, 4.2, 4.3, 4.4, 5.3, 6, 8 and 9. It does not supersede §§ 1, 2, 3, 5.1, 5.2, 5.4, 5.5, 7, 10 or 11. It adds one counter to the telemetry section dated 2026-10-11. All prior dated sections and the original body remain preserved as historical record.

### §4 — Transposition table (superseded)

**§4.1 Schema.** Live TT entries contain three additional fields beyond the schema in §4.1: `stored_halfmove`, `stored_track_rep`, `stored_rep_fp`, all set at `search.py:1395-1397` and required by the probe gate at `search.py:791-804`. Live entries written by `_store_tt` therefore have eleven fields, not eight.

**§4.2 Constants.** Live `CURRENT_TT_VERSION = 2` (`search.py:38`). Every occurrence of "`CURRENT_TT_VERSION = 1`" in the original §4.2, §9 and the 2026-09-27 §9 correction is superseded by this value.

**§4.3 Read gate — checks on the retrieved entry.**

The read path and the write path are distinct operations. §4.3 describes what happens during a TT probe, when a lookup has been issued by `_pvs_result` and the engine is deciding whether the retrieved entry can be trusted. §4.4 describes what happens during a TT write, when `_store_tt` is deciding whether a new candidate entry should replace an existing stored entry. The ten-key presence check in §4.3 stage 1 below is a *read* operation on the retrieved entry; the replacement conditions in §4.4 are *write* operations evaluated against the existing stored entry. Neither is redundant with the other, and neither should be described in terms of the other.

The live read path proceeds in stages:

1. **Key-presence gate.** The retrieved entry must contain all ten keys: `provenance_version`, `valid`, `source_type`, `source_depth`, `depth`, `flag`, `score`, `stored_halfmove`, `stored_track_rep`, `stored_rep_fp`. An entry missing any of these is not a candidate. (`search.py:791-804`.)

2. **Provenance-validity gate.** Among entries that passed stage 1, `provenance_version` must equal `self.tt_version` and `valid` must be `True`. Only then does the entry become `tt_entry`. (`search.py:806-811`.)

3. **Depth gate.** `tt_entry["depth"] >= depth` must hold. (`search.py:813`.)

4. **Context gate.** `_tt_context_compatible(tt_entry, board)` must return `True`. This check requires:
   - `entry["stored_track_rep"] == board.track_repetition`
   - `entry["stored_halfmove"] == board.halfmove_clock`
   - if `board.track_repetition` is `True`, `entry["stored_rep_fp"] == _rep_fingerprint(board)`

   (`search.py:814`, `1365-1374`.)

The counter `tt_context_rejections` increments only when a depth-qualified entry (stage 3 passed) is rejected at stage 4 (`search.py:858`). Entries rejected at stages 1 or 2 do not increment this counter — they are filtered before the depth gate is reached.

`_tt_context_compatible` uses `.get()` on the retrieved entry's fields, so a missing field yields `None`, which never equals any concrete value and therefore returns `False`. This path is unreachable in practice because stage 1 already required the three context fields to be present; the `.get()` calls are defence in depth, not a live rejection path.

**§4.4 Write rules (`_store_tt`) — replacement decisions on the existing stored entry.**

`_store_tt` (`search.py:1376-1451`) assembles a new candidate entry with all eleven fields set (`search.py:1386-1398`), then decides whether to write it by comparing against the existing stored entry at the same hash key. Each branch below tests the existing stored entry against the new candidate entry and stops on the first match:

1. Existing stored entry absent (`old is None`) — insert and increment `tt_inserts` (`search.py:1404-1406`).
2. Existing stored entry's `provenance_version` missing or not equal to `self.tt_version` — replace and increment `tt_stale_replaces` (`search.py:1407-1412`).
3. Existing stored entry missing any required provenance key (`source_type`, `source_depth`, `depth`, `flag`, `valid`, `score`) — replace (`search.py:1413-1421`).
4. Existing stored entry's `valid` is not `True` — replace (`search.py:1422-1423`).
5. Existing stored entry's `stored_halfmove` differs from the new candidate entry's — replace (`search.py:1424-1425`).
6. Existing stored entry's `stored_track_rep` differs from the new candidate entry's — replace (`search.py:1426-1427`).
7. New candidate entry's `stored_track_rep` is truthy and the existing stored entry's `stored_rep_fp` differs — replace (`search.py:1428-1432`).
8. New candidate entry's `depth` exceeds the existing stored entry's `depth` — replace (`search.py:1433-1434`).
9. New candidate entry's `depth` equals the existing stored entry's `depth`, new candidate's `flag == "exact"`, existing stored entry's `flag != "exact"` — replace (`search.py:1435-1440`).
10. Otherwise — retain the existing stored entry.

Whenever any branch replaces an existing stored entry, `tt_replaces` is incremented (`search.py:1442-1445`). LRU eviction runs after the write: if `len(self.tt) > self.tt_max`, one entry is removed via `popitem(last=False)` (`search.py:1447-1451`).

Rules 5, 6 and 7 are new since the original §4.4 text (Patch 4A context fields). Rules 1, 2, 3, 4, 8 and 9 are present in the original §4.4; rules 8 and 9 correspond to original rules 5 and 6, shifted by the three context rules inserted between rule 4 and the depth check.

The read/write distinction worth emphasising: stage 1 of §4.3 checks the retrieved entry for ten keys — a lookup-miss filter. Rule 3 of §4.4 checks the existing stored entry for six keys — a write-time replacement filter. Both are key-presence checks, but they apply to different entries in different directions. They are not equivalent and neither supersedes the other.

### §5.3 — Move ordering and LMR (superseded in part)

The move-ordering priority list at §5.3 (TT move, capture gain, killer moves, history heuristic, NN policy index) matches live `_order_moves` at `search.py:1110-1134`. The reduction formula `reduction = 1 + (i - 3) // 6` at §5.3 line 188 matches live code at `search.py:921`. Neither is superseded.

**LMR entry threshold.** §5.3 line 186 states the reduction applies "For `i >= 4`". Live code applies reduction only for `i >= 6` (`search.py:907`). This is the P5.15J LMR threshold 6 regression recorded in the roadmap dated 2026-10-11. `i >= 4` is superseded by `i >= 6`.

**Checking-move exemption (P5.15I).** A move that gives check is never LMR-reduced in live code. The check test runs after `make_move` at `search.py:917-919`, so the moving side's `board.white_turn` reflects the opponent and castling rook movement is modeled. This exemption is not documented in §5.3.

**En-passant capture classification.** The `is_capture` test at `search.py:890-898` treats an en-passant move as a capture (by checking the destination against `board.en_passant`), so en-passant moves are not LMR-reduced even though the destination square is empty. §5.3's "non-capture" condition implicitly assumes a non-empty destination; that assumption is superseded for en-passant.

### §6 — Quiescence search (superseded in part)

The four resource-limit and search-behaviour claims in the original §6 are superseded by the following.

**Resource limits.** Live `_quiescence_result` (`search.py:1197-1358`) uses `q_depth > MAX_Q_DEPTH` where `MAX_Q_DEPTH = 6` (`search.py:41`). The constants `MAX_Q_NODES` and a `ply > 12` cap do not exist in live source. Every fallback occurs at `q_depth > 6`, not by ply or node count.

**Mate at depth cap (Patch 2).** When `q_depth > MAX_Q_DEPTH`, the live code detects checkmate before returning the heuristic. It checks whether the side to move is in check; if so, it generates legal moves; if none exist, it returns `SearchResult(-MATE_SCORE + ply, "exact", True, "terminal", None)` (`search.py:1218-1231`). Only if the side is not checkmated does it return the heuristic fallback. This checkmate-at-cap behaviour is not described in the original §6.

**Capture ordering.** When not in check, the capture list is sorted by MVV-LVA (`search.py:1294-1301`), not by NN policy probability. The top sixteen captures are retained. When in check, all legal moves are searched and no sixteen-cap applies.

**Delta pruning (not previously documented).** When not in check, `search.py:1303-1320` prunes a capture whose material gain cannot raise alpha past the delta margin, but re-includes it if `_capture_gives_check` returns True. Delta pruning is therefore check-aware: a capture that gives check is never pruned, even if its immediate material gain is below the prune threshold.

The claims in §6 that remain accurate and are not superseded: `source_type="quiescence"` for selective results; `source_type="heuristic"` for resource fallbacks; `_tt_exact_eligible` excluding quiescence sources; `_quiescence_result` never calling `_store_tt` directly.

**Known open defect.** Live `generate_legal_captures` filters on a non-empty destination in both the in-check path (`board.py:640-642`) and the ordinary path (`board.py:646-649`), so en-passant captures are omitted from the quiescence capture list in both paths. If that generation were corrected, a secondary interaction remains: the delta-pruning victim lookup at `search.py:1305-1312` reads `board.board[move[2]][move[3]]`, which is empty for en-passant. This yields `victim_cp = 0` and therefore `gain_cp = 0`, so an en-passant capture whose true material gain would keep it above the prune threshold may nevertheless satisfy `stand_pat + gain_cp + DELTA_MARGIN <= alpha` and be pruned. The severity is position-dependent — it is an underestimate of the capture's value, not a guaranteed rejection. Correcting generation without correcting the victim lookup would leave this secondary defect. Both must be addressed together. This is recorded as open in `docs/AUDIT_STATUS.md` §3 and is not addressed by any patch described in this reconciliation section.

### §8 — Root authority (superseded)

**Two-case acceptance gate.** `_root_acceptable` (`search.py:181-194`) accepts an iteration under two distinct conditions, not one:

- **Case A (move-producing):** `result.valid` and `result.bound == "exact"` and `result.source_type in AUTHORITATIVE_ROOT_SOURCES` and `iteration_move` is present and legal.
- **Case B (terminal):** `result.valid` and `result.bound == "exact"` and `result.source_type == "terminal"` and no `iteration_move`.

The original §8 describes only the move-producing path and omits the terminal path.

**Authoritative source set.** `AUTHORITATIVE_ROOT_SOURCES = frozenset({"search", "terminal"})` (`search.py:48`) is the positive source gate for both root acceptance and TT-exact eligibility. The comment at `search.py:45-47` states: "only these source_type values may be treated as authoritative at the root or written to the TT as exact. quiescence and heuristic results are never authoritative." Sources outside this set (`"quiescence"`, `"heuristic"`) cannot populate accepted-root fields even when they return `bound="exact"`.

**Accepted-root fields.** The live `SearchEngine.search()` maintains seven accepted-root fields, not six: `accepted_root_best_move`, `accepted_root_best_score`, `accepted_root_depth`, `accepted_root_scores`, `accepted_root_source_type`, `accepted_root_source_depth`, and `accepted_root_multipv` (`search.py:97-103`). The seventh field is populated only when `multipv > 1` (`search.py:482-491`).

**P5.15I defensive verification (not previously documented).** When an iteration produces a mate-level root result that fails `_root_acceptable`, `search()` saves `self.tt`, replaces it with a fresh empty `OrderedDict`, calls `_root_full_window_research(board, iteration_move, depth)` for a full-window re-search on the candidate move, restores the original TT in a `finally` block, and — only if the re-search returns a score exactly matching the original result's score — promotes the iteration to accepted with `bound="exact"`, `source_type="search"`, `source_depth=depth` (`search.py:421-453`, `196-210`). Any non-exact, non-authoritative, or timeout result returns `None` and no promotion occurs. The verification gate fires only when `abs(result.score) > MATE_SCORE - MATE_PLY_BOUND` (`search.py:426`), so the mechanism is confined to mate-level scores.

**Non-authoritative fallback.** The fallback described in §8 remains accurate but is under-specified. In the `accepted_root_depth == 0` case, the live code additionally sets `self.last_pv = self._extract_pv(board)` after the fallback selection (`search.py:570`), which is not stated in the original §8. The fallback does not populate accepted-root fields and does not trigger the PV assertion.

### §9 — Relevant module-level constants (superseded)

The live module-level constants relevant to this document are:

| Constant | Value | Line |
|---|---:|---:|
| `MAX_DEPTH` | `20` | 27 |
| `MATE_SCORE` | `30000` | 28 |
| `MATE_PLY_BOUND` | `1000` | 29 |
| `TT_MAX` | `500000` | 34 |
| `NN_CACHE_MAX` | `50000` | 35 |
| `NN_SCALE` | `800` | 36 |
| `TOP_POLICY_N` | `32` | 37 |
| `CURRENT_TT_VERSION` | `2` | 38 |
| `SEARCH_SEMANTIC_VERSION` | `1` | 39 |
| `PV_MAX` | `1024` | 40 |
| `MAX_Q_DEPTH` | `6` | 41 |
| `DELTA_MARGIN` | `200` | 42 |
| `_PIECE_CP` | `{'P':100,'N':320,'B':330,'R':500,'Q':900,'K':0}` | 43 |
| `AUTHORITATIVE_ROOT_SOURCES` | `frozenset({"search", "terminal"})` | 48 |

`MATE_PLY_BOUND`, `SEARCH_SEMANTIC_VERSION`, `PV_MAX`, `_PIECE_CP` and `AUTHORITATIVE_ROOT_SOURCES` are not present in the original §9. `MAX_Q_NODES` is not a live constant and every reference to it in this document is superseded.

The comment block at `search.py:30-33` records that `MATE_PLY_BOUND = 1000` with the strict `>` comparison produces an effective threshold of "exactly `MATE_SCORE` minus the bound excluded", and that this value is intentionally aligned with the "`> 29000`" threshold used in `web_control.py` and `frontend/js/analysis.js`. Any future change to this bound therefore needs to be applied consistently across those three sites or the display and search thresholds will diverge.

### §10 — Open items (re-verified, unchanged)

The three open items in §10 remain accurate as of this reconciliation:

- **Evaluator perspective/score contract** — still OPEN.
- **NN value-head validation** — still OPEN, downstream of the evaluator contract.
- **Leaf combination** — the exact expression `combined_eval(board) + int(val * NN_SCALE)` is still present at `search.py:1233-1237` and `search.py:1255-1258`. No fix has been applied.

§10 requires no supersession.

### Telemetry (supplemental to 2026-10-11)

The 2026-10-11 telemetry section is accurate for the counters it enumerates. Patch 4A added one counter not covered there: `tt_context_rejections`, incremented at `search.py:858` when a depth-qualified TT entry fails `_tt_context_compatible` even though it passed the key-presence and provenance-validity checks. This counter distinguishes "the entry exists but belongs to a different repetition/halfmove context" from `tt_stale_replaces` (which counts overwrites of entries written under an older provenance version) and from `tt_valid_hits` (which counts only entries that passed all checks).

### Status

The patches and constants documented above reflect live `search.py` at `fee2145a…` as of this reconciliation. This section does not attest that the search implementation is correct, complete, or free of tactical defects. Known open issues recorded elsewhere — the en-passant capture omission in quiescence (`board.py:640-649` plus the secondary victim-lookup interaction at `search.py:1305-1312`), the non-atomic `set_fen` path (`board.py:801`), the `is_draw` claimable-vs-automatic ambiguity (`board.py:732-746`), and the two-version `fresh` parameter split between `/api/analyze` and `/api/jobs` (`web_control.py:3512` vs `1454-1491`) — remain open and are recorded in `docs/AUDIT_STATUS.md` §§3–11. This document describes how the current search implementation is structured, not that its structure is defect-free.
