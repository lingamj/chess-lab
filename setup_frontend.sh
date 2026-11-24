#!/bin/bash
set -e

echo "🚀 Setting up Chess Study Frontend..."

# ---------- Create frontend directories ----------
mkdir -p frontend/{js,css,pieces}

# ---------- Backend: add /api/move and /api/legal_moves ----------
# Check if web_control.py exists
if [ ! -f web_control.py ]; then
    echo "⚠️  web_control.py not found. Please ensure you are in ~/chess_ai"
    exit 1
fi

# Backup web_control.py
cp web_control.py web_control.py.bak

# Add new endpoints if not already present
if ! grep -q "@app.route('/api/move'" web_control.py; then
    echo "Adding /api/move endpoint..."
    cat >> web_control.py << 'PYEOF'

@app.route('/api/move', methods=['POST'])
def api_move():
    """Apply a single move and return the new FEN and SAN."""
    data = request.get_json()
    fen = data.get('fen')
    uci = data.get('uci')
    if not fen or not uci:
        return jsonify({'error': 'Missing fen or uci'}), 400

    board = ChessBoard()
    board.set_fen(fen)
    move = str_to_move(uci)
    if move is None:
        return jsonify({'error': 'Invalid move format'}), 400
    legal = board.generate_legal_moves()
    if move not in legal:
        return jsonify({'error': 'Illegal move'}), 400
    san = move_to_san(move, board)
    board.make_move(move)
    return jsonify({
        'fen': board.to_fen(),
        'uci': uci,
        'san': san
    })

@app.route('/api/legal_moves', methods=['POST'])
def api_legal_moves():
    """Return list of legal UCI moves for the given position."""
    data = request.get_json()
    fen = data.get('fen')
    if not fen:
        return jsonify({'error': 'Missing fen'}), 400
    board = ChessBoard()
    board.set_fen(fen)
    moves = board.generate_legal_moves()
    ucis = [move_to_str(m) for m in moves]
    return jsonify({'moves': ucis})
PYEOF
    echo "✅ Added /api/move and /api/legal_moves"
else
    echo "✅ Endpoints already exist."
fi

# ---------- frontend/index.html ----------
cat > frontend/index.html << 'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chess Study</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <div id="app">
        <div id="error-box" style="display:none; color:red; padding:10px; background:#ffeeee; border:1px solid red; border-radius:4px; margin:10px;"></div>

        <div id="board-area" style="position:relative; width:100%; max-width:600px; margin:0 auto;">
            <div id="file-labels" class="file-labels"></div>
            <div id="board-container" style="display:flex;">
                <div id="rank-labels" class="rank-labels"></div>
                <div id="board" style="width:100%; aspect-ratio:1; display:grid; grid-template-columns:repeat(8,1fr); position:relative; z-index:1;"></div>
            </div>
            <div id="arrows-container" style="position:absolute; inset:0; z-index:2; pointer-events:none;"></div>
        </div>

        <div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;">
            <button id="flip-board">Flip</button>
            <button id="reset-board">Reset</button>
            <button id="back-btn">◀</button>
            <button id="forward-btn">▶</button>
            <button id="export-pgn">Export PGN</button>
        </div>
        <div id="fen-display" style="font-size:12px; color:#888;">FEN: ...</div>
        <div id="move-history" style="margin:8px 0; font-size:14px; background:#f9f9f9; padding:4px; border-radius:4px; min-height:24px;"></div>

        <div id="info" style="margin-top:16px;">
            <h2>Opening Explorer</h2>
            <div id="eco-display">ECO: -</div>
            <ul id="tree" style="list-style:none; padding:0;"></ul>

            <hr>

            <h3>Engine Analysis</h3>
            <div id="eval-display">Score: -</div>
            <div id="best-move">Best: -</div>
            <div id="pv-line">PV: -</div>
            <canvas id="eval-graph" style="width:100%; height:120px; background:#f9f9f9; border-radius:4px;"></canvas>

            <hr>

            <h3>Repertoire</h3>
            <div id="rep-stats">Loading stats...</div>
            <label>Color: <select id="rep-color"><option value="white">White</option><option value="black">Black</option></select></label>
            <label>Main move: <input id="rep-main-move" placeholder="e2e4"></label>
            <label>Alternatives: <input id="rep-alternatives" placeholder="d2d4,Nf3"></label>
            <label>Notes: <textarea id="rep-notes" rows="2" cols="30"></textarea></label>
            <label>Tags: <input id="rep-tags" placeholder="opening, sicilian"></label>
            <button id="rep-save">Save</button>
            <button id="rep-delete">Delete</button>

            <hr>

            <h3>Trainer</h3>
            <div id="trainer-fen">-</div>
            <input id="trainer-input" placeholder="Enter move (e.g. Nf3 or e2e4)">
            <button id="trainer-submit">Check</button>
            <button id="trainer-button">Next</button>
            <div id="trainer-result"></div>
        </div>
    </div>
    <script type="module" src="js/app.js"></script>
