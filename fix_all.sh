#!/bin/bash
set -e
echo "🔧 Applying comprehensive fixes..."

# ---------- 1. Ensure build_tree.py exists ----------
if [ ! -f build_tree.py ]; then
    echo "📄 Creating build_tree.py..."
    cat > build_tree.py << 'PY'
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
                    'results': [0, 0, 0],
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
    meta = {'version': 1, 'created': int(time.time()), 'games': game_count}
    with gzip.open(path, 'wb') as f:
        pickle.dump(meta, f, pickle.HIGHEST_PROTOCOL)
    print(f"Saved meta to {path}")

if __name__ == "__main__":
    if not os.path.exists(PGN_FILE):
        print(f"PGN file {PGN_FILE} not found.")
        sys.exit(1)
    print("Building opening tree...")
    tree, examples, fen_to_id, game_count = build_tree_from_pgn(PGN_FILE)
    save_tree(tree)
    save_examples(examples)
    save_meta(game_count)
    print(f"Tree build complete. {game_count} games processed.")
PY
fi

# ---------- 2. Create a sample PGN if none exists ----------
if [ ! -f last_import.pgn ]; then
    echo "📄 Creating sample PGN..."
    cat > last_import.pgn << 'PGN'
[Event "Sample"]
[Site "?"]
[Date "2025.01.01"]
[Round "1"]
[White "Player"]
[Black "Computer"]
[Result "1-0"]
1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Na4 c5 16. dxe5 dxe5 17. Bxf6 Bxf6 18. Qxd8 Raxd8 19. Rad1 Rxd1 20. Rxd1 Bc8 21. Nxe5 Bxe5 22. Bxf7+ Kh8 23. Rxd7 Bxd7 24. Bxg6 hxg6 25. Nc5 Bc8 26. Ne6 Rf4 27. Nxf4 Bxf4 28. b3 Be5 29. f4 Bf6 30. Kf2 Kg8 31. Ke3 Kf8 32. Ke4 Ke7 33. Kf5 Kd6 34. g4 Bxg4 35. Kxg4 Ke5 36. h4 Ke4 37. h5 Ke5 38. Kf3 Kd4 39. h6 Ke5 40. h7 Kf5 41. h8=Q Ke5 42. Qe8+ Kd4 43. Qxe7 Kc3 44. Qe3+ Kc2 45. Ke4 Kb2 46. Kd4 Kxb3 47. Qe2 Ka4 48. Kc4 Ka5 49. Qa2+ Kb6 50. Qb3+ Ka7 51. Kc5 Ka6 52. Qb6# 1-0
PGN
fi

# ---------- 3. Build the opening tree ----------
echo "🌳 Building opening tree..."
python build_tree.py

# ---------- 4. Fix frontend constants ----------
cat > frontend/js/constants.js << 'CONST'
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const COLORS = { WHITE: 'white', BLACK: 'black' };
export const TRAINING_DELAY = 2000;
export const API_BASE = '';
export const MAX_GRAPH_POINTS = 100;
CONST

# ---------- 5. Fix board.js (Unicode pieces, proper sizing) ----------
cat > frontend/js/board.js << 'BOARD'
import { state, refreshUI } from './state.js';

const pieceSymbols = {
    'r': '♜','n':'♞','b':'♝','q':'♛','k':'♚','p':'♟',
    'R': '♖','N':'♘','B':'♗','Q':'♕','K':'♔','P':'♙'
};

export function parseFen(fen) {
    const parts = fen.split(' ');
    const rows = parts[0].split('/');
    const board = [];
    for (const row of rows) {
        const line = [];
        for (const ch of row) {
            if (ch >= '1' && ch <= '8') {
                for (let i = 0; i < parseInt(ch, 10); i++) line.push(null);
            } else {
                line.push(ch);
            }
        }
        board.push(line);
    }
    return board;
}

