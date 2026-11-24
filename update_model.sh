#!/bin/bash
cd ~/chess_ai

MODEL="chess_nn_master.pkl"
DATASET="training_data.pkl"        # or training_data_merged.pkl if you prefer
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

echo "Continuing training on $DATASET..."
python train.py "$DATASET" "$EPOCHS" "$LR" "$BATCH" "$MODEL"
echo "Done. Master model saved to $MODEL."
