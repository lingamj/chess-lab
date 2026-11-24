
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


    if (callbacks.renderBoard) await callbacks.// renderBoard(state.currentFen);
    if (callbacks.loadTree) await callbacks.loadTree(state.currentFen);
    if (callbacks.loadRepertoire) await callbacks.loadRepertoire(state.currentFen);
    if (callbacks.renderMoveHistory) await callbacks.renderMoveHistory();
    if (callbacks.renderEvalGraph) await callbacks.renderEvalGraph();
    if (callbacks.renderArrows) await callbacks.renderArrows();
    if (callbacks.applyHeatmap) await callbacks.applyHeatmap();
}

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

    state.moveHistory = [];
    state.historyIndex = -1;
    await goToFen(START_FEN);
}


    state.error = error;
    const el = document.getElementById('error-box');
    if (el) {
        el.textContent = error || '';
        el.style.display = error ? 'block' : 'none';
    }
}

    const res = await fetch(API_BASE + url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    let data;
    try { data = await res.json(); } catch { throw new Error(`Invalid JSON (${res.status})`); }
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
}

    return api('/api/move', { method: 'POST', body: JSON.stringify({ fen, uci }) });
}

    return api('/api/tree', { method: 'POST', body: JSON.stringify({ fen }) });
}

    return api('/api/repertoire?fen=' + encodeURIComponent(fen));
}

    return api('/api/repertoire', { method: 'POST', body: JSON.stringify({ fen, data }) });
}

    return api('/api/repertoire/' + encodeURIComponent(fen), { method: 'DELETE' });
}

    return api('/api/train/next');
}

    return api('/api/train/review', { method: 'POST', body: JSON.stringify({ fen, move }) });
}

    return api('/api/repertoire/stats');
}

    return api('/api/repertoire/export');
}

    return api('/api/repertoire/import', { method: 'POST', body: JSON.stringify(data) });
}

const pieceSymbols = {
    'r': '♜','n':'♞','b':'♝','q':'♛','k':'♚','p':'♟',
    'R': '♖','N':'♘','B':'♗','Q':'♕','K':'♔','P':'♙'
};

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

    state.flipped = !state.flipped;
    await refreshUI();
}

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

let dragData = null;
let ignoreNextClick = false;

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

    if (!confirm('Delete this entry?')) return;
    try {
        await deleteRepertoireEntry(state.currentFen);
        state.repertoire = null;
        await loadRepertoire(state.currentFen);
        await updateStats();
        alert('Deleted.');
    } catch (e) { setError(e.message); }
}

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

    if (state.historyIndex <= 0) return;
    state.historyIndex--;
    const entry = state.moveHistory[state.historyIndex];
    if (entry) { state.currentFen = entry.fen_after; await refreshUI(); }
}

    if (state.historyIndex >= state.moveHistory.length - 1) return;
    state.historyIndex++;
    const entry = state.moveHistory[state.historyIndex];
    if (entry) { state.currentFen = entry.fen_after; await refreshUI(); }
}

// Need refreshUI imported – add at top

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
