# Chess AI — Audit Status
**Phase:** Phase-0 Static Defect Resolution
**Status:** Static remediation completed; runtime verification pending
**Recorded:** 2026-08-09

## Phase-0 Completion
The confirmed Phase-0 defects B-020 through B-034 have been applied.

### Defects Resolved
- **B-020** — `board.py`: repetition count restored during `undo_move`
- **B-021** — `web_control.py`: inverted checkmate result corrected
- **B-022** — model path unified to `chess_nn.pkl`
- **B-023** — shared engine analysis protected with an engine lock
- **B-024** — SSE queue bounded
- **B-025** — human batch polling uses `current_fen`
- **B-026** — aspiration-search timeout retains the last valid score
- **B-027** — `stop_event` initialized and cleared appropriately
- **B-028** — themed training data unpacking corrected
- **B-029** — MCTS selection sign corrected
- **B-030** — `nn.train()` accepts integer or one-hot policy targets
- **B-031** — `fen_queue` bounded
- **B-032** — infinite-search handling corrected
- **B-033** — Stockfish analysis error handling corrected
- **B-034** — background game-thread exception handlers added
- **B-035** — `search.py`: missing `import threading` – added during runtime verification

## Static Verification
| File | Result |
|---|---|
| `board.py` | PASS |
| `web_control.py` | PASS |
| `search.py` | PASS |
| `uci_engine.py` | PASS |
| `nn.py` | PASS |

## B-034 Transactional Verification
| Check | Result |
|---|---|
| Original structure verified | PASS |
| Candidate constructed in memory | PASS |
| Candidate compilation | PASS |
| Backup created | PASS |
| Actual file compilation | PASS |
| `run_test_batch` try/except | PASS |
| `run_human_game` try/except | PASS |
| `/api/analyze` boundary preserved | PASS |
| Final external `py_compile` | PASS |

## Runtime Verification
| Test | Status |
|---|---|
| Flask restart | PASS    |
| RV-01 | PASS    |
| RV-02 | PASS    |
| RV-03 | PASS    |
| RV-04 | PASS    |
| RV-05 | PASS    |
| RV-06 | PASS    |
| RV-07 | PASS    |
| RV-08 | PASS    |

## Current Baseline
**Static code remediation:** COMPLETE
**Python syntax verification:** COMPLETE
**Runtime verification:** COMPLETE

============================================================
 PRESERVED CONTENT: Original root-level AUDIT_STATUS.md content preserved
============================================================

# Chess AI — Audit Status
**Phase:** Phase-0 Static Defect Resolution
**Status:** Static remediation completed; runtime verification pending
**Recorded:** 2026-08-09

## Phase-0 Completion
The confirmed Phase-0 defects B-020 through B-034 have been applied.

### Defects Resolved
- **B-020** — `board.py`: repetition count restored during `undo_move`
- **B-021** — `web_control.py`: inverted checkmate result corrected
- **B-022** — model path unified to `chess_nn.pkl`
- **B-023** — shared engine analysis protected with an engine lock
- **B-024** — SSE queue bounded
- **B-025** — human batch polling uses `current_fen`
- **B-026** — aspiration-search timeout retains the last valid score
- **B-027** — `stop_event` initialized and cleared appropriately
- **B-028** — themed training data unpacking corrected
- **B-029** — MCTS selection sign corrected
- **B-030** — `nn.train()` accepts integer or one-hot policy targets
- **B-031** — `fen_queue` bounded
- **B-032** — infinite-search handling corrected
- **B-033** — Stockfish analysis error handling corrected
- **B-034** — background game-thread exception handlers added
- **B-035** — `search.py`: missing `import threading` – added during runtime verification

## Static Verification
The following files passed Python syntax compilation after the Phase-0 fixes:

| File | Result |
|---|---|
| `board.py` | PASS |
| `web_control.py` | PASS |
| `search.py` | PASS |
| `uci_engine.py` | PASS |
| `nn.py` | PASS |

## B-034 Transactional Verification
B-034 was applied using a transactional candidate-build procedure.

| Check | Result |
|---|---|
| Original structure verified | PASS |
| Candidate constructed in memory | PASS |
| Candidate compilation | PASS |
| Backup created | PASS |
| Actual file compilation | PASS |
| `run_test_batch` try/except | PASS |
| `run_human_game` try/except | PASS |
| `/api/analyze` boundary preserved | PASS |
| Final external `py_compile` | PASS |

