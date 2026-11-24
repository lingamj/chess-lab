# Chess AI

**Updated:** 2026-09-12

**Current project status: actively under engineering validation; not all
roadmap items or previously described automation behaviors are currently
production-verified.**

This README is an entry point. It is not the authoritative source for
any specific subsystem. Technical details are maintained in the
documentation index below.

---

## Authority hierarchy

For current behavior:

1. Live source and runtime verification — highest precedence
2. Reconciled subsystem documentation (`docs/*.md`)
3. This README summary
4. Historical archive (`~/chess_ai_historical_2026-08-23/`) — reference only

Live source and runtime verification take precedence over documentation.
Reconciled subsystem documentation takes precedence over this README
summary. Historical archive material is reference-only and does not
describe current behavior.

---

## Current Production Checkpoint (2026-08-23)

- schema_version: 5
- games: 14,916
- game_moves: 1,031,269
- import_batches: 67
- import_records: 23,496
- sync_jobs: 2
- canonical_players: 1
- player_aliases: 2
- source_username NULL: 0
- sync_state tree_dirty: 0 for both sources

Canonical identity:

- `jothi`
  - `jothilingam` → lichess
  - `jothi_lingam` → chesscom

This is a historical snapshot as of 2026-08-23. Current live state is
recorded in `docs/AUDIT_STATUS.md`.

---

## Documentation index

Authoritative documents. When a statement in this README disagrees with
one of these, the authoritative document wins.

