# API_REFERENCE

**Project:** Chess AI
**Updated:** 2026-09-11
**Source of truth:** live `~/chess_ai/web_control.py`

This document lists the live Flask routes served by `web_control.py`.
For each route, the handler line number is given so the request/response
shape can be read directly from the source. This document does not
reproduce every request body and response field, because those shapes
must match the live code exactly, not a summary.

Default method is GET unless `methods=` is specified in the decorator.

---

## Endpoint index

| Method | Path | Category | Handler line |
|---|---|---|---|
| GET | `/api/position_analysis` | Position analysis | 309 |
| POST | `/api/provenance/normalize-source-username` | Provenance | 939 |
| GET | `/api/provenance/audit` | Provenance | 1091 |
| GET | `/api/stats/dashboard` | Statistics | 1100 |
| POST | `/api/move` | Game state | 1504 |
| POST | `/api/human_move` | Game state | 1529 |
| POST | `/api/legal_moves` | Game state | 1533 |
| GET | `/api/current_fen` | Game state | 1540 |
| POST | `/api/start_test_batch` | Batch testing | 1545 |
| GET | `/api/test_batch_status` | Batch testing | 1571 |
| GET | `/api/test_batch_games` | Batch testing | 1579 |
| GET | `/api/stop_test_batch` | Batch testing | 1584 |
| POST | `/api/analyze` | Engine analysis | 1763 |
| POST | `/api/jump` | Game state | 1811 |
| POST | `/api/pgn` | Game state | 1827 |
| GET | `/api/database_games` | Database browse | 1845 |
| GET | `/api/game/<int:game_id>` | Database browse | 1853 |
| GET | `/api/node_games` | Database browse | 1867 |
| POST | `/api/tree` | Opening tree | 1899 |
| POST | `/api/game_examples` | Opening tree | 1909 |
| GET | `/api/repertoire` | Repertoire | 1920 |
| POST | `/api/repertoire` | Repertoire | 1932 |
| DELETE | `/api/repertoire/<fen>` | Repertoire | 1946 |
| GET | `/api/repertoire/stats` | Repertoire | 1954 |
| GET | `/api/repertoire/export` | Repertoire | 1972 |
| POST | `/api/repertoire/import` | Repertoire | 1979 |
| GET | `/api/train/next` | Training | 1994 |
| POST | `/api/train/review` | Training | 2008 |
| POST | `/api/start_analysis` | Engine analysis | 2042 |
| GET | `/api/stop_analysis` | Engine analysis | 2058 |
| GET | `/api/analysis_status` | Engine analysis | 2064 |
| GET | `/api/reload_opening` | Opening tree | 2099 |
| POST | `/api/import_games` | Import | 2107 |
| POST | `/api/sync` | Sync | 2179 |
| GET | `/api/sync_state` | Sync | 2489 |
| POST | `/api/sync/start` | Sync | 2549 |
| GET | `/api/sync/status` | Sync | 2612 |
| POST | `/api/sync/cancel` | Sync | 2630 |
| GET | `/` | Frontend | 2650 |
| GET | `/<path:path>` | Frontend | 2654 |
| POST | `/api/start_live_game` | Live game | 2710 |
| POST | `/api/stop_live_game` | Live game | 2724 |
| GET | `/api/live_game_state` | Live game | 2732 |
| GET | `/api/stream_game` | Live game | 2752 |
| POST | `/api/analyze_sf` | Stockfish | 2859 |

---

## Engine analysis

### `POST /api/analyze` (line 1763)

Runs the shared `SearchEngine` under a module-level engine lock.

Response shape consumed by the current frontend:

    result = engine.search(board, time_limit=2000)
    move   = result[0]
    score  = result[1]
    depth  = result[2]
    nodes  = result[3]

The search result is the four-value tuple
`(best_move, best_score, current_depth, nodes)` described in
`SEARCH_ALGORITHM.md`. The engine lock prevents concurrent searches
on the shared analysis engine.

