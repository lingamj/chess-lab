# WORKFLOW


## Standard Change Sequence
1. Inspect live code/schema
2. Create backups
3. Patch code/docs
4. Syntax-check
5. Validate invariants
6. Reconcile
7. Close after backup/acceptance

## Current Invariants
- schema_version: 5
- games: 14,916
- game_moves: 1,031,269
- source_username NULL: 0
- tree_dirty: 0 for both sources


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

This section supplements the sequence and invariants above. It does not
replace them. Historical sections remain in force.

### Phase classification

Every operation belongs to exactly one phase. Do not blur them.

| Phase | Purpose | Allowed actions |
|---|---|---|
| Documentation | Reconcile Markdown against live source | Read live source; edit `.md` files only |
| Test | Verify behavior | Run isolated tests on the live tree |
| Production | Change live behavior | Require explicit gate and backup |

### Safe during documentation

- Reading any file.
- Running read-only diagnostics: `cat`, `grep`, `sha256sum`, `wc`, `stat`, `find`.
- Creating backups of `.md` files.
- Editing `.md` files with the fail-closed pattern.

### Not safe during documentation

- Do not run `train_auto.sh`.
- Do not run `auto_sync_train.py`.
- Do not run any `run_pipeline*.sh`.
- Do not restart Flask.
- Do not run production sync.
- Do not modify the production DB.
- Do not rebuild the opening tree.
- Do not activate or replace model artifacts.
- Do not edit any `.py` or `.sh` source file.

### Documentation-edit pattern

Each Markdown change follows this order:

1. Preflight: record mode, sha256, line count.
2. Backup-count pre-check: refuse if a backup already exists.
3. Collision-safe backup with checksum verification.
4. Candidate written to `<file>.candidate`.
5. Candidate verified by Python assertion block.
6. Failure: delete candidate, no install.
7. Success: install by `mv`.
8. Verify installed checksum equals validated candidate.
9. Verify original bytes are an exact prefix.
10. Verify mode preserved and exactly one backup remains.

### Workflows not currently safe to run end to end

The following are documented in `docs/TRAINING_GUIDE.md` as not safe to
execute as-is:

- `train_auto.sh` — checks only for the existence of `distilled_nn.pkl`,
  then copies it over `chess_nn.pkl`. A stale artifact present on disk
  will be promoted regardless of whether training succeeded.
- `run_training.sh` — merges new data into `training_data.pkl` before
  invoking `train.py`, and does not check the exit status of `train.py`.
- `update_model.sh` — invokes `train.py` and immediately reports success
  without checking the exit status.
- `auto_sync_train.py` — combines external sync, dataset mutation, and
  training via a legacy `train.py` CLI.
- The five legacy `train.py` flag-style callers — incompatible with the
  current positional CLI.

### Invariants drift note

The "Current Invariants" block above records a 2026-08-23 production
checkpoint. It is not a live reading. Live readings are recorded in
`docs/AUDIT_STATUS.md` under the current-status section.

Do not update the invariant numbers here without a live read-only
verification.

### Authority reference

The full document authority map is in `docs/DEVELOPER_GUIDE.md` under
"File authority map". This section does not duplicate it.