## Runtime Verification

| Test | Status |
|---|---|
| Flask restart | PASS    |
| RV-01 | PASS    |
| RV-02 | PASS    |
| RV-03 | PASS    |
| RV-04 | PASS    |
| RV-05 | PASS    |
| RV-06 | PASS    |
| RV-07 | PASS    |
| RV-08 | PASS    |

## Current Baseline
The current state is therefore:

**Static code remediation:** COMPLETE
**Python syntax verification:** COMPLETE
**Runtime verification:** COMPLETE

No runtime result should be considered validated until RV-01 through RV-08 are executed and reviewed.


---

## 2026-08-23 Production Update

- schema_version: 5
- games: 14,916
- game_moves: 1,031,269
- import_batches: 67
- import_records: 23,496
- sync_jobs: 2
- source_username NULL: 0
- canonical identity: jothi
- tree_dirty: 0 for both sources

---

## 2026-09-11 — Current Status (Post-Patch-A)

This section is the authoritative current-status section for present-state interpretation.
Historical sections above remain preserved as recorded.

### Verified from live Termux

**Patch A — Search Provenance: COMPLETE**
- A–J changes applied to `search.py`.
- `SearchResult` with score, bound, validity, source type, source depth.
- Accepted-root authority fields bind returned move and score to one accepted authoritative iteration.
- TT provenance/version validation and replacement rules.
- Source-depth coverage handling for PVS/LMR results.
- Quiescence results excluded from exact-TT eligibility.
- PV extraction requires current version, valid, exact entry, and legal move.
- Scalar `_pvs()` / `_quiescence()` wrappers preserved.

**Validation layers**
| Layer | Status |
|---|---|
| Structural audit [0]–[13] | PASS |
| Production DB [14] | PASS (`integrity_check: ok`) |
| Backup [15] | PASS (checksum `5155d241…`, 382 lines) |
| Layer 1 — infrastructure | PASS |
| Layer 2 — real NN preflight | PASS |
| Layer 3 — real NN direct search | PASS |
| Layer 4 — targeted Patch-A contract tests | PASS |

**Production integration**
- All production `search()` callers verified four-value compatible:
  `uci_engine.py`, `web_control.py`, `parallel_search.py`.

**KQK root-provenance regression (`kq6/8/8/8/8/8/8/K7 b - - 0 1`)**
- Returned move and score remain paired with the same accepted root iteration at depths 1–4.
- Depths 5–6 correctly retain the last accepted depth-4 result when no deeper iteration is accepted.
- The historical stale root-move / score-provenance failure is not reproduced.

### Open — evaluator contract

**KQK depth-parity score anomaly — OPEN**
- Odd accepted depths ≈ +1160 / +1178; even accepted depths produce −0.0.
- Direct leaf trace confirms `combined_eval()` is White-perspective in the tested KQK positions.
- NN value head does not show a coherent material/perspective signal on the four KQK probes; a wider validation set is required before drawing a broader conclusion.
- No evaluator or search implementation change has been applied from this investigation.

**P5.17 evaluator perspective/score contract** — OPEN.
**P5.18 NN value-head validation** — OPEN, downstream of P5.17.

### Compatibility status

No live caller expects the old three-value `search()` return. Every
`SearchEngine.search(...)` call site outside `search.py` consumes the
four-value tuple `(move, score, depth, nodes)`.

The prior version of this section listed four callers as still using
the three-value form. By the time this was last inspected, all four had
already been migrated.

### Not established

- A queen-sacrifice defect has not been demonstrated.
- No search or evaluator fix has been applied for queen-sacrifice behavior.

### Documentation reconciliation

- `docs/CHANGELOG.md` updated 2026-09-11 to record Patch A, the KQK regression, the evaluator investigation, the non-production compatibility issues, and the current documentation status.
- Further documentation reconciliation pending, one file at a time.

### Preserved production checkpoint (2026-08-23)

- schema_version: 5
- games: 14,916
- game_moves: 1,031,269
- import_batches: 67
- import_records: 23,496
- sync_jobs: 2
- source_username NULL: 0
- canonical identity: jothi
- tree_dirty: 0 for both sources

