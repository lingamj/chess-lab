import pickle, sys, os, numpy as np
from nn import DualNet
from move_helpers import NUM_MOVES

# ------- Load 20k subset (handle both formats) -------
with open('training_data_20k.pkl', 'rb') as f:
    subset = pickle.load(f)

keys = ['positions','policies','values','move_uci','source',
        'white_elo','black_elo','opening','date','game_ids','game_starts']

if isinstance(subset, list):
    conv = {k: [] for k in keys}
    for item in subset:
        conv['positions'].append(item[0])
        conv['policies'].append(item[1] if item[1] is not None else 0)
        conv['values'].append(item[3] if isinstance(item[3], (int,float)) else 0.0)
        conv['move_uci'].append(item[2] if len(item)>2 and item[2] else '?')
        conv['source'].append(item[4] if len(item)>4 and isinstance(item[4], int) else 0)
        conv['white_elo'].append(str(item[5]) if len(item)>5 else '')
        conv['black_elo'].append(str(item[6]) if len(item)>6 else '')
        conv['opening'].append(str(item[7]) if len(item)>7 else '')
        conv['date'].append(str(item[8]) if len(item)>8 else '')
        conv['game_ids'].append(0)
        conv['game_starts'].append(False)
    subset = conv
elif not isinstance(subset, dict):
    print("Unknown format in training_data_20k.pkl"); sys.exit(1)

# ------- Load capture data -------
with open('capture_training.pkl', 'rb') as f:
    cap = pickle.load(f)

# ------- Append -------
for k in keys:
    if k in cap:
        subset[k].extend(cap[k])
subset['format_version'] = 2

# Filter out invalid policy indices
positions = subset['positions']
values    = subset['values']
policies  = subset['policies']
valid = [(p, v, pol) for p, v, pol in zip(positions, values, policies)
         if isinstance(pol, (int, np.integer)) and 0 <= pol < NUM_MOVES]
if len(valid) < len(positions):
    print(f"Filtered out {len(positions) - len(valid)} invalid policy indices.")
positions, values, policies = zip(*valid) if valid else ([], [], [])
positions = list(positions)
values    = list(values)
policies  = list(policies)

print(f"Merged dataset: {len(positions)} valid positions")

# ------- Build one‑hot policy matrix -------
one_hot = np.zeros((len(policies), NUM_MOVES), dtype=np.float32)
for i, pol_idx in enumerate(policies):
    if 0 <= pol_idx < NUM_MOVES:
        one_hot[i, pol_idx] = 1.0

# ------- Train master model -------
if not os.path.exists('chess_nn_master.pkl'):
    import shutil; shutil.copy2('chess_nn.pkl', 'chess_nn_master.pkl')
    print("Created master model from chess_nn.pkl")

net = DualNet()
net.load('chess_nn_master.pkl')
net.train(positions, values, one_hot, epochs=3, lr=0.0005, batch_size=512)
net.save('chess_nn_master.pkl')
print("Master model saved.  Training complete.")
