#!/data/data/com.termux/files/usr/bin/bash
cd /data/data/com.termux/files/home/chess_ai

echo "=== AUTO TRAINING ==="
echo "Using: 20 epochs, learning rate 0.001"
echo "This will take 10-30 minutes. Do NOT press any keys."
echo ""

# Pipe all the answers into multi_train.py automatically
{
  echo "5"       # option 5 – Merge PGN + Stockfish
  echo ""        # accept default epochs (20)
  echo ""        # accept default learning rate (0.001)
  echo "6"       # quit after training
} | python multi_train.py

# Check if training succeeded
if [ -f "distilled_nn.pkl" ]; then
    echo ""
    echo "=== TRAINING COMPLETE ==="
    cp distilled_nn.pkl chess_nn.pkl
    echo "Activated distilled network -> chess_nn.pkl"
    echo "You can now restart the web engine or UCI engine."
else
    echo "ERROR: Training failed – distilled_nn.pkl not created."
fi
