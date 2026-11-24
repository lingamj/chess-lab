# Chess AI Bug Tracker
**Project:** Chess AI · **Type:** Static source audit · **Date:** 2026-08-09

## Summary
| Category | Count |
|---|---:|
| Fixed bugs (verified in current source) | 19 |
| Confirmed Phase-0 defects (now fixed) | 15 |
| Runtime verification required | 8 |
| Improvements (non-defects) | 17 |

---

## Fixed Bugs (B-001 – B-019)
| ID | Severity | File | Description |
|---|---|---|---|
| B-001 | Critical | `search.py` | Neural value head disabled (`NN_SCALE = 0`) – changed to 800 |
| B-002 | High | `search.py` | Transposition table eviction was LIFO – changed to FIFO via `OrderedDict` |
| B-003 | High | `search.py` | En-passant not treated as capture in LMR/killer logic |
| B-004 | Critical | `parallel_search.py` | Returned 3 values instead of 4 – added `self.nodes` |
| B-005 | Critical | `uci_engine.py` | Unpacked 3 values from search result – now unpacks 4 |
| B-006 | High | `web_control.py` | `get_fen()` called instead of `to_fen()` in live game state |
| B-007 | Critical | `web_control.py` | `LiveGame` class missing – `def run(self):` was nested inside `static_files` |
| B-008 | Critical | `web_control.py` | `/api/human_move` endpoint missing – added |
| B-009 | High | `web_control.py` | `result` undefined in `run_human_game` on early stop – initialized to `"*"` |
| B-010 | Medium | `web_control.py` | Busy-wait `time.sleep(0)` burned CPU – changed to `0.05` |
| B-011 | Medium | `web_control.py` | Race condition on `engine_color` – moved assignment inside `test_batch_lock` |
| B-012 | Medium | `web_control.py` | `all_pgns_count` missing from batch status – added |
| B-013 | High | `web_control.py` | Broken live-game locking – replaced with module-level `live_game_lock` |
| B-014 | Medium | `batch.js` | Wrong element ID `batchOpponent` – corrected to existing `batch-opponent` handling |
| B-015 | Low | `batch.js` | Duplicate Stockfish analysis block – deleted |
| B-016 | Low | `web_control.py` | Duplicate imports (`threading`, `time`, `random`) – cleaned |
| B-017 | High | `analysis.js` | `stateFromFEN` not exposed globally – fixed |
| B-018 | Medium | `board.js` | Manual board clicks did not trigger re-analysis – analysis call added |
| B-019 | Low | `train.py` | Legacy format policy index extraction – corrected |

---

## Phase-0 Confirmed Defects (B-020 – B-034)
| ID | Severity | File | Description |
|---|---|---|---|
| B-020 | Critical | `board.py` | `undo_move` does not restore repetition count of pre-move position |
| B-021 | Critical | `web_control.py` | Inverted checkmate result |
| B-022 | Critical | `web_control.py` | Model path split-brain (`distilled_nn.pkl` vs `chess_nn.pkl`) |
| B-023 | Critical | `web_control.py` | No lock around shared analysis engine |
| B-024 | Critical | `web_control.py` | SSE `fen_queue.get()` blocks without timeout |
| B-025 | Critical | `batch.js` | Human polling uses `data.fen` instead of `data.current_fen` |
| B-026 | High | `search.py` | Aspiration timeout returns bound instead of true score |
| B-027 | Critical | `uci_engine.py` | Single-thread UCI mode crashes due to `stop_event` / unpack handling |
| B-028 | High | `generate_themed_data.py` | Unpacking 3 values from a 4-tuple search result |
| B-029 | High | `mcts.py` | MCTS selection formula sign-inverted |
| B-030 | High | training modules | Policy targets passed as integer indices when `nn.train()` expects one-hot |
| B-031 | Medium | `web_control.py` | `fen_queue` unbounded |
| B-032 | Medium | `uci_engine.py` | `go infinite` uses default 3-second time limit |
| B-033 | Medium | `web_control.py` | `/api/analyze_sf` bare `raise` can return HTML error page |
| B-034 | Medium | `web_control.py` | Background batch/human game threads lack top-level exception handler |
| B-035 | Medium | `search.py` | Missing `import threading` – fixed during runtime verification |

---

## Runtime Verification
| Test | Status |
|---|---|
| RV-01 | PASS    |
| RV-02 | PASS    |
| RV-03 | PASS    |
| RV-04 | PASS    |
| RV-05 | PASS    |
| RV-06 | PASS    |
| RV-07 | PASS    |
| RV-08 | PASS    |


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
Historical entries above remain preserved as recorded.

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

### Open

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

- `docs/CHANGELOG.md` updated 2026-09-11.
- `docs/AUDIT_STATUS.md` updated 2026-09-11.
- Further documentation reconciliation pending, one file at a time.

---

## 2026-09-12 — B-022 status correction

The "Fixed Bugs" and "Phase-0 Confirmed Defects" tables above record
B-022 as a fixed defect. The row itself describes the historical defect:

    | B-022 | Critical | `web_control.py` | Model path split-brain
      (`distilled_nn.pkl` vs `chess_nn.pkl`) |

That row and the counts (19 fixed, 15 Phase-0) are preserved as
historical record. The current live source shows the split remains.

### Live evidence

`web_control.py:22` sets:

    MODEL_PATH = os.path.join(CHESS_DIR, "distilled_nn.pkl")

All other model-load sites identified in the current tree use
`chess_nn.pkl` or `chess_nn_master.pkl`.

### Status

B-022 is **contradicted by live source**, not currently resolved.

Whether the fix was applied and later reverted in `web_control.py`, or
was recorded without an applied change, is **not established** by the
reviewed evidence.

The item remains **OPEN** pending determination of the intended
canonical artifact and a validated live-source correction.

### Effect on the fixed counts

The "19" and "15" counts above include B-022. They are not recomputed
by this section. Recomputation is deferred until B-022's exact status
(regression vs never-applied) is classified.

### Historical record preserved

The tables and counts above remain the historical record for their
date. They are not edited.

### Cross-references

- `docs/AUDIT_STATUS.md` — "2026-09-12 — B-022 status correction".
- `docs/TRAINING_GUIDE.md` — documents the model-artifact split.
- `docs/DEVELOPER_GUIDE.md` — "Current known contradiction".
- `docs/WORKFLOW.md` — safety implication for `train_auto.sh`.


---

## 2026-09-27 — Live-source reconciliation

### Unsupported count in the Summary table

The historical Summary table records:

    Improvements (non-defects) | 17

No list, table, or appendix of 17 improvements exists in this file. The
count is unsupported by the current file content and should not be treated
as verified.

### Phase-0 range label

The historical section is titled “Phase-0 Confirmed Defects (B-020 –
B-034)” but the table inside includes B-035. The correct range label is
B-020 through B-035.

### “Authoritative” self-label

The 2026-09-11 section self-describes as “the authoritative current-status
section for present-state interpretation”. The 2026-09-12 B-022 correction
below it supersedes part of that section. No single section is now the
sole authoritative current-status source.

### B-022 line drift

The 2026-09-12 B-022 correction cites `web_control.py:22`. The current
live line is 25. The underlying claim is correct; only the citation is
stale.

### Status

The historical body is preserved as recorded. This section records the
current reconciliation without editing the historical sections.

### Cross-references

- `docs/AUDIT_STATUS.md` — current verified state.
- `docs/API_REFERENCE.md` — current route inventory.
