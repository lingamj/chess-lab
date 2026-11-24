#!/usr/bin/env python3
"""
Capture training script — merge, validate, and train on capture data.
Phase 1 stable version: memory‑friendly filtering, model checks, epoch saves,
checkpoint offset, interrupt safety, optional reproducibility.
"""

import os, sys, pickle, time, random, numpy as np
from nn import DualNet
from move_helpers import NUM_MOVES
from board import ChessBoard          # for isinstance check

# Record start time for training report
overall_start = time.time()

# Optional reproducibility
SEED = 42
if SEED is not None:
    random.seed(SEED)
    np.random.seed(SEED)

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
BASE_DATASET      = "training_data_5k_v2.pkl"
CAPTURE_DATASET   = "capture_training.pkl"
MASTER_MODEL      = "chess_nn_master.pkl"
INITIAL_MODEL     = "chess_nn.pkl"

SMOKE_EPOCHS      = 1
SMOKE_BATCH       = 16
FULL_EPOCHS       = 3
FULL_BATCH        = 32
LEARNING_RATE     = 0.0005

CHECKPOINT_PREFIX = "checkpoint"
os.makedirs("checkpoints", exist_ok=True)   # ensure checkpoint folder exists

# ----------------------------------------------------------------------
# 1. Startup checks
# ----------------------------------------------------------------------
print("=" * 56)
print("Capture Training")
print("=" * 56)
print("Checking datasets...")

for path in [BASE_DATASET, CAPTURE_DATASET, INITIAL_MODEL]:
    if not os.path.exists(path):
        sys.exit(f"ERROR: Missing file: {path}")
print("All required files found.\n")

# ----------------------------------------------------------------------
# 2. Dataset validation
# ----------------------------------------------------------------------
def load_and_check(path, name):
    with open(path, "rb") as f:
        data = pickle.load(f)

    if not isinstance(data, dict):
        raise SystemExit(f"ERROR: {name} is not a dict (got {type(data).__name__})")

    required = {"positions", "values", "policies"}
    if not required.issubset(data.keys()):
        raise SystemExit(f"ERROR: {name} missing keys: {required - set(data.keys())}")

    pos = data["positions"]
    val = data["values"]
    pol = data["policies"]

    if not (len(pos) == len(val) == len(pol)):
        raise SystemExit(f"ERROR: {name} length mismatch: pos={len(pos)}, val={len(val)}, pol={len(pol)}")

    if len(pos) == 0:
        raise SystemExit(f"ERROR: {name} is empty")

    # Safer type check using isinstance
    if not isinstance(pos[0], ChessBoard):
        raise SystemExit(f"ERROR: {name} positions[0] is not a ChessBoard (type={type(pos[0]).__name__})")

    # Quick policy check on first few
    for i in range(min(5, len(pol))):
        if not isinstance(pol[i], (int, np.integer)) or not (0 <= pol[i] < NUM_MOVES):
            raise SystemExit(f"ERROR: {name} invalid policy at index {i}: {pol[i]}")

    print(f"  {name:20s}: {len(pos)} samples")
    return data

# ----------------------------------------------------------------------
# 3. Load datasets
# ----------------------------------------------------------------------
base = load_and_check(BASE_DATASET, "Base dataset")
cap  = load_and_check(CAPTURE_DATASET, "Capture dataset")

# ----------------------------------------------------------------------
# 4. Merge (only core keys, single extend per list)
# ----------------------------------------------------------------------
positions = base["positions"].copy()
values    = base["values"].copy()
policies  = base["policies"].copy()

positions.extend(cap["positions"])
values.extend(cap["values"])
policies.extend(cap["policies"])

print(f"\nMerged samples: {len(positions)}")

# ----------------------------------------------------------------------
# 5. Memory‑friendly filtering
# ----------------------------------------------------------------------
positions2, values2, policies2 = [], [], []
rejected = 0
for p, v, pol in zip(positions, values, policies):
    if isinstance(pol, (int, np.integer)) and 0 <= pol < NUM_MOVES:
        positions2.append(p)
        values2.append(v)
        policies2.append(pol)
    else:
        rejected += 1

positions = positions2
values    = values2
policies  = policies2

print(f"Valid samples : {len(positions)}")
print(f"Rejected      : {rejected}\n")