MultiPV handling:

- The endpoint may accept and echo MultiPV-oriented request data.
- Patch A does **not** implement authoritative MultiPV. `accepted_root_scores`
  holds a single accepted candidate. MultiPV is future work.
- Do not interpret API-level MultiPV parameters as evidence that the engine
  produces authoritative MultiPV output.

### `POST /api/start_analysis` (line 2042), `GET /api/stop_analysis` (line 2058), `GET /api/analysis_status` (line 2064)

Long-running analysis control. `analysis_status` reflects live analysis
state. Request/response shape: see handler.

### `POST /api/analyze_sf` (line 2859)

Stockfish analysis endpoint. Error handling was corrected in Phase-0
(B-033). Request/response shape: see handler.

---

## Game state (human play)

### `POST /api/move` (line 1504)

Apply a move to the live board.

### `POST /api/human_move` (line 1529)

Apply a human-player move. Endpoint added in Phase-0 (B-008).

### `POST /api/legal_moves` (line 1533)

Return legal moves for a given position.

### `GET /api/current_fen` (line 1540)

Return the current FEN. Phase-0 (B-006) fixed the handler to call
`to_fen()` rather than `get_fen()`.

### `POST /api/jump` (line 1811)

Jump to a specific position within the current game line.

### `POST /api/pgn` (line 1827)

Load or export PGN for the current game.

---

## Batch testing

- `POST /api/start_test_batch` (1545)
- `GET /api/test_batch_status` (1571)
- `GET /api/test_batch_games` (1579)
- `GET /api/stop_test_batch` (1584)

Batch test-batch control. Phase-0 added top-level exception handlers
to the background game threads (B-034) and bounded the SSE `fen_queue`
(B-024, B-031).

---

## Live game

- `POST /api/start_live_game` (2710)
- `POST /api/stop_live_game` (2724)
- `GET /api/live_game_state` (2732)
- `GET /api/stream_game` (2752)

Server-side live game state. Phase-0 fixed broken live-game locking
(B-013) and added a module-level `live_game_lock`.

---

## Position analysis

### `GET /api/position_analysis` (line 309)

Historical PositionAnalysis endpoint (P3/P4 work). Request/response
shape: see handler.

---

## Statistics

### `GET /api/stats/dashboard` (line 1100)

Read-only analytics dashboard data. Backed by the authoritative
production database.

---

## Opening tree

### `POST /api/tree` (line 1899)

Opening tree query.

### `POST /api/game_examples` (line 1909)

Return example games matching a position or opening.

### `GET /api/reload_opening` (line 2099)

Reload the in-memory opening tree from the authoritative source.

---

## Database browse

- `GET /api/database_games` (1845)
- `GET /api/game/<int:game_id>` (1853)
- `GET /api/node_games` (1867)

Read-only access to the authoritative game database.

---

## Repertoire

- `GET /api/repertoire` (1920)
- `POST /api/repertoire` (1932)
- `DELETE /api/repertoire/<fen>` (1946)
- `GET /api/repertoire/stats` (1954)
- `GET /api/repertoire/export` (1972)
- `POST /api/repertoire/import` (1979)

Repertoire storage and statistics.

---

## Training

- `GET /api/train/next` (1994)
- `POST /api/train/review` (2008)

Repertoire training flow.

---

## Import and sync

### `POST /api/import_games` (line 2107)

Import games into the authoritative database.

### `POST /api/sync` (2179), `GET /api/sync_state` (2489), `POST /api/sync/start` (2549), `GET /api/sync/status` (2612), `POST /api/sync/cancel` (2630)

Sync control and status. Backed by the `sync_jobs` and `sync_state`
tables in the production database.

---

## Provenance

### `POST /api/provenance/normalize-source-username` (line 939)

Normalization is loopback-only, transactional, and validates exact row counts before commit.

### `GET /api/provenance/audit` (line 1091)

Read-only provenance audit.

---

