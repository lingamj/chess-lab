# Chess AI – Product Roadmap
**Project:** Personal Chess AI

## Current Baseline
**Phase-0 audit completed:** 2026-08-09
Static remediation is complete. Runtime verification has passed.

## Phase-0 – Audit & Stabilisation
- Resolve B-020 through B-034
- Preserve the earlier B-001 through B-019 fixes
- Complete Python syntax verification
- Execute RV-01 through RV-08

## Phase-1 – Personal Game Database
- Import 3,000+ games from Lichess / Chess.com / PGN
- Store metadata, positions, and move sequences
- Search and filter by opening, opponent, date, result

## Phase-2 – Game Analyzer
- Engine analysis for every move
- Mistake classification
- Tactical theme detection
- “Why was this bad?” explanations

## Phase-3 – Personal Intelligence
- Recurring mistake detection
- Strength/weakness profile
- Opening performance analysis
- Position-type analysis
- Time-management analysis

## Phase-4 – Personal Trainer
- Automatic exercise generation from mistakes
- Spaced repetition
- Repertoire drilling
- Progress tracking

## Phase-5 – Neural Learning
- Train NN on personal games
- Versioned model management
- Automated Elo testing
- Promote only stronger models

## Phase-6 – Continuous Improvement Loop
- Auto-import new games
- Auto-analyse and update profile
- Scheduled model retraining
- Full regression test suite

============================================================
 PRESERVED CONTENT: Original docs/ROADMAP.md content preserved
============================================================

# ROADMAP
## Phase-0 Audit & Stabilisation
Static defect remediation B-020 through B-034 has been completed.
Runtime verification RV-01 through RV-08 has passed.
See `AUDIT_STATUS.md` for the current verification baseline.


---

## 2026-08-23 Current Checkpoint

Completed:
- Phase-0 Audit & Stabilisation
- Sync accounting repair
- Zero-move handling
- Statistics & Database Insights: B1, B1.1, B2, B3, B4
- D1 Data & Provenance Normalization: D1.0 through D1.4

Current schema/version:
- schema_version: 5
- canonical_players: 1
- player_aliases: 2
- source_username NULL: 0

Pending:
- D1.5 Documentation Update
- Position-wise Analytics
- Repertoire Intelligence
- Game Analysis
- Personal Intelligence
- Training
- Neural Learning Pipeline
- Android/Product Hardening


---

## 2026-08-23 — Workspace Separation

Active workspace: `~/chess_ai/`
Historical archive: `~/chess_ai_historical_2026-08-23/`

The archive is preserved for rollback/reference and may contain older
implementations, experiments, and generated diagnostics. It is not an active
runtime dependency.

---

## 2026-09-11 — Current Status (Post-Patch-A)

This section is a current engineering checkpoint, not a replacement of the historical
Phase-0 through Phase-6 plan above. Historical roadmap phases remain preserved as recorded.

### Closed since 2026-08-23

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

### Open — no project-wide readiness claim

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

---

## 2026-09-11 — Full Roadmap Extension

The historical Phase-0 through Phase-6 roadmap above is preserved as the historical
product roadmap. The sections below make currently verified engineering state and
additional future work explicit. A feature is not considered complete merely because
it appears in this roadmap. Completion requires implementation and appropriate
validation evidence.

### How to read this roadmap

Product phases describe what the finished chess product should do.
Engineering tracks describe the cross-cutting work needed to make that product real.
Validation gates describe what must be proven before downstream work can be
considered complete.

### Phase-0 — Audit & Stabilisation

Historical objective
- Resolve B-020 through B-034.
- Preserve B-001 through B-019 fixes.
- Complete syntax verification.
- Execute RV-01 through RV-08.

Current state
- The documented Phase-0 remediation and RV-01 through RV-08 runtime verification are complete.

### Phase-1 — Personal Game Database

Product objective
- Create the authoritative personal chess-game data foundation.

Scope
- Lichess / Chess.com / PGN import.
- Persistent game metadata.
- Persistent positions and moves.
- Search/filter by opening, opponent, date, and result.
- Duplicate-game prevention.
- Game/source identity and provenance.
- Canonical player identity.
- Import accounting and synchronization state.
- Authoritative SQLite storage.
- Database-backed opening-tree generation.
- Canonical-position aggregation.
- Transposition handling.
- Full-FEN lookup compatibility.
- Database-tree / PGN-tree validation.

Related data work
- Data and provenance normalization.
- Statistics and database insights.
- Position-wise historical analytics.
- Repertoire statistics.

Current state
- The authoritative database foundation exists and the current production database has been validated.
- Remaining work must distinguish the existing database foundation from the complete original Phase-1 product goal and from future position-wise analytics.

### Phase-2 — Game Analyzer

Product objective
- Provide trustworthy move-by-move and game-level analysis.

Scope
- Engine analysis for every move.
- Mistake classification.
- Tactical theme detection.
- "Why was this bad?" explanations.
- PositionAnalysis.
- Candidate-move comparison.
- Game reports.
- Analysis history.

Engineering dependency
- PositionAnalysis and downstream analysis should not be considered fully complete while material questions about evaluator/search score semantics remain unresolved.

### Phase-3 — Personal Intelligence

Product objective
- Turn analyzed games into persistent personal chess intelligence.

Scope
- Recurring mistake detection.
- Strength/weakness profiling.
- Opening performance.
- Position-type performance.
- Time-management analysis.
- Historical trend analysis.
- Repertoire intelligence.
- Position-specific historical performance.

### Phase-4 — Personal Trainer

Product objective
- Convert mistakes, weaknesses, and repertoire knowledge into personalized training.

Scope
- Automatic exercise generation.
- Mistake-based exercises.
- Tactical exercises.
- Repertoire drilling.
- Spaced repetition.
- Progress tracking.
- Weakness-targeted training.
- Training-history feedback.

### Phase-5 — Neural Learning

Product objective
- Build a controlled and measurable neural-learning pipeline.

Scope
- Train the neural network on personal-game data.
- Validate training targets.
- Maintain model versions.
- Maintain checkpoints.
- Resume training where supported.
- Evaluate candidate models.
- Automated strength/Elo testing.
- Promote only validated improvements.
- Preserve rollback capability.
- Maintain reproducible training lineage.

Current engineering gates
- Evaluator perspective/score contract — OPEN.
- NN value-head validation — OPEN.
- Strength benchmark — NOT ESTABLISHED.

The presence of a loadable model does not by itself establish that the complete
neural-learning pipeline is correct or that a newly trained model is stronger.

