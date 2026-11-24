# NEURAL NETWORK

**Project:** Chess AI
**Updated:** 2026-09-11
**Source of truth:** live `~/chess_ai/nn.py`

This document describes the neural network implementation in the active
workspace. It does not describe training results, training data lineage,
or model quality. Those are separate concerns.

---

## 1. Scope

`nn.py` defines a dual-head neural network (`DualNet`) used by the search
engine for leaf evaluation and move ordering. It is a small NumPy
implementation, not a PyTorch model. Inference and a minimal SGD training
loop are both implemented in the same file.

The module is responsible for:

- feature encoding of a board position
- a value head (scalar, tanh-bounded)
- a policy head (per-move logits)
- pickle-based model save/load
- incremental feature updates via `FeatureCache`

The module is not responsible for:

- defining the semantics of the training value target
- the perspective of the value output
- how the search engine combines value output with static evaluation

---

## 2. Architecture

`DualNet.INPUT_SIZE = 783`

Layer stack (NumPy, float32):

    input (783)
        │
        ├─ linear → 512   → ReLU   (self.w1, self.b1)
        │
        ├─ linear → 256   → ReLU   (self.w2, self.b2)
        │
        ├─ value head:
        │       linear → 1 → tanh  (self.v_w, self.v_b)
        │       output range: (-1, +1)
        │
        └─ policy head:
                linear → NUM_MOVES  (self.p_w, self.p_b)
                output: raw logits, no activation

`NUM_MOVES` is imported from `move_helpers` and equals `20480`.

Default hidden sizes: `hidden1=512`, `hidden2=256`.

The policy head produces one raw logit for every entry in the global
20480-move index space. Legal-move filtering happens in the search layer.
The policy head is not restricted to legal moves for the current position;
the search indexes into it via `move_to_index(move)`.

---

## 3. Feature encoding (783 floats)

| Range | Feature | Encoding |
|---|---|---|
| 0–767 | Piece placement | 64 squares × 12 piece types, one-hot. `_FEATURE_IDX[sq, pt] = sq * 12 + pt`. Piece types: `P N B R Q K p n b r q k` |
| 768 | Side to move | `+1.0` if White to move, `-1.0` if Black to move |
| 769 | White kingside castling | `1.0` / `0.0` |
| 770 | White queenside castling | `1.0` / `0.0` |
| 771 | Black kingside castling | `1.0` / `0.0` |
| 772 | Black queenside castling | `1.0` / `0.0` |
| 773–780 | En-passant file | one-hot over 8 files; all zeros if no en-passant square |
| 781 | Repetition flag | `1.0` if position count ≥ 3 and `board.track_repetition`, else `0.0` |
| 782 | Halfmove clock | `halfmove_clock / 100.0` |

Index 768 is the explicit side-to-move feature in the NN input encoding.

---

## 4. Forward pass

`DualNet.forward(x)`:

    h1 = ReLU(x @ w1.T + b1)
    h2 = ReLU(h1 @ w2.T + b2)
    value  = tanh(h2 @ v_w.T + v_b)         # shape (batch,)
    policy = h2 @ p_w.T + p_b               # shape (batch, NUM_MOVES)

`value` is returned as a 1-D array. `policy` is returned as a 2-D array;
callers that want a flat vector apply `.ravel()` or index `[0]`.

---

## 5. Evaluation API

`DualNet.evaluate(board)`:

- Uses `board._nn_cache` (`FeatureCache`) if present.
- If a `MoveDelta` is pending on the board, applies it incrementally.
- If the cache is missing or the hash does not match the board, rebuilds
  the full feature vector.
- Clears `board._pending_delta` before returning. This is an invariant:
  after `evaluate()`, `board._pending_delta is None`.
- Returns `(float(value[0]), policy[0])`.

The returned policy is a 1-D NumPy array of length `NUM_MOVES`.

Feature cache:

- `FeatureCache` holds a 783-float vector and the board hash it was built
  from.
- Incremental updates (`apply_delta`) modify only the changed squares plus
  the meta features at indices 768–782.
