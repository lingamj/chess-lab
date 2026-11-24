#!/usr/bin/env python3
"""Generate multi‑source training data (version‑2 dict).
   Value convention: side-to-move perspective.
   Fields: positions, policies, values, move_uci, source, white_elo, black_elo,
            opening, date, game_ids, game_starts, format_version.
"""

import pickle, os, random, time, re
from board import ChessBoard
from nn import DualNet
from search import SearchEngine
from move_helpers import move_to_str, str_to_move, move_to_index, move_to_san
from dataset_schema import FORMAT_VERSION, FIELDS, validate_integrity
from training_targets import blended_value

MODEL_PATH = 'chess_nn.pkl'
GAMES_PER_THEME = 2
DEPTH = 6
TIME_LIMIT = 100
STOCKFISH_PATH = '/data/data/com.termux/files/home/chess_ai/stockfish.sh'
USER_PGN_FILE = 'last_import.pgn'
NUM_SF_GAMES = 10

THEMES = [
    'checkmate', 'capture', 'pawnpush', 'king_safety', 'mobility',
    'opening', 'endgame', 'check', 'tactical', 'defense',
]

def load_engine():
    nn = DualNet()
    if not nn.load(MODEL_PATH):
        raise FileNotFoundError("Model not found")
    return SearchEngine(nn=nn, max_depth=DEPTH)

def _remove_variations(text):
    result = []
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            if depth > 0:
                depth -= 1
        elif depth == 0:
            result.append(ch)
    return ''.join(result)

# ---------- Self‑play ----------
def play_self_play_game(engine):
    engine.tt.clear()
    if hasattr(engine, 'root_scores'): engine.root_scores.clear()
    if hasattr(engine, 'sorted_root_scores'): engine.sorted_root_scores.clear()
    if hasattr(engine, 'last_pv'): engine.last_pv = []

    board = ChessBoard()
    positions, moves_tup, moves_idx = [], [], []
    while True:
        legal = board.generate_legal_moves()
        if not legal:
            break
        move, _, _, _ = engine.search(board, time_limit=TIME_LIMIT, depth=DEPTH)
        if move is None or move not in legal:
            move = random.choice(legal)
        positions.append(board.copy())
        moves_tup.append(move)
        moves_idx.append(move_to_index(move))
        board.make_move(move)
        if board.is_checkmate() or board.is_draw():
            break
    if board.is_checkmate():
        white_result = -1.0 if board.white_turn else 1.0
    elif board.is_draw():
        white_result = 0.0
    else:
        white_result = 0.0
    values = []
    for pos in positions:
        if white_result == 0.0:
            values.append(0.0)
        else:
            values.append(blended_value(white_result, pos))
    return positions, moves_tup, moves_idx, values

# Theme filters (unchanged)
def theme_checkmate(board, move, engine):
    try: _, score, _, _ = engine.search(board, time_limit=500, depth=6); return abs(score) > 29000
    except: return False
def theme_capture(board, move, engine):
    return board.board[move[2]][move[3]] != '.' or (len(move) > 4 and move[4] is not None)
def theme_pawnpush(board, move, engine):
    return board.board[move[0]][move[1]].upper() == 'P'
def theme_king_safety(board, move, engine):
    return board.is_king_in_check('w' if board.white_turn else 'b')
def theme_mobility(board, move, engine):
    return len(board.generate_legal_moves()) >= 30
def theme_opening(board, move, engine):
    return board.fullmove_number <= 10
def theme_endgame(board, move, engine):
    return sum(1 for row in board.board for p in row if p != '.') <= 12
def theme_check(board, move, engine):
    undo = board.make_move(move, update_history=False)
    opponent = 'b' if board.white_turn else 'w'
    g = board.is_king_in_check(opponent)
    board.undo_move(undo, update_history=False)
    return g
def theme_tactical(board, move, engine):
    return theme_capture(board, move, engine) or theme_check(board, move, engine)
def theme_defense(board, move, engine):
    return board.is_king_in_check('w' if board.white_turn else 'b')