### Phase-6 — Continuous Improvement Loop

Product objective
- Connect importing, analysis, learning, validation, and model promotion into a controlled improvement cycle.

Scope
- Auto-import new games.
- Auto-analyze new games.
- Update personal statistics/profile.
- Generate training data.
- Scheduled model training.
- Candidate-model evaluation.
- Automated regression validation.
- Model promotion only after passing gates.
- Rollback and recovery.

### Engineering Track A — Search & Engine Correctness

This track supports Phases 2–6.

Patch A — Search Provenance
- Status: COMPLETE and validated.

Verified areas include:
- Provenance-aware `SearchResult`.
- Accepted-root authority.
- TT provenance/version handling.
- TT replacement rules.
- Source-depth coverage.
- Quiescence exact-TT exclusion.
- PV provenance and legality checks.
- Scalar compatibility wrappers.
- Four-value public `search()` result.

Remaining engine work
- Evaluator perspective/score contract.
- NN value-head validation.
- Strength benchmark.
- Future MultiPV work.
- Remaining non-production caller compatibility.

### Engineering Track B — Statistics & Database Insights

Foundation
- Historical checkpoint records completion of the documented Statistics & Database Insights work B1, B1.1, B2, B3, and B4.

Future extension — Position-wise historical repertoire analytics
- canonical position identity;
- side-to-move identity;
- game-level position contributions;
- move-level statistics;
- selected-player perspective;
- explicit result semantics;
- transposition-aware aggregation;
- authoritative DB-derived statistics;
- independence from opening-tree cache;
- API exposure.

Status: PLANNED / VALIDATION PENDING.

### Engineering Track C — API & Frontend Integration

Scope
- Keep backend/API contracts synchronized with engine behavior.
- Keep frontend analysis and statistics backed by authoritative data.
- Remove stale result-shape assumptions.
- Complete database/frontend integration.
- Maintain compatibility during engine refactors.

Compatibility debt
- Compatibility status for `SearchEngine.search(...)` consumers is tracked in `API_REFERENCE.md`.

### Engineering Track D — Repertoire Intelligence

Scope
- Opening repertoire extraction.
- Position popularity.
- Personal move statistics.
- Win/draw/loss statistics.
- Historical comparison.
- Transposition-aware repertoire aggregation.
- Repertoire gaps.
- Repertoire recommendations.

Status: PLANNED / dependent on validated position-wise statistics.

### Engineering Track E — Data & Provenance

Scope
- Game identity.
- Source identity.
- Player identity normalization.
- Canonical position identity.
- Historical occurrence identity.
- Deterministic result interpretation.
- Import provenance.
- Data lineage.
- Reproducible derived statistics.

The historical D1.0–D1.4 checkpoint remains preserved; later work should be recorded
separately rather than rewriting that historical checkpoint.

### Engineering Track F — Training Infrastructure

Planned items
- Versioned master dataset.
- Resume training from checkpoints.
- Preserve optimizer state where appropriate.
- Dataset validation.
- Reproducible training.
- Model checkpoint management.
- Automated candidate-model comparison.
- Model-selection policy.

Status: PLANNED unless separately validated.

### Engineering Track G — Search Performance & Strength

Planned items
- Time-management calibration.
- Move-overhead calibration.
- Search-performance optimization.
- Improved quiescence behavior.
- Efficient incremental neural evaluation / NNUE-style investigation.
- Endgame tablebase integration where practical.
- Fixed-condition engine-strength benchmarking.
- Automated Elo tracking.

Status: PLANNED / NOT ESTABLISHED unless individually validated.

### Engineering Track H — Advanced Learning

Future research direction
- Self-play reinforcement learning.
- AlphaZero-style experimentation.
- Distributed self-play across multiple devices.
- Automated model selection.
- More advanced neural-learning pipelines.

Status: FUTURE / NOT ADOPTED AS CURRENT IMPLEMENTATION.

### Engineering Track I — Platform & Product

Planned Android/product work
- Android-native/polished UI.
- Termux/runtime hardening.
- Packaging and deployment reliability.
- Runtime recovery.
- Resource-management improvements.
- User-facing training and analysis experience.

Status: PLANNED.

### Engineering Track J — Documentation & Maintainability

Scope
- Keep README synchronized with implementation.
- Keep API reference synchronized with endpoints.
- Keep architecture documentation synchronized with actual modules.
- Keep search documentation synchronized with Patch-A behavior.
- Maintain training/dataset documentation.
- Preserve historical checkpoints.
- Clearly distinguish historical, current, planned, and deferred work.

Status: IN PROGRESS.

### Current engineering gates

These are gates rather than additional product phases.

- Search provenance/root-result correctness — PASS.
- Evaluator perspective/score contract — OPEN.
- NN value-head validation — OPEN.
- Strength benchmark — NOT ESTABLISHED.
- PositionAnalysis readiness — DEPENDENT on sufficient engine/evaluation stabilization.
- Automated model promotion — DEPENDENT on validated targets, models, benchmarks, and regression protection.

### Historical project-planning items recovered from earlier documentation

These longer-term ideas remain historical/planning material unless separately adopted:
- Versioned unified/master datasets.
- Resume training with optimizer state.
- Quiescence improvements including checks.
- Move-overhead and time-management calibration.
- NNUE-style efficient updates.
- Syzygy tablebase probing.
- Distributed self-play.
- Automated Elo/model selection.
- AlphaZero-style self-play reinforcement learning.
- GPU-accelerated training.
- Opening-book learning from engine analysis.
- Full Android application.

These items must not be interpreted as completed features merely because they appear
in historical documentation.

### Live / historical workspace rule

The active runtime workspace is authoritative for current behavior.
Historical archives are reference and rollback material only.
A file or capability existing in an archive does not establish that it is part of the
active runtime.

### Overall project status

Verified complete
- Documented Phase-0 remediation scope.
- RV-01 through RV-08.
- Current database foundation and integrity baseline.
- Patch-A search provenance/root-result work.
- Verified production four-value search integration.
- Current documentation reconciliation work already completed for the reconciled files.

Open
- Evaluator perspective/score contract.
- NN value-head validation.
- Strength benchmarking.
- Position-wise analytics implementation and validation.
- Remaining non-production search callers.
- Future MultiPV/API integration.
- Remaining frontend/database integration.

Planned
- Repertoire intelligence.
- Personal trainer expansion.
- Training infrastructure improvements.
- Advanced self-play / reinforcement-learning work.
- Search performance improvements.
- Tablebase research.
- Android/product hardening.
- Long-term continuous-improvement automation.

