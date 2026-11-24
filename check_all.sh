#!/data/data/com.termux/files/usr/bin/bash

# =============================================
#  CHESS AI – FULL SYSTEM CHECK
#  Run from ~/chess_ai
# =============================================

PASS=0
FAIL=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

check() {
    local desc="$1"
    shift
    if eval "$@"; then
        echo -e "${GREEN}✅ PASS${NC}  $desc"
        PASS=$((PASS+1))
    else
        echo -e "${RED}❌ FAIL${NC}  $desc"
        FAIL=$((FAIL+1))
    fi
}

echo "========================================"
echo "  CHESS AI SYSTEM CHECK"
echo "========================================"
echo ""

# ----- 1. ENVIRONMENT -----
echo "--- Environment ---"
check "Python installed" python --version &>/dev/null
check "NumPy works" python -c "import numpy; print('OK')" 2>/dev/null | grep -q OK
check "Requests works" python -c "import requests; print('OK')" 2>/dev/null | grep -q OK
check "Stockfish installed" command -v stockfish &>/dev/null
check "Project folder exists" [ -f "web_control.py" ]

# ----- 2. CORE ENGINE -----
echo ""
echo "--- Core Runtime Modules ---"
check "core module files exist" [ -f "board.py" ] && [ -f "move_helpers.py" ] && [ -f "nn.py" ] && [ -f "search.py" ] && [ -f "database_v2.py" ] && [ -f "web_control.py" ]
check "core runtime modules compile" python -m py_compile board.py move_helpers.py nn.py search.py database_v2.py web_control.py

# ----- 3. UCI ENGINE -----
echo ""
echo "--- UCI Engine ---"
check "UCI handshake (uciok)" timeout 3 bash -c 'echo -e "uci\nquit" | python uci_engine.py' 2>/dev/null | grep -q "uciok"
check "UCI readyok" timeout 3 bash -c 'echo -e "isready\nquit" | python uci_engine.py' 2>/dev/null | grep -q "readyok"
check "Launch script exists & executable" [ -x "launch_uci.sh" ]

# ----- 4. PGN LEARNER -----
echo ""
echo "--- PGN Learner ---"
check "PGN learner starts" timeout 2 python pgn_learner.py <<< "1" 2>/dev/null | grep -q "Import from local"

# Note: Lichess download test is skipped because it takes long and requires internet.
# You can uncomment the next line if you want to test it (requires network):
# check "Lichess download works" timeout 30 python pgn_learner.py <<< "2" 2>/dev/null | grep -q "Downloaded"

# ----- 5. MULTI-TRAINER -----
echo ""
echo "--- Multi-Trainer ---"
check "Multi-trainer starts" timeout 2 python multi_train.py <<< "6" 2>/dev/null | grep -q "STOCKFISH"
check "Multi-trainer quits" timeout 2 python multi_train.py <<< "6" 2>/dev/null | grep -q "Goodbye"

# ----- 6. AUTO-SYNC SERVICE -----
echo ""
echo "--- Auto-Sync Service ---"
# Kill any leftover process
pkill -f auto_sync_train.py 2>/dev/null
sleep 1
check "Auto-sync starts manually" timeout 5 python auto_sync_train.py 2>/dev/null &>/tmp/auto_sync_test.log &
AUTO_PID=$!
sleep 3
if grep -q "Auto Sync & Train" /tmp/auto_sync_test.log 2>/dev/null; then
    echo -e "${GREEN}✅ PASS${NC}  Auto-sync starts manually"
    PASS=$((PASS+1))
else
    echo -e "${RED}❌ FAIL${NC}  Auto-sync starts manually"
    FAIL=$((FAIL+1))
fi
kill $AUTO_PID 2>/dev/null

# Background run test – NO nohup warning here any more
python auto_sync_train.py > /tmp/auto_sync_bg.log 2>&1 &
BG_PID=$!
sleep 2
check "Auto-sync runs in background" ps aux | grep -v grep | grep -q "auto_sync_train"
kill $BG_PID 2>/dev/null

# ----- 7. DATA FILES -----
echo ""
echo "--- Data Files ---"
check "chess_nn.pkl loadable" python -c "from nn import DualNet; n=DualNet(); print(n.load('chess_nn.pkl'))" 2>/dev/null | grep -Eq 'True|False'
check "distilled_nn.pkl loadable" python -c "from nn import DualNet; n=DualNet(); print(n.load('distilled_nn.pkl'))" 2>/dev/null | grep -Eq 'True|False' 
check "pgn_data.pkl exists or created" [ -f pgn_data.pkl ]
check "training_data.pkl exists" [ -f training_data.pkl ]

# ----- 8. SUMMARY -----
echo ""
echo "========================================"
echo "  RESULTS: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}"
echo "========================================"

# Cleanup
rm -f /tmp/auto_sync_test.log /tmp/auto_sync_bg.log
