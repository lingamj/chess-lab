# TRAINING GUIDE

**Project:** Chess AI
**Updated:** 2026-09-12
**Source of truth:** live `~/chess_ai/` training scripts

This document describes the training scripts and dataset/model paths
observed in the active workspace. It does not declare a single
authoritative training workflow, because the live tree contains multiple
incompatible training paths and representations.

---

## 1. Scope

The workspace contains multiple training entry points. They differ in:

- the dataset representation they read
- the value-handling convention they use
- the model path they write
- whether they promote a new model or overwrite the active model directly
- whether checkpoints or backups are created

This document records observed behavior. The question of which path should
be authoritative remains part of the dedicated training-pipeline audit
(P5.18).

---

## 2. Training entry points

| Script | Observed input | Observed output | Model promotion / activation |
|---|---|---|---|
| `run_training.sh` | calls `generate_themed_data.py`, then reads `training_data_merged.pkl` and merges into `training_data.pkl` | `training_data.pkl` (V2 master) | invokes `train.py training_data.pkl 10 0.0005 512 chess_nn_master.pkl` |
| `train.py` | loose dict or list/tuple records | `chess_nn_master.pkl` by default | after successful training, copies `chess_nn_master.pkl` to `chess_nn.pkl`; backs up the prior active model |
| `train_auto.sh` | piped answers to `multi_train.py` | delegated | checks for `distilled_nn.pkl` and copies it to `chess_nn.pkl` |
| `multi_train.py` | dict with `positions/values/policies` or list records interpreted by its loader | `chess_nn.pkl` | no separate promotion layer observed; writes active model directly |
| `merge_and_train.py` | `training_data_20k.pkl` + `capture_training.pkl` | `chess_nn_master.pkl` | no active-model promotion observed |
| `train_capture.py` | `training_data_5k_v2.pkl` + `capture_training.pkl` | checkpoints + `chess_nn_master.pkl` | no active-model promotion observed |
| `time_train.py` | every `training_data_*.pkl` file it discovers | `chess_nn.pkl` | no backup/promotion layer observed |
| `incremental_train.py` | default `training_data_merged.pkl`, interpreted as 3-tuples | `chess_nn.pkl` | no backup/promotion layer observed |
| `train_incremental.py` | per-file list records interpreted by its loader | `chess_nn.pkl` | no backup/promotion layer observed |
| `update_model.sh` | `training_data.pkl` | `chess_nn_master.pkl` | none; reports completion without checking `train.py` exit status |
| `auto_sync_train.py` | fetches games from Lichess and Chess.com, writes `training_data.pkl` | delegates training via `train.py` | references `distilled_nn.pkl`; uses legacy flag-style `train.py` invocation |

Additional training/model-related scripts:

- `run_pipeline.sh`, `run_pipeline_10k.sh`,
  `run_pipeline_20k_pgn.sh`, and `run_pipeline_safe.sh` invoke `train.py`
  using the older flag-based interface (see §7) and reference
  `distilled_nn.pkl`.
- `update_all.sh` contains embedded training code, including a default
  output model of `chess_nn.pkl`.
- `arena.py` loads model files for comparison; it is evaluation/comparison,
  not training.

---

## 3. Dataset representations and loader contracts

The live tree contains multiple dataset representations and multiple
loader contracts. They must not be treated as interchangeable.

### V2 dictionary

The formal V2 schema is defined by `dataset_schema.py` and includes
`format_version` plus the 11 required dataset fields documented in
`DATASET_FORMAT.md`.

`train.py` accepts a dict containing at least:

- `positions`
- `values`
- `policies`

Extra fields are ignored by `train.py`.

### List-record formats

Several scripts consume list records, but their positional conventions
are not identical.

`convert_all.py` writes records of the form:

    (ChessBoard, policy_index, move_uci, value,
     source, white_elo, black_elo, opening, date)

Here:

- `item[1]` is the policy index
- `item[2]` is UCI
- `item[3]` is the value

By contrast, `multi_train.py` and `train_incremental.py` interpret their
list input as records where:

- `item[0]` is the board
- `item[1]` is a centipawn score
- `item[2]` is UCI

They derive the policy index from the UCI move.

Therefore the phrase "9-tuple format" does not identify one uniform
semantic schema across the workspace.

### Three-tuple loader

`incremental_train.py` expects `(position, value, policy)` records and
defaults to reading `training_data_merged.pkl`.

However, `generate_themed_data.py` writes `training_data_merged.pkl` as a
V2 dictionary and calls `dataset_schema.validate_integrity` before
writing. `run_training.sh` reads that same file as its source of new data
and merges it into `training_data.pkl`.