Not established
- Entire project is bug-free.
- Entire engine is strength-validated.
- NN value-head semantics are fully established.
- Every Phase-1 through Phase-6 objective is complete.

### Documentation reconciliation

- `docs/CHANGELOG.md` updated 2026-09-11.
- `docs/AUDIT_STATUS.md` updated 2026-09-11.
- `docs/BUG_TRACKER.md` updated 2026-09-11.
- `docs/CODE_AUDIT.md` updated 2026-09-11.
- `docs/FINAL_REPORT.md` updated 2026-09-11.
- Further documentation reconciliation pending, one file at a time.


---

## 2026-09-27 — Live-source reconciliation and product-alignment supplement

This section supplements the 2026-09-11 Full Roadmap Extension and the
2026-08-23 checkpoints above. It does not replace them. It records decisions
established during the 2026-09-27 documentation reconciliation and aligns the
existing Phase and Track structure with those decisions. A feature appearing
in this section is not evidence that it is implemented; the status distinctions
used elsewhere in this document still apply.

### Documentation reconciliation status

Eleven documents were reconciled against live source during the 2026-09-27
pass and installed under the fail-closed pattern (patch-specific backup,
prefix-preserving append, verification, rollback-protected install):

- `docs/SEARCH_ALGORITHM.md`
- `docs/API_REFERENCE.md`
- `docs/ARCHITECTURE.md`
- `README.md`
- `docs/AUDIT_STATUS.md`
- `docs/FINAL_REPORT.md`
- `docs/BUG_TRACKER.md`
- `docs/CODE_AUDIT.md`
- `docs/CHANGELOG.md`
- `docs/NEURAL_NETWORK.md`
- `docs/DEVELOPER_GUIDE.md`

This ROADMAP.md section is the last item of that pass. Each historical document
body remains preserved as recorded; the 2026-09-27 sections appended to those
documents record current live state without editing the historical text.

### Analysis Reuse Contract

Two distinct reuse scenarios must not be collapsed:

**Live-session continuation** — resuming an analysis session that exists or
existed. Three levels are implemented:

- HOT — same `SearchEngine` instance retained. TT, NN cache, heuristics,
  accepted root, and `last_pv` are preserved in memory.
- WARM — continuation snapshot restored onto a rebuilt engine. TT and NN
  cache are rebuilt; accepted frontier is restored.
- COLD — checkpoint on disk across a process or server restart. The session
  is reconstructed and the accepted frontier is restored.

**Persistent semantic Analysis History** — revisiting a semantically
compatible position in a later, unrelated session. This layer is not yet
implemented. It is a position-keyed store of validated accepted analyses,
distinct from the raw process-local transposition table.

The reuse contract is:

    Same semantic position
    + compatible model identity / hash
    + compatible evaluation semantic version
    + compatible search semantic version
    + compatible MultiPV / analysis mode
    → reuse accepted frontier (HOT / WARM / COLD / persistent)
    Otherwise
    → historical informational result only
    → reanalyze

A bounded RAM LRU supplements the persistent store for recently visited
positions. Neither the RAM LRU nor the persistent store should be a dump of
the raw transposition table. The transposition table remains a process-local
search structure.

Rationale: the transposition table carries provenance fields, coverage depth,
bound type, replacement semantics, and semantic-version assumptions that are
valid only inside one search configuration. Persisting it would be large,
fragile, and semantically ambiguous. A validated semantic analysis record is
smaller, self-describing, and safely reusable.

### Interactive vs whole-game analysis

Selected-position analysis:

    start → depth 1 → depth 2 → … → depth N → … → user presses Stop
    → last fully accepted iteration remains authoritative

The browser analysis path already invokes the engine with
`time_limit=None, unlimited=True`. `MAX_DEPTH` is the bounded-search default,
not a ceiling for this mode. This behavior is live.

Whole-game analysis:

    game → position extraction → deduplicate against Analysis History
    → queue only required work → per-position budgeted search
    → save accepted frontier → next position

Whole-game analysis is a separate, queued workflow. It is not implemented.
The current dispatch set contains only `'analysis'`. A whole-game job type
does not exist. This workflow must reuse compatible historical analyses
rather than re-search every position, and must support cancellation, resume,
and a shared resource budget.

One unbounded search per browser session remains the interactive resource
boundary. Whole-game analysis must not launch unlimited searches on every
position simultaneously.

### Position intelligence and Opening Tree

Current state:

- `POST /api/tree` returns `{fen, eco, opening, moves}` only.
- `GET /api/position_analysis` returns historical canonical-position
  statistics and reserves an `"engine": None` slot that is currently empty.
- `_build_position_analysis` performs database aggregation only; it does not
  invoke the engine.

Target state: every canonical position in the Opening Tree becomes a
position-intelligence node carrying:

- Historical — games, wins, draws, losses, score percentage.
- Personal — games involving the user, results, move frequency.
- Combined — aggregate dataset statistics.
- Engine — score, depth, best move, PV, MultiPV, model identity,
  search/eval semantic versions, timestamp.
- Analysis history — deepest accepted depth, last analyzed, resumable
  frontier, compatibility for reuse.
- Repertoire — personal frequency, opponent frequency, alternatives,
  gaps.
- Coach — mistakes, opportunities, recurring patterns, evidence.

The `"engine": None` slot already anticipated this. Filling it is
implementation work, not a schema change.

### Engine capability gaps

MultiPV, configurable Hash, and Threads currently exist only in the Stockfish
integration path. Our own `SearchEngine` does not expose these capabilities.

- MultiPV must be a root-search algorithm, not N independent full searches.
  `MultiPV = 1` must remain on the fastest normal path. The current
  accepted-root model holds one accepted line; generalizing it to a set of
  accepted root lines is a data-model change.

**2026-10-02 correction:** P5.15E implemented root MultiPV inside
`SearchEngine.search(...)`. The engine now accepts `multipv` and exposes
ranked exact lines via `sorted_root_scores`; in-memory accepted-root
state is no longer single-line. P5.15F.1 forwarded `multipv` from
`/api/analyze`; the capability is reachable on the quick path. The
artificial `[1, 8]` upper bound was removed from both the engine
validation and the API clamp. Configurable Hash and Threads remain
unimplemented for our engine. Persistence deliberately remains
`multipv=1` (see Analysis Reuse Contract above).
- Hash must be user-facing in MB, not an internal entry count. Diagnostics
  must expose capacity, occupancy, probe/hit/exact-hit/cutoff-hit rates,
  replacement count, stale/version rejection count, and hashfull.
