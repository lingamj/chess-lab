#!/usr/bin/env python3
"""Fast capture data generator – no engine search, finishes quickly."""
import pickle, random
from board import ChessBoard
from move_helpers import move_to_str, move_to_index

NUM_GAMES = 200
MAX_MOVES = 200

def main():
    data = {'positions':[], 'policies':[], 'values':[], 'move_uci':[],
            'source':[], 'white_elo':[], 'black_elo':[], 'opening':[],
            'date':[], 'game_ids':[], 'game_starts':[]}
    game_id = 0

    for _ in range(NUM_GAMES):
        board = ChessBoard()
        game_positions = []
        for _ in range(MAX_MOVES):
            legals = board.generate_legal_moves()
            if not legals:
                break
            captures = [m for m in legals if board.board[m[2]][m[3]] != '.' or (len(m)>4 and m[4] is not None)]
            move = random.choice(captures) if captures else random.choice(legals)
            if move in captures:
                game_positions.append((board.copy(), move, move_to_str(move)))
            board.make_move(move)
            if board.is_checkmate() or board.is_draw():
                break

        if board.is_checkmate():
            white_result = -1.0 if board.white_turn else 1.0
        elif board.is_draw():
            white_result = 0.0
        else:
            white_result = 0.0

        first = True
        for pos, move, uci in game_positions:
            idx = move_to_index(move)
            if idx < 0: continue
            value = white_result if white_result==0 else (white_result if pos.white_turn else -white_result)
            data['positions'].append(pos)
            data['policies'].append(idx)
            data['values'].append(value)
            data['move_uci'].append(uci)
            data['source'].append(1)
            data['white_elo'].append('')
            data['black_elo'].append('')
            data['opening'].append('')
            data['date'].append('')
            data['game_ids'].append(game_id)
            data['game_starts'].append(first)
            first = False
        game_id += 1
        if game_id % 20 == 0:
            print(f'{game_id} games...')

    data['format_version'] = 2
    with open('capture_training.pkl', 'wb') as f:
        pickle.dump(data, f)
    print(f'Saved capture_training.pkl with {len(data["positions"])} positions.')

if __name__ == '__main__':
    main()
