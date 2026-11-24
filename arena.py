#!/usr/bin/env python3
"""
Arena testing: compare two models by playing N games.
Usage: python arena.py --model1 model_a.pkl --model2 model_b.pkl --games 100 --sims 200
"""

import argparse
import random
import numpy as np
from board import ChessBoard
from nn import DualNet
from mcts import MCTS

def play_game(white_nn, black_nn, sims=200):
    board = ChessBoard()
    move_count = 0
    while not board.is_draw() and not board.is_checkmate() and move_count < 200:
        if board.white_turn:
            nn = white_nn
        else:
            nn = black_nn

        mcts = MCTS(nn, num_simulations=sims)
        policy = mcts.search(board, temperature=0.0)

        # -- FIX: handle empty policy --
        if not policy:
            moves = board.generate_legal_moves()
            if not moves:
                winner = 'draw'
                break
            move = random.choice(moves)
        else:
            move = max(policy.items(), key=lambda x: x[1])[0]

        board.make_move(move)
        move_count += 1

    if board.is_checkmate():
        if board.white_turn:
            winner = 'black'
        else:
            winner = 'white'
    elif board.is_draw():
        winner = 'draw'
    else:
        # Fallback (rare)
        w_mat = sum({'P':1,'N':3,'B':3,'R':5,'Q':9,'K':0}.get(p.upper(),0) for row in board.board for p in row if p.isupper())
        b_mat = sum({'P':1,'N':3,'B':3,'R':5,'Q':9,'K':0}.get(p.upper(),0) for row in board.board for p in row if p.islower())
        if w_mat > b_mat:
            winner = 'white'
        elif b_mat > w_mat:
            winner = 'black'
        else:
            winner = 'draw'

    return winner

def arena(model1_path, model2_path, games=100, sims=200):
    print(f"Loading models...")
    m1 = DualNet()
    if not m1.load(model1_path):
        print(f"Failed to load {model1_path}")
        return
    m2 = DualNet()
    if not m2.load(model2_path):
        print(f"Failed to load {model2_path}")
        return

    wins1 = 0
    wins2 = 0
    draws = 0

    for g in range(games):
        if g % 2 == 0:
            result = play_game(m1, m2, sims=sims)
            if result == 'white':
                wins1 += 1
            elif result == 'black':
                wins2 += 1
            else:
                draws += 1
        else:
            result = play_game(m2, m1, sims=sims)
            if result == 'white':
                wins2 += 1
            elif result == 'black':
                wins1 += 1
            else:
                draws += 1

        if (g+1) % 10 == 0:
            print(f"  Game {g+1}/{games} completed")

    total = wins1 + wins2 + draws
    if total == 0:
        return

    score1 = (wins1 + 0.5 * draws) / total
    score2 = 1 - score1
    elo_diff = -400 * np.log10((1 - score1) / max(score1, 0.001))

    print("\n" + "="*50)
    print("Arena Results")
    print("="*50)
    print(f"Model 1 ({model1_path}): {wins1} wins")
    print(f"Model 2 ({model2_path}): {wins2} wins")
    print(f"Draws: {draws}")
    print(f"Total games: {games}")
    print(f"Model 1 score: {score1*100:.1f}%")
    print(f"Model 2 score: {score2*100:.1f}%")
    if elo_diff > 0:
        print(f"Model 1 is estimated to be +{elo_diff:.1f} Elo stronger.")
    else:
        print(f"Model 2 is estimated to be +{-elo_diff:.1f} Elo stronger.")
    print("="*50)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Arena test between two models")
    parser.add_argument('--model1', required=True, help='Path to first model')
    parser.add_argument('--model2', required=True, help='Path to second model')
    parser.add_argument('--games', type=int, default=50, help='Number of games')
    parser.add_argument('--sims', type=int, default=200, help='MCTS simulations per move')
    args = parser.parse_args()
    arena(args.model1, args.model2, args.games, args.sims)