- Threads must be staged: (1) root parallelism, (2) synchronized shared TT
  with preserved publication semantics, (3) advanced shared-tree parallelism
  only when measurement justifies it. Thread-local by default: killers,
  history, continuation heuristics, recursive PV state.

Application concurrency and search parallelism are distinct. A scheduler must
prevent `4 browser jobs × 4 engine threads = 16 uncontrolled workers`.

### Search performance methodology

The engine's optimization objective is maximum useful search depth and
analysis strength per unit of wall-clock time. NPS is an important measurement
but not the sole acceptance criterion.

Acceptance order for search-algorithm changes:

1. Correctness
2. Analysis quality
3. Tactical strength
4. Depth at fixed time
5. Wall-clock performance
6. NPS
7. Memory and CPU efficiency

Acceptance order for pure implementation optimizations:

1. Correctness
2. Identical or compatible result
3. Wall-clock improvement
4. NPS improvement

A change that lowers raw NPS but produces a materially deeper accepted
iteration at the same wall-clock budget is not automatically rejected.

Rejected experiments are recorded with the specific invariant they failed
(correctness, overhead, insufficient end-to-end benefit, search regression,
memory cost, or speed), not labeled solely "NPS rejection."

Before further optimization, the engine must report per-search telemetry:

- total NPS, total nodes, q-nodes
- TT probes, hits, usable hits, exact hits, cutoff hits, replacements,
  stale/version rejects, occupancy, hashfull
- NN calls, NN cache hits/misses, NN evaluation time, feature-generation time
- make/undo time, attack-detection time, move-generation time
- move-ordering time
- evaluation time
- time per accepted iterative-deepening iteration

The historical profiling evidence showed substantial time in NN evaluation,
board make/undo, attack detection, move generation, and evaluation work. The
next optimization must be measurement-driven.

### NN direction and learning pipeline

Long-term destination:

- Evaluator is fully NN-only.
- Handcrafted / static evaluation is a transitional compatibility layer and
  is not the permanent architecture.

Two parallel tracks:

- Track A — search depth, efficiency, and strength. Immediate priority.
- Track B — NN quality, training, and NN-only transition. Long-term
  continuous work.

The two tracks do not block each other. Search optimization continues while
NN strength work proceeds.

NN learning from games and test mode is collect-only during play:

    play / test → collect positions, moves, scores, PVs, results
    → learning queue → validated dataset → candidate NN
    → regression → strength testing → promote / reject

The active model must never be silently modified from live play or test mode.
The current live tree does not implement a learning collection pipeline.

Model identity must be explicit. The current runtime artifacts
(`chess_nn.pkl`, `chess_nn_master.pkl`, `distilled_nn.pkl`) have identical
sizes and different SHA-256 hashes; filename-based identity is not sufficient
for safe promotion or rollback.

### Browser-first operating model

Long-term, the browser is the normal control plane for:

- Import, sync
- Selected-position analysis, whole-game analysis
- Opening Tree, statistics
- Coach, training
- Testing, benchmarking
- Datasets, models, candidate validation
- Regression, strength tests
- Promotion, rollback
- Monitoring, cancellation, resume
- Reports

Termux becomes primarily a service layer: activation, maintenance, recovery,
diagnostics.

This is a product architecture requirement, not UI polish.

### Rejection ledger

A new document, `docs/REJECTION_LEDGER.md`, is planned. It is distinct from
`docs/REJECTION_REPORT.md`, which is a historical import-event report and
remains preserved as such.

Each ledger entry records:

- experiment
- purpose
- correctness result
- quality result
- performance result
- memory cost
- decision
- conditions for reconsideration

A rejected implementation is a statement about one implementation under
tested conditions. It is not a permanent ban on the underlying idea. A future
implementation with a different design and better evidence can revisit any
rejected idea, provided the reason for the original rejection is addressed.

### Mapping to existing phases and tracks

The clarifications above attach to the existing structure rather than
replacing it:

| Existing area | 2026-09-27 clarification |
|---|---|
| Phase 2 — Game Analyzer | HOT / WARM / COLD / persistent semantic analysis history; unlimited interactive analysis; whole-game queued analysis |
| Phase 2 / Track B | Position-wise engine intelligence as a canonical node property |
| Phase 2 / Track C | Browser job/session execution, cancellation, resume |
| Phase 3 / Track D | Opening Tree as canonical position intelligence |
| Track E | Semantic provenance and invalidation |
| Track G | Search depth/time optimization, telemetry, NPS plus analysis quality |
| Phase 5 / Track F | Collect-only learning pipeline, candidate model lifecycle, model registry |
| Phase 5 | Eventual NN-only evaluation |
| Track I | Browser-first product control plane |
| Track J | Rejection ledger and continued documentation synchronization |

No new product phases or tracks are introduced. The existing structure remains
the roadmap.

### Updated project status

Verified live from the 2026-09-27 audit:

- Search provenance and accepted-root authority.
- Unlimited selected-position analysis via the browser job path.
- HOT / WARM / COLD session lifecycle and checkpoint restore.
- Browser job/session routes and frontend callers.
- Database integrity and production invariants.
- Documentation reconciliation of the eleven documents listed above.

Partially implemented or missing:

- Persistent semantic Analysis History.
- Opening Tree engine-score integration.
- Whole-game queued analysis.
- Our engine MultiPV, configurable Hash, Threads.
- Search-pipeline telemetry.
- Collect-only learning pipeline.
- Candidate model lifecycle and model registry.
- NN-only evaluator.
- Shared resource scheduler.
- Fully browser-owned product workflows.

Not established:

- All bugs fixed.
- Full engine strength validation.
- NN value-head semantics.
- Complete Phase-1 through Phase-6 product completion.

### Implementation order

Following this documentation pass, the recommended engineering sequence is:

1. Search-pipeline telemetry (instrumentation only; no behavior change).
2. Fixed benchmark suite for reproducible comparison.
3. Search quality and depth optimization, using the acceptance order above.
4. Persistent semantic Analysis History and RAM LRU.
5. Opening Tree engine-score integration.
6. MultiPV (root search).
7. Configurable Hash in MB with diagnostics.
8. Threaded search with resource scheduling.
9. Whole-game queued analysis with reuse.
10. Collect-only learning pipeline.
11. Candidate NN lifecycle and regression.
12. NN-only evaluator transition.
13. Browser-first completion of remaining workflows.

