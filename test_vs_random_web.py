#!/usr/bin/env python3
"""Test engine vs random mover with live web UI display."""

import sys
import time
import random
import subprocess
import requests
from board import ChessBoard
from nn import DualNet
from search import SearchEngine
from move_helpers import move_to_str

API_URL = "http://localhost:5000/api/move"

def start_server():
    try:
        requests.get("http://localhost:5000", timeout=0.5)
        print("✅ Flask server already running.")
        return
    except requests.exceptions.ConnectionError:
        print("⏳ Starting Flask server...")
        subprocess.Popen(["python", "web_control.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(10):
            time.sleep(0.5)
            try:
                requests.get("http://localhost:5000", timeout=0.5)
                print("✅ Flask server started.")
                return
            except:
                pass
        print("❌ Failed to start Flask server. Please start it manually: python web_control.py")
        sys.exit(1)

def send_move(fen, uci):
    """Send a move to the web UI (FEN before the move)."""
    try:
        r = requests.post(API_URL, json={'fen': fen, 'uci': uci}, timeout=0.5)
        if r.status_code != 200:
            print(f"Web update error: {r.text} (FEN: {fen}, UCI: {uci})")
    except Exception as e:
        print(f"Web update failed: {e}")

def random_move(board):
    moves = board.generate_legal_moves()
    if not moves:
        return None
    return random.choice(moves)

def play_game(nn, engine_white=True, depth=4, time_limit=1000):
    board = ChessBoard()
    engine = SearchEngine(nn=nn, max_depth=depth)
    move_count = 0

    while not board.is_draw() and not board.is_checkmate() and move_count < 200:
        if board.white_turn == engine_white:
            move, _, _, _ = engine.search(board, time_limit=time_limit, depth=depth)
            if move is None or move not in board.generate_legal_moves():
                move = random_move(board)
            if move is None:
                break
        else:
            move = random_move(board)
            if move is None:
                break

        # ---- CORRECT ORDER ----
        fen_before = board.to_fen()
        uci = move_to_str(move)

        # Apply move locally
        board.make_move(move)
        move_count += 1

        # Send to web UI (with FEN before the move)
        send_move(fen_before, uci)
        time.sleep(0.1)  # small delay for browser update

    if board.is_checkmate():
        return "loss" if board.white_turn == engine_white else "win"
    return "draw"

def main():
    start_server()
    nn = DualNet()
    if not nn.load("chess_nn.pkl"):
        print("Failed to load model")
        return

    games = 10
    depth = 4
    wins = losses = draws = 0
    print(f"Testing engine with depth={depth} against random (watch at http://localhost:5000)")

    for i in range(games):
        engine_white = (i % 2 == 0)
        result = play_game(nn, engine_white, depth=depth)
        if result == "win":
            wins += 1
        elif result == "loss":
            losses += 1
        else:
            draws += 1
        print(f"Game {i+1}: {'Engine' if engine_white else 'Random'} as white -> {result}")

    print(f"Wins: {wins}, Losses: {losses}, Draws: {draws}")

if __name__ == "__main__":
    main()
