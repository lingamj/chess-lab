import pickle, numpy as np, sys
files = sys.argv[1:]
weights = {}
for f in files:
    with open(f, 'rb') as fp:
        d = pickle.load(fp)
    for k in d:
        if k not in weights:
            weights[k] = []
        weights[k].append(d[k])
merged = {}
for k in weights:
    merged[k] = np.mean(weights[k], axis=0)
with open('distilled_nn_merged.pkl', 'wb') as f:
    pickle.dump(merged, f)
print("Merged model saved as distilled_nn_merged.pkl")