This order is not rigid. NN strength work proceeds in parallel from step 2
onward and does not block search optimization.

### Rejection-history clarification

The historical rejection record is not a list of ideas that are permanently
forbidden. Rejections recorded prior to this date reflect the specific
implementation, evidence, and acceptance criteria in force at the time. The
underlying concepts may be revisited under a materially different
implementation, new evidence, or changed acceptance criteria. This
clarification is consistent with the acceptance-order rules above.

### Cross-references

- `docs/SEARCH_ALGORITHM.md` — current search contract, continuation
  primitives, unlimited mode.
- `docs/API_REFERENCE.md` — current route inventory, job/session subsystem.
- `docs/ARCHITECTURE.md` — job/session layer, search layer, model-artifact
  correction.
- `docs/AUDIT_STATUS.md` — current verified state and open engineering gates.
- `docs/TRAINING_GUIDE.md` — model-artifact split.
- `docs/DEVELOPER_GUIDE.md` — current known contradiction.

## 2026-10-02 — Post-P5.15E / F.1 status update

This section records state changes since the 2026-09-27 supplement. It
does not rewrite the earlier sections. Where they disagree, this section
is authoritative for the date it records.

### Closed since 2026-09-27

- **P5.15E** — root MultiPV implemented inside `SearchEngine.search(...)`.
  Bounded re-search of bound-only candidates; exact-bound ranking; NN
  ordering only, never exclusion. 20/20 construction-site contract
  intact. Full regression green.
- **P5.15F.1** — `multipv` forwarded from `/api/analyze` into the engine.
  Runtime gate 6/6 PASS at 2026-10-02.
- **MultiPV cap removal** — the artificial `[1, 8]` bound removed from
  `search.py` validation and `web_control.py` clamp. `multipv` is now a
  positive int with no engine-imposed maximum. Returned line count is
  bounded by legal root moves and by the search budget actually
  completed.

### Implementation order — status correction

The 2026-09-27 "Implementation order" listed MultiPV as step 6, after
telemetry, benchmark, optimization, and Analysis History. Actual
execution diverged: MultiPV engine (P5.15E) and quick-path wiring
(P5.15F.1) were completed first. Steps 1, 2, 3, 4, 5 remain open.
Nothing is wrong with the original order as a design suggestion. It is
simply not the order that was taken, and this section records that so
the roadmap does not read as if the sequence above were executed as
written.

### Live-audit findings (2026-10-02)

- **Browser model mismatch.** `web_control.py:25` loads `distilled_nn.pkl`;
  `benchmark.py:9` and most trainers use `chess_nn.pkl`. Same architecture
  size, different SHA-256. Prior NPS/tactical/self-play figures were
  measured against `chess_nn.pkl`, not the browser-served model.
- **Live-model write risk.** Four trainers (`multi_train.py`,
  `incremental_train.py`, `train_incremental.py`, `time_train.py`) call
  `nn.save('chess_nn.pkl')` directly, bypassing the master/active split.
  Live-search model immutability is not enforced by code.
- **Value-target heterogeneity.** At least three target semantics are
  in use (game-result, blended, score-derived); `dataset_schema.py`
  validates UCI structure but not value semantics.
- **`parallel_search.py` unsuitable as a threading baseline.** Plain
  dict as shared TT (incompatible with `OrderedDict.popitem(last=False)`),
  no real SMP cooperation, result selection ignores completed depth.
- **MCTS is isolated.** `mcts.py` reachable only from `arena.py` and
  `match_vs_stockfish.py`; not on the browser path.
- **No browser NN training route.** `'training'` is declared in
  `VALID_JOB_TYPES` but has no dispatcher. All NN training is shell-only.
- **Orphan analysis UI.** `#eval-display` / `#best-move` / `#pv-line` /
  `#analyze-btn` belong to the retired `combined.js` path. Not loaded.
  Cleanup candidate, not a design surface.

### Still open (unchanged from the 2026-09-27 supplement)

- Search-pipeline telemetry (instrumentation only).
- Fixed benchmark suite.
- Search quality / depth optimization.
- Persistent semantic Analysis History RAM LRU.
- Opening Tree engine-score integration.
- Deep-job MultiPV integration (P5.15F.2).
- Quick-path revisit / reuse.
- Whole-game queued analysis with reuse and scheduling.
- Configurable Hash in MB with diagnostics.
- Threaded search with resource scheduling.
- Collect-only learning pipeline.
- Candidate NN lifecycle and regression.
- NN-only evaluator transition.
- Browser-first completion of remaining workflows.
- Board / UI visual quality (BUI-1..BUI-6).
- `docs/REJECTION_LEDGER.md` (planned; still absent).


---

## 2026-10-11 — P5.15I mate-path correction and harness verification

This dated supplement records verified work completed after the
2026-10-02 checkpoint. It supplements historical entries; it does not
replace prior roadmap phases or establish project-wide readiness.

### Verified closed

- TT mate-score normalization was corrected for positive and negative
  mate scores and verified by store/retrieval contract tests.
- Checking moves are exempted from late-move reductions.
- A rejected mate-level root result can be checked with a full-window
  re-search using a temporary empty TT. The ongoing search TT is restored
  in a `finally` block, and promotion uses `dataclasses.replace` so
  `SearchResult` validation is rerun.
- The P5.15D AST contract remains at 20 `SearchResult` construction
  sites; P5.15D and P5.15E pass.
- The verified mate-in-3 fixture
  (`6k1/5pp1/8/8/8/8/5PP1/1R1Q2K1 w - - 0 1`)
  returned `b1b8`, score 29997, and accepted depths 3, 4, and 5.
- Four mate-in-1 regression positions passed with score 29999.
- The targeted TT score-retrieval contracts passed.
- The three quiet-position controls retained their tested move, score,
  and reported depth.
- `run_tests.sh` now reports success only after the full chained suite
  succeeds and exits nonzero when a test fails.
- The full suite passed on 2026-10-11, including hash tests, move-index
  checks, the search-result contract tests, benchmark, and perft through
  depth 5.

### Recorded live-source baseline

- `search.py`: `961765fce5e3029d342df3be6b1b5a0c1737a5cbc8bdd456f88763d8d5e210a4`
- `run_tests.sh`: `4f0021bf26eb649b1ecc26551e07885c335718496c6cc1951347f054a506f04f`
- `test_search_contract.py`: `a418b772d7c93ba1ef9f5d39cfbf6a408a0bdc2d63a561808aedb8ad52e06921`
- `benchmark.py`: `386a74f162d494e5c484801e105167c87c51fa603e6d4b8fffb03406a279537f`