---

## 2026-09-12 — B-022 status correction

The Phase-0 lists above record B-022 as "model path unified to
`chess_nn.pkl`". Live source inspection contradicts that record.

### Live evidence

Model-artifact consumers identified in the current tree:

| File | Line(s) | Artifact loaded |
|---|---|---|
| `web_control.py` | 22, 1109 | `distilled_nn.pkl` |
| `uci_engine.py` | 14, 41, 71, 114 | `chess_nn.pkl` |
| `merge_and_train.py` | 67 | `chess_nn_master.pkl` |

All other model-load sites identified in the current tree use
`chess_nn.pkl` or `chess_nn_master.pkl`.

`web_control.py:22` sets:

    MODEL_PATH = os.path.join(CHESS_DIR, "distilled_nn.pkl")

### Status

B-022 is **contradicted by live source**, not currently resolved.

Whether this is a regression (B-022 was applied and later reverted in
`web_control.py`) or a claim that was recorded without an applied
change is **not established** by the reviewed evidence.

The item remains **OPEN** pending determination of the intended
canonical artifact and a validated live-source correction.

### Historical record preserved

The Phase-0 lists above remain the historical record for their date.
They are not edited. This section records the current state.

### Cross-references

- `docs/TRAINING_GUIDE.md` — documents the model-artifact split.
- `docs/DEVELOPER_GUIDE.md` — records the same contradiction under
  "Current known contradiction".
- `docs/WORKFLOW.md` — records the safety implication for
  `train_auto.sh` and the other affected scripts.

### Effect on the Phase-0 fixed counts

The Phase-0 fixed count above is not recalculated by this section.
Recomputation is deferred until B-022's exact status (regression vs
never-applied) is classified.


---

## 2026-09-27 — Live-source reconciliation

### Duplicated Phase-0 block

The historical body of this file contains the entire Phase-0 section
twice: once as normal content and once under a “PRESERVED CONTENT”
banner. Both copies are preserved as recorded. Any reader should treat
them as the same historical record, not two independent claims.

### Runtime-verification contradiction

Both copies of the “Current Baseline” block show RV-01 through RV-08
as PASS, immediately followed by the sentence:

    No runtime result should be considered validated until RV-01
    through RV-08 are executed and reviewed.

That sentence predates the RV run and is contradicted by the table
above it. The correct status is the table: RV-01 through RV-08 passed.

### “Authoritative” self-label

The 2026-09-11 section self-describes as “the authoritative current-status
section for present-state interpretation”. The 2026-09-12 B-022 correction
below it supersedes part of that section, and `docs/CHANGELOG.md` records
a further 2026-09-19 correction. No single section is now the sole
authoritative current-status source.

### B-022 line drift

The 2026-09-12 B-022 correction cites:

    web_control.py | 22, 1109 | distilled_nn.pkl

The current live lines are 25 and 2304. The underlying claim is correct;
only the citations are stale.

### Status

The historical body is preserved as recorded. This section records the
current status without editing the historical sections.

### Cross-references

- `docs/API_REFERENCE.md` — current route inventory.
- `docs/SEARCH_ALGORITHM.md` — current search contract.
- `docs/ARCHITECTURE.md` — current architecture.


---

## 2026-11-10 — Live-source audit findings

This section records findings from the November 7–10 read-only Termux source and database inspections. It supplements earlier audit entries without rewriting historical findings.

### 1. Inspected source baseline

| File | SHA-256 |
|---|---|
| `search.py` | `fee2145a1035b7a56db669ef549a27cabb46d8496b457f46203aaea179fad93c` |
| `board.py` | `352c9c72003ede96da573593247348e10a9fc0e4a9f75451c6e9cec2534d1d1d` |
| `static_eval.py` | `8ef173d23288ad8e9873da84e96b306e3146ed3c3b4a6e35979281058a6eba6f` |
| `web_control.py` | `86887ae8d8b7cc4678d6e81e28aee9c0963cd2274338f4c40af583edc6d17643` |
| `database_v2.py` | `cee3d6e6badaf904c0c2c9a133632f20e8be69b1d402b235a80a15c7a9a067a6` |

These hashes identify the inspected versions. They do not establish that every function, caller or runtime behaviour has been tested.

