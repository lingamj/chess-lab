
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