The 2026-10-11 benchmark snapshot used `chess_nn.pkl` and measured
approximately 983 NPS and a 35.7% TT hit rate over five one-second
positions. These figures describe that benchmark configuration only;
they must not be presented as browser-engine results until model
identity and runtime loading are reconciled.

### Open and not established

- Forced mates beyond the tested mate-in-3 fixture are not established
  by this milestone; mate-in-4 and longer require a broader verified suite.
- No guarantee is made that the engine finds every forced mate.
- The terminal-aware clamp-boundary FixA experiment remains a separate,
  unapplied candidate.
- The root verifier has measurable extra cost on the mate-in-3 fixture;
  the performance impact should be measured during a dedicated profiling
  milestone.
- The October 2 audit's browser-versus-benchmark model mismatch and
  direct trainer writes to `chess_nn.pkl` remain open pending renewed
  inspection of live source.
- Search telemetry, fixed benchmarking, persistent semantic analysis
  history, Opening Tree engine scores, whole-game queued analysis,
  configurable Hash and Threads, browser learning, candidate-model
  promotion, NN-only evaluation, and remaining frontend and
  documentation work remain open or planned as recorded above.

This milestone closes a specific verified root-mate regression. It does
not establish that the engine or entire product is bug-free or strength-
validated.



## 2026-10-11 - P5.15J LMR threshold 6 regression

Status: applied to live search.py; targeted regressions and full suite passed.

### Change and provenance

- Changed the LMR move-index threshold in SearchEngine._pvs_result
  from i >= 4 to i >= 6. No other search.py source lines were changed
  by this patch.
- Verified live search.py SHA-256:
  99997380a2881f87a2d57757a13050b9122b750b61ae58c9f0c22b7fbd257bea
- Read-only pre-patch backup:
  search.py.20261011.pre_lmr_threshold_6.bak
- Backup preserves pre-patch SHA-256:
  961765fce5e3029d342df3be6b1b5a0c1737a5cbc8bdd456f88763d8d5e210a4

### Verified results

- Four existing mate-in-1 fixtures passed, with expected moves and score
  29999.
- The mate-in-3 fixture passed at requested depths 3, 4, and 5, with
  score 29997 and accepted depths 3, 4, and 5.
- The 5-ply queen-versus-knight fixture returned a3a4 and score 29995.
- The formerly failing 5-ply rook-versus-king fixture returned a4b3
  and score 29995; the previous threshold-4 result was g3g2 / 487.
- test_search_contract.py passed P5.15D and P5.15E; all 20
  SearchResult construction sites and provenance tuples passed.
- run_tests.sh exited 0 and printed "=== All tests passed ===".
  Its benchmark reported mate-in-1 solved 4/4, self-play of 10 games
  with zero illegal moves and zero crashes, and correct perft results
  through depth 5.

### Costs and limitations

- In the controlled in-memory comparison, threshold 6 used about 6.7%
  more nodes on start position and 8.3% more on the queen-versus-knight
  5-ply fixture than threshold 4. A separate 500 ms middlegame control
  did not complete depth 1 under either variant; this is an open
  performance/telemetry issue, not evidence of equal analysis quality.
- The measurements are device- and time-control-specific. They do not
  establish a general Elo gain.
- The 7-ply queen-versus-rook and queen-versus-king fixtures remain
  unresolved. The earlier tests timed out before completing deeper
  iterations. This LMR change has not been shown to fix them.
- Four mate-in-1 and the additional short-mate fixtures are not yet all
  permanent benchmark gates. Promote verified fixtures into the existing
  benchmark implementation in a separate, guarded step.
- Overall playing strength, deep-mate reliability, and superiority to
  other engines remain unproven pending broader tests and controlled
  matches.

### Next engineering priorities

1. Preserve this verified search baseline and make the new tactical
   fixtures permanent regression tests.
2. Continue profiling completed-depth time, quiescence tree shape,
   move generation, NN evaluation/cache behaviour, and TT effectiveness.
3. Use those measurements to guide search-speed changes while tracking
   missed tactics and analysis quality as well as NPS.
4. Continue the existing roadmap for TT semantics and configurable Hash,
   deep-job MultiPV, resumable semantic analysis, and browser-controlled
   analysis jobs.
5. Audit Opening Tree engine scores separately from historical game
   results, and unify personal/opponent filters across game-derived
   sections.
6. Audit all training inputs, target semantics, train/validation splits,
   and model writers before implementing candidate-model training,
   validation, safe promotion, and rollback.
7. Unify both engine panels and ensure board arrows refresh from the
   selected Opening Tree position and its current compatible PV, starting
   at initialization. Clear stale arrows when the selected position or
   analysis changes. Improve queen distinction, piece contrast, and
   arrow visibility as part of the existing UI redesign.
8. Reconcile existing Markdown documentation against verified live code.
   Do not use an old ZIP archive as the current source of truth.

No model or production database was changed by this milestone.

## 2026-10-11 — Benchmark model alignment and expanded tactical gates

This supplement records benchmark changes verified against the live workspace.
It supplements the P5.15J checkpoint; it does not replace earlier history,
change existing milestone IDs, or establish overall engine-strength readiness.

### Change and provenance

- `benchmark.py` now loads `distilled_nn.pkl`, aligning the benchmark model
  with the model reference in the browser runtime (`web_control.py`).
- The benchmark includes the `MATES_DEEP` gate set: a mate-in-3 fixture and
  two five-ply tactical fixtures (queen versus knight and rook versus king).
- Mate-in-1 and deep-tactical gate failures terminate the benchmark with
  a nonzero exit status via `SystemExit(1)`.
- Live `benchmark.py` SHA-256:
  `b4bbb9028494df0790ddb990f3b1ef4d95bfe7d2ae147b1a4894a84ef21ea2e4`.
- Recorded pre-model-alignment backup:
  `benchmark.py.20261011.pre_model_alignment_gate.bak`,
  SHA-256 `bac73eb52c7571933c48a99aa5b929b70427cb099db50f1ec1f3b734b7958140`.

### Verification recorded

- Four mate-in-1 fixtures passed.
- All three current `MATES_DEEP` fixtures passed in the verified run.
- The ten-game self-play gate reported zero illegal moves and zero crashes.
- `run_tests.sh` completed successfully and reported `=== All tests passed ===`
  in the verified 2026-10-11 run.

