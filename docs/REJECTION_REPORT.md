# Import Rejection Report

## Summary
- Source games: 6442
- Inserted: 6412
- Duplicates: 19
- Zero-move games rejected: 11
- Not inserted total: 30

## Zero-move games

| Source # | White | Black | Result | Termination |
|----------|-------|-------|--------|-------------|
| 22 | jothi_lingam | IanWilder | 0-1 | game abandoned |
| 106 | crowhead1970 | jothi_lingam | 0-1 | game abandoned |
| 128 | jothi_lingam | bizarreblitz | 0-1 | game abandoned |
| 137 | MJFar | jothi_lingam | 0-1 | game abandoned |
| 149 | sukumar_4141 | jothi_lingam | 0-1 | won on time |
| 269 | adityapalnitkar | jothi_lingam | 0-1 | won by resignation |
| 272 | BenVelo | jothi_lingam | 0-1 | won on time |
| 1007 | SHAKERISMZ21 | jothi_lingam | 0-1 | won on time |
| 1120 | hariantomdn | jothi_lingam | 0-1 | won on time |
| 3003 | jothi_lingam | mrmeo | 0-1 | won by resignation |
| 3012 | szachowykokses | jothi_lingam | 0-1 | won by resignation |


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

## 2026-09-12 — Historical-scope note

This document is a historical import report. It is preserved as
recorded and is not updated to reflect subsequent state.

Scope of the "Summary" block above:

- The counts (source games 6442, inserted 6412, duplicates 19,
  zero-move rejected 11, not inserted total 30) describe **one specific
  import event**, not the current production database.
- The eleven-game table below the summary lists the specific games
  rejected during that same event.
- The "2026-08-23 Production Update" block below is a snapshot of the
  production database as of 2026-08-23, not a live reading.

Current production state is recorded in `docs/AUDIT_STATUS.md` under the
current-status section.

This document should not be modernized. Terminology, filenames, and
counts are preserved as recorded. If a later import event needs to be
recorded, add a new dated section rather than editing the existing ones.
