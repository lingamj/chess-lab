#!/bin/bash
echo "🔧 Fixing board rendering..."

# 1. Update constants.js with correct START_FEN
cat > frontend/js/constants.js << 'CONST'
export const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
export const COLORS = { WHITE: 'white', BLACK: 'black' };
export const TRAINING_DELAY = 2000;
export const API_BASE = '';
export const MAX_GRAPH_POINTS = 100;
CONST

# 2. Replace board.js with Unicode-only rendering (no SVG, no numbers)
cat > frontend/js/board.js << 'BOARD'
import { state, refreshUI } from './state.js';

// Unicode chess pieces (reliable, no external files)
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
                // Use Unicode piece directly
                sq.textContent = pieceSymbols[piece] || piece;
                sq.style.fontSize = '44px';   // larger, visible
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

# 3. Ensure CSS doesn't hide pieces
cat > frontend/css/style.css << 'CSS'
* { box-sizing: border-box; }
body { font-family: sans-serif; margin: 10px; background: #f5f5f5; }
#app { max-width: 700px; margin:0 auto; }

#board-area { position:relative; width:100%; max-width:600px; margin:0 auto; }
.file-labels { display:flex; justify-content:space-around; padding:0 20px; font-size:14px; }
.rank-labels { display:flex; flex-direction:column; justify-content:space-around; padding-right:6px; font-size:14px; float:left; height:100%; }
#board-container { display:flex; }
#board { width:100%; aspect-ratio:1; display:grid; grid-template-columns:repeat(8,1fr); position:relative; z-index:1; }
.square { aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:44px; font-weight:bold; cursor:pointer; user-select:none; position:relative; }
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

echo "✅ Board fix applied. Restart Flask server:"
echo "   python web_control.py"