The reviewed source therefore does not establish that
`training_data_merged.pkl` is ever a three-tuple file when
`incremental_train.py` runs.

---

## 4. Value handling conventions

The workspace contains multiple value-generation and value-consumption
behaviors.

### Blended target generation

`training_targets.py` defines:

    VALUE_TARGET_MODE = "blended"

and contains `blended_value(white_result, board)`.

`generate_themed_data.py` imports `blended_value` and uses it when
constructing dataset values.

The full final sign convention of the blended target was not established
by the reviewed source excerpt.

### Game-result values

`convert_all.py` writes:

- `1-0 → +1.0`
- `0-1 → -1.0`
- other → `0.0`

That producer therefore writes a White-signed game-result convention.

### Score-to-value conversion

`multi_train.py` and `train_incremental.py` contain:

    value_from_score(score_cp) =
        max(-1.0, min(1.0, score_cp / 400.0))

No side-to-move sign conversion is present in the reviewed function.

If the incoming score is White-perspective, the resulting value is
White-perspective. If the incoming score is side-to-move, the resulting
value is side-to-move. The reviewed source does not establish which.

### `train.py` passthrough

`train.py:load_dataset()` accepts numeric values already present in the
dataset and **rejects** values outside `[-1, 1]`. It does not establish
their perspective and does not clip them into range.

There is no central component in the reviewed training paths that
reconciles all these value conventions.

---

## 5. Model save, promotion, and activation paths

The model lifecycle in the reviewed tree has three distinct stages:

    trainer output  →  promotion artifact  →  runtime-consumed artifact

Not every path implements all three. The reviewed tree shows:

    multi_train.py     → chess_nn.pkl           → (no promotion stage)
    train.py           → chess_nn_master.pkl    → chess_nn.pkl
    train_auto.sh      → expects distilled_nn.pkl → chess_nn.pkl
    web_control.py     → (loads) distilled_nn.pkl
    uci_engine.py      → (loads) chess_nn.pkl

The producer, promotion, and consumer stages do not share a single
artifact name, and the runtime consumers do not agree on which artifact
is authoritative.

### `train.py` — master then activation

`train.py` accepts a fifth argument `output_model` and saves the trained
model to that path. The default is `chess_nn_master.pkl`.

After successful training, the following promotion block runs:

1. if `chess_nn.pkl` exists, it is copied to a timestamped
   `chess_nn_backup_YYYYMMDD_HHMMSS.pkl`;
2. `chess_nn_master.pkl` is copied to `chess_nn.pkl`.

Note: the promotion block specifically references
`chess_nn_master.pkl`, not the caller-provided `output_model`. A custom
output path is saved but not promoted.

Activation is gated by the Python-level `training_ok` result, which is
set true only after `net.train(...)` returns successfully.

This is the clearest explicit active-model promotion path observed.

### `train_auto.sh` — shell-copy activation

`train_auto.sh` invokes `multi_train.py` by piping answers into it:

    { echo "5"; echo ""; echo ""; echo "6"; } | python multi_train.py

The shell script contains:

- no `set -e`
- no `set -u`
- no `PIPESTATUS` check
- no `$?` check after the pipeline

The only success test in the script is:

    if [ -f "distilled_nn.pkl" ]; then
        cp distilled_nn.pkl chess_nn.pkl
    else
        echo "ERROR: Training failed – distilled_nn.pkl not created."
    fi

`multi_train.py` writes `chess_nn.pkl`. It does not write
`distilled_nn.pkl`. A `distilled_nn.pkl` file is already present in the
live tree, and no current trainer writes that file.

Because a pre-existing `distilled_nn.pkl` is present and no current
trainer writes it, a successful `multi_train.py` run can be followed by
replacement of its newly written `chess_nn.pkl` with that pre-existing
artifact. The script performs no provenance or freshness check on the
file before copying it.

### Direct active-model writes

The reviewed source shows direct writes to `chess_nn.pkl` from:

- `multi_train.py`
- `time_train.py`
- `incremental_train.py`
- `train_incremental.py`

No automatic timestamped active-model backup was observed in those
scripts.

These are therefore higher-risk activation paths under the project's
production safety boundary.

`update_all.sh` also contains embedded training code with `chess_nn.pkl`
as its default output; its overall invocation semantics require separate
audit.

### Master-only training paths

`merge_and_train.py` and `train_capture.py` write
`chess_nn_master.pkl` and do not show active-model promotion in the
reviewed portions.

---

## 6. Resume and checkpoint behavior

### `train.py`

If the requested output model exists, `train.py` loads it before training
and therefore resumes from that model.

The default output is `chess_nn_master.pkl`.

