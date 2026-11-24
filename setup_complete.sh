#!/bin/bash
set -e
echo "🚀 Setting up ChessAI – complete backend + frontend..."

# ---------- 1. Ensure all Python modules exist ----------
echo "📦 Checking required Python modules..."
for f in board.py move_helpers.py search.py nn.py opening.py repertoire.py build_tree.py; do
    if [ ! -f "$f" ]; then
        echo "❌ Missing $f – please ensure you have all files."
        exit 1
    fi
done

# ---------- 2. Build opening tree ----------
echo "🌳 Building opening tree..."
if [ -f "last_import.pgn" ]; then
    python build_tree.py
else
    echo "⚠️  No PGN found. Creating a sample game..."
    cat > sample.pgn << 'PGN'
[Event "Sample"]
[Site "?"]
[Date "2025.01.01"]
[Round "1"]
[White "Player"]
[Black "Computer"]
[Result "1-0"]
1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Na4 c5 16. dxe5 dxe5 17. Bxf6 Bxf6 18. Qxd8 Raxd8 19. Rad1 Rxd1 20. Rxd1 Bc8 21. Nxe5 Bxe5 22. Bxf7+ Kh8 23. Rxd7 Bxd7 24. Bxg6 hxg6 25. Nc5 Bc8 26. Ne6 Rf4 27. Nxf4 Bxf4 28. b3 Be5 29. f4 Bf6 30. Kf2 Kg8 31. Ke3 Kf8 32. Ke4 Ke7 33. Kf5 Kd6 34. g4 Bxg4 35. Kxg4 Ke5 36. h4 Ke4 37. h5 Ke5 38. Kf3 Kd4 39. h6 Ke5 40. h7 Kf5 41. h8=Q Ke5 42. Qe8+ Kd4 43. Qxe7 Kc3 44. Qe3+ Kc2 45. Ke4 Kb2 46. Kd4 Kxb3 47. Qe2 Ka4 48. Kc4 Ka5 49. Qa2+ Kb6 50. Qb3+ Ka7 51. Kc5 Ka6 52. Qb6# 1-0
PGN
    mv sample.pgn last_import.pgn
    python build_tree.py
fi

# ---------- 3. Add import endpoint to web_control.py ----------
echo "🔌 Adding import endpoint..."
if ! grep -q "/api/import_games" web_control.py; then
    cat >> web_control.py << 'PYEND'

@app.route('/api/import_games', methods=['POST'])
def api_import_games():
    """Import games from Lichess or Chess.com, rebuild opening tree."""
    import subprocess, os
    data = request.get_json()
    source = data.get('source')
    username = data.get('username', '').strip()
    if not username:
        return jsonify({'error': 'Username required'}), 400
    try:
        from pgn_learner import download_all_lichess_games, download_all_chesscom_games
    except ImportError:
        return jsonify({'error': 'pgn_learner.py not found'}), 500
    if source == 'lichess':
        pgn = download_all_lichess_games(username)
    elif source == 'chesscom':
        pgn = download_all_chesscom_games(username)
    else:
        return jsonify({'error': 'Invalid source'}), 400
    if not pgn.strip():
        return jsonify({'error': 'No games downloaded'}), 400
    pgn_path = os.path.join(CHESS_DIR, 'last_import.pgn')
    with open(pgn_path, 'w', encoding='utf-8') as f:
        f.write(pgn)
    result = subprocess.run(['python', os.path.join(CHESS_DIR, 'build_tree.py')],
                             capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        return jsonify({'error': 'Tree build failed', 'details': result.stderr}), 500
    return jsonify({'status': 'ok', 'message': f'Imported {source} games for {username} and rebuilt tree.'})
PYEND
    echo "✅ Import endpoint added."
else
    echo "✅ Import endpoint already exists."
fi

# ---------- 4. Download SVG pieces (fallback to Unicode) ----------
echo "🖼️  Downloading SVG pieces..."
mkdir -p frontend/pieces
cd frontend/pieces
for piece in wK wQ wR wB wN wP bK bQ bR bB bN bP; do
    [ -f "${piece}.svg" ] || curl -s -o "${piece}.svg" "https://cdn.jsdelivr.net/gh/ornicar/lila-pieces@main/merida/${piece}.svg" &
done
wait
cd ../..

# ---------- 5. Fix board.js to use Unicode fallback ----------
echo "🛠️  Updating board.js (Unicode fallback)..."
cat > frontend/js/board.js << 'JS'
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
                const img = document.createElement('img');
                const color = piece === piece.toUpperCase() ? 'w' : 'b';
                const typeMap = { 'K':'K','Q':'Q','R':'R','B':'B','N':'N','P':'P' };
                const type = typeMap[piece.toUpperCase()];
                img.src = `frontend/pieces/${color}${type}.svg`;
                img.className = 'piece';
                img.draggable = false;
                img.alt = piece;
                img.onerror = function() {
                    this.style.display = 'none';
                    this.parentElement.textContent = pieceSymbols[piece] || piece;
                };
                sq.appendChild(img);
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
JS

# ---------- 6. Start the server ----------
echo "▶️  Starting Flask server..."
echo "   Access at: http://localhost:5000/frontend/index.html"
python web_control.py
