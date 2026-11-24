#!/bin/bash
echo "📦 Creating 5k subset from training_data.pkl..."
python -c "
import pickle, random
data = pickle.load(open('training_data.pkl','rb'))
random.shuffle(data)
subset = data[:5000]
with open('training_data_5k.pkl','wb') as f:
    pickle.dump(subset, f)
print(f'Subset size: {len(subset)}')
"

echo "🧠 Training supervised on 5k positions..."
python train.py --mode supervised --epochs 20 --lr 0.001 --batch-size 128 --data-file training_data_5k.pkl

echo "♟️ Testing against random mover..."
python test_vs_random.py

echo "✅ Pipeline complete."
