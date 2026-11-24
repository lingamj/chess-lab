# DATASET_FORMAT


- schema_version: 5
- games: 14,916
- game_moves: 1,031,269
- source_username NULL: 0

## Provenance Mapping
- lichess → jothilingam
- bulk_import → jothi_lingam
- import_test → jothi_lingam
- chesscom → jothi_lingam

Canonical identity:
- jothi
  - jothilingam → lichess
  - jothi_lingam → chesscom

---

## 2026-09-11 — Training Dataset Format

This section documents the training dataset representations used in the
active workspace. It does not replace the historical checkpoint and
provenance content above.

### Scope

The training data path in this project is not a single producer → schema →
consumer chain. Multiple generations of format coexist in the live tree.
This document distinguishes them and states which are formally specified.

### V2 schema — formal specification

`dataset_schema.py` is the workspace's explicit formal training-dataset
schema module identified by the current source search.

    FORMAT_VERSION = 2
    SUPPORTED_VERSIONS = {2}

Required fields (all lists, all the same length `N`):

| Field | Type | Constraint |
|---|---|---|
| `positions` | list | all `ChessBoard` instances |
| `policies` | list | integers in `[0, NUM_MOVES)` |
| `values` | list | reals in `[-1.0, +1.0]` |
| `move_uci` | list | valid UCI strings (4 or 5 chars; promotion in `qrbn`) |
| `source` | list | integers in `{0, 1, 2}` |
| `white_elo` | list | strings |
| `black_elo` | list | strings |
| `opening` | list | strings |
| `date` | list | strings |
| `game_ids` | list | integers, monotonically nondecreasing |
| `game_starts` | list | booleans |

Additional invariant for `game_ids` / `game_starts`:

- the first sample of each `game_id` must have `game_starts=True`
- each `game_id` may have at most one `game_starts=True`

The dict must also contain `format_version == 2`.

`validate_integrity(data, num_moves)` enforces all of the above. It is
called explicitly by producers; it is not invoked automatically by
`train.py`.

### Producers

| Producer | Representation | Sets `format_version=2` | Calls `validate_integrity` in inspected code |
|---|---|---|---|
| `prepare_pgn_with_policy.py` | V2 dict | Yes | Yes |
| `generate_themed_data.py` | V2 dict | Yes | Yes |
| `generate_capture_data.py` | representation not established by reviewed output | Yes | No evidence |
| `personal_coach.py` | representation not established by reviewed output | Yes | No evidence |
| `merge_and_train.py` | representation not established by reviewed output | Yes | No evidence |
| `convert_all.py` | legacy tuple records | No | No |
| `pgn_learner.py` | legacy outer 2-tuple | No | No |

**Legacy producers in detail:**

- `convert_all.py` writes `training_data.pkl` as a list of records of the
  form `(ChessBoard, policy_index, move_uci, value, source, white_elo,
  black_elo, opening, date)`. Value convention in this producer:
  `1-0 → +1.0`, `0-1 → -1.0`, other → `0.0`. That is a White-perspective
  sign. `convert_all.py` does not import `dataset_schema`.
- `pgn_learner.py` writes `pgn_data.pkl` as an outer 2-tuple
  `(all_positions, all_results)`. This is a legacy format; it is not V2
  and is not schema-validated. The current `train.py` tuple branch does
  **not** directly interpret this outer two-element structure as its
  normal tuple-record format.

### Consumer: `train.py`

`train.py:load_dataset(path)` accepts:

- a dict containing at least `{'positions', 'values', 'policies'}`; extra
  keys are ignored
- a list of tuples of length ≥ 4, in the form `(position, policy, …,
  value)`

It performs its own validation inline:

- numeric value targets
- value targets in `[-1, 1]`
- policy indices as integers in `[0, NUM_MOVES)`
- length equality across the three lists

`train.py` does **not** import `dataset_schema` and does **not** call
`validate_integrity`. A V2 dict will load. A loose dict will load. A
legacy tuple list will load. Malformed metadata fields in a dict (missing
`game_ids`, wrong `source` values, mismatched `move_uci` strings) will not
be caught by `train.py`.

### Other consumers

- `dataset_audit.py` accepts a 3-key dict or a list of tuples. It does not
  import `dataset_schema`.

### Value target construction

`training_targets.py` contains value-target generation logic. The
reviewed live output does not establish every current caller of this
module.

- `VALUE_TARGET_MODE = "blended"` is defined in the module.
- The module contains White-signed static-evaluation components, including
  `material_score()`, which uses the standard sign convention
  (`P N B R Q` positive for White; `p n b r q` negative).
- The final perspective of the value target delivered to
  `DualNet.train(...)` is **not verified** by the reviewed output. The
  presence of White-signed components does not establish that the
  produced target is White-perspective rather than side-to-move.

Neither `dataset_schema.py` nor `train.py` defines a perspective.

### Validation-enforcement gap — OPEN

`dataset_schema.py` provides a strict formal validator. `train.py` does
not invoke it. A dataset can be labeled `format_version = 2` and still
bypass the formal schema when consumed by `train.py`.

This is an identified engineering issue in the training pipeline, not
merely a documentation note. It is recorded here as **OPEN** and is
outside the scope of this documentation pass to change.

### What is established by the reviewed source

- `dataset_schema.py` is the formal schema module identified by the
  source search.
- Two producers call `validate_integrity`.
- Three producers set `format_version = 2` without importing
  `dataset_schema`.
- `train.py` accepts three representations and does not enforce the
  schema.
- `training_targets.py` exists and contains value-target generation logic
  with White-signed static-evaluation components.
- `convert_all.py` produces legacy tuple records with a White-signed value
  convention.

### What is not established by the reviewed source

- Whether the entire producer → train chain currently uses one format in
  production, or a mixture.
- Whether the value target handed to `DualNet.train(...)` is White-signed
  or side-to-move-signed at the final hand-off.
- Whether `pgn_data.pkl` (2-tuple) is still consumed by any active
  training path.
- Whether the "V2-labeled but unvalidated" producers emit schema-correct
  V2 content.
- No inspected live source establishes a complete lineage from the current
  `chess_nn.pkl` artifact back to a specific dataset representation or
  version.

These are open questions. They are not resolved by this document.

### Non-goals

- This document does not declare a single "authoritative current format."
  The live tree does not support that claim.
- This document does not define the semantic perspective of the value
  target. That belongs to the training-target audit (P5.17 / P5.18).