### 2. Confirmed implementation and patch evidence

- Patch 0 NN cache key (`search.py:672-709`).
- Patches 1, 2, 3, 4A (`search.py:747-760`, `1205-1242`, `29`, `38` + `1365-1374`).
- P5.15I defensive mate verification (`search.py:421-453`, `196-210`).
- Unlimited path and Stop event (`search.py:295-296`, `596-601`, `108`).
- Patch 5c incremental material (`board.py:341-344, 386, 94-96, 161, 874-876`).
- Patch 5e king-square lookup (`static_eval.py:25-26`).
- `copy()` initialises `__new__`-constructed attributes (`board.py:146-162`).
- Legal-move generation preserves pending delta (`board.py:591-706`).

Source confirmations are not a substitute for re-running full regression tests after future changes.

### 3. Confirmed defect: en-passant in quiescence

`generate_legal_captures` filters on non-empty destination (`board.py:640-649`), so ep captures are omitted. `search.py:1305-1312` reads the victim from the destination square, which is empty for ep, so qsearch delta pruning rejects the move even if generation is fixed.

Both must be corrected together. Regression coverage must include: capture generation, make/undo, capture while in check, capture exposing the moving king, qsearch delta pruning of ep, both colours and edge files.

PVS move generation is unaffected.

### 4. Confirmed state-integrity defect: non-atomic FEN loading

`set_fen` assigns `self.board` at `board.py:801`, before completing validation of side-to-move, castling, en-passant, clocks, king counts and pawn ranks (`board.py:803-861`). If any check raises, `self.hash`, `_king_sq`, `_piece_code`, `material` and `position_counts` are left stale (`board.py:863-876`).

`_validate_fen_syntax` (`web_control.py:1557-1564`) delegates to `board.set_fen()`, so the atomicity defect reaches the HTTP layer. Any endpoint calling `_validate_fen_syntax` or `set_fen` on user-supplied FEN can leave a session object corrupted.

Validation must commit atomically. Tests must verify that rejected FENs leave the original board unchanged. FEN validation must also check ep rank, the pawn that advanced, halfmove consistency, counter ranges and legality — without rejecting valid ep targets merely because no adjacent pawn can capture.

### 5. Draw-rule classification: open

`is_draw()` (`board.py:732-746`) returns draw at halfmove clock 100 and repetition count 3 — claimable under FIDE, not automatic. It does not model the 75-move or fivefold automatic rules.

The search engine does not call `board.is_draw()`; its draw logic is inline in `_pvs_result` at `search.py:762-774`, with mate-precedence gating. `board.is_draw()` appears to be game-layer-only, but only `search.py`'s inline draw logic has been inspected. Game-layer call sites of `board.is_draw()` have not been traced.

This remains a candidate issue until game-layer call sites are identified, the search-vs-game distinction is established, and checkmate precedence is verified at those call sites. No game-rules defect is claimed by this audit.

### 6. Analysis persistence and resume

`_run_analysis_job` (`web_control.py:1060-1375`) uses unlimited search (`web_control.py:1331-1334`) and cancels via the shared stop event (`web_control.py:727-728`, `1050-1055`).

Continuation restores accepted-root state and resumes from accepted depth (`search.py:609-660`, `1326-1328`). It does not restore the RAM TT.

Persistence mismatch: new sessions are `unknown` (`web_control.py:211`); checkpoint-loaded sessions are `frontier_only` (`web_control.py:670`); `_persist_position_analysis` writes `session.history_context` (`web_control.py:590`); `_lookup_reusable_frontier` requires `unknown` (`web_control.py:839`).

Consequence: any analysis performed on a session resumed from checkpoint is persisted as `frontier_only` and becomes permanently unavailable to the reusable-frontier lookup. Because checkpoints are written on every accepted iteration (`web_control.py:1307`), resuming and analysing further grows the `frontier_only` pool with normal use.

The repair must define explicit compatibility semantics for full-history, frontier-only and FEN-only contexts rather than relabelling incomplete history as complete.

Persistence errors are swallowed by `_persist_position_analysis` (`web_control.py:605-606`). Add observable failure reporting and retry/recovery policy before relying on it as durable history.

### 7. Unlimited analysis verification status

