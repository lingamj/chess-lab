#!/bin/bash

echo "📦 Creating 2k subset from training_data.pkl..."
START_TIME=$(date +%s)

python -c "
import pickle, random
data = pickle.load(open('training_data.pkl','rb'))
random.shuffle(data)
subset = data[:2000]
with open('training_data_2k.pkl','wb') as f:
    pickle.dump(subset, f)
print(f'Subset size: {len(subset)}')
"

echo "🧠 Training supervised on 2k positions (batch_size=64)..."
TRAIN_START=$(date +%s)
python train.py --mode supervised --epochs 15 --lr 0.001 --batch-size 64 --data-file training_data_2k.pkl
TRAIN_END=$(date +%s)
echo "Training took $((TRAIN_END - TRAIN_START)) seconds."

echo "♟️ Testing against random mover (saving PGN)..."
TEST_START=$(date +%s)
python - <<'PYEOF'
import random, time, sys
from board import ChessBoard
from nn import DualNet
from mcts import MCTS
from move_helpers import move_to_str

def random_move(board):
    moves = board.generate_legal_moves()
    if not moves:
        return None
    return random.choice(moves)

def play_game(nn, engine_white=True, sims=30, return_moves=False):
    board = ChessBoard()
    moves_history = []
    move_count = 0
    while not board.is_draw() and not board.is_checkmate() and move_count < 200:
        if board.white_turn == engine_white:
            mcts = MCTS(nn, num_simulations=sims)
            try:
                policy = mcts.search(board, temperature=0.0)
            except:
                policy = {}
            if not policy:
                move = random_move(board)
            else:
                move = max(policy.items(), key=lambda x: x[1])[0]
        else:
            move = random_move(board)
            if move is None:
                break
        board.make_move(move)
        moves_history.append(move_to_str(move))
        move_count += 1
    if board.is_checkmate():
        if board.white_turn == engine_white:
            result = "0-1" if engine_white else "1-0"
        else:
            result = "1-0" if engine_white else "0-1"
    elif board.is_draw():
        result = "1/2-1/2"
    else:
        result = "*"
    if return_moves:
        return result, moves_history, board.to_fen()
    return result

def main():
    nn = DualNet()
    if not nn.load("distilled_nn.pkl"):
        print("Failed to load model")
        return

    games = 10
    results = []
    for i in range(games):
        engine_white = (i % 2 == 0)
        result, moves, final_fen = play_game(nn, engine_white, sims=30, return_moves=True)
        results.append((result, moves, final_fen))
        print(f"Game {i+1}: {'Engine' if engine_white else 'Random'} as white -> {result}")

    # Write PGN
    pgn_lines = []
    for i, (result, moves, final_fen) in enumerate(results):
        engine_white = (i % 2 == 0)
        pgn_lines.append(f"[Event \"Test vs Random\"]")
        pgn_lines.append(f"[Site \"ChessAI\"]")
        pgn_lines.append(f"[Date \"{time.strftime('%Y.%m.%d')}\"]")
        pgn_lines.append(f"[Round \"{i+1}\"]")
        pgn_lines.append(f"[White \"{'Engine' if engine_white else 'Random'}\"]")
        pgn_lines.append(f"[Black \"{'Random' if engine_white else 'Engine'}\"]")
        pgn_lines.append(f"[Result \"{result}\"]")
        pgn_lines.append(f"[FEN \"{final_fen}\"]")
        pgn_lines.append("")
        move_str = ""
        for j, m in enumerate(moves):
            if j % 2 == 0:
                move_str += f"{j//2 + 1}. "
            move_str += m + " "
        pgn_lines.append(move_str + result)
        pgn_lines.append("")

    with open("test_vs_random.pgn", "w") as f:
        f.write("\n".join(pgn_lines))
    print(f"✅ PGN saved to test_vs_random.pgn")

    # Count engine wins/losses/draws
    engine_wins = 0
    engine_losses = 0
    engine_draws = 0
    for i, (r, _, _) in enumerate(results):
        if (i % 2 == 0 and r == "1-0") or (i % 2 == 1 and r == "0-1"):
            engine_wins += 1
        elif (i % 2 == 0 and r == "0-1") or (i % 2 == 1 and r == "1-0"):
            engine_losses += 1
        else:
            engine_draws += 1
    print(f"Engine wins: {engine_wins}, Losses: {engine_losses}, Draws: {engine_draws}")
    return engine_wins, engine_losses, engine_draws

if __name__ == "__main__":
    main()
PYEOF

TEST_END=$(date +%s)
echo "Test took $((TEST_END - TEST_START)) seconds."
TOTAL_END=$(date +%s)
echo "Total pipeline time: $((TOTAL_END - START_TIME)) seconds."
echo "✅ Pipeline complete. PGN saved to test_vs_random.pgn"