export function squareToPixels(square) {
    const boardEl = document.getElementById('board');
    const size = boardEl ? boardEl.clientWidth / 8 : 50;
    let file = square.charCodeAt(0) - 97;
    let rank = 8 - parseInt(square[1], 10);
    if (state.flipped) {
        file = 7 - file;
        rank = 7 - rank;
    }
    return { x: file * size + size/2, y: rank * size + size/2 };
}

export function renderBoard(fen) {
    const board = parseFen(fen);
    const container = document.getElementById('board');
    if (!container) return;
    container.innerHTML = '';

    const rows = state.flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
    const cols = state.flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];

    for (const r of rows) {
        for (const c of cols) {
            const sq = document.createElement('div');
            const isLight = (r + c) % 2 === 0;
            sq.className = 'square ' + (isLight ? 'light' : 'dark');
            const piece = board[r][c];
            if (piece) {
                sq.textContent = pieceSymbols[piece] || piece;
                sq.style.fontSize = '48px';
                sq.style.fontWeight = 'bold';
            }
            sq.dataset.row = r;
            sq.dataset.col = c;
            container.appendChild(sq);
        }
    }

    renderLabels();
    document.getElementById('fen-display').textContent = 'FEN: ' + fen;
}

function renderLabels() {
    const fileContainer = document.getElementById('file-labels');
    const rankContainer = document.getElementById('rank-labels');
    if (!fileContainer || !rankContainer) return;
    const files = state.flipped ? ['h','g','f','e','d','c','b','a'] : ['a','b','c','d','e','f','g','h'];
    const ranks = state.flipped ? ['1','2','3','4','5','6','7','8'] : ['8','7','6','5','4','3','2','1'];
    fileContainer.innerHTML = files.map(f => `<span>${f}</span>`).join('');
    rankContainer.innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
}

export async function flipBoard() {
    state.flipped = !state.flipped;
    await refreshUI();
}
BOARD

# ---------- 6. Update CSS for piece size ----------
cat > frontend/css/style.css << 'CSS'
* { box-sizing: border-box; }
body { font-family: sans-serif; margin: 10px; background: #f5f5f5; }
#app { max-width: 700px; margin:0 auto; }

#board-area { position:relative; width:100%; max-width:600px; margin:0 auto; }
.file-labels { display:flex; justify-content:space-around; padding:0 20px; font-size:14px; }
.rank-labels { display:flex; flex-direction:column; justify-content:space-around; padding-right:6px; font-size:14px; float:left; height:100%; }
#board-container { display:flex; }
#board { width:100%; aspect-ratio:1; display:grid; grid-template-columns:repeat(8,1fr); position:relative; z-index:1; }
.square { aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:48px; font-weight:bold; cursor:pointer; user-select:none; position:relative; }
.light { background:#f0d9b5; }
.dark { background:#b58863; }
.square.legal { box-shadow: inset 0 0 0 4px #4caf50; }

#arrows-container { position:absolute; inset:0; z-index:2; pointer-events:none; }
#move-history span { cursor:pointer; color:#2c3e50; text-decoration:underline; margin-right:6px; }
#move-history span:hover { color:#e74c3c; }

#info { background:#fff; padding:16px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); }
#tree li { padding:4px 0; border-bottom:1px solid #eee; display:flex; gap:8px; align-items:center; cursor:pointer; }
#tree li:hover { background:#f0f0f0; }
.popularity-bar { flex:1; height:6px; background:#ddd; border-radius:3px; overflow:hidden; }
.popularity-fill { height:100%; background:#2c3e50; border-radius:3px; }
.stat { font-size:12px; color:#555; white-space:nowrap; }

label { display:block; margin-top:8px; font-size:14px; }
input, textarea, select { width:100%; padding:4px; font-size:14px; }
button { margin:4px 2px; padding:4px 12px; cursor:pointer; }
CSS

echo ""
echo "✅ All fixes applied."
echo "▶️  Start the server with: python web_control.py"
echo "🌐 Then open: http://localhost:5000/frontend/index.html"