## Frontend

- `GET /` (2650)
- `GET /<path:path>` (2654)

Static frontend and SPA fallback.

---

## Compatibility notes

### Public search result contract

Production callers verified to consume the four-value search result:

- `uci_engine.py` — unpacks four values.
- `web_control.py` — indexes `result[0..3]` in `/api/analyze` and
  the position-analysis path.
- `parallel_search.py` — unpacks four values.

### Compatibility status

No live caller expects the old three-value `search()` return. Every
`SearchEngine.search(...)` call site outside `search.py` consumes the
four-value tuple `(move, score, depth, nodes)`.

The prior version of this section listed four callers as still using
the three-value form. By the time this was last inspected, all four had
already been migrated.

### Engine analysis contract

The four-value return and the accepted-root authority model are described
in `SEARCH_ALGORITHM.md`. API consumers must not rely on the diagnostic
`root_scores` accumulation; they must use the returned
`(move, score, depth, nodes)` tuple.

---

## Non-goals

- This document does not enumerate every request body and response field
  for every route. Handler line numbers are given so the shape can be read
  from source.
- MultiPV is not an authoritative engine capability. API-level MultiPV
  parameters are not proof of implementation.
- This document does not cover the historical archive's endpoints. Only
  routes served by the live `web_control.py` are listed.


---

## 2026-09-27 — Current route inventory (line-number correction)

The historical "Endpoint index" above was written against a `web_control.py`
that was approximately 1,200 lines shorter than the current live file. Every
handler line number in that index is stale. The historical index is preserved
as recorded and is not edited in place.

The table below is the current live inventory. All paths in the historical
index remain live; only their handler line numbers have changed. Five
job/session routes that were not present in the historical index are added.

Line numbers below refer to the `@app.route` decorator line in the current
live `web_control.py` (sha256 prefix `3fe5045be0705cbb`, 4,190 lines).

### Current route inventory

| Method | Path | Category | Decorator line |
|---|---|---|---|
| POST | `/api/jobs` | Jobs / sessions | 1147 |
| GET | `/api/jobs` | Jobs / sessions | 1188 |
| GET | `/api/jobs/<job_id>` | Jobs / sessions | 1198 |
| GET | `/api/session/<session_id>` | Jobs / sessions | 1206 |
| POST | `/api/jobs/<job_id>/cancel` | Jobs / sessions | 1216 |
| GET | `/api/position_analysis` | Position analysis | 1504 |
| POST | `/api/provenance/normalize-source-username` | Provenance | 2134 |
| GET | `/api/provenance/audit` | Provenance | 2286 |
| GET | `/api/stats/dashboard` | Statistics | 2295 |
| POST | `/api/move` | Game state | 2713 |
| POST | `/api/human_move` | Game state | 2738 |
| POST | `/api/legal_moves` | Game state | 2742 |
| GET | `/api/current_fen` | Game state | 2749 |
| POST | `/api/start_test_batch` | Batch testing | 2754 |
| GET | `/api/test_batch_status` | Batch testing | 2780 |
| GET | `/api/test_batch_games` | Batch testing | 2788 |
| GET | `/api/stop_test_batch` | Batch testing | 2793 |
| POST | `/api/analyze` | Engine analysis | 2972 |
| POST | `/api/jump` | Game state | 3020 |
| POST | `/api/pgn` | Game state | 3036 |
| GET | `/api/database_games` | Database browse | 3054 |
| GET | `/api/game/<int:game_id>` | Database browse | 3062 |
| GET | `/api/node_games` | Database browse | 3076 |
| POST | `/api/tree` | Opening tree | 3126 |
| POST | `/api/game_examples` | Opening tree | 3136 |
| GET | `/api/repertoire` | Repertoire | 3147 |
| POST | `/api/repertoire` | Repertoire | 3159 |
| DELETE | `/api/repertoire/<fen>` | Repertoire | 3173 |
| GET | `/api/repertoire/stats` | Repertoire | 3181 |
| GET | `/api/repertoire/export` | Repertoire | 3199 |
| POST | `/api/repertoire/import` | Repertoire | 3206 |
| GET | `/api/train/next` | Training | 3221 |
| POST | `/api/train/review` | Training | 3235 |
| POST | `/api/start_analysis` | Engine analysis (legacy shim) | 3269 |
| GET | `/api/stop_analysis` | Engine analysis (legacy shim) | 3290 |
| GET | `/api/analysis_status` | Engine analysis (legacy shim) | 3299 |
| GET | `/api/reload_opening` | Opening tree | 3323 |
| POST | `/api/import_games` | Import | 3331 |
| POST | `/api/sync` | Sync | 3403 |
| GET | `/api/sync_state` | Sync | 3713 |
| POST | `/api/sync/start` | Sync | 3773 |
| GET | `/api/sync/status` | Sync | 3836 |
| POST | `/api/sync/cancel` | Sync | 3854 |
| GET | `/` | Frontend | 3874 |
| GET | `/<path:path>` | Frontend | 3878 |
| POST | `/api/start_live_game` | Live game | 3934 |
| POST | `/api/stop_live_game` | Live game | 3948 |
| GET | `/api/live_game_state` | Live game | 3956 |
| GET | `/api/stream_game` | Live game | 3976 |
| POST | `/api/analyze_sf` | Stockfish | 4083 |

