# ARCHITECTURE


Browser frontend → Flask API → SQLite/workers/engine.

Termux is the runtime/development environment. The frontend is the normal control plane.

## Identity Layers
1. Historical game record: games.white / games.black
2. Source account: games.source / games.source_username
3. Canonical person: canonical_players / player_aliases

Historical names are not overwritten.


---

## Project Workspace Separation — 2026-08-23

The project now distinguishes between the active workspace and historical material.

- Active workspace: `~/chess_ai/`
- Historical archive: `~/chess_ai_historical_2026-08-23/`

The historical archive contains rollback snapshots, obsolete implementations,
experimental/debug files, generated diagnostics, and previous model/database versions.

Historical files are moved, not deleted, so rollback/reference material remains
available outside the active runtime workspace.

The active workspace retains:

- production source
- current frontend
- current documentation
- evaluation modules
- supported tests/scripts
- production database
- active models
- opening-tree/runtime artifacts
- supported training/import assets

Historical archive contents must not be treated as active runtime dependencies.

---

## 2026-09-11 — Current Architecture (Post-Patch-A)

This section records the current architecture as verified against the live
workspace. It does not replace the historical sections above.

### Layered view

    Browser frontend  ──►  Flask API (web_control.py)
                                │
                                ├──► SearchEngine (search.py)
                                │       └── DualNet (nn.py) ── chess_nn.pkl
                                │
                                ├──► Opening tree (opening.py, build_tree.py)
                                │
                                ├──► SQLite (chess_ai.db)
                                │
                                └──► Sync/import workers
                                        (pgn_learner.py, database_v2.py)

Termux is the runtime environment. The browser frontend is the normal
control plane.

### Component inventory

| Layer | File | Role |
|---|---|---|
| Board | `board.py` | Position representation, move generation, make/undo, hashing, repetition tracking |
| Move indexing | `move_helpers.py` | `NUM_MOVES = 20480`, move↔index round-trip, perft |
| Evaluation | `static_eval.py` | Static evaluation; `combined_eval(board)` is White-perspective in the validated investigation |
| Neural network | `nn.py` | `DualNet`; loads `chess_nn.pkl`; value head + policy head |
| Search | `search.py` | `SearchEngine`; four-value public return |
| Parallel search | `parallel_search.py` | Multi-board search wrapper; four-value consumer |
| UCI | `uci_engine.py` | UCI engine; four-value consumer |
| Flask API | `web_control.py` | HTTP endpoints and frontend serving |
| Database | `chess_ai.db` | Authoritative SQLite store |
| DB helpers | `database_v2.py` | Database/import/provenance support |
| PGN import | `pgn_learner.py`, `pgn_utils_v2.py` | PGN/game-import support |

### Search layer

The active search implementation is documented in `SEARCH_ALGORITHM.md`.
Its architecture, in brief:

- `SearchResult` carries explicit `score`, `bound`, `valid`, `source_type`,
  `source_depth`.
- Accepted-root authority fields (`accepted_root_*`) bind the returned move
  and score to one accepted authoritative iteration.
- The transposition table stores provenance fields
  (`provenance_version`, `source_type`, `source_depth`) and validates them
  on read and write.
- Quiescence results are excluded from exact-TT eligibility (Option B).
- PV extraction is provenance-gated.

Public contract:

    search(board, time_limit=3000, depth=None)
        -> (best_move, best_score, current_depth, nodes)

### API layer

The active API is served by `web_control.py`. The route surface is
documented in `API_REFERENCE.md`. 44 unique paths, dominated by:

- Engine analysis (`/api/analyze`, `/api/start_analysis`, `/api/analyze_sf`)
- Game state (`/api/move`, `/api/human_move`, `/api/current_fen`)
- Batch and live game control
- Opening tree and database browse
- Repertoire and training
- Import and sync
- Provenance and statistics

### Database layer

The authoritative database is `~/chess_ai/chess_ai.db`.
Production checkpoint values currently verified:

- `schema_version = 5`
- `games = 14916`
- `game_moves = 1031269`
- `import_batches = 67`
- `import_records = 23496`
- `sync_jobs = 2`
- `source_username NULL = 0`
- `canonical_identity = jothi`

`PRAGMA integrity_check` returns `ok`.

### Identity layers

The three-level identity model is preserved:

1. Historical game record (`games.white` / `games.black`)
2. Source account (`games.source` / `games.source_username`)
3. Canonical person (`canonical_players` / `player_aliases`)

Historical names are never overwritten.

### Engine / evaluator status

- Patch-A search provenance: implemented and validated.
- Evaluator perspective/score contract: OPEN.
- NN value-head validation: OPEN.
- Strength benchmark: NOT ESTABLISHED.
- MultiPV: not implemented.

The leaf evaluation path currently combines:

    combined_eval(board) + int(val * NN_SCALE)

`combined_eval` is White-perspective. The NN value head's perspective
is not yet established. This is the subject of the open evaluator
investigation; no fix has been applied.

### Workspace rule

The live workspace `~/chess_ai/` is authoritative for current behavior.
The historical archive `~/chess_ai_historical_2026-08-23/` is reference and
rollback material only. Files existing in the archive are not active
runtime dependencies.

### Non-goals

