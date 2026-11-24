#!/usr/bin/env python3
"""
Auto-sync new games from Lichess & Chess.com, convert to training_data.pkl,
then run supervised training (your games first).
Run manually or set up as a cron job.
"""

import os, pickle, time, datetime, hashlib, requests, re, sys, subprocess
from board import ChessBoard
from nn import DualNet
from move_helpers import move_to_index
import chess.pgn

# --- Configuration ---
LICHESS_USER = "jothilingam"
CHESSCOM_USER = "jothi_lingam"
SLEEP_MINUTES = 1440  # 24 hours

HOME = os.path.expanduser("~")
CHESS_DIR = os.path.join(HOME, "chess_ai")
TIMESTAMP_FILE = os.path.join(CHESS_DIR, "last_sync.txt")
SEEN_GAMES_FILE = os.path.join(CHESS_DIR, "seen_games.pkl")
TRAINING_DATA = os.path.join(CHESS_DIR, "training_data.pkl")
DISTILLED_MODEL = os.path.join(CHESS_DIR, "distilled_nn.pkl")

def get_last_sync():
    if os.path.exists(TIMESTAMP_FILE):
        with open(TIMESTAMP_FILE) as f:
            return int(f.read().strip())
    return int(time.time()) - 86400

def save_last_sync(ts):
    with open(TIMESTAMP_FILE, 'w') as f:
        f.write(str(ts))

def load_seen():
    if os.path.exists(SEEN_GAMES_FILE):
        with open(SEEN_GAMES_FILE, 'rb') as f:
            return pickle.load(f)
    return set()

def save_seen(seen):
    with open(SEEN_GAMES_FILE, 'wb') as f:
        pickle.dump(seen, f)

def fetch_lichess_new(username, since_ms):
    url = f"https://lichess.org/api/games/user/{username}"
    params = {"since": since_ms, "max": 999999, "perfType": "blitz,rapid,classical", "moves": True, "pgnInJson": False}
    headers = {"Accept": "application/x-chess-pgn"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=180)
        resp.raise_for_status()
        pgn = resp.text
        cnt = pgn.count("[Event ")
        return pgn, cnt
    except Exception as e:
        print(f"    Lichess error: {e}")
        return "", 0

def fetch_chesscom_new(username, since_ms):
    headers = {"User-Agent": "ChessAI Mobile/1.0"}
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    try:
        resp = requests.get(archives_url, headers=headers, timeout=60)
        resp.raise_for_status()
        archives = resp.json().get("archives", [])
    except Exception as e:
        print(f"    Chess.com error: {e}")
        return "", 0
    new_pgn = ""
    total = 0
    for url in archives[-3:]:
        try:
            resp = requests.get(url, headers=headers, timeout=120)
            resp.raise_for_status()
            games = resp.json().get("games", [])
            for g in games:
                pgn = g.get("pgn", "")
                if not pgn: continue
                date_match = re.search(r'\[UTCDate\s+"(\d{4}\.\d{2}\.\d{2})"\]', pgn)
                time_match = re.search(r'\[UTCTime\s+"(\d{2}:\d{2}:\d{2})"\]', pgn)
                if date_match:
                    ds = date_match.group(1).replace('.', '-')
                    ts = time_match.group(1) if time_match else "00:00:00"
                    dt = datetime.datetime.strptime(ds + "T" + ts, "%Y-%m-%dT%H:%M:%S")
                    if int(dt.timestamp() * 1000) > since_ms:
                        new_pgn += pgn + "\n\n"
                        total += 1
        except Exception as e:
            print(f"    Chess.com archive error: {e}")
            continue
    return new_pgn, total

def run_supervised_training():
    print("  Running supervised training on updated training_data.pkl...")
    # Use subprocess to call train.py with supervised mode
    cmd = ["python", "train.py", "--mode", "supervised", "--epochs", "10", "--lr", "0.001"]
    subprocess.run(cmd, cwd=CHESS_DIR)

def main():
    print("=== Auto Sync & Train ===")
    print(f"Lichess: {LICHESS_USER}")
    print(f"Chess.com: {CHESSCOM_USER}")
    print(f"Interval: {SLEEP_MINUTES} minutes")
    print("Press Ctrl+C to stop.\n")

    seen = load_seen()
    while True:
        now_ms = int(time.time() * 1000)
        last_sync = get_last_sync()
        print(f"[{datetime.datetime.now()}] Checking for new games...")

        pgn_l, cnt_l = fetch_lichess_new(LICHESS_USER, last_sync)
        if cnt_l > 0:
            # Save to a temp file and convert
            temp_pgn = os.path.join(CHESS_DIR, "temp_lichess.pgn")
            with open(temp_pgn, 'w') as f:
                f.write(pgn_l)
            # Use prepare_pgn_with_policy.py to append
            subprocess.run(["python", "prepare_pgn_with_policy.py", temp_pgn, "0", "1"], cwd=CHESS_DIR)
            os.remove(temp_pgn)
            print(f"    Lichess: added {cnt_l} games.")
        else:
            print("    No new Lichess games.")

        pgn_c, cnt_c = fetch_chesscom_new(CHESSCOM_USER, last_sync)
        if cnt_c > 0:
            temp_pgn = os.path.join(CHESS_DIR, "temp_chesscom.pgn")
            with open(temp_pgn, 'w') as f:
                f.write(pgn_c)
            subprocess.run(["python", "prepare_pgn_with_policy.py", temp_pgn, "0", "1"], cwd=CHESS_DIR)
            os.remove(temp_pgn)
            print(f"    Chess.com: added {cnt_c} games.")
        else:
            print("    No new Chess.com games.")

        # Run supervised training if any new games were added
        if cnt_l > 0 or cnt_c > 0:
            run_supervised_training()

        save_last_sync(now_ms)
        print(f"    Sleeping {SLEEP_MINUTES} minutes...\n")
        time.sleep(SLEEP_MINUTES * 60)

if __name__ == "__main__":
    main()