</body>
</html>
HTML

# ---------- frontend/css/style.css ----------
cat > frontend/css/style.css << 'CSS'
* { box-sizing: border-box; }
body { font-family: sans-serif; margin: 10px; background: #f5f5f5; }
#app { max-width: 700px; margin:0 auto; }

#board-area { position:relative; width:100%; max-width:600px; margin:0 auto; }
.file-labels { display:flex; justify-content:space-around; padding:0 20px; font-size:14px; }
.rank-labels { display:flex; flex-direction:column; justify-content:space-around; padding-right:6px; font-size:14px; float:left; height:100%; }
#board-container { display:flex; }
#board { width:100%; aspect-ratio:1; display:grid; grid-template-columns:repeat(8,1fr); position:relative; z-index:1; }
.square { aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:32px; font-weight:bold; cursor:pointer; user-select:none; position:relative; }
.light { background:#f0d9b5; }
.dark { background:#b58863; }
.square.legal { box-shadow: inset 0 0 0 4px #4caf50; }
.piece { width:90%; height:90%; object-fit:contain; pointer-events:none; user-select:none; -webkit-user-drag:none; }

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

# ---------- frontend/js/constants.js ----------
cat > frontend/js/constants.js << 'JS'
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const COLORS = { WHITE: 'white', BLACK: 'black' };
export const TRAINING_DELAY = 2000;
export const API_BASE = '';
export const MAX_GRAPH_POINTS = 100;
JS

# ---------- frontend/js/state.js ----------
cat > frontend/js/state.js << 'JS'
import { START_FEN } from './constants.js';

export const state = {
    currentFen: START_FEN,
    moveHistory: [],
    historyIndex: -1,
    legalMovesByFrom: {},
    repertoire: null,
    eco: null,
    opening: null,
    selectedSquare: null,
    flipped: false,
    training: {
        active: false,
        entry: null,
        eco: null,
        timer: null,
    },
    loading: false,
    error: null,
    stats: {
        total_positions: 0,
        due_positions: 0,
        accuracy: 0,
        white_count: 0,
        black_count: 0,
    },
    analysis: {
        score: null,
        depth: null,
        bestmove: null,
        pv: [],
        multiPv: [],
    },
    evaluations: [],
    depths: [],
    arrows: [],
    ui: {
        mobile: true,
        showAnalysis: true,
        showTrainer: true,
        showRepertoire: true,
        showHeatmap: true,
    },
};

let callbacks = {};

export function registerCallbacks(cb) { callbacks = cb; }

export async function refreshUI() {
    if (callbacks.renderBoard) await callbacks.renderBoard(state.currentFen);
    if (callbacks.loadTree) await callbacks.loadTree(state.currentFen);
    if (callbacks.loadRepertoire) await callbacks.loadRepertoire(state.currentFen);
    if (callbacks.renderMoveHistory) await callbacks.renderMoveHistory();
    if (callbacks.renderEvalGraph) await callbacks.renderEvalGraph();
    if (callbacks.renderArrows) await callbacks.renderArrows();
    if (callbacks.applyHeatmap) await callbacks.applyHeatmap();
}

export async function goToFen(fen, move = null, addToHistory = true) {
    const previousFen = state.currentFen;
    state.currentFen = fen;
    if (move && addToHistory) {
        state.moveHistory.push({
            ply: state.moveHistory.length + 1,
            fen_before: previousFen,
            uci: move.uci,
            san: move.san,
            fen_after: fen,
        });
        state.historyIndex = state.moveHistory.length - 1;
    }
    await refreshUI();
}

export async function goToStart() {
    state.moveHistory = [];
    state.historyIndex = -1;
    await goToFen(START_FEN);
}

export function setLoading(loading) { state.loading = loading; }

export function setError(error) {
    state.error = error;
    const el = document.getElementById('error-box');
    if (el) {
        el.textContent = error || '';
        el.style.display = error ? 'block' : 'none';
    }
}
JS

# ---------- frontend/js/api.js ----------
cat > frontend/js/api.js << 'JS'
import { API_BASE } from './constants.js';

export async function api(url, options = {}) {
    const res = await fetch(API_BASE + url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    let data;
    try { data = await res.json(); } catch { throw new Error(`Invalid JSON (${res.status})`); }
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
}

export async function applyMove(fen, uci) {
    return api('/api/move', { method: 'POST', body: JSON.stringify({ fen, uci }) });
}

export async function getTree(fen) {
    return api('/api/tree', { method: 'POST', body: JSON.stringify({ fen }) });
}

export async function getRepertoire(fen) {
    return api('/api/repertoire?fen=' + encodeURIComponent(fen));
}

export async function saveRepertoire(fen, data) {
    return api('/api/repertoire', { method: 'POST', body: JSON.stringify({ fen, data }) });
}

export async function deleteRepertoireEntry(fen) {
    return api('/api/repertoire/' + encodeURIComponent(fen), { method: 'DELETE' });
}

export async function getNextTraining() {
    return api('/api/train/next');
}

export async function reviewMove(fen, move) {
    return api('/api/train/review', { method: 'POST', body: JSON.stringify({ fen, move }) });
}

export async function getRepertoireStats() {
    return api('/api/repertoire/stats');
}

export async function exportRepertoire() {
    return api('/api/repertoire/export');
}

export async function importRepertoire(data) {
    return api('/api/repertoire/import', { method: 'POST', body: JSON.stringify(data) });
}
JS

# ---------- frontend/js/board.js ----------
cat > frontend/js/board.js << 'JS'
import { state, refreshUI } from './state.js';

const pieceMap = {
    'K':'wK','Q':'wQ','R':'wR','B':'wB','N':'wN','P':'wP',
    'k':'bK','q':'bQ','r':'bR','b':'bB','n':'bN','p':'bP'
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
                img.src = `pieces/${pieceMap[piece]}.svg`;
                img.className = 'piece';
                img.draggable = false;
                img.alt = piece;
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

# ---------- frontend/js/tree.js ----------
cat > frontend/js/tree.js << 'JS'
import { state, goToFen, setError } from './state.js';
import { getTree, applyMove } from './api.js';

export async function loadTree(fen) {
    const list = document.getElementById('tree');
    const ecoEl = document.getElementById('eco-display');
    if (!list) return;
    try {
        const data = await getTree(fen);
        if (ecoEl) ecoEl.textContent = `ECO: ${data.eco || '-'} – ${data.opening || ''}`;
        list.innerHTML = '';
        if (!data.moves || data.moves.length === 0) {
            list.innerHTML = '<li style="color:#888;">No moves in database.</li>';
            return;
        }
        for (const m of data.moves) {
            const li = document.createElement('li');
            li.innerHTML = `
                <span><strong>${m.san}</strong></span>
                <span class="stat">${m.games} games</span>
                <span class="stat">${m.win_pct}% / ${m.draw_pct}% / ${m.loss_pct}%</span>
                <div class="popularity-bar"><div class="popularity-fill" style="width:${m.popularity}%"></div></div>
            `;
            li.addEventListener('click', async () => {
                try {
                    const result = await applyMove(state.currentFen, m.uci);
                    if (result.fen) {
                        await goToFen(result.fen, { uci: result.uci, san: result.san });
                    }
                } catch (e) { setError(e.message); }
            });
            list.appendChild(li);
        }
    } catch (e) { setError(e.message); }
}
JS

# ---------- frontend/js/repertoire.js ----------
cat > frontend/js/repertoire.js << 'JS'
import { state, setError } from './state.js';
import { getRepertoire, saveRepertoire, deleteRepertoireEntry } from './api.js';
import { updateStats } from './stats.js';

export async function loadRepertoire(fen) {
    try {
        const data = await getRepertoire(fen);
        state.repertoire = data.entry || null;
        document.getElementById('rep-main-move').value = state.repertoire?.main_move || '';
        document.getElementById('rep-alternatives').value = state.repertoire?.alternatives?.join(',') || '';
        document.getElementById('rep-notes').value = state.repertoire?.notes || '';
        document.getElementById('rep-tags').value = state.repertoire?.tags?.join(',') || '';
        document.getElementById('rep-color').value = state.repertoire?.color || 'white';
    } catch (e) { setError(e.message); }
}

export async function saveCurrentRepertoire() {
    const data = {
        color: document.getElementById('rep-color').value || 'white',
        main_move: document.getElementById('rep-main-move').value.trim() || '',
        alternatives: document.getElementById('rep-alternatives').value.split(',').map(s=>s.trim()).filter(Boolean),
        notes: document.getElementById('rep-notes').value.trim(),
        tags: document.getElementById('rep-tags').value.split(',').map(s=>s.trim()).filter(Boolean),
    };
    try {
        await saveRepertoire(state.currentFen, data);
        await loadRepertoire(state.currentFen);
        await updateStats();
        alert('Repertoire saved.');
    } catch (e) { setError(e.message); }
}

export async function deleteCurrentRepertoire() {
    if (!confirm('Delete this entry?')) return;
    try {
        await deleteRepertoireEntry(state.currentFen);
        state.repertoire = null;
        await loadRepertoire(state.currentFen);
        await updateStats();
        alert('Deleted.');
    } catch (e) { setError(e.message); }
}
JS

# ---------- frontend/js/trainer.js ----------
cat > frontend/js/trainer.js << 'JS'
import { state, goToFen, setError } from './state.js';
import { getNextTraining, reviewMove } from './api.js';
import { TRAINING_DELAY } from './constants.js';
import { updateStats } from './stats.js';

export async function startTraining() {
    if (state.training.timer) { clearTimeout(state.training.timer); state.training.timer = null; }
    try {
        const data = await getNextTraining();
        if (!data.fen) { document.getElementById('trainer-result').textContent = '🎉 All reviewed!'; return; }
        await goToFen(data.fen);
        state.training.active = true;
        state.training.entry = data.entry;
        state.training.eco = data.eco;
        document.getElementById('trainer-fen').textContent = data.fen;
        document.getElementById('trainer-input').value = '';
        document.getElementById('trainer-result').textContent = 'Enter your move (SAN or UCI).';
        document.getElementById('trainer-input').focus();
    } catch (e) { setError(e.message); }
}

export async function submitTrainingAnswer() {
    const input = document.getElementById('trainer-input');
    const move = input.value.trim();
    if (!move) return;
    try {
        const result = await reviewMove(state.currentFen, move);
        const resultDiv = document.getElementById('trainer-result');
        if (result.correct) {
            resultDiv.textContent = `✅ Correct! Interval: ${result.interval}d, Easiness: ${result.easiness}`;
        } else {
            resultDiv.textContent = `❌ Wrong. Expected: ${result.expected_san} (${result.expected_uci}). Interval reset.`;
        }
        await updateStats();
        if (state.training.timer) clearTimeout(state.training.timer);
        state.training.timer = setTimeout(startTraining, TRAINING_DELAY);
    } catch (e) { setError(e.message); }
}
JS

# ---------- frontend/js/history.js ----------
cat > frontend/js/history.js << 'JS'
import { state, goToFen } from './state.js';

export function renderMoveHistory() {
    const el = document.getElementById('move-history');
    if (!el) return;
    if (state.moveHistory.length === 0) {
        el.innerHTML = '<span style="color:#888;">No moves yet.</span>';
        return;
    }
    el.innerHTML = state.moveHistory.map((m, i) =>
        `<span class="history-move" data-index="${i}" style="cursor:pointer; color:${i === state.historyIndex ? '#e74c3c' : '#2c3e50'}; text-decoration:underline; margin-right:6px; font-weight:${i === state.historyIndex ? 'bold' : 'normal'};">${m.ply}. ${m.san}</span>`
    ).join('');

    el.querySelectorAll('.history-move').forEach(span => {
        span.addEventListener('click', (e) => {
            const idx = parseInt(span.dataset.index, 10);
            if (idx < 0 || idx >= state.moveHistory.length) return;
            const entry = state.moveHistory[idx];
            const fen = e.shiftKey ? entry.fen_before : entry.fen_after;
            if (fen) goToFen(fen, null, false);
        });
    });
}

export async function goBack() {
    if (state.historyIndex <= 0) return;
    state.historyIndex--;
    const entry = state.moveHistory[state.historyIndex];
    if (entry) { state.currentFen = entry.fen_after; await refreshUI(); }
}

export async function goForward() {
    if (state.historyIndex >= state.moveHistory.length - 1) return;
    state.historyIndex++;
    const entry = state.moveHistory[state.historyIndex];
    if (entry) { state.currentFen = entry.fen_after; await refreshUI(); }
}

// Need refreshUI imported – add at top
import { refreshUI } from './state.js';
JS

# ---------- frontend/js/stats.js ----------
cat > frontend/js/stats.js << 'JS'
import { state } from './state.js';
import { getRepertoireStats } from './api.js';

export async function updateStats() {
    try {
        const stats = await getRepertoireStats();
        state.stats = {
            total_positions: stats.total_positions || 0,
            due_positions: stats.due_positions || 0,
            accuracy: stats.accuracy || 0,
            white_count: stats.white_count || 0,
            black_count: stats.black_count || 0,
        };
        const el = document.getElementById('rep-stats');
        if (el) {
            el.textContent = `Total: ${state.stats.total_positions} | Due: ${state.stats.due_positions} | Accuracy: ${state.stats.accuracy}% | White: ${state.stats.white_count} | Black: ${state.stats.black_count}`;
        }
        return state.stats;
    } catch { return null; }
}
JS

# ---------- frontend/js/legal.js ----------
cat > frontend/js/legal.js << 'JS'
import { state } from './state.js';
import { api } from './api.js';

export async function fetchLegalMoves(fen) {
    try {
        const data = await api('/api/legal_moves', {
            method: 'POST',
            body: JSON.stringify({ fen })
        });
        const map = {};
        for (const uci of (data.moves || [])) {
            if (uci.length < 4) continue;
            const from = uci.slice(0, 2);
            const to = uci.slice(2, 4);
            if (!map[from]) map[from] = new Set();
            map[from].add(to);
        }
        state.legalMovesByFrom = map;
        updateHighlights();
    } catch (e) {
        state.legalMovesByFrom = {};
    }
}

export function updateHighlights() {
    const selected = state.selectedSquare;
    let targets = new Set();
    if (selected) {
        const from = `${String.fromCharCode(97 + selected.col)}${8 - selected.row}`;
        targets = state.legalMovesByFrom[from] || new Set();
    }
    document.querySelectorAll('.square').forEach(el => {
        const row = parseInt(el.dataset.row, 10);
        const col = parseInt(el.dataset.col, 10);
        const square = `${String.fromCharCode(97 + col)}${8 - row}`;
        el.classList.toggle('legal', targets.has(square));
    });
}
JS

# ---------- frontend/js/dragdrop.js ----------
cat > frontend/js/dragdrop.js << 'JS'
import { state, goToFen, setError, refreshUI } from './state.js';
import { applyMove } from './api.js';
import { parseFen } from './board.js';
import { fetchLegalMoves, updateHighlights } from './legal.js';

let dragData = null;
let ignoreNextClick = false;

export function initDragDrop() {
    const boardEl = document.getElementById('board');
    if (!boardEl) return;
    boardEl.addEventListener('mousedown', onStart);
    boardEl.addEventListener('mouseup', onEnd);
    boardEl.addEventListener('mouseleave', onCancel);
    boardEl.addEventListener('touchstart', onTouchStart, { passive: false });
    boardEl.addEventListener('touchmove', onTouchMove, { passive: false });
    boardEl.addEventListener('touchend', onTouchEnd, { passive: false });
    boardEl.addEventListener('click', onTap);
}

function getSquareFromEvent(clientX, clientY) {
    const boardRect = document.getElementById('board').getBoundingClientRect();
    const x = (clientX - boardRect.left) / boardRect.width * 8;
    const y = (clientY - boardRect.top) / boardRect.height * 8;
    const col = Math.floor(x);
    const row = Math.floor(y);
    if (row < 0 || row > 7 || col < 0 || col > 7) return null;
    const el = document.querySelector(`.square[data-row="${row}"][data-col="${col}"]`);
    return { row, col, el };
}

function isOwnPiece(piece, fen) {
    if (!piece) return false;
    const turn = fen.split(' ')[1];
    const isWhite = piece === piece.toUpperCase();
    return (turn === 'w' && isWhite) || (turn === 'b' && !isWhite);
}

function getPromotion(fromRow, toRow, piece) {
    if (piece.toUpperCase() !== 'P') return null;
    if ((piece === 'P' && toRow === 0) || (piece === 'p' && toRow === 7)) return 'q';
    return null;
}

async function makeMove(fromRow, fromCol, toRow, toCol) {
    const board = parseFen(state.currentFen);
    const piece = board[fromRow]?.[fromCol];
    const from = `${String.fromCharCode(97 + fromCol)}${8 - fromRow}`;
    const to = `${String.fromCharCode(97 + toCol)}${8 - toRow}`;
    let uci = from + to;
    const promo = getPromotion(fromRow, toRow, piece);
    if (promo) uci += promo;
    try {
        const result = await applyMove(state.currentFen, uci);
        if (result.fen) {
            state.selectedSquare = null;
            state.legalMovesByFrom = {};
            await goToFen(result.fen, { uci: result.uci, san: result.san });
        }
    } catch (e) { setError(e.message); }
    document.querySelectorAll('.square').forEach(el => el.style.opacity = '1');
}

// ----- Mouse -----
function onStart(e) {
    const sq = getSquareFromEvent(e.clientX, e.clientY);
    if (!sq) return;
    const board = parseFen(state.currentFen);
    const piece = board[sq.row]?.[sq.col];
    if (!isOwnPiece(piece, state.currentFen)) return;
    dragData = { fromRow: sq.row, fromCol: sq.col, piece };
    sq.el.style.opacity = '0.5';
}

async function onEnd(e) {
    if (!dragData) return;
    const sq = getSquareFromEvent(e.clientX, e.clientY);
    if (sq) await makeMove(dragData.fromRow, dragData.fromCol, sq.row, sq.col);
    dragData = null;
}

function onCancel() {
    dragData = null;
    document.querySelectorAll('.square').forEach(el => el.style.opacity = '1');
}

// ----- Touch -----
function onTouchStart(e) {
    e.preventDefault();
    const touch = e.touches[0];
    const sq = getSquareFromEvent(touch.clientX, touch.clientY);
    if (!sq) return;
    const board = parseFen(state.currentFen);
    const piece = board[sq.row]?.[sq.col];
    if (!isOwnPiece(piece, state.currentFen)) return;
    dragData = { fromRow: sq.row, fromCol: sq.col, piece };
    sq.el.style.opacity = '0.5';
}

function onTouchMove(e) { e.preventDefault(); }

async function onTouchEnd(e) {
    if (!dragData) return;
    const touch = e.changedTouches[0];
    const sq = getSquareFromEvent(touch.clientX, touch.clientY);
    if (sq) await makeMove(dragData.fromRow, dragData.fromCol, sq.row, sq.col);
    dragData = null;
    ignoreNextClick = true;
    setTimeout(() => { ignoreNextClick = false; }, 300);
}

// ----- Tap -----
async function onTap(e) {
    if (ignoreNextClick) return;
    if (dragData) return;
    const clientX = e.clientX || e.changedTouches?.[0]?.clientX;
    const clientY = e.clientY || e.changedTouches?.[0]?.clientY;
    if (clientX === undefined || clientY === undefined) return;
    const sq = getSquareFromEvent(clientX, clientY);
    if (!sq) return;
    const board = parseFen(state.currentFen);
    const piece = board[sq.row]?.[sq.col];

    if (state.selectedSquare) {
        await makeMove(state.selectedSquare.row, state.selectedSquare.col, sq.row, sq.col);
        state.selectedSquare = null;
        state.legalMovesByFrom = {};
        updateHighlights();
        return;
    }

    if (isOwnPiece(piece, state.currentFen)) {
        state.selectedSquare = { row: sq.row, col: sq.col };
        await fetchLegalMoves(state.currentFen);
        const from = `${String.fromCharCode(97 + sq.col)}${8 - sq.row}`;
        const filtered = {};
        if (state.legalMovesByFrom[from]) {
            filtered[from] = state.legalMovesByFrom[from];
        }
        state.legalMovesByFrom = filtered;
        updateHighlights();
    } else {
        state.selectedSquare = null;
        state.legalMovesByFrom = {};
        updateHighlights();
    }
}
JS

# ---------- frontend/js/analysis.js ----------
cat > frontend/js/analysis.js << 'JS'
import { state } from './state.js';
import { api } from './api.js';

export async function analyzePosition(fen) {
    try {
        const data = await api('/api/analyze', {
            method: 'POST',
            body: JSON.stringify({ fen })
        });
        state.analysis = {
            score: data.score,
            depth: data.depth,
            bestmove: data.best_move,
            pv: data.pv || [],
            multiPv: data.multipv || [],
        };
        document.getElementById('eval-display').textContent = `Score: ${data.score}`;
        document.getElementById('best-move').textContent = `Best: ${data.best_move}`;
        document.getElementById('pv-line').textContent = `PV: ${(data.pv || []).join(' ')}`;
        if (data.cp !== undefined) {
            state.evaluations.push(data.cp);
            state.depths.push(data.depth);
            if (state.evaluations.length > 50) state.evaluations.shift();
            if (state.depths.length > 50) state.depths.shift();
        }
        state.arrows = (data.multipv || []).slice(0, 3).map((m, i) => {
            const uci = m.move;
            const from = uci.slice(0, 2);
            const to = uci.slice(2, 4);
            const weight = 100 - i * 30;
            const colors = ['#00ff00', '#ffaa00', '#ff0000'];
            return { from, to, weight, color: colors[i] || '#888' };
        });
    } catch (e) {}
}
JS

# ---------- frontend/js/graph.js ----------
cat > frontend/js/graph.js << 'JS'
import { state } from './state.js';
import { MAX_GRAPH_POINTS } from './constants.js';

export function renderEvalGraph() {
    const canvas = document.getElementById('eval-graph');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.parentElement.clientWidth || 400;
    const h = canvas.height = 120;

    let evals = state.evaluations || [];
    if (evals.length < 2) {
        ctx.fillStyle = '#aaa';
        ctx.font = '14px sans-serif';
        ctx.fillText('No evaluation data.', 10, h/2);
        return;
    }
    if (evals.length > MAX_GRAPH_POINTS) {
        state.evaluations = evals.slice(-MAX_GRAPH_POINTS);
        state.depths = (state.depths || []).slice(-MAX_GRAPH_POINTS);
        evals = state.evaluations;
    }

    const maxAbs = Math.max(5, ...evals.map(Math.abs));
    const range = maxAbs * 2;
    const mid = h / 2;

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();

    ctx.strokeStyle = '#2c3e50';
    ctx.lineWidth = 2;
    const step = (w - 20) / (evals.length - 1);
    ctx.beginPath();
    for (let i = 0; i < evals.length; i++) {
        const x = 10 + i * step;
        const y = mid - (evals[i] / range) * (h * 0.4);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
}
JS

# ---------- frontend/js/arrows.js ----------
cat > frontend/js/arrows.js << 'JS'
import { state } from './state.js';
import { squareToPixels } from './board.js';

export function renderArrows() {
    const container = document.getElementById('arrows-container');
    if (!container) return;
    container.innerHTML = '';
    const arrows = state.arrows || [];
    if (arrows.length === 0) return;

    const board = document.getElementById('board');
    const size = board ? board.clientWidth : 400;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';

    arrows.forEach(a => {
        const from = squareToPixels(a.from);
        const to = squareToPixels(a.to);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', from.x);
        line.setAttribute('y1', from.y);
        line.setAttribute('x2', to.x);
        line.setAttribute('y2', to.y);
        line.setAttribute('stroke', a.color || '#ff0000');
        line.setAttribute('stroke-width', Math.max(2, a.weight / 10));
        line.setAttribute('opacity', 0.7);
        const dx = to.x - from.x, dy = to.y - from.y;
        const angle = Math.atan2(dy, dx);
        const size2 = 8;
        const points = [
            [to.x, to.y],
            [to.x - size2 * Math.cos(angle - 0.5), to.y - size2 * Math.sin(angle - 0.5)],
            [to.x - size2 * Math.cos(angle + 0.5), to.y - size2 * Math.sin(angle + 0.5)],
        ];
        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        arrow.setAttribute('points', points.map(p => p.join(',')).join(' '));
        arrow.setAttribute('fill', a.color || '#ff0000');
        svg.appendChild(line);
        svg.appendChild(arrow);
    });
    container.appendChild(svg);
}
JS

# ---------- frontend/js/heatmap.js ----------
cat > frontend/js/heatmap.js << 'JS'
import { state } from './state.js';
import { getTree } from './api.js';

export async function applyHeatmap() {
    const tree = await getTree(state.currentFen);
    if (!tree.moves) return;
    const listItems = document.querySelectorAll('#tree li');
    listItems.forEach((li, idx) => {
        const m = tree.moves[idx];
        if (!m) return;
        const pop = m.popularity || 0;
        let color = '';
        if (pop > 60) color = 'rgba(0,200,0,0.25)';
        else if (pop > 40) color = 'rgba(200,200,0,0.25)';
        else if (pop > 20) color = 'rgba(255,150,0,0.25)';
        else color = 'rgba(200,0,0,0.15)';
        li.style.backgroundColor = color;
        const bar = li.querySelector('.popularity-fill');
        if (bar) bar.style.width = pop + '%';
    });
}
JS

# ---------- frontend/js/pgn.js ----------
cat > frontend/js/pgn.js << 'JS'
import { state } from './state.js';

export function generatePGN() {
    const moves = state.moveHistory;
    if (moves.length === 0) return '';
    let pgn = '[Event "Chess Study"]\n[Date "' + new Date().toISOString().slice(0,10) + '"]\n[White "User"]\n[Black "Study"]\n';
    let moveText = '';
    for (let i = 0; i < moves.length; i++) {
        const m = moves[i];
        if (i % 2 === 0) moveText += `${m.ply}. `;
        moveText += m.san + ' ';
    }
    pgn += moveText.trim();
    return pgn;
}

export function exportPGN() {
    const pgn = generatePGN();
    const blob = new Blob([pgn], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chess_study.pgn';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
JS

# ---------- frontend/js/app.js ----------
cat > frontend/js/app.js << 'JS'
import { state, registerCallbacks, goToStart, setError } from './state.js';
import { renderBoard, flipBoard } from './board.js';
import { loadTree } from './tree.js';
import { loadRepertoire, saveCurrentRepertoire, deleteCurrentRepertoire } from './repertoire.js';
import { startTraining, submitTrainingAnswer } from './trainer.js';
import { renderMoveHistory, goBack, goForward } from './history.js';
import { updateStats } from './stats.js';
import { initDragDrop } from './dragdrop.js';
import { exportPGN } from './pgn.js';
import { renderEvalGraph } from './graph.js';
import { renderArrows } from './arrows.js';
import { applyHeatmap } from './heatmap.js';
import { analyzePosition } from './analysis.js';
import { fetchLegalMoves } from './legal.js';

registerCallbacks({
    renderBoard,
    loadTree,
    loadRepertoire,
    renderMoveHistory,
    renderEvalGraph,
    renderArrows,
    applyHeatmap,
});

function initApp() {
    document.getElementById('trainer-button')?.addEventListener('click', startTraining);
    document.getElementById('trainer-submit')?.addEventListener('click', submitTrainingAnswer);
    document.getElementById('trainer-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitTrainingAnswer();
    });
    document.getElementById('rep-save')?.addEventListener('click', saveCurrentRepertoire);
    document.getElementById('rep-delete')?.addEventListener('click', deleteCurrentRepertoire);
    document.getElementById('flip-board')?.addEventListener('click', flipBoard);
    document.getElementById('reset-board')?.addEventListener('click', goToStart);
    document.getElementById('back-btn')?.addEventListener('click', goBack);
    document.getElementById('forward-btn')?.addEventListener('click', goForward);
    document.getElementById('export-pgn')?.addEventListener('click', exportPGN);

    initDragDrop();

    (async () => {
        try {
            await renderBoard(state.currentFen);
            await loadTree(state.currentFen);
            await loadRepertoire(state.currentFen);
            await renderMoveHistory();
            await updateStats();
            await analyzePosition(state.currentFen);
            await fetchLegalMoves(state.currentFen);
        } catch (e) { setError(e.message); }
    })();

    console.log('Chess Study ready.');
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
JS

echo "✅ All frontend files created."

# ---------- Download SVG pieces ----------
echo "📥 Downloading SVG chess pieces..."
cd frontend/pieces
for piece in wK wQ wR wB wN wP bK bQ bR bB bN bP; do
    if [ ! -f "${piece}.svg" ]; then
        echo "  Downloading ${piece}.svg..."
        curl -s -o "${piece}.svg" "https://cdn.jsdelivr.net/gh/ornicar/lila-pieces@main/merida/${piece}.svg" || echo "  ⚠️ Failed to download ${piece}.svg"
    fi
done
cd ../..

echo "✅ Setup complete!"
echo ""
echo "▶️ To start the engine:"
echo "   cd ~/chess_ai"
echo "   python web_control.py"
echo ""
echo "▶️ Then open your browser to: http://localhost:5000/frontend/index.html"
echo ""
echo "ℹ️  If you don't have the opening tree, run: python build_tree.py"
