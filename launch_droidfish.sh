#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:$PATH
cd /data/data/com.termux/files/home/chess_ai
exec python uci_engine.py
