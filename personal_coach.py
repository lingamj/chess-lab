#!/usr/bin/env python3
"""Personal Coach – processes your PGNs (12k+ games), builds opening repertoire,
   mistake patterns, strengths, and exports training data for a personalised NN."""

import sys, os, pickle, time, chess, chess.pgn
from collections import defaultdict, Counter
from board import ChessBoard
from nn import DualNet
from search import SearchEngine, MATE_SCORE, NN_SCALE

MODEL_PATH = 'chess_nn.pkl'
OUTPUT_PROFILE = 'player_profile.pkl'
OUTPUT_TRAINING = 'personal_training_data.pkl'

BLUNDER_THRESHOLD = 2.0         # eval drop > 200 centipawns
MISTAKE_THRESHOLD = 1.0         # > 100 centipawns
STRONG_THRESHOLD = 1.5          # gain > 150 centipawns

def classify_phase(board, move_number):
    pieces = sum(1 for row in board.board for p in row if p != '.')
    if move_number <= 12:
        return 'opening'
    elif pieces <= 12:
        return 'endgame'
    else:
        return 'middlegame'

def main(pgn_path, player_name_lower):
    print("Loading neural network...")
    nn = DualNet()
    if not nn.load(MODEL_PATH):
        print("ERROR: chess_nn.pkl not found.")
        sys.exit(1)
    engine = SearchEngine(nn=nn, max_depth=8, tt_max=100000)

    openings = defaultdict(lambda: {'games':0,'wins':0,'draws':0,'losses':0,
                                    'white':0,'black':0,'rating_sum':0,'rating_count':0})
    mistakes = Counter()
    mistake_by_phase = defaultdict(Counter)
    strengths = Counter()
    training_data = {'positions':[], 'policies':[], 'values':[], 'game_ids':[], 'game_starts':[]}
    game_id_counter = 0

    total_games = 0
    start_time = time.time()

    with open(pgn_path, encoding='utf-8', errors='ignore') as f:
        while True:
            game = chess.pgn.read_game(f)
            if game is None:
                break

            result = game.headers.get('Result', '*')
            white = game.headers.get('White', '?')
            black = game.headers.get('Black', '?')
            white_elo = game.headers.get('WhiteElo', '0')
            black_elo = game.headers.get('BlackElo', '0')
            opening = game.headers.get('Opening', '?')
            eco = game.headers.get('ECO', '?')

            your_color = None
            if player_name_lower in white.lower():
                your_color = 'white'
            elif player_name_lower in black.lower():
                your_color = 'black'
            else:
                continue  # not your game

            total_games += 1

            key = f"{opening} ({eco})"
            openings[key]['games'] += 1
            if your_color == 'white':
                openings[key]['white'] += 1
            else:
                openings[key]['black'] += 1
            try:
                if your_color == 'white':
                    elo = int(white_elo)
                else:
                    elo = int(black_elo)
                openings[key]['rating_sum'] += elo
                openings[key]['rating_count'] += 1
            except ValueError:
                pass
            if (your_color == 'white' and result == '1-0') or (your_color == 'black' and result == '0-1'):
                openings[key]['wins'] += 1
            elif result == '1/2-1/2':
                openings[key]['draws'] += 1
            else:
                openings[key]['losses'] += 1

            board = ChessBoard()
            engine.tt.clear()
            first_move = True
            for move_number, move in enumerate(game.mainline_moves()):
                _, score_before, _, _ = engine.search(board, time_limit=100, depth=4)
                score_before = score_before / NN_SCALE

                engine_move = (7 - chess.square_rank(move.from_square),
                               chess.square_file(move.from_square),
                               7 - chess.square_rank(move.to_square),
                               chess.square_file(move.to_square))
                promo = move.promotion
                if promo:
                    promo_char = chess.PIECE_SYMBOLS[promo].upper()
                    engine_move = engine_move + (promo_char,)
                try:
                    undo = board.make_move(engine_move)
                except Exception:
                    break

                _, score_after, _, _ = engine.search(board, time_limit=100, depth=4)
                score_after = score_after / NN_SCALE

                diff = score_after - score_before
                if your_color == 'black':
                    diff = -diff

                phase = classify_phase(board, move_number + 1)

                if diff < -BLUNDER_THRESHOLD:
                    mistakes['Blunder'] += 1
                    mistake_by_phase[phase]['Blunder'] += 1
                elif diff < -MISTAKE_THRESHOLD:
                    mistakes['Mistake'] += 1
                    mistake_by_phase[phase]['Mistake'] += 1
                elif diff > STRONG_THRESHOLD:
                    strengths['Strong move'] += 1

                from move_helpers import move_to_index
                idx = move_to_index(engine_move)
                if idx >= 0:
                    training_data['positions'].append(board.copy())
                    training_data['policies'].append(idx)
                    if (your_color == 'white' and result == '1-0') or (your_color == 'black' and result == '0-1'):
                        val = 1.0 if board.white_turn else -1.0
                    elif result == '1/2-1/2':
                        val = 0.0
                    else:
                        val = -1.0 if board.white_turn else 1.0
                    training_data['values'].append(val)
                    training_data['game_ids'].append(game_id_counter)
                    training_data['game_starts'].append(first_move)
                    first_move = False

                board.undo_move(undo)

            game_id_counter += 1

            if total_games % 500 == 0:
                elapsed = time.time() - start_time
                print(f"  {total_games} games analysed ({elapsed:.0f}s) ...")
                with open(OUTPUT_PROFILE, 'wb') as pf:
                    pickle.dump({'openings':dict(openings),
                                 'mistakes':dict(mistakes),
                                 'mistake_by_phase':{k:dict(v) for k,v in mistake_by_phase.items()},
                                 'strengths':dict(strengths),
                                 'total_games':total_games}, pf)

    elapsed = time.time() - start_time
    profile = {
        'openings': dict(openings),
        'mistakes': dict(mistakes),
        'mistake_by_phase': {k: dict(v) for k, v in mistake_by_phase.items()},
        'strengths': dict(strengths),
        'total_games': total_games,
    }
    with open(OUTPUT_PROFILE, 'wb') as f:
        pickle.dump(profile, f)

    print(f"\n{'='*60}")
    print(f"Personal Chess Profile")
    print(f"{'='*60}")
    print(f"Games analysed : {total_games}")
    print(f"Time           : {elapsed:.0f}s")

    print(f"\n--- Top 10 Openings ---")
    for name, stats in sorted(profile['openings'].items(), key=lambda x: -x[1]['games'])[:10]:
        total = stats['games']
        win_pct = stats['wins']/total*100 if total else 0
        avg_rating = stats['rating_sum']/stats['rating_count'] if stats['rating_count'] else 0
        print(f"  {name}: {total} games, {win_pct:.1f}% wins, avg opponent {avg_rating:.0f}")

    print(f"\n--- Most Frequent Mistakes ---")
    for pattern, count in profile['mistakes'].most_common(10):
        print(f"  {pattern}: {count}")

    print(f"\n--- Mistakes by Game Phase ---")
    for phase in ('opening', 'middlegame', 'endgame'):
        counts = profile['mistake_by_phase'].get(phase, {})
        total = sum(counts.values())
        if total:
            print(f"  {phase.capitalize()}: {total} total mistakes")
            for pat, cnt in sorted(counts.items(), key=lambda x: -x[1])[:5]:
                print(f"    {pat}: {cnt}")

    print(f"\n--- Notable Strengths ---")
    for pattern, count in profile['strengths'].most_common(5):
        print(f"  {pattern}: {count}")

    training_data['format_version'] = 2
    with open(OUTPUT_TRAINING, 'wb') as f:
        pickle.dump(training_data, f)
    print(f"\nPersonalised training data saved to {OUTPUT_TRAINING} ({len(training_data['positions'])} positions).")
    print(f"\nRun: python train.py {OUTPUT_TRAINING} 50 0.001 512 chess_nn_personal.pkl")
    print("to train a network tailored to your style.")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python personal_coach.py <your_games.pgn> <your_name_lowercase>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2].lower())
