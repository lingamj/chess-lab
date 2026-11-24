#!/data/data/com.termux/files/usr/bin/bash
cd /data/data/com.termux/files/home/chess_ai
echo "Enter FEN (or press Enter for start position):"
read fen
if [ -z "$fen" ]; then
    fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
fi
echo "Thinking for 5 seconds..."
echo -e "uci\nposition fen $fen\ngo movetime 5000\nquit" | python uci_engine.py