These results establish that the listed gates passed under the tested model,
search settings, fixtures, and device conditions. They do not establish general
Elo, superiority to other engines, or reliable discovery of every long forced
mate. Mate-in-50+ capability remains unproven and requires broader testing.

### Training-data documentation follow-up

The next documentation-only follow-up belongs in `docs/TRAINING_GUIDE.md`,
under its existing section 7, "Confirmed live risks and incompatibilities".
The source/data audit identified specific examples that should be recorded
there without creating a new training milestone:

- `training_data_tactical.pkl` (70 samples) and
  `training_data_checkmate.pkl` (158 samples) were measured to have all-zero
  value targets.
- `training_targets.py` uses a phase-dependent blend of game outcome and
  `tanh(static_eval(board) / 400.0)`, but returns literal `0.0` immediately
  when `white_result == 0.0`. In the reviewed self-play generator, that value
  is assigned for both draws and move-cap termination.
- `training_data_5k_v2.pkl` has only `positions`, `values`, and `policies`;
  it does not conform to the current eleven-field `dataset_schema.py`
  validator contract.
- The training lineage of `distilled_nn.pkl` remains unknown from the
  evidence reviewed. Its performance on the small tactical fixture set does
  not prove its overall playing strength or exact training history.

These are concrete data/source observations, not proof that every dataset is
corrupt or that target variance alone caused measured differences between
models. Training-source changes, retraining, and model promotion are outside
the scope of this documentation patch.

### Next engineering priority

Per the existing implementation order, search-pipeline telemetry remains
the next engineering priority. It should instrument completed-depth timing,
node and quiescence counts, TT usefulness, NN/cache costs, move generation,
and evaluation time before behavior-changing performance patches.

The fixed benchmark suite is partially strengthened by the gates recorded
above, but wider reproducible tactical and playing-strength validation remains
necessary. Search changes will continue to be judged by correctness, analysis
quality, tactical strength, completed depth at a fixed budget, wall-clock
performance, and NPS—not NPS alone.

## 2026-10-12 — UI fixes and roadmap reconciliation

This supplement records the UI changes verified during this session and
updates the engineering priority order. It supplements the existing
milestones; it does not replace their historical records or establish
project-wide readiness.

### Changes applied and observed

- **Opening Tree initial arrows:** `frontend/js/board.js` now calls
  `renderBoard(window._CURRENT_STATE)` after `_TREE` and `_CURRENT_NODE`
  are assigned and `renderTree()` is called in `initDatabaseRepertoire()`.
  The supplied browser screenshots showed arrows on initial load.
  - Live SHA-256:
    `75351b267824b08c09ea40f41bbb9312d82baf5ad0e3b8d3e3de4583465360be`
  - Pre-patch backup:
    `frontend/js/board.js.20261012.pre_arrow_init_fix.bak`
    (mode `0400`).

- **Database-mode polling guard:** `frontend/js/batch.js` checks
  `_DATA_SOURCE === 'database'` before issuing the `/api/current_fen`
  request. This prevents the interval from sending that request while
  browsing the database. The previous live log showed approximately
  two requests per second before the change.
  - Intermediate SHA after this change:
    `30e8eb40eb229422629450697e935e77630b20d92543e70cc5d8c3e8ecdcd172`
  - Pre-patch backup:
    `frontend/js/batch.js.20261012.pre_poll_guard.bak`
    (mode `0400`).

- **Current-line persistence:** the idle clearing branch in
  `startBatchPolling()` was narrowed from `else` to
  `else if (data.running)`. Supplied browser screenshots showed the
  current-line chips and ply counter populated after this change.
  - Current live SHA-256:
    `8d14d5eab6c62092569d2f715b9d6a2ba16f867f9dfdc35cf8560fc50d2b1387`
  - Pre-patch backup:
    `frontend/js/batch.js.20261012.pre_line_guard.bak`
    (mode `0400`).

- **Retracted arrow suspicion:** the earlier claim that arrows at a
  non-root position were incorrect was withdrawn after reviewing the
  screenshots. Do not treat it as an open defect without new evidence.

### Verification limits

The changes above are recorded from the patch outputs and browser
observations supplied in the session. The following behaviours remain
unverified after the changes:

- The number of `/api/current_fen` requests during a clean, 20-second
  idle window in database mode.
- Whether the current-line display remains correct throughout a running
  single-game Test session using the SSE update path.
- A fresh rerun of the search fixed-depth equivalence tests.

These remain open verification items, not confirmed defects.

### Live-source baseline recorded on 2026-10-12

- `frontend/js/board.js`:
  `75351b267824b08c09ea40f41bbb9312d82baf5ad0e3b8d3e3de4583465360be`
- `frontend/js/batch.js`:
  `8d14d5eab6c62092569d2f715b9d6a2ba16f867f9dfdc35cf8560fc50d2b1387`
- `search.py`:
  `fa0a23df31c7202f23498f78d53111477fccde07592394e7f2aeb8593f809df5`
- `benchmark.py`:
  `b4bbb9028494df0790ddb990f3b1ef4d95bfe7d2ae147b1a4894a84ef21ea2e4`
- `training_targets.py`:
  `a0b05f385fc72127f776e7ee9a9bd005d69f5bfdac50ab6a12bad93ef551ef3e`
- `dataset_schema.py`:
  `6885d29d5b7048d49d18f89b92b353f93f8829d64c5d002fd8df54fbc14b0f7a`

These hashes identify the files inspected; they do not imply that those
files or the project as a whole are defect-free.

### Updated engineering priorities

The previous note naming search telemetry as the next task is superseded
by this priority order. Telemetry instrumentation was reported complete
in the preceding session, but its regression suite was not rerun during
this documentation update.

1. **Fixed benchmark and tactical regression gates.** Preserve the
   passing mate-in-1, mate-in-3, five-ply tactical and self-play results
   under their recorded test conditions. Keep unresolved deeper positions
   visible as open cases instead of silently dropping them.
2. **Search correctness audit.** Inspect the current live `search.py`
   for TT bounds and replacement, mate-score normalization, accepted-root
   provenance, timeout/stop handling and completed-iteration reporting.
3. **Evidence-led speed and quality work.** Profile completed-depth time,
   quiescence, move generation, evaluation, NN/cache behaviour and TT
   usefulness. Judge changes by correctness, tactical accuracy, depth at
   a fixed budget, wall-clock time and NPS—not NPS alone.
4. **Persistent semantic Analysis History and resumable analysis.**
5. **Opening Tree position scores and root MultiPV integration.**
6. **Configurable Hash in MB and a measured thread strategy.**
7. **Resumable whole-game analysis and job controls.**
8. **Collect-only learning, training-data/target audit, candidate-model
   validation, safe promotion and rollback.**
