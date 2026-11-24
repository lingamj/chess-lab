#!/usr/bin/env python3
"""Build opening tree from PGN files – with ECO/opening counts, fen_id, compression."""

import os, sys, pickle, gzip, time
from collections import defaultdict
from board import ChessBoard
from move_helpers import move_to_str, str_to_move, move_to_san
import chess.pgn

HOME = os.path.expanduser("~")
CHESS_DIR = os.path.join(HOME, "chess_ai")
PGN_FILE = os.path.join(CHESS_DIR, "last_import.pgn")
TREE_FILE = os.path.join(CHESS_DIR, "opening_tree.pkl.gz")
EXAMPLES_FILE = os.path.join(CHESS_DIR, "game_examples.pkl.gz")
META_FILE = os.path.join(CHESS_DIR, "opening_meta.pkl.gz")

def parse_elo(x):
    try:
        return int(x)
    except (ValueError, TypeError):
        return 0

def build_tree_from_pgn(pgn_path, max_games=100000):
    tree = {}
    examples = {}
    fen_to_id = {}
    next_id = 0
    game_count = 0

    with open(pgn_path, 'r', encoding='utf-8', errors='ignore') as f:
        while game_count < max_games:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            result = game.headers.get("Result", "*")
            white = game.headers.get("White", "")
            black = game.headers.get("Black", "")
            white_elo = parse_elo(game.headers.get("WhiteElo"))
            black_elo = parse_elo(game.headers.get("BlackElo"))
            eco = game.headers.get("ECO", "")
            opening = game.headers.get("Opening", "")
            date = game.headers.get("Date", "")
            moves = list(game.mainline_moves())
            if not moves:
                continue

            board = ChessBoard()
            for move in moves:
                fen = board.to_fen()
                uci = move.uci()
                engine_move = str_to_move(uci)
                if engine_move is None:
                    break
                legal = board.generate_legal_moves()
                if engine_move not in legal:
                    break
                san = move_to_san(engine_move, board)

                if fen not in fen_to_id:
                    fen_to_id[fen] = next_id
                    next_id += 1
                fen_id = fen_to_id[fen]

                if fen not in tree:
                    tree[fen] = {
                        'id': fen_id,
                        'eco_counts': {},
                        'opening_counts': {},
                        'total_games': 0,
                        'moves': {}
                    }
                pos = tree[fen]
                pos['total_games'] += 1
                if eco:
                    pos['eco_counts'][eco] = pos['eco_counts'].get(eco, 0) + 1
                if opening:
                    pos['opening_counts'][opening] = pos['opening_counts'].get(opening, 0) + 1

                move_data = pos['moves'].setdefault(uci, {
                    'uci': uci,
                    'san': san,
                    'games': 0,
                    'results': [0, 0, 0],   # [white_wins, draws, black_wins]
                    'elo_sum': 0,
                    'elo_count': 0,
                })
                move_data['games'] += 1
                avg_elo = (white_elo + black_elo) // 2 if white_elo and black_elo else 0
                if avg_elo > 0:
                    move_data['elo_sum'] += avg_elo
                    move_data['elo_count'] += 1
                if result == "1-0":
                    move_data['results'][0] += 1
                elif result == "0-1":
                    move_data['results'][2] += 1
                else:
                    move_data['results'][1] += 1

                key = (fen_id, uci)
                if key not in examples:
                    examples[key] = []
                examples[key].append({
                    'white': white,
                    'black': black,
                    'date': date,
                    'result': result,
                    'elo': avg_elo
                })
                examples[key].sort(key=lambda x: -x['elo'])
                examples[key] = examples[key][:5]

                board.make_move(engine_move)
            game_count += 1
            if game_count % 100 == 0:
                print(f"Processed {game_count} games...")

    # Post-process
    for fen, pos in tree.items():
        total = pos['total_games']
        if total == 0:
            continue
        if pos['eco_counts']:
            pos['eco'] = max(pos['eco_counts'], key=pos['eco_counts'].get)
        else:
            pos['eco'] = 'A00'
        if pos['opening_counts']:
            pos['opening'] = max(pos['opening_counts'], key=pos['opening_counts'].get)
        else:
            pos['opening'] = 'Unclassified'
        del pos['eco_counts']
        del pos['opening_counts']

        for uci, stats in pos['moves'].items():
            stats['avg_elo'] = (stats['elo_sum'] // stats['elo_count']) if stats['elo_count'] else 0
            del stats['elo_sum']
            del stats['elo_count']
            stats['popularity'] = round(stats['games'] * 100.0 / total, 1)

    return tree, examples, fen_to_id, game_count

def save_tree(tree, path=TREE_FILE):
    with gzip.open(path, 'wb') as f:
        pickle.dump(tree, f, pickle.HIGHEST_PROTOCOL)
    print(f"Saved tree to {path}")

def save_examples(examples, path=EXAMPLES_FILE):
    with gzip.open(path, 'wb') as f:
        pickle.dump(examples, f, pickle.HIGHEST_PROTOCOL)
    print(f"Saved examples to {path}")

def save_meta(game_count, path=META_FILE):
    meta = {
        'version': 1,
        'created': int(time.time()),
        'games': game_count
    }
    with gzip.open(path, 'wb') as f:
        pickle.dump(meta, f, pickle.HIGHEST_PROTOCOL)
    print(f"Saved meta to {path}")


def build_tree_from_db(max_games=100000, game_ids=None):
    """Build the opening tree from the SQLite game database.

    Returns the same (tree, examples, fen_to_id, game_count) tuple
    as build_tree_from_pgn(), but reads from chess_ai.db instead of
    a PGN file.
    """
    import sqlite3
    DB_PATH = os.path.join(CHESS_DIR, "chess_ai.db")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Ownership aliases: canonical player names + all recorded aliases.
    try:
        _alias_rows = conn.execute(
            "SELECT alias FROM player_aliases "
            "UNION SELECT canonical_name FROM canonical_players"
        ).fetchall()
        ownership_aliases = {
            (r[0] or "").strip().lower()
            for r in _alias_rows
            if r and r[0]
        }
    except sqlite3.Error:
        ownership_aliases = set()

    tree = {}
    examples = {}
    example_seen = {}
    fen_to_id = {}
    next_id = 0
    game_count = 0

    if game_ids is not None:
        game_ids = list(game_ids)
        if not game_ids:
            games = []
        else:
            placeholders = ",".join("?" for _ in game_ids)
            games = conn.execute(
                f"SELECT id, white, black, white_elo, black_elo, result, eco, opening, date "
                f"FROM games WHERE id IN ({placeholders}) ORDER BY id",
                game_ids
            ).fetchall()
    else:
        games = conn.execute(
            "SELECT id, white, black, white_elo, black_elo, result, eco, opening, date "
            "FROM games ORDER BY id"
        ).fetchall()

    for game in games:
        if game_count >= max_games:
            break

        moves = conn.execute(
            """SELECT gm.ply, gm.uci, gm.san, p.fen, p.canonical_fen
               FROM game_moves gm
               JOIN positions p ON p.id = gm.position_id
               WHERE gm.game_id = ?
               ORDER BY gm.ply""",
            (game["id"],)
        ).fetchall()

        if not moves:
            continue

        # Zero-move games have only one game_moves row at ply 0.
        # They belong in games/statistics but do not contribute to
        # the opening tree and should not consume tree capacity.
        if len(moves) <= 1:
            continue

        raw_white = (game["white"] or "").strip().lower()
        raw_black = (game["black"] or "").strip().lower()
        is_me_white = raw_white in ownership_aliases
        is_me_black = raw_black in ownership_aliases

        white   = game["white"] or "?"
        black   = game["black"] or "?"
        white_elo = game["white_elo"] or 0
        black_elo = game["black_elo"] or 0
        result  = game["result"] or "*"
        eco     = game["eco"] or ""
        opening = game["opening"] or ""
        date    = game["date"] or ""

        avg_elo = (white_elo + black_elo) // 2 if white_elo and black_elo else 0

        for i in range(1, len(moves)):
            prev_fen = moves[i-1]["canonical_fen"] or moves[i-1]["fen"]
            uci      = moves[i]["uci"]
            san      = moves[i]["san"]

            if prev_fen not in fen_to_id:
                fen_to_id[prev_fen] = next_id
                next_id += 1
            fen_id = fen_to_id[prev_fen]

            if prev_fen not in tree:
                tree[prev_fen] = {
                    'id': fen_id,
                    'eco_counts': {},
                    'opening_counts': {},
                    'total_games': 0,
                    'positions': 0,
                    '_seen_games': set(),
                    'moves': {}
                }
            pos = tree[prev_fen]
            pos['positions'] += 1

            if game["id"] not in pos['_seen_games']:
                pos['_seen_games'].add(game["id"])
                pos['total_games'] += 1
                if eco:
                    pos['eco_counts'][eco] = pos['eco_counts'].get(eco, 0) + 1
                if opening:
                    pos['opening_counts'][opening] = pos['opening_counts'].get(opening, 0) + 1

            move_data = pos['moves'].setdefault(uci, {
                'uci': uci,
                'san': san,
                'games': 0,
                'positions': 0,
                '_seen_games': set(),
                'results': [0, 0, 0],
                'elo_sum': 0,
                'elo_count': 0,

                'my_white_games': 0,
                'my_white_results': [0, 0, 0],
                'my_white_elo_sum': 0,
                'my_white_elo_count': 0,
                'my_black_games': 0,
                'my_black_results': [0, 0, 0],
                'my_black_elo_sum': 0,
                'my_black_elo_count': 0,
            })
            move_data['positions'] += 1

            if game["id"] not in move_data['_seen_games']:
                move_data['_seen_games'].add(game["id"])
                move_data['games'] += 1
                if avg_elo > 0:
                    move_data['elo_sum'] += avg_elo
                    move_data['elo_count'] += 1
                if result == "1-0":
                    move_data['results'][0] += 1
                elif result == "0-1":
                    move_data['results'][2] += 1
                else:
                    move_data['results'][1] += 1

                if is_me_white:
                    move_data['my_white_games'] += 1
                    if result == "1-0":
                        move_data['my_white_results'][0] += 1
                    elif result == "0-1":
                        move_data['my_white_results'][2] += 1
                    else:
                        move_data['my_white_results'][1] += 1
                    if white_elo > 0:
                        move_data['my_white_elo_sum'] += white_elo
                        move_data['my_white_elo_count'] += 1

                if is_me_black:
                    move_data['my_black_games'] += 1
                    if result == "1-0":
                        move_data['my_black_results'][0] += 1
                    elif result == "0-1":
                        move_data['my_black_results'][2] += 1
                    else:
                        move_data['my_black_results'][1] += 1
                    if black_elo > 0:
                        move_data['my_black_elo_sum'] += black_elo
                        move_data['my_black_elo_count'] += 1

            key = (fen_id, uci)
            if key not in examples:
                examples[key] = []
                example_seen[key] = set()
            if game["id"] not in example_seen[key]:
                example_seen[key].add(game["id"])
                examples[key].append({
                    'white': white,
                    'black': black,
                    'date': date,
                    'result': result,
                    'elo': avg_elo
                })
                examples[key].sort(key=lambda x: -x['elo'])
                examples[key] = examples[key][:5]

        game_count += 1
        if game_count % 100 == 0:
            print(f"Processed {game_count} games...")

    conn.close()

    for fen, pos in tree.items():
        total = pos['total_games']
        if total == 0:
            continue
        if pos['eco_counts']:
            pos['eco'] = max(pos['eco_counts'], key=pos['eco_counts'].get)
        else:
            pos['eco'] = 'A00'
        if pos['opening_counts']:
            pos['opening'] = max(pos['opening_counts'], key=pos['opening_counts'].get)
        else:
            pos['opening'] = 'Unclassified'
        del pos['eco_counts']
        del pos['opening_counts']
        del pos['_seen_games']

        for uci, stats in pos['moves'].items():
            stats['avg_elo'] = (stats['elo_sum'] // stats['elo_count']) if stats['elo_count'] else 0
            stats['my_white_avg_elo'] = (
                stats['my_white_elo_sum'] // stats['my_white_elo_count']
                if stats['my_white_elo_count'] else 0
            )
            stats['my_black_avg_elo'] = (
                stats['my_black_elo_sum'] // stats['my_black_elo_count']
                if stats['my_black_elo_count'] else 0
            )
            del stats['elo_sum']
            del stats['elo_count']
            del stats['_seen_games']
            del stats['my_white_elo_sum']
            del stats['my_white_elo_count']
            del stats['my_black_elo_sum']
            del stats['my_black_elo_count']
            stats['popularity'] = round(stats['games'] * 100.0 / total, 1)

    return tree, examples, fen_to_id, game_count
if __name__ == "__main__":
    print("Building opening tree from database...")
    tree, examples, fen_to_id, game_count = build_tree_from_db()
    save_tree(tree)
    save_examples(examples)
    save_meta(game_count)
    print(f"Tree build complete. {game_count} games processed.")