### Differences from the historical index

- Five job/session routes are added at the top of the table:
  `POST /api/jobs`, `GET /api/jobs`, `GET /api/jobs/<job_id>`,
  `GET /api/session/<session_id>`, and
  `POST /api/jobs/<job_id>/cancel`.
- Every handler line number in the historical index has shifted by roughly
  1,200 lines. The historical index was written against a version of
  `web_control.py` that predates the job/session subsystem.
- All other paths remain unchanged.

### The job/session subsystem

The five job/session routes are the modern execution path for long-running
analysis:

- `POST /api/jobs` creates or reattaches an analysis job (HTTP 201 for new,
  200 for reattach).
- `GET /api/jobs` and `GET /api/jobs/<job_id>` poll job status.
- `POST /api/jobs/<job_id>/cancel` requests cancellation; the handler
  delegates to `_cancel_job`.
- `GET /api/session/<session_id>` retrieves a live session from the registry,
  falling back to `_load_checkpoint` when the session is not in memory. This
  fallback is what allows a COLD session to be reattached after a Flask
  restart.

The browser frontend reaches these routes from `frontend/js/analysis.js`.

### Legacy analysis endpoints

`POST /api/start_analysis`, `GET /api/stop_analysis`, and
`GET /api/analysis_status` are a compatibility shim over the job subsystem.
They acquire a module-level legacy lock and delegate to the same
`_create_job` / `_start_analysis_job` / `_cancel_job` machinery used by the
job routes. They are not independent analysis paths, and no current frontend
file calls them.

### What this supersedes

- Every handler line number in the historical "Endpoint index" above.
- The "44 unique paths" count stated in `docs/ARCHITECTURE.md`.

### What this does not change

- The route paths themselves. Every path in the historical index remains
  live.
- The per-section descriptions below the index (Engine analysis, Game
  state, Batch testing, Live game, Position analysis, Statistics, Opening
  tree, Database browse, Repertoire, Training, Import and sync,
  Provenance, Frontend, Compatibility notes, Non-goals). Those sections
  name routes and describe behavior; they do not depend on the historical
  handler line numbers being exact.
- The four-value search-result contract described under Compatibility notes.
- The MultiPV non-goal statement.

### Status

Historical "Endpoint index" handler line numbers are contradicted by live
source. This section records the current live inventory. The historical
index is preserved as recorded and is not edited in place.

### Cross-references

- `docs/ARCHITECTURE.md` — route count and the job/session layer.
- `docs/AUDIT_STATUS.md` — current verified state.