Training success is represented by the Python-level `training_ok` result,
which is set true only after `net.train(...)` returns successfully.

SIGINT/SIGTERM handling prints:

    Stopping (model NOT saved).

### `train_capture.py`

The reviewed source creates a `checkpoints/` directory and defines
checkpoint saving alongside master-model saving.

It also uses:

- smoke epochs
- full epochs
- fixed batch sizes
- a fixed learning rate
- optional reproducibility with a fixed seed

The detailed checkpoint restart semantics require the remaining body to
be audited before being described as resumable.

### Other trainers

No unified checkpoint policy was established for the remaining direct
training scripts.

---

## 7. Confirmed live risks and incompatibilities

The reviewed source establishes several concrete risks.

### Dataset loader incompatibility

`incremental_train.py` expects 3-tuples and defaults to
`training_data_merged.pkl`. The reviewed producer
(`generate_themed_data.py`) writes that file as a V2 dictionary. A run of
`incremental_train.py` on the produced file would iterate over dictionary
keys rather than triples.

### Mixed 9-tuple semantics

`convert_all.py` writes policy at tuple index 1 and value at index 3.

`multi_train.py` and `train_incremental.py` interpret tuple index 1 as a
centipawn score and derive policy from tuple index 2.

These are incompatible positional contracts and require explicit
reconciliation before the associated data paths can be treated as one
format.

### Broad glob with heterogeneous datasets

`time_train.py` automatically discovers every `training_data_*.pkl`
file but its loader expects iterable `(position, value, policy)` records.
The live tree contains multiple dataset representations, so this broad
glob is not established as representation-safe.

### Direct active-model overwrite

Four reviewed scripts write directly to `chess_nn.pkl` without an
automatic timestamped backup.

### `train_auto.sh` model-replacement risk

`train_auto.sh` runs `multi_train.py` (which writes `chess_nn.pkl`) and
then copies `distilled_nn.pkl` over `chess_nn.pkl` if a file of that name
exists.

The script contains no error handling around the pipeline and does not
check the exit status of `multi_train.py`. It has no `set -e`, no
`PIPESTATUS` check, and no `$?` check.

`multi_train.py` writes `chess_nn.pkl`; no current trainer writes
`distilled_nn.pkl`. Because a pre-existing `distilled_nn.pkl` is present
in the live tree and no current trainer writes it, a successful
`multi_train.py` run can be followed by replacement of its newly written
`chess_nn.pkl` with that pre-existing artifact. The script performs no
provenance or freshness check before copying.

### Artifact-production gap

No literal source reference in the reviewed `*.py` / `*.sh` files writes
to `distilled_nn.pkl`. All observed literal references are loads,
existence checks, model-path declarations/defaults, command examples, or
copies; no literal write/save/dump operation to that filename was found.

### Runtime-consumer inconsistency

Different runtime consumers load different model artifacts:

- `web_control.py` sets `MODEL_PATH` to `distilled_nn.pkl`.
- `uci_engine.py` sets `MODEL_PATH` to `chess_nn.pkl`.

Because `distilled_nn.pkl` has no literal producer in the reviewed tree,
`web_control.py` is configured to load a model artifact whose origin is
not established by any current training script.

Until a single active-model contract is defined, a successful training
run and its activation cannot be assumed to affect every runtime consumer
consistently.

### Training-success reporting gap

Shell wrappers can report successful completion without validating the
trainer's exit status. The reviewed wrappers exhibiting this are:

- `run_training.sh` checks the exit status of `generate_themed_data.py`
  and aborts on failure. It does not check the exit status of the
  subsequent `python train.py ...` invocation.
- `update_model.sh` invokes `python train.py ...` and then immediately
  prints `Done. Master model saved to $MODEL.` with no exit-status check.

In both scripts, the final success message is not, by itself, evidence
that training succeeded.

### Embedded training path

`update_all.sh` contains embedded training code whose default output
model is `chess_nn.pkl`. Its invocation semantics and any backup or
promotion behavior require a separate audit before being treated as a
supported training path.

### Schema-enforcement gap

`train.py` does not invoke `dataset_schema.validate_integrity()`.
Therefore a dataset can be labeled V2 while bypassing the formal schema.

### Multiple value conventions

The reviewed workspace contains blended targets, direct game-result
values, score-derived values, and passthrough values without a central
perspective contract.

### `train.py` output-model / promotion contract inconsistency

`train.py` accepts a caller-provided `output_model` argument and saves
the trained model to that path. However, the promotion block specifically
checks and copies `chess_nn_master.pkl`.

For the default invocation this happens to align. For a custom output
path, the saved model is not the model that gets promoted to
`chess_nn.pkl`.