THEME_FILTERS = {
    'checkmate': theme_checkmate, 'capture': theme_capture,
    'pawnpush': theme_pawnpush, 'king_safety': theme_king_safety,
    'mobility': theme_mobility, 'opening': theme_opening,
    'endgame': theme_endgame, 'check': theme_check,
    'tactical': theme_tactical, 'defense': theme_defense,
}

def generate_theme_data(theme, engine, num_games, start_game_id):
    out = {f: [] for f in FIELDS}
    filter_fn = THEME_FILTERS[theme]
    for g in range(num_games):
        print(f"  Theme {theme}: game {g+1}/{num_games}")
        positions, moves_tup, moves_idx, values = play_self_play_game(engine)
        first = True
        for pos, mtup, idx, val in zip(positions, moves_tup, moves_idx, values):
            if filter_fn(pos, mtup, engine):
                out["positions"].append(pos)
                out["policies"].append(idx)
                out["values"].append(val)
                out["move_uci"].append(move_to_str(mtup))
                out["source"].append(1)
                out["white_elo"].append("")
                out["black_elo"].append("")
                out["opening"].append(theme)
                out["date"].append("")
                out["game_ids"].append(start_game_id + g)
                out["game_starts"].append(first)
                first = False
    return out

# ---------- PGN parsing ----------
def parse_pgn_to_training(pgn_text, start_game_id):
    # Auto-clean comments and variations
    import re
    pgn_text = re.sub(r"\{[^}]*\}", "", pgn_text, flags=re.DOTALL)
    def _remove_parens(text):
        result = []
        depth = 0
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth > 0:
                    depth -= 1
            elif depth == 0:
                result.append(ch)
        return "".join(result)
    pgn_text = _remove_parens(pgn_text)
    pgn_text = re.sub(r"^%.*$", "", pgn_text, flags=re.MULTILINE)
    """Robust PGN parser – converts all legal moves into training positions."""
    out = {f: [] for f in FIELDS}
    import re
    # Split games: look for "[Event " at the start of a line
    raw_games = re.split(r'\n(?=\[Event )', pgn_text.strip())
    games = [g for g in raw_games if g.startswith('[Event ')]

    for gidx, game_str in enumerate(games):
        board = ChessBoard()
        result = '*'
        for line in game_str.split('\n'):
            if line.startswith('[Result '):
                result = line.split('"')[1]
                break
        white_result = 1.0 if result == '1-0' else (-1.0 if result == '0-1' else 0.0)

        # Extract moves: text after the last header bracket
        last_tag = game_str.rfind(']')
        moves_text = game_str[last_tag+1:]
        moves_text = re.sub(r'\{[^}]*\}', '', moves_text, flags=re.DOTALL)
        moves_text = moves_text.replace('{', '').replace('}', '')
        moves_text = _remove_variations(moves_text)
        moves_text = re.sub(r'\d+\.', '', moves_text)
        moves_text = re.sub(r'[?!+#]', '', moves_text)
        tokens = moves_text.split()
        if tokens and tokens[-1] in ('1-0','0-1','1/2-1/2','*'):
            tokens = tokens[:-1]

        first = True
        for san in tokens:
            legal = board.generate_legal_moves()
            move_found = None
            # 1. Try direct SAN matching
            for m in legal:
                try:
                    if move_to_san(m, board) == san:
                        move_found = m
                        break
                except:
                    pass
            # 2. Fallback: coordinate notation like d2d4
            if move_found is None and len(san) >= 4 and san[0].islower() and san[1].isdigit():
                try:
                    candidate = str_to_move(san)
                    if candidate in legal:
                        move_found = candidate
                except:
                    pass
            # 3. Fallback: promotion with '=' like a8=Q
            if move_found is None and '=' in san:
                clean = san.replace('=', '')
                try:
                    candidate = str_to_move(clean)
                    if candidate in legal:
                        move_found = candidate
                except:
                    pass
            if move_found is None:
                continue  # skip unparseable tokens

            out["positions"].append(board.copy())
            out["policies"].append(move_to_index(move_found))
            val = blended_value(white_result, board)
            out["values"].append(val)
            out["move_uci"].append(move_to_str(move_found))
            out["source"].append(0)   # 0 = PGN
            out["white_elo"].append("")
            out["black_elo"].append("")
            out["opening"].append("")
            out["date"].append("")
            out["game_ids"].append(start_game_id + gidx)
            out["game_starts"].append(first)
            first = False
            board.make_move(move_found)

    return out

