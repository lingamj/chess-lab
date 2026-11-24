#!/bin/bash
cd ~/chess_ai

echo "=== Generating themed training data ==="
python generate_themed_data.py
if [ $? -ne 0 ]; then
    echo "Data generation failed. Exiting."
    exit 1
fi

echo ""
echo "=== Merging new data into master dataset (atomic write, dedup by pos+move+value) ==="
python -c "
import pickle, os, shutil, time, tempfile

MASTER_FILE = 'training_data.pkl'
NEW_FILE    = 'training_data_merged.pkl'
MAX_POSITIONS = 2_000_000   # warn if exceeded

# ---------- 1. Load master dataset (or create empty) ----------
if os.path.exists(MASTER_FILE):
    # Backup before modifying
    shutil.copy2(MASTER_FILE, MASTER_FILE + '.bak')
    print(f'Backup saved to {MASTER_FILE}.bak')
    with open(MASTER_FILE, 'rb') as f:
        master = pickle.load(f)
else:
    master = {k: [] for k in ['positions','policies','values','move_uci','source',
                               'white_elo','black_elo','opening','date','game_ids','game_starts']}

# ---------- 2. Build set of existing (position, policy, value) keys ----------
# Use exact float, no rounding
existing_keys = set()
for i in range(len(master['positions'])):
    board = master['positions'][i]
    fen = board.to_fen()
    pos_key = ' '.join(fen.split()[:4])
    policy = master['policies'][i]
    val = master['values'][i]                # keep exact
    existing_keys.add((pos_key, policy, val))

# ---------- 3. Load and validate new data ----------
if not os.path.exists(NEW_FILE):
    print('No new data found – skipping merge.')
    raise SystemExit(0)

with open(NEW_FILE, 'rb') as f:
    new_data = pickle.load(f)

required = ['positions','policies','values','move_uci','source',
            'white_elo','black_elo','opening','date','game_ids','game_starts']
for k in required:
    if k not in new_data:
        raise SystemExit(f'Missing field {k} in new data. Aborting merge.')
    if not isinstance(new_data[k], list):
        raise SystemExit(f'Field {k} is not a list. Aborting merge.')

n = len(new_data['positions'])
if n == 0:
    print('New dataset is empty – skipping merge.')
    raise SystemExit(0)

for k in required:
    if len(new_data[k]) != n:
        raise SystemExit(f'Length mismatch: positions has {n}, {k} has {len(new_data[k])}.')

print(f'New dataset contains {n} positions. Checking for duplicates...')

# ---------- 4. Append only truly new (position, policy, value) triples ----------
added = 0
for i in range(n):
    board = new_data['positions'][i]
    fen = board.to_fen()
    pos_key = ' '.join(fen.split()[:4])
    policy = new_data['policies'][i]
    val = new_data['values'][i]            # exact
    if (pos_key, policy, val) not in existing_keys:
        existing_keys.add((pos_key, policy, val))
        for field in master:
            if field in new_data:
                master[field].append(new_data[field][i])
        added += 1

print(f'Added {added} new unique (position, move, value) triples (skipped {n - added} duplicates).')

# ---------- 5. Versioning metadata ----------
master['format_version'] = 2
master['last_merge'] = time.time()
master['dataset_version'] = master.get('dataset_version', 0) + 1
master['total_merges'] = master.get('total_merges', 0) + 1

total = len(master['positions'])
print(f'Master dataset now has {total} positions (version {master[\"dataset_version\"]}).')
if total > MAX_POSITIONS:
    print(f'Warning: dataset exceeded {MAX_POSITIONS} positions. Consider periodic cleanup.')

# ---------- 6. Save atomically ----------
tmp_fd, tmp_path = tempfile.mkstemp(dir='.', prefix='training_data_')
with os.fdopen(tmp_fd, 'wb') as f:
    pickle.dump(master, f)
os.replace(tmp_path, MASTER_FILE)
print('Master dataset saved atomically.')
"

echo ""
echo "=== Training master model ==="
DATASET="training_data.pkl"
MODEL="chess_nn_master.pkl"
EPOCHS=10
LR=0.0005
BATCH=512

if [ ! -f "$DATASET" ]; then
    echo "Error: $DATASET not found."
    exit 1
fi

if [ ! -f "$MODEL" ]; then
    echo "Creating master model from chess_nn.pkl..."
    cp chess_nn.pkl "$MODEL"
fi

python train.py "$DATASET" "$EPOCHS" "$LR" "$BATCH" "$MODEL"
echo "Done. Master model saved to $MODEL."