- `DEBUG_INCREMENTAL = False` by default. When set to `True`, incremental
  updates are validated against a fresh full rebuild and any mismatch
  raises `AssertionError`.

---

## 6. Save / load contract

`DualNet.save(path)` pickles a dict:

    {
        'w1', 'b1',    # layer 1
        'w2', 'b2',    # layer 2
        'v_w', 'v_b',  # value head
        'p_w', 'p_b',  # policy head
    }

`DualNet.load(path)`:

- Returns `False` if the file is missing or unpickleable.
- Returns `False` if `data['w1'].shape[1] != INPUT_SIZE` (input size mismatch).
- If `'v_w'` is absent, treats the file as an old single-head model and
  converts it: copies `w1, b1, w2, b2`, maps `w3/b3` (if present) onto
  `v_w/v_b`. Returns `True` on success.
- Otherwise requires `w1, w2, v_w, p_w, b1, b2, v_b, p_b` to all be present,
  else returns `False`.
- Reshapes `v_w` and `v_b` if stored with a leading singleton axis.
- **Policy head reinit behavior**: if `p_w.shape[0] != NUM_MOVES`, the head
  is replaced with fresh random weights after printing a warning.

Important consequence: a successful `load()` does **not** by itself prove
the saved policy weights were retained. If the stored policy shape did not
match `NUM_MOVES`, the head is replaced with fresh weights. Consumers that
depend on policy behavior should verify the policy output is consistent
with the loaded model, not merely that `load()` returned `True`.

### Shape validation

The loader explicitly rejects an input-size mismatch for `w1` and checks
the policy-head row count against `NUM_MOVES`. It does not perform a
complete cross-layer shape validation of every stored tensor before
assignment.

---

## 7. Training (minimal SGD)

`DualNet.train(positions, targets_value, targets_policy, epochs=10, lr=0.001, batch_size=512, value_loss_weight=1.0)`

- Value loss: mean squared error against `targets_value`.
- Policy loss: softmax cross-entropy against `targets_policy`.
- If `targets_policy` is a 1-D array of integer move indices, it is
  converted to one-hot (B-030 fix).
- Optimizer: plain SGD with the supplied `lr`. No momentum, no Adam.
- Prints loss every 5 epochs.

This is a minimal reference trainer. It does not implement the training
pipeline (data loading, validation split, checkpoints, model selection).

### Value head target semantics

`nn.py` does **not** define what the value head represents. It trains on
whatever `targets_value` the caller supplies and returns the raw `tanh`
output at inference. Therefore:

- The perspective of the value output (White-perspective, side-to-move,
  or anything else) is determined entirely by the training data, not by
  the architecture.
- A trained model's value head reflects the convention of the pipeline
  that produced its training targets.
- Verifying the value head's perspective requires inspecting the training
  data pipeline, not `nn.py`.

`nn.py` defines the value output range and training interface, but it does
not define the semantic convention of the target. The target-producing
pipeline must be audited before any perspective is declared authoritative.

---

## 8. Relationship to search

The search engine consumes the network through `_get_nn_eval`:

    val, pol = self.nn.evaluate(board)
    pol = np.asarray(pol).ravel()
    top_dict = self._top_k_dict(pol, TOP_POLICY_N)

- `val` is used in the leaf combination
  `combined_eval(board) + int(val * NN_SCALE)` with `NN_SCALE = 800`.
- `pol` is used by `_order_moves` to rank moves using the policy logits.

The search layer currently consumes `val` directly; the NN module itself
does not declare whether that value is White-perspective,
Black-perspective, or side-to-move-perspective. If the NN's value output
and `combined_eval` are not on the same perspective, the leaf value can
be inconsistent. This is the subject of the open evaluator investigation.

---

## 9. Current model artifact

`chess_nn.pkl` in the live workspace:

- Size: approximately 23 MiB.
- Loads successfully via `DualNet.load('chess_nn.pkl')` returning `True`.
- Policy output shape after ravel: `20480` (matches `NUM_MOVES`).
- Value output is finite on tested positions.
- `evaluate()` does not alter the board's position hash.