# ---------- Stockfish games ----------
class StockfishEngine:
    def __init__(self, path='stockfish'):
        import subprocess
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        self._send('uci'); self._read_until('uciok'); self._send('isready'); self._read_until('readyok')
    def _send(self, cmd): self.proc.stdin.write(cmd+'\n'); self.proc.stdin.flush()
    def _read_until(self, keyword):
        while True:
            line = self.proc.stdout.readline().strip()
            if keyword in line: break
    def get_move(self, fen, time_ms=1000):
        self._send(f'position fen {fen}'); self._send(f'go movetime {time_ms}')
        best = None
        while True:
            line = self.proc.stdout.readline().strip()
            if line.startswith('bestmove'):
                parts = line.split()
                if len(parts) >= 2 and parts[1] != '(none)': best = parts[1]
                break
        return str_to_move(best) if best else None
    def quit(self): self.proc.terminate()

def generate_stockfish_games(engine, num_games, start_game_id):
    out = {f: [] for f in FIELDS}
    try:
        sf = StockfishEngine(STOCKFISH_PATH)
    except Exception as e:
        print(f"  Stockfish unavailable ({e}), skipping.")
        return out
    for g in range(num_games):
        print(f"  Stockfish game {g+1}/{num_games}")
        board = ChessBoard()
        engine_white = random.choice([True, False])
        engine_moves = []
        while True:
            legal = board.generate_legal_moves()
            if not legal: break
            if (engine_white and board.white_turn) or (not engine_white and not board.white_turn):
                move, _, _, _ = engine.search(board, time_limit=100, depth=6)
                if move is None or move not in legal:
                    move = random.choice(legal)
                engine_moves.append((board.copy(), move_to_index(move), move))
            else:
                try:
                    move = sf.get_move(board.to_fen(), 100)
                    if move is None or move not in legal:
                        move = random.choice(legal)
                except:
                    move = random.choice(legal)
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
        for pos, idx, move in engine_moves:
            out["positions"].append(pos)
            out["policies"].append(idx)
            val = blended_value(white_result, pos)
            out["values"].append(val)
            out["move_uci"].append(move_to_str(move))
            out["source"].append(2)
            out["white_elo"].append("")
            out["black_elo"].append("")
            out["opening"].append("")
            out["date"].append("")
            out["game_ids"].append(start_game_id + g)
            out["game_starts"].append(first)
            first = False
    sf.quit()
    return out

def main():
    engine = load_engine()
    all_data = {f: [] for f in FIELDS}
    next_game_id = 0

    for theme in THEMES:
        print(f"\n=== Themed self‑play: {theme} ===")
        d = generate_theme_data(theme, engine, GAMES_PER_THEME, next_game_id)
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += GAMES_PER_THEME
        print(f"  Collected {len(d['positions'])} positions.")

    print("\n=== Importing user PGN games ===")
    pgn_content = ''
    if os.path.exists(USER_PGN_FILE):
        with open(USER_PGN_FILE) as f:
            pgn_content = f.read()
    if pgn_content:
        d = parse_pgn_to_training(pgn_content, next_game_id)
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += len(set(d["game_ids"]))
        print(f"  Added {len(d['positions'])} PGN positions.")
    else:
        print("  No PGN file found, skipping.")

    print("\n=== Playing vs Stockfish ===")
    d = generate_stockfish_games(engine, NUM_SF_GAMES, next_game_id)
    if d["positions"]:
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += NUM_SF_GAMES
        print(f"  Added {len(d['positions'])} Stockfish positions.")

    all_data["format_version"] = FORMAT_VERSION
    from move_helpers import NUM_MOVES
    validate_integrity(all_data, NUM_MOVES)

    with open('training_data_merged.pkl', 'wb') as f:
        pickle.dump(all_data, f)
    print(f"Saved training_data_merged.pkl ({len(all_data['positions'])} positions, version {FORMAT_VERSION}).")

if __name__ == '__main__':
    main()