| Purpose | Authority |
|---|---|
| Search contract | `docs/SEARCH_ALGORITHM.md` |
| Dataset contract | `docs/DATASET_FORMAT.md` |
| Training reality | `docs/TRAINING_GUIDE.md` |
| API surface | `docs/API_REFERENCE.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Neural network | `docs/NEURAL_NETWORK.md` |
| Roadmap | `docs/ROADMAP.md` |
| Current status | `docs/AUDIT_STATUS.md` |
| Defect history | `docs/BUG_TRACKER.md` |
| Changelog | `docs/CHANGELOG.md` |
| Code audit | `docs/CODE_AUDIT.md` |
| Final audit report | `docs/FINAL_REPORT.md` |
| Developer rules | `docs/DEVELOPER_GUIDE.md` |
| Safe operations | `docs/WORKFLOW.md` |
| Rejection/audit history | `docs/REJECTION_REPORT.md` |

---

## What the system is

A chess engine written in Python and NumPy, running on Android/Termux
and desktop Linux. Main components:

- `board.py` — board representation, move generation, hashing
- `move_helpers.py` — move index space (`NUM_MOVES = 20480`)
- `nn.py` — dual-head neural network (`DualNet`), pure NumPy
- `search.py` — PVS search with iterative deepening, TT, quiescence
- `uci_engine.py` — UCI protocol runtime
- `web_control.py` — Flask HTTP API and frontend
- `chess_ai.db` — authoritative production SQLite store; production
  database changes are restricted during audit and test phases.

Component-level description: `docs/ARCHITECTURE.md`.

---

## Search

Current public contract:

    search(board, time_limit=3000, depth=None)
        -> (best_move, best_score, current_depth, nodes)

The `SearchResult` provenance model, TT rules, and quiescence policy are
documented in `docs/SEARCH_ALGORITHM.md`.

Patch A root-result/provenance correction is runtime-validated. The
evaluator perspective contract (P5.17) and several downstream search
consumers remain open. Detail: `docs/SEARCH_ALGORITHM.md` and
`docs/AUDIT_STATUS.md`.

---

## Neural network

`DualNet` is a pure-NumPy dual-head network:

- 783 input features (piece placement, side to move, castling,
  en-passant, repetition, halfmove clock)
- Value head: `tanh`-bounded scalar
- Policy head: 20480 raw logits (no activation)

The value head's perspective contract is **OPEN** (`P5.17`). Whether the
value output is White-perspective, side-to-move-perspective, or another
convention is not established by the reviewed source.

Detail: `docs/NEURAL_NETWORK.md`.

---

## Model artifacts

The current tree contains multiple model artifacts:

- `chess_nn.pkl` — loaded by `uci_engine.py`; other consumers are documented in the model-artifact audit.
- `distilled_nn.pkl` — loaded by `web_control.py`.
- `chess_nn_master.pkl` — `train.py` default training output/promotion source; not established as the canonical runtime artifact.

There is no single canonical production artifact yet. This is tracked
as **OPEN** (`B-022`). Detail: `docs/TRAINING_GUIDE.md` and the B-022
status corrections in `docs/AUDIT_STATUS.md`, `docs/BUG_TRACKER.md`,
`docs/CHANGELOG.md`, `docs/ARCHITECTURE.md`, `docs/NEURAL_NETWORK.md`.

---

## Training and datasets

Multiple training entry points and dataset representations exist. Both
are documented in `docs/TRAINING_GUIDE.md` and `docs/DATASET_FORMAT.md`.
Neither document declares a single authoritative format, because the
current tree does not contain one.

A dataset can be labeled `format_version = 2` while bypassing the formal
schema validator. See `docs/DATASET_FORMAT.md`, "Validation-enforcement
gap". This is **OPEN**.

---

## Safe operations

Do **not** run during documentation or analysis phases:

- `train_auto.sh`
- `auto_sync_train.py`
- any `run_pipeline*.sh`
- production training, sync, or Flask restart
- opening-tree rebuild
- model activation

Rationale and the full safe/unsafe operation list:
`docs/WORKFLOW.md` and `docs/DEVELOPER_GUIDE.md`.

---

## Testing

The following bounded validation tools are used during the current
audit. Their latest verified results are recorded in
`docs/AUDIT_STATUS.md`. Do not infer a permanent pass state from this
list.

- `test_hash.py` — Zobrist hash consistency
- `test_move_index.py` — move index round-trip
- `audit_move_table.py` — complete move-table audit
- bounded perft (depth 1–4)

Do not run `benchmark.py` or `perft_test.py` at depth 5 without a
specific reason.

---

## Known open items

- B-022: canonical model artifact / lifecycle convergence
- P5.17: evaluator perspective / score contract
- P5.18A: NN technical/training validation
- Legacy flag-style `train.py` callers
- `train.py` custom-output / promotion inconsistency
- `train_auto.sh` stale-artifact replacement risk
- Dataset/model transaction separation (`run_training.sh`)
- Training automation failure/exit-status verification
- MultiPV root algorithm not implemented (P5.15E)

Full list: `docs/AUDIT_STATUS.md` and `docs/BUG_TRACKER.md`.

---

## Roadmap

See `docs/ROADMAP.md`. That document carries the historical phase model
and the current cross-cutting engineering tracks.

---

## Historical workspace separation (2026-08-23)

The project distinguishes between the active workspace and historical
material.

- Active workspace: `~/chess_ai/`
- Historical archive: `~/chess_ai_historical_2026-08-23/`

The historical archive contains rollback snapshots, obsolete
implementations, experimental/debug files, generated diagnostics, and
previous model/database versions.

Historical files are moved, not deleted, so rollback/reference material
remains available outside the active runtime workspace.

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

Historical archive contents must not be treated as active runtime
dependencies.


---

## 2026-09-27 — Live-source reconciliation

### Search contract (parameter list incomplete)

The historical “Search” section shows:

    search(board, time_limit=3000, depth=None)
        -> (best_move, best_score, current_depth, nodes)

The live signature also accepts:

    on_accepted_iteration=None, unlimited=False, continue_from=None,
    multipv=1

- `unlimited=True` replaces the bounded `range(start_depth, depth+1)`
  iteration with `itertools.count(start_depth)`. The browser analysis
  path uses `time_limit=None, unlimited=True` and continues until Stop.
- `continue_from` resumes a continuation; it must equal the engine's
  current `accepted_root_depth`, and the search then starts at
  `continue_from + 1`.
- `multipv` is a positive integer, default 1. It requests up to N
  exact authoritative root lines. There is no engine-imposed maximum.
  The number actually returned is bounded by the available legal root
  moves and by the search budget actually completed. The engine returns
  fewer lines rather than padding. `multipv=1` executes no MultiPV-
  specific work and is behaviorally equivalent to pre-P5.15E.

### Job/session subsystem

The system exposes a modern job/session layer over the engine:

- `POST /api/jobs` (200 reattach / 201 new), `GET /api/jobs`,
  `GET /api/jobs/<job_id>`, `POST /api/jobs/<job_id>/cancel`.
- `GET /api/session/<session_id>` with `_load_checkpoint` fallback.
- HOT / WARM / COLD session lifecycle.
- Checkpoint records written under `session_checkpoints/`.

The browser reaches these routes from `frontend/js/analysis.js`.

### Production checkpoint (field missing)

The 2026-08-23 checkpoint block records games, game_moves, import_batches,
import_records, sync_jobs, but omits `positions`. The current live count
is `positions: 892383`.

### Status

The historical body is preserved as recorded. This section records the
additional live facts above.
