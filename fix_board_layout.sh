#!/bin/bash
echo "🔧 Fixing board layout and coordinates..."

# 1. Update constants.js with correct START_FEN
cat > frontend/js/constants.js << 'CONST'
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const COLORS = { WHITE: 'white', BLACK: 'black' };
export const TRAINING_DELAY = 2000;
export const API_BASE = '';
export const MAX_GRAPH_POINTS = 100;
CONST

# 2. Update board.js to render rank labels on the left, file labels below
cat > frontend/js/board.js << 'BOARD'
import { state, refreshUI } from './state.js';

const pieceSymbols = {
    'r': '♜','n':'♞','b':'♝','q':'♛','k':'♚','p':'♟',
    'R': '♖','N':'♘','B':'♗','Q':'♕','K':'♔','P':'♙'
};

export function parseFen(fen) {
    if (!fen) return Array(8).fill(null).map(() => Array(8).fill(null));
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
    // Pad if necessary
    while (board.length < 8) board.push(Array(8).fill(null));
    return board;
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
            const piece = board[r]?.[c];
            if (piece) {
                sq.textContent = pieceSymbols[piece] || piece;
            }
            sq.dataset.row = r;
            sq.dataset.col = c;
            container.appendChild(sq);
        }
    }

    // Update rank and file labels
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

# 3. Update index.html to have a proper board layout with labels
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

        <div id="board-area">
            <div id="board-wrapper">
                <div id="rank-labels"></div>
                <div id="board-container">
                    <div id="board"></div>
                </div>
            </div>
            <div id="file-labels"></div>
            <div id="fen-display">FEN: ...</div>
            <div id="arrows-container"></div>
        </div>

        <div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;">
            <button id="flip-board">Flip</button>
            <button id="reset-board">Reset</button>
            <button id="back-btn">◀</button>
            <button id="forward-btn">▶</button>
            <button id="export-pgn">Export PGN</button>
        </div>
        <div id="move-history" style="margin:8px 0; font-size:14px; background:#f9f9f9; padding:4px; border-radius:4px; min-height:24px;"></div>

        <div id="info">
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

            <h3>Import Games</h3>
            <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
                <input id="import-username" placeholder="Your username" style="flex:1; min-width:120px;">
                <button id="import-lichess" style="background:#4a6fa5; color:white; border:none; padding:6px 12px;">Lichess</button>
                <button id="import-chesscom" style="background:#1a1a1a; color:white; border:none; padding:6px 12px;">Chess.com</button>
            </div>
            <div id="import-status" style="font-size:14px; color:#555; margin-bottom:12px;"></div>

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

# 4. Update CSS for board layout
cat > frontend/css/style.css << 'CSS'
* { box-sizing: border-box; }
body { font-family: sans-serif; margin: 10px; background: #f5f5f5; }
#app { max-width: 700px; margin:0 auto; }

#board-area { position:relative; width:100%; max-width:600px; margin:0 auto; }
#board-wrapper { display:flex; align-items:flex-start; }
#rank-labels { display:flex; flex-direction:column; justify-content:space-around; padding-right:6px; font-size:14px; height:100%; min-height:100%; }
#rank-labels span { display:flex; align-items:center; justify-content:center; height:12.5%; }
#board-container { flex:1; }
#board { width:100%; aspect-ratio:1; display:grid; grid-template-columns:repeat(8,1fr); position:relative; z-index:1; }
.square { aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:48px; font-weight:bold; cursor:pointer; user-select:none; position:relative; }
.light { background:#f0d9b5; }
.dark { background:#b58863; }
.square.legal { box-shadow: inset 0 0 0 4px #4caf50; }

#file-labels { display:flex; justify-content:space-around; padding-left:24px; font-size:14px; margin-top:2px; }
#file-labels span { flex:1; text-align:center; }

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

# 5. Ensure app.js uses the correct functions
cat > frontend/js/app.js << 'JS'
import { state, registerCallbacks, goToStart, setError, refreshUI } from './state.js';
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

    // Import buttons
    document.getElementById('import-lichess')?.addEventListener('click', () => importGames('lichess'));
    document.getElementById('import-chesscom')?.addEventListener('click', () => importGames('chesscom'));

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
        } catch (e) {
            setError(e.message);
        }
    })();

    console.log('Chess Study ready.');
}

async function importGames(source) {
    const username = document.getElementById('import-username').value.trim();
    if (!username) {
        document.getElementById('import-status').textContent = '⚠️ Please enter a username.';
        return;
    }
    document.getElementById('import-status').textContent = `⏳ Importing ${source} games for ${username}...`;
    try {
        const response = await fetch('/api/import_games', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ source, username })
        });
        const data = await response.json();
        if (data.status === 'ok') {
            document.getElementById('import-status').textContent = '✅ ' + data.message;
            await loadTree(state.currentFen);
        } else {
            document.getElementById('import-status').textContent = '❌ ' + (data.error || 'Unknown error');
        }
    } catch (e) {
        document.getElementById('import-status').textContent = '❌ Error: ' + e.message;
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}
JS

echo "✅ Board layout and coordinates fixed."
echo "▶️  Start the server with: python web_control.py"
echo "🌐 Then open: http://localhost:5000/frontend/index.html"
