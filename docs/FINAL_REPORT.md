# Chess AI – Final Report
**Project:** Chess AI · **Date:** 2026-08-09

> **Historical report.** This document reflects project state as of
> 2026-08-09 (with a production update on 2026-08-23). Live state has
> advanced past this report. For current behavior consult
> `docs/ARCHITECTURE.md`, `docs/API_REFERENCE.md`, and
> `docs/AUDIT_STATUS.md`.

## Phase-0 Status
- All 15 confirmed Phase-0 defects addressed.
- Python syntax checks pass.
- Runtime verification RV-01 through RV-08 has passed.
- Flask runtime verification has been completed.

## Release Readiness
**Phase‑0 Complete – ready for Phase‑1**
The project has passed all planned runtime verification tests.


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
The historical Phase-0 completion and release-readiness statements above remain preserved
as recorded for their date. Their scope was the Phase-0 remediation and runtime verification
cycle, not a project-wide readiness claim for the current engine.

### Patch A — Search Provenance: COMPLETE

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

### Open — engine not project-wide ready

**KQK depth-parity score anomaly — OPEN**
- Odd accepted depths ≈ +1160 / +1178; even accepted depths produce −0.0.
- Direct leaf trace confirms `combined_eval()` is White-perspective in the tested KQK positions.
- NN value head does not show a coherent material/perspective signal on the four KQK probes; a wider validation set is required before drawing a broader conclusion.
- No evaluator or search implementation change has been applied from this investigation.

**P5.17 evaluator perspective/score contract** — OPEN.
**P5.18 NN value-head validation** — OPEN, downstream of P5.17.

### Known non-production compatibility issues

Four callers still expect the old three-value `search()` return. Outside the verified production path:
- `test_vs_random_web.py:57`
- `generate_themed_data.py:86`
- `update_all.sh:1494`
- `update_all.sh:2587`

### Not established

- A queen-sacrifice defect has not been demonstrated.
- No search or evaluator fix has been applied for queen-sacrifice behavior.

### Documentation reconciliation

- `docs/CHANGELOG.md` updated 2026-09-11.
- `docs/AUDIT_STATUS.md` updated 2026-09-11.
- `docs/BUG_TRACKER.md` updated 2026-09-11.
- `docs/CODE_AUDIT.md` updated 2026-09-11.
- Further documentation reconciliation pending, one file at a time.


---

## 2026-09-27 — Live-source reconciliation

### Stale three-value caller claim

The “Known non-production compatibility issues” section of the
2026-09-11 block lists four callers as still expecting the old three-value
`search()` return:

    test_vs_random_web.py:57
    generate_themed_data.py:86
    update_all.sh:1494
    update_all.sh:2587

`docs/CHANGELOG.md` records a 2026-09-19 entry stating that this claim
is stale and was corrected across the doc set. The current live tree
has no caller expecting the three-value form. The listed section is
superseded.

### B-022 correction absent

This file does not carry the 2026-09-12 B-022 correction present in
`docs/AUDIT_STATUS.md`, `docs/BUG_TRACKER.md`, `docs/CHANGELOG.md`,
`docs/NEURAL_NETWORK.md`, `docs/TRAINING_GUIDE.md`,
`docs/DEVELOPER_GUIDE.md`, and `docs/ARCHITECTURE.md`.

The current live source loads `distilled_nn.pkl` from `web_control.py`
and `chess_nn.pkl` from `uci_engine.py`. The canonical-artifact decision
remains **OPEN** under B-022.

### “Authoritative” self-label

The 2026-09-11 section self-describes as “the authoritative current-status
section for present-state interpretation”. The 2026-09-12 B-022 correction
and the 2026-09-19 CHANGELOG entry supersede part of that section. No
single section is now the sole authoritative current-status source.

### Status

The historical body is preserved as recorded. This section records the
supersession and the missing correction above.

### Cross-references

- `docs/CHANGELOG.md` — 2026-09-19 caller-migration entry.
- `docs/AUDIT_STATUS.md` — current verified state and B-022 correction.