if len(positions) == 0:
    sys.exit("ERROR: No valid training samples after filtering.")

# ----------------------------------------------------------------------
# 6. Model loading & compatibility checks
# ----------------------------------------------------------------------
if not os.path.exists(MASTER_MODEL):
    import shutil
    shutil.copy2(INITIAL_MODEL, MASTER_MODEL)
    print(f"Created {MASTER_MODEL} from {INITIAL_MODEL}")

net = DualNet()
if not net.load(MASTER_MODEL):
    sys.exit("ERROR: Failed to load model")

if net.p_w.shape[0] != NUM_MOVES:
    sys.exit(f"ERROR: Model policy head size {net.p_w.shape[0]} != NUM_MOVES ({NUM_MOVES})")

print(f"Model OK")
print(f"Policy outputs : {net.p_w.shape[0]}\n")

# ----------------------------------------------------------------------
# 7. Training loop with checkpoint offset & interrupt handling
# ----------------------------------------------------------------------
def train_phase(name, epochs, batch_size, start_epoch=0):
    print(f"{name}")
    print("-" * 40)
    start_time = time.time()
    for epoch in range(1, epochs + 1):
        global_epoch = start_epoch + epoch
        epoch_start = time.time()
        try:
            net.train(positions, values, policies,
                      epochs=1, lr=LEARNING_RATE, batch_size=batch_size)
        except Exception as e:
            print(f"ERROR during training: {e}")
            raise

        elapsed = time.time() - epoch_start
        remaining = elapsed * (epochs - epoch)
        ckpt_path = os.path.join("checkpoints", f"checkpoint_epoch_{global_epoch:03d}.pkl")
        net.save(ckpt_path)
        net.save(MASTER_MODEL)

        print(f"Epoch {epoch}/{epochs} (global {global_epoch})  "
              f"Time={elapsed:.1f}s  Remaining~{remaining:.0f}s  "
              f"[saved {ckpt_path}]")

    total = time.time() - start_time
    print(f"Phase complete. Total time: {total:.0f}s\n")
    return total

# Top‑level interrupt handler
try:
    smoke_time = train_phase("Smoke Test", SMOKE_EPOCHS, SMOKE_BATCH, start_epoch=0)
    full_time = train_phase("Main Training", FULL_EPOCHS, FULL_BATCH,
                            start_epoch=SMOKE_EPOCHS)
except KeyboardInterrupt:
    print("\nTraining interrupted by user.")
    net.save(MASTER_MODEL)
    print(f"Latest model saved to {MASTER_MODEL}.")
    sys.exit(0)

total_time = smoke_time + full_time

# ----------------------------------------------------------------------
# 8. Write training report
# ----------------------------------------------------------------------
with open("training_report.txt", "w") as f:
    f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(overall_start))}\n")
    f.write(f"Finished: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))}\n")
    f.write(f"Duration: {total_time:.1f} seconds\n")
    f.write(f"Base dataset: {BASE_DATASET}\n")
    f.write(f"Base samples: {len(base['positions'])}\n")
    f.write(f"Capture dataset: {CAPTURE_DATASET}\n")
    f.write(f"Capture samples: {len(cap['positions'])}\n")
    f.write(f"Merged samples: {len(positions)}\n")
    f.write(f"Learning rate: {LEARNING_RATE}\n")
    f.write(f"Smoke epochs: {SMOKE_EPOCHS}\n")
    f.write(f"Main epochs: {FULL_EPOCHS}\n")
    f.write(f"Seed: {SEED}\n")
    f.write(f"Model: {MASTER_MODEL}\n")

# ----------------------------------------------------------------------
# 9. Final summary
# ----------------------------------------------------------------------
print("=" * 56)
print("Training Complete")
print("=" * 56)
print(f"Samples trained : {len(positions)}")
print(f"Epochs (total)  : {SMOKE_EPOCHS + FULL_EPOCHS}")
print(f"Smoke batch     : {SMOKE_BATCH}")
print(f"Full batch      : {FULL_BATCH}")
print(f"Model saved as  : {MASTER_MODEL} (and checkpoints in checkpoints/)")
print(f"Total time      : {int(total_time // 60)}m {int(total_time % 60)}s")
print(f"Training report : training_report.txt")
