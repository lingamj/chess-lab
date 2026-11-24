#!/data/data/com.termux/files/usr/bin/bash
source /data/data/com.termux/files/usr/etc/bash.bashrc 2>/dev/null
export PATH=/data/data/com.termux/files/usr/bin:$PATH
export HOME=/data/data/com.termux/files/home
cd $HOME/chess_ai
exec python uci_engine.py