`_run_analysis_job` calls the engine with `unlimited=True` (`web_control.py:1331-1334`). The browser Stop control reaches cancellation via `frontend/js/analysis.js:1033` → `504-510` → `web_control.py:1522` → `1026-1055`.

The database has 193 position-analysis records at TT v1, max depth 20. These records do not demonstrate that the current unlimited path has reached depths above 20.

A controlled runtime test must verify accepted iterations beyond depth 20, Stop responsiveness, checkpoint durability, browser reattachment and continuation after service restart.

### 8. Ownership and identity gap

The `games` table has `white`, `black` and `source_username` but no owner field. `canonical_players` and `player_aliases` exist; the two aliases (`jothilingam`/lichess, `jothi_lingam`/chesscom) both refer to `canonical_player_id = 1`.

This provides a basis for identity resolution but does not implement complete ownership separation. Required distinctions: dataset/import account, actual White player, actual Black player, user's canonical identity, user's colour, move actor and source provenance. All game-derived sections must use consistent backend ownership semantics.

### 9. Position-analysis schema and portability

The composite PK is eight fields: `position_id`, `model_sha256`, `eval_semantic_version`, `search_semantic_version`, `tt_semantic_version`, `multipv`, `analysis_mode`, `history_context`. It matches the upsert conflict target in `_persist_position_analysis` (`web_control.py:563-567`).

My Engine rows use an absolute path in `model_id` (`/data/data/com.termux/files/home/chess_ai/distilled_nn.pkl`). Model SHA-256 is the portable identity. Future reuse and migration must not depend on the absolute path remaining unchanged.

All 193 observed rows are TT v1 and ineligible for the TT v2 reusable-frontier query (`web_control.py:836, 848`).

### 10. Database baseline

| Measurement | Value |
|---|---:|
| Database file | 300,060,672 bytes |
| Games | 14,916 |
| Positions | 892,398 |
| Game moves | 1,031,269 |
| Position-analysis rows | 193 |
| `unknown` history context | 184 |
| `frontier_only` history context | 9 |
| Maximum accepted depth | 20 |
| Average accepted depth | 6.1658 |
| Integrity check | `ok` |

`schema_version` table exists; source declares `SCHEMA_VERSION = 6`; the on-disk table value was not printed and must be checked separately. `PRAGMA user_version = 0` is a separate setting.

The audit-script error attempting `SELECT id FROM position_analysis` was caused by the composite PK; it was an audit-script defect, not a database defect.

### 11. Additional architectural observations

- `_resolve_fresh_session()` (`web_control.py:873-882`) may seed a newly created session from a stored frontier (`pending_resume_source = 'COLD'`). A `/api/jobs` request without a `session_id` therefore may silently reuse stored analysis via this path, despite the caller not having requested continuation. Whether this is desired behavior for the quick-analysis path is unverified.
- `/api/jobs` (`api_create_job`, `web_control.py:1454-1491`) does not read a `fresh` parameter. The older `/api/analyze` path does (`web_control.py:3512`).
- `_start_analysis_job` calls `_cancel_other_analysis_jobs` (`web_control.py:1423`), cancelling other active analysis jobs before starting a new one. Current resource policy, not necessarily a defect.
- Checkpoints are written via temp file and `os.replace` on accepted iterations (`web_control.py:494-499`). Repeated write activity; explicit `fsync` per iteration was not established.
- MCTS remains outside the browser analysis path per the earlier source audit. Comparative strength remains unproven.
- Training, datasets, model writers, frontend consumers and the full dependency graph still require a dedicated audit.

### 12. Documentation baseline

The November 10 read-only inventory identified the sixteen Markdown documents and recorded their hashes and headings. `docs/ROADMAP.md` was fully printed and verified at `293cc6fd6ba59aaa129638a1ede3ed40e328b15385be05e24e93ef48ad723a91`. The other fifteen bodies were not printed in that inventory output. Hash and heading inventories are baseline evidence, not a full content audit.

### 13. Safety and implementation status

No source patch, production database migration, training run, service restart or file cleanup was performed by these read-only audits.

Implementation decisions must preserve production recovery options, retain existing backups, and require dedicated tests for every behaviour change. The live workspace remains authoritative; historical archives are not current source.

See `docs/ROADMAP.md` for the project phase structure and implementation order.
