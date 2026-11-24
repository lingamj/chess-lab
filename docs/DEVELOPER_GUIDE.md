# DEVELOPER_GUIDE


## Production Guardrails
- Live ~/chess_ai is authoritative.
- Run read-only diagnostics before writes.
- Create WAL-safe backups before migrations.
- Validate on isolated DB snapshots for risky changes.
- Do not modify games.white/games.black historical values.

## Canonical Identity
- canonical_players.canonical_name is stable.
- player_aliases maps historical names to canonical identity.


---

## Workspace Hygiene — 2026-08-23

Before archiving or removing an old file:

1. Determine whether current runtime code references it.
2. Determine whether it contains unique useful knowledge.
3. Merge unique useful knowledge into the authoritative current file when appropriate.
4. Preserve rollback material in the historical archive.
5. Do not delete historical material merely because it is old.
6. Verify the live application after moving files.

---

## 2026-09-12 — Current-state Addendum

This section supplements the guardrails above. It does not replace them.
The historical guardrails remain in force.

### Live source authority

The active workspace `~/chess_ai/` is the authoritative source for
current runtime behavior. Historical archives are reference and
rollback material only. A file existing in an archive does not
establish that it exists in the active runtime.

Where a historical archive and the current live source disagree, the
live source wins. Where neither establishes enough evidence, the item
remains OPEN rather than being inferred.

### File authority map

| Purpose | Authority |
|---|---|
| Search contract | `docs/SEARCH_ALGORITHM.md` |
| Dataset contract | `docs/DATASET_FORMAT.md` |
| Training reality | `docs/TRAINING_GUIDE.md` |
| Roadmap | `docs/ROADMAP.md` |
| Bug status | `docs/BUG_TRACKER.md` |
| Historical decisions | `docs/CHANGELOG.md`, `docs/REJECTION_REPORT.md` |
| Current architecture | live source, mirrored in `docs/ARCHITECTURE.md` |
| User-facing overview | `README.md`, after rewrite |

Other documents do not override these on their respective topics.

### Production safety boundary

During any phase that is not explicitly a production-change phase:

- Do not run production training.
- Do not run `train_auto.sh`, `auto_sync_train.py`, or any
  `run_pipeline*.sh` script.
- Do not restart Flask.
- Do not run production sync.
- Do not modify the production DB.
- Do not rebuild the opening tree.
- Do not activate or replace model artifacts.

Rationale for the `train_auto.sh` restriction: the script runs
`multi_train.py`, which writes `chess_nn.pkl`, then checks only for the
existence of `distilled_nn.pkl` and copies it over `chess_nn.pkl`. A
stale `distilled_nn.pkl` present on disk will be promoted regardless of
the outcome of the training run.

### Documentation-change rule

Documentation changes are not code changes. Do not modify `search.py`,
`nn.py`, training scripts, or any live `.py` or `.sh` file while working
on documentation reconciliation.

When a document records a claim that the live source contradicts, mark
the claim contradicted and record the live evidence. Do not silently
modify code to match documentation.

### Definition of done

A defect is RESOLVED only when all six of the following hold:

1. A source change exists.
2. A regression test exists, or a justified runtime validation exists.
3. Live behavior matches the intended contract.
4. Documentation is updated.
5. No contradictory documentation remains.
6. Production safety impact is reviewed.

Without all six, the correct status is OPEN, PARTIALLY VALIDATED, or
DOCUMENTED ONLY. Not RESOLVED, not FIXED.

### Current known contradiction

`web_control.py:22` sets `MODEL_PATH` to `distilled_nn.pkl`. Every
other live model consumer identified in the current tree uses
`chess_nn.pkl` or `chess_nn_master.pkl`. Several documents record B-022
as having unified the model path to `chess_nn.pkl`. Those documents are
contradicted by the live source.

Whether this is a regression or a claim that was never applied is not
established. The item remains OPEN.


---

## 2026-09-27 — Line-reference correction

The “Current known contradiction” section cites `web_control.py:22`.
The current live line is 25. The underlying claim is correct; only the
citation is stale.

### Cross-references

- `docs/AUDIT_STATUS.md` — current verified state.
- `docs/TRAINING_GUIDE.md` — model-artifact split.