### Legacy flag-style `train.py` CLI incompatibility

The current `train.py` accepts positional arguments only:

    train.py <dataset.pkl> [epochs] [lr] [batch_size] [output_model]

Five callers invoke it with the older flag-based interface:

- `run_pipeline.sh`
- `run_pipeline_10k.sh`
- `run_pipeline_20k_pgn.sh`
- `run_pipeline_safe.sh`
- `auto_sync_train.py`

These callers use forms such as:

    python train.py --mode supervised --epochs 20 --lr 0.001 \
        --batch-size 128 --data-file training_data_5k.pkl

`train.py` does not parse `--mode`, `--data-file`, or the other flags.
Running these scripts against the current trainer will not invoke the
trainer with the intended arguments.

### Unvalidated automation path — `auto_sync_train.py`

`auto_sync_train.py` combines external game ingestion, dataset mutation,
and training automation:

    fetch from Lichess / Chess.com
        ↓
    write training_data.pkl
        ↓
    invoke train.py via subprocess

It also uses the legacy flag-based `train.py` interface described above,
and references `distilled_nn.pkl`.

Because this path combines external synchronization, dataset mutation,
and model training, it requires an explicit production-safety review
before it can be considered an approved automated workflow.

### Dataset/model transaction separation

`run_training.sh` first merges new data into `training_data.pkl`
(atomically) and only afterward invokes `train.py`. A training failure
therefore leaves the master dataset updated while the active model
remains unchanged.

Dataset state and model activation do not advance atomically as one
transaction.

### All-zero value targets in themed tactical files

`training_data_tactical.pkl` (70 samples) and `training_data_checkmate.pkl`
(158 samples) were measured during the 2026-10-11 audit to have all-zero
value targets. Every value inspected in both files was `0.0`. Their theme
generators are the `theme_tactical` and `theme_checkmate` filters in
`generate_themed_data.py`, which test position properties at inclusion time
but write labels via `blended_value(white_result, pos)` from the enclosing
game. In the reviewed self-play loop, `white_result` is set to `0.0` for
both draws and move-cap termination.

### `blended_value()` phase-dependent formula and draw/unfinished collapse

`training_targets.py` implements `blended_value(white_result, board)` with
`VALUE_TARGET_MODE = "blended"` as the default:

    ph = phase(board)
    static_weight = 0.6 - 0.4 * ph
    result_weight = 1.0 - static_weight
    static_part = math.tanh(static_eval(board) / 400.0)
    blended = result_weight * white_result + static_weight * static_part

The function returns literal `0.0` for any position where
`white_result == 0.0`, before the blend is evaluated. That condition is
reached for both true draws and, in the reviewed self-play generator,
move-cap termination. The weight applied to game outcome therefore varies
between 0.4 in the opening phase and 0.8 in the endgame phase.

### Legacy three-field dataset outside the current schema

`training_data_5k_v2.pkl` contains only `positions`, `values`, and
`policies`. It does not contain the eleven fields enumerated by
`dataset_schema.FIELDS` and would not pass `validate_integrity()`. The
file is consumed by `train_capture.py`, which does not invoke that
validator. `train.py` also does not call `validate_integrity()`; see the
existing `Schema-enforcement gap` subsection above.

---

## 8. What the reviewed source does not establish

- Which training path is intended to be authoritative.
- Whether the final value target is White-perspective,
  side-to-move-perspective, or another convention.
- Whether the current `chess_nn.pkl` was produced by `train.py`,
  `multi_train.py`, `time_train.py`, `incremental_train.py`,
  `train_incremental.py`, or another path.
- Which artifact is intended to be the canonical active model, given that
  `web_control.py` and `uci_engine.py` reference different files.
- Whether `distilled_nn.pkl` is intended to exist as a distinct artifact
  or is a legacy name whose producer has been removed.
- Whether every `training_data_*.pkl` file is compatible with
  `time_train.py`.
- Whether `training_data_merged.pkl` is intended to be a three-tuple
  dataset for `incremental_train.py` or a V2 dictionary for another path.
- Whether the full `blended_value()` implementation produces a value in
  the same perspective consumed by search.
- Whether the current model artifact has complete dataset lineage.
- Whether the direct-overwrite paths are intentional legacy tools or
  unsupported production workflows.
- Whether the legacy flag-style callers are intended to be maintained,
  migrated, or retired.

---

## 9. Non-goals

- This document does not recommend a single training workflow.
- This document does not modify any training or model-promotion script.
- This document does not define the value-target perspective contract.
  That belongs to the P5.17/P5.18 training-target audit.
- This document does not define a canonical dataset format; see
  `DATASET_FORMAT.md`.
- This document does not claim any model-strength level.