9. **Long-term NN-only evaluation, conditional on validation.**
10. **Consistent game-ownership filters, unified engine panels, board and
    arrow improvements, and completion of browser-controlled workflows.**

The project remains unproven against broad playing-strength benchmarks,
and reliable detection of every mate in 50 or more moves is not
established. Training-data risks identified in earlier audits must be
rechecked against the live inputs before training or model promotion.

The inventory identified 16 Markdown documents. This entry synchronizes
the roadmap status only; it does not claim that every other document has
already been audited or updated. No search code, model or production
database was changed by this documentation step.



---

## 2026-11-10 — Live-source audit reconciliation

This section records the November 7–10 live-source inspections. It supplements the existing product phases and Engineering Tracks A–J. It does not create new phases, replace historical checkpoints, or establish project-wide readiness.

### Source evidence

The following live files were inspected using read-only Termux probes. Their SHA-256 hashes matched the recorded source baselines:

| File | SHA-256 |
|---|---|
| `search.py` | `fee2145a1035b7a56db669ef549a27cabb46d8496b457f46203aaea179fad93c` |
| `board.py` | `352c9c72003ede96da573593247348e10a9fc0e4a9f75451c6e9cec2534d1d1d` |
| `static_eval.py` | `8ef173d23288ad8e9873da84e96b306e3146ed3c3b4a6e35979281058a6eba6f` |
| `web_control.py` | `86887ae8d8b7cc4678d6e81e28aee9c0963cd2274338f4c40af583edc6d17643` |
| `database_v2.py` | `cee3d6e6badaf904c0c2c9a133632f20e8be69b1d402b235a80a15c7a9a067a6` |

All five inspected Python files parsed successfully during their respective audits.

### Installed patch ledger

The following patches are installed in the inspected live source. Their presence is established by the source inspections recorded in `docs/AUDIT_STATUS.md`.

| Patch | File(s) | Current SHA-256 | Description |
|---|---|---|---|
| 0 | `search.py` | `fee2145a…` | NN cache key includes `(board.hash, en_passant, halfmove_clock, repetition_flag)` |
| 1 | `search.py` | `fee2145a…` | Mate precedence at halfmove/repetition draw thresholds |
| 2 | `search.py` | `fee2145a…` | Quiescence checkmate at depth cap before heuristic return |
| 3 | `search.py` | `fee2145a…` | `MATE_PLY_BOUND = 1000` consolidated across the mate-score classification sites |
| 4A | `search.py` | `fee2145a…` | TT v2 with halfmove/repetition context compatibility (`CURRENT_TT_VERSION = 2`) |
| 5a | `benchmark.py` | `235ab8134ee92d0f9c20253db1465aba72bed734bac534783a804ecc6c5c1134` | `CountingOrderedDict(OrderedDict)` instrumentation container |
| 5c | `board.py`, `static_eval.py` | `352c9c72…`, `8ef173d2…` | Incremental material; `combined_eval` reads `board.material` |
| 5e | `static_eval.py` | `8ef173d2…` | `eval_king_safety` reads `_king_sq` instead of scanning 64 squares |

The `benchmark.py` hash `235ab813…` was recorded in the November 10 source-file inventory. `benchmark.py` was not re-inspected in the deep source audits.

### Search and engine findings

The live search source confirms TT v2 provenance and context compatibility; search-result provenance and authoritative-root handling; mate precedence at the implemented draw thresholds; mate detection at the quiescence depth cap; the NN cache key; the inline TT probe in `_pvs_result`; `AUTHORITATIVE_ROOT_SOURCES = frozenset({'search', 'terminal'})`; `MAX_DEPTH = 20` as the default depth configuration (not a ceiling for `unlimited=True`); the unbounded depth iterator for unlimited search; and the P5.15I defensive mate verification with a temporary empty TT.

The constructor and continuation implementation distinguish fresh root state from persistent engine-instance state. A fresh search clears accepted-root state but does not explicitly clear the engine's TT.

### Board and evaluation findings

Patch 5c incremental material and Patch 5e king-square optimisation are confirmed in the inspected board and evaluation source.

The board audit also identified three concrete issues and one candidate: en-passant captures are omitted by the capture-only generator (empty destination square filter); qsearch delta pruning calculates the capture victim from the same empty square, so correcting generation alone is insufficient; FEN loading modifies the board before all validation finishes, creating partial-state mutation on later errors; and `board.is_draw()` returns draw at claimable thresholds without modelling automatic ones — classification pending call-site inspection.

Detailed findings are in `docs/AUDIT_STATUS.md` §3–§5.

### Browser analysis and persistence findings

The modern `/api/jobs` analysis path invokes `SearchEngine.search()` with `unlimited=True` and `time_limit=None`. The browser Stop control, cancellation API, shared session/engine stop event and engine timeout check were traced through the inspected frontend and backend source.

Continuation restores accepted-root state and resumes from the accepted depth. A checkpoint-restored engine does not restore the original in-memory TT.

The persistent analysis path has a history-context inconsistency: checkpoint-loaded sessions are assigned `frontier_only`, while reusable-frontier lookup requires `unknown`. Records written under the incompatible context are not candidates for reuse. As checkpoint-restored sessions accumulate further analysis, the pool of unreusable records grows with normal use.

### Database and ownership findings

The live database inspection confirmed 14,916 games; 892,398 positions; 1,031,269 game moves; 193 position-analysis records; all 193 at TT version 1; 184 `history_context='unknown'` and 9 `history_context='frontier_only'`; maximum accepted depth 20; `PRAGMA integrity_check` returned `ok`; no foreign-key violations.

The `position_analysis` primary key is eight fields and matches the persistence conflict target.

The `games` table does not contain a structural owner field. `canonical_players` and `player_aliases` provide a basis for identity resolution, but complete ownership-aware backend query behaviour remains to be audited.

Source declares `SCHEMA_VERSION = 6`; the on-disk `schema_version` table value is unverified. `PRAGMA user_version = 0` is a separate setting and does not indicate a mismatch.

### Status and priority

The October 12 implementation order (the ten-item priority list at pre-append lines 1293–1313) remains the governing project priority structure. The November audit adds correctness and evidence gates before relevant implementation work.

No project-wide bug-free, strength-validated, or complete-product claim is made by this update.

See `docs/AUDIT_STATUS.md` for detailed findings and classification.