Loading alone does not establish value-head correctness or strength.

---

## 10. Open items

- **Value-head perspective — OPEN.** `nn.py` does not define what the
  value represents. The KQK probes returned small negative values for
  four different (material, side-to-move) orientations. That is
  consistent with a training-target problem or an uninformative head,
  not with a specific architectural defect. A wider probe is required
  before drawing a conclusion.
- **Policy-head shape mismatch — warning + reinitialization.** When the
  stored policy head has a different row count than `NUM_MOVES`, `load()`
  prints `WARNING: Policy size mismatch, reinitializing policy head.`,
  replaces the head with fresh random weights, and still returns `True`.
  A successful load with a mismatched policy head is not a failed load,
  but it is also not a guaranteed-faithful load. Callers should not treat
  the return value alone as proof of a fully-restored model.
- **Training pipeline.** The training data pipeline, target construction,
  and model selection policy are outside `nn.py`. This document does not
  claim the pipeline is correct.

---

## 11. Non-goals

- This document does not describe training data or the training pipeline.
- This document does not describe the search-side leaf combination beyond
  what is needed to state the interface; see `SEARCH_ALGORITHM.md`.
- This document does not claim a strength level for the current model.
- `distilled_nn.pkl` and `chess_nn_master.pkl` are not described here.
  `chess_nn.pkl` is the production model artifact referenced by the
  current architecture documentation.

---

## 2026-09-12 — Model-artifact correction

The §11 statement above:

    `chess_nn.pkl` is the production model artifact referenced by the
    current architecture documentation.

The §11 statement is accurate for the UCI runtime path, but it is not
a complete description of the current runtime model consumers.

### Live evidence

| Consumer | Line | Artifact loaded | Role |
|---|---|---|---|
| `web_control.py` | 22, 1109 | `distilled_nn.pkl` | web runtime |
| `uci_engine.py` | 14, 41, 71, 114 | `chess_nn.pkl` | UCI runtime |

All other model-load sites identified in the current tree use
`chess_nn.pkl` or `chess_nn_master.pkl`.

### What this supersedes

The §11 sentence "`chess_nn.pkl` is the production model artifact
referenced by the current architecture documentation" is incomplete
for the current runtime. `chess_nn.pkl` is the UCI runtime artifact.
`web_control.py` uses `distilled_nn.pkl`.

The intent behind the original §11 wording is not inferred here. Only
the current live-source reality is recorded.

### What this does not change

- `nn.py` itself is unchanged.
- Sections 1–8, and the non-artifact portions of Sections 10–11, are
  not affected by this correction. Section 9 is specifically about the
  current model artifact and is the relevant historical section for
  this correction.
- The §11 non-goal on `distilled_nn.pkl` and `chess_nn_master.pkl`
  remaining outside this document is preserved.

### Status

The single-artifact statement in §11 is **contradicted by live
source**. The canonical-artifact decision remains **OPEN**.

### Cross-references

- `docs/ARCHITECTURE.md` — "2026-09-12 — Model-artifact correction".
- `docs/AUDIT_STATUS.md` — "2026-09-12 — B-022 status correction".
- `docs/BUG_TRACKER.md` — "2026-09-12 — B-022 status correction".
- `docs/CHANGELOG.md` — "2026-09-12 — B-022 status correction".
- `docs/TRAINING_GUIDE.md` — documents the model-artifact split.
- `docs/DEVELOPER_GUIDE.md` — "Current known contradiction".
- `docs/WORKFLOW.md` — safety implication for `train_auto.sh`.


---

## 2026-09-27 — Line-reference correction

The 2026-09-12 model-artifact correction cites:

    web_control.py | 22, 1109 | distilled_nn.pkl

The current live lines are 25 and 2304. The underlying claim is correct;
only the citations are stale. `uci_engine.py:14, 41, 71, 114` (from the
same table) remains accurate.

### Cross-references

- `docs/AUDIT_STATUS.md` — current verified state.
- `docs/TRAINING_GUIDE.md` — model-artifact split.