- MultiPV is not implemented in the current engine.
- TT state is not persisted as a cross-search statistics/cache artifact.
- Position-wise historical analytics is planned but not yet part of the
  implemented runtime architecture.

### Documentation cross-reference

- `SEARCH_ALGORITHM.md` — search contract.
- `API_REFERENCE.md` — HTTP route surface.
- `AUDIT_STATUS.md` — current verified state and open items.
- `ROADMAP.md` — historical phases plus the current cross-cutting tracks.

---

## 2026-09-12 — Model-artifact correction

The "2026-09-11 — Current Architecture" section above presents a
single Neural-network line in the layered view and a single
Neural-network row in the component inventory, both naming
`chess_nn.pkl` as the model. Live source inspection shows two runtime
consumers with different artifacts.

### Live evidence

| Consumer | Line | Artifact loaded | Role |
|---|---|---|---|
| `web_control.py` | 22, 1109 | `distilled_nn.pkl` | web runtime |
| `uci_engine.py` | 14, 41, 71, 114 | `chess_nn.pkl` | UCI runtime |

All other model-load sites identified in the current tree use
`chess_nn.pkl` or `chess_nn_master.pkl`.

### What this supersedes

- In the "Layered view", the line `DualNet (nn.py) ── chess_nn.pkl`
  describes the UCI path only. The web runtime uses `distilled_nn.pkl`.
- In the "Component inventory", the row
  ``| Neural network | `nn.py` | `DualNet`; loads `chess_nn.pkl`; value head + policy head |``
  describes the UCI path only.

### What this does not change

- `nn.py` itself is unchanged. `DualNet` loads whatever path the caller
  provides.
- The historical sections above the "2026-09-11" appendix are not
  affected.
- The rest of the 2026-09-11 appendix — search layer, API layer,
  database layer, identity layers, engine status, workspace rule,
  non-goals, documentation cross-reference — is not affected by this
  correction.

### Status

The single-artifact presentation is **contradicted by live source**.
The canonical-artifact decision remains **OPEN**.

### Cross-references

- `docs/AUDIT_STATUS.md` — "2026-09-12 — B-022 status correction".
- `docs/BUG_TRACKER.md` — "2026-09-12 — B-022 status correction".
- `docs/CHANGELOG.md` — "2026-09-12 — B-022 status correction".
- `docs/TRAINING_GUIDE.md` — documents the model-artifact split.
- `docs/DEVELOPER_GUIDE.md` — "Current known contradiction".
- `docs/WORKFLOW.md` — safety implication for `train_auto.sh`.


---

## 2026-09-27 — Live-source reconciliation

Sections of the 2026-09-11 appendix below predate the live job/session
subsystem and the continuation-search work now present in `search.py` and
`web_control.py`. The historical body is preserved as recorded and is not
edited in place.

### Job/session layer (missing from the layered view)

The historical layered view shows the Flask API talking directly to a
`SearchEngine`, the opening tree, SQLite, and sync/import workers. Live
source adds a job/session layer between the API and the engine:

- `AnalysisSession` objects live in a registry (HOT) or as checkpoints
  on disk (COLD).
- `POST /api/jobs` creates or reattaches a job; `GET /api/jobs`,
  `GET /api/jobs/<job_id>`, `POST /api/jobs/<job_id>/cancel` poll and
  cancel; `GET /api/session/<session_id>` retrieves a live session and
  falls back to `_load_checkpoint` for a COLD session.
- `_run_analysis_job` acquires `_CPU_HEAVY_SEMAPHORE`, restores the
  continuation snapshot if the engine was released, and invokes
  `engine.search(board, time_limit=None, unlimited=True,
  on_accepted_iteration=_cb, continue_from=continue_from)`.
- A 1 Hz heartbeat publishes `job.progress['searching']` and
  `job.progress['session_accepted_root']`.
- `_cb` writes `session.accepted_root` and calls `_save_checkpoint`
  on each accepted root iteration.

The frontend reaches these routes from `frontend/js/analysis.js`.

### Search layer (parameter list incomplete)

The historical search-layer paragraph shows:

    search(board, time_limit=3000, depth=None)

The live signature also accepts:

    on_accepted_iteration=None, unlimited=False, continue_from=None

See `SEARCH_ALGORITHM.md` “2026-09-27 — Live-source reconciliation”
for the semantics of these parameters.

### Route count

The historical API layer states “44 unique paths”. The current live
inventory is 50 method/path rows (48 distinct path strings, with
`/api/jobs` and `/api/repertoire` each carrying two methods). See
`API_REFERENCE.md` “2026-09-27 — Current route inventory” for the
full table.

### Model-artifact correction (line drift)

The 2026-09-12 correction section cites:

    web_control.py | 22, 1109 | distilled_nn.pkl

The current live lines are 25 and 2304. The underlying claim (web runtime
loads `distilled_nn.pkl`; UCI runtime loads `chess_nn.pkl`) is correct.
Only the cited line numbers are stale.

### Status

The historical body is preserved as recorded. This section records the
current live architecture and corrects the specific items above.

### Cross-references

- `docs/SEARCH_ALGORITHM.md` — search contract and continuation semantics.
- `docs/API_REFERENCE.md` — current route inventory.
- `docs/AUDIT_STATUS.md` — current verified state.
