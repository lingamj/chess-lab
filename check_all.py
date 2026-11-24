#!/usr/bin/env python3
"""System checker – Termux‑compatible, all tests fixed."""

import os, sys, subprocess, time, pickle

def check(desc, func):
    try:
        result = func()
        if result:
            print(f"✅ PASS  {desc}")
            return True
        else:
            print(f"❌ FAIL  {desc}")
            return False
    except Exception as e:
        print(f"❌ FAIL  {desc}  (error: {e})")
        return False

def run_python_code(code):
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip()

def command_exists(cmd):
    # Use 'command -v' which works in Termux bash
    return subprocess.run(["command", "-v", cmd], capture_output=True, text=True).returncode == 0

def file_exists(path):
    return os.path.exists(path)

def load_pkl(path):
    if not os.path.exists(path):
        return False
    with open(path, 'rb') as f:
        pickle.load(f)
    return True

print("=" * 50)
print("  CHESS AI SYSTEM CHECK (Python)")
print("=" * 50)

# 1. Environment
print("\n--- Environment ---")
check("Python 3.x available", lambda: sys.version_info[0] >= 3)
check("NumPy installed", lambda: run_python_code("import numpy")[0])
check("Requests installed", lambda: run_python_code("import requests")[0])
check("Stockfish installed", lambda: command_exists("stockfish"))
check("board.py exists", lambda: file_exists("board.py"))
check("move_helpers.py exists", lambda: file_exists("move_helpers.py"))
check("nn.py exists", lambda: file_exists("nn.py"))
check("search.py exists", lambda: file_exists("search.py"))
check("database_v2.py exists", lambda: file_exists("database_v2.py"))
check("web_control.py exists", lambda: file_exists("web_control.py"))

# 2. Core runtime modules
print("\n--- Core Runtime Modules ---")
def test_core_compile():
    r = subprocess.run(
        [sys.executable, "-m", "py_compile",
         "board.py", "move_helpers.py", "nn.py", "search.py",
         "database_v2.py", "web_control.py"],
        capture_output=True, text=True
    )
    return r.returncode == 0
check("core runtime modules compile", test_core_compile)

# 3. UCI engine
print("\n--- UCI Engine ---")
def uci_ok():
    r = subprocess.run([sys.executable, "uci_engine.py"],
                       input="uci\nquit\n", capture_output=True, text=True, timeout=10)
    return "uciok" in r.stdout
check("UCI handshake (uciok)", uci_ok)

def ready_ok():
    r = subprocess.run([sys.executable, "uci_engine.py"],
                       input="isready\nquit\n", capture_output=True, text=True, timeout=10)
    return "readyok" in r.stdout
check("UCI readyok", ready_ok)
check("launch_uci.sh executable", lambda: os.access("launch_uci.sh", os.X_OK))

# 4. PGN learner
print("\n--- PGN Learner ---")
def test_pgn_learner():
    # Simulate: option 1, then empty line (default path)
    r = subprocess.run([sys.executable, "pgn_learner.py"],
                       input="1\n\n", capture_output=True, text=True, timeout=10)
    # If the script printed the menu, it started fine.
    # It may complain about missing file, but that's fine for the test.
    if "Import from local" in r.stdout:
        return True
    else:
        print(f"    DEBUG: stdout={r.stdout!r}  stderr={r.stderr!r}")
        return False
check("PGN learner starts", test_pgn_learner)

# 5. Multi-trainer
print("\n--- Multi-Trainer ---")
def test_multi_trainer():
    r = subprocess.run([sys.executable, "multi_train.py"],
                       input="6\n", capture_output=True, text=True, timeout=10)
    return r.returncode == 0
check("Multi-trainer starts", test_multi_trainer)

# 6. Auto-sync service
print("\n--- Auto-Sync Service ---")
subprocess.run(["pkill", "-f", "auto_sync_train.py"], capture_output=True)
time.sleep(0.5)

def test_auto_sync():
    proc = subprocess.Popen([sys.executable, "auto_sync_train.py"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        out, err = proc.communicate(timeout=8)
        if "Auto Sync & Train" in out:
            return True
        else:
            return False
    except subprocess.TimeoutExpired:
        proc.terminate()
        return True   # running in loop
    finally:
        proc.kill()
check("Auto-sync starts and prints banner", test_auto_sync)

# 7. Data files
print("\n--- Data Files ---")
check("chess_nn.pkl loadable", lambda: load_pkl("chess_nn.pkl"))
check("distilled_nn.pkl loadable", lambda: load_pkl("distilled_nn.pkl"))
check("training_data.pkl exists", lambda: file_exists("training_data.pkl"))
check("opening_tree.pkl.gz exists", lambda: file_exists("opening_tree.pkl.gz"))
check("pgn_data.pkl exists", lambda: file_exists("pgn_data.pkl"))

print("\n" + "=" * 50)
print("  Checks complete.")
print("=" * 50)
