/* ===== Utility ===== */
function readFileAsText(file){ return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsText(file); }); }
function debounce(fn, delay) { let timer; return function(...args) { clearTimeout(timer); timer = setTimeout(() => fn.apply(this, args), delay); }; }

/* ===== PGN parsing ===== */
function splitGames(pgnText) {
  const parts = pgnText.split(/\n\s*\n(?=\[)/);
  if (parts.length > 1) return parts.map(s => s.trim()).filter(Boolean);
  const games = [];
  const re = /(?:^|\n\n)((?:\[[\s\S]*?\]\s*\n)+)([\s\S]*?)(?=\n\n\[|$)/g;
  let m;
  while ((m = re.exec(pgnText)) !== null) { const c = (m[1] + m[2]).trim(); if (c) games.push(c); }
  return games.length ? games : [pgnText.trim()].filter(Boolean);
}

function sanitizeMoves(movesText) {
  let s = movesText.replace(/\{[^}]*\}/g, ' ').replace(/;.*$/gm, ' '); let prev;
  do { prev = s; s = s.replace(/\([^)]*\)/g, ' '); } while (s !== prev);
  return s.replace(/\$\d+/g, ' ').replace(/(1-0|0-1|1\/2-1\/2|\*)\s*$/g, '')
    .replace(/0-0-0/g, 'O-O-O').replace(/0-0/g, 'O-O').replace(/[+#!?]+/g, '')
    .replace(/\r?\n/g, ' ').replace(/\s+/g, ' ').trim();
}

function isStandardStartFEN(fen) { return fen.trim() === 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'; }

function parsePGN(pgn) {
  const tags = {}; const re = /\[(\w+)\s+"([\s\S]*?)"\]/g; let m;
  while ((m = re.exec(pgn)) !== null) tags[m[1]] = m[2].replace(/[\r\n]+/g, ' ').trim();
  if (tags.SetUp === '1' && tags.FEN && !isStandardStartFEN(tags.FEN)) return { tags, moves: [], skip: true, reason: 'Non-standard FEN: ' + tags.FEN };
  const lastTagIdx = pgn.lastIndexOf(']'); const movesRaw = (lastTagIdx >= 0) ? pgn.slice(lastTagIdx + 1) : pgn;
  const cleaned = sanitizeMoves(movesRaw);
  const tokens = cleaned.split(/\s+/).filter(t => t && !/^(1-0|0-1|1\/2-1\/2|\*)$/.test(t)).filter(t => !/^[\d.]+$/.test(t)).filter(t => !/[()]/.test(t));
  return { tags, moves: tokens, skip: false };
}

/* ===== Board engine ===== */
function initialBoardState() {
  const e = [null, null, null, null, null, null, null, null];
  return {
    board: [['bR','bN','bB','bQ','bK','bB','bN','bR'], ['bP','bP','bP','bP','bP','bP','bP','bP'], e.slice(), e.slice(), e.slice(), e.slice(), ['wP','wP','wP','wP','wP','wP','wP','wP'], ['wR','wN','wB','wQ','wK','wB','wN','wR']],
    turn: 'w', castling: { wK: true, wQ: true, bK: true, bQ: true }, enPassant: null, lastMove: null, halfmoveClock: 0, fullmoveNumber: 1
  };
}
function cloneState(s) { return { board: s.board.map(r => r.slice()), turn: s.turn, castling: { ...s.castling }, enPassant: s.enPassant ? [s.enPassant[0], s.enPassant[1]] : null, lastMove: s.lastMove ? { ...s.lastMove } : null, halfmoveClock: s.halfmoveClock, fullmoveNumber: s.fullmoveNumber }; }
function pieceColor(p) { return p ? p[0] : null; }
function pieceType(p) { return p ? p[1].toUpperCase() : null; }
function coordsFromSquare(sq) { const f = sq[0].toLowerCase(), r = parseInt(sq[1], 10); return [8 - r, f.charCodeAt(0) - 97]; }

function generatePseudoMoves(state, color) {
  const moves = [], board = state.board, dir = (color === 'w' ? -1 : 1);
  for (let r = 0; r < 8; r++) { for (let c = 0; c < 8; c++) {
    const piece = board[r][c]; if (!piece || pieceColor(piece) !== color) continue; const type = pieceType(piece);
    if (type === 'P') {
      const nr = r + dir, promo = (color === 'w' ? 0 : 7);
      if (nr >= 0 && nr < 8 && !board[nr][c]) {
        if (nr === promo) { for (const p of ['Q','R','B','N']) moves.push({ fromR: r, fromC: c, toR: nr, toC: c, capture: false, promotion: p }); }
        else { moves.push({ fromR: r, fromC: c, toR: nr, toC: c, capture: false }); const sr = (color === 'w' ? 6 : 1), tr = r + 2 * dir; if (r === sr && !board[tr][c]) moves.push({ fromR: r, fromC: c, toR: tr, toC: c, capture: false, doublePawn: true }); }
      }
      for (const dc of [-1, 1]) { const cc = c + dc, rr = r + dir; if (rr < 0 || rr > 7 || cc < 0 || cc > 7) continue; const t = board[rr][cc];
        if (t && pieceColor(t) !== color) { if (rr === promo) { for (const p of ['Q','R','B','N']) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: true, promotion: p }); } else moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: true }); }
        else if (state.enPassant && state.enPassant[0] === rr && state.enPassant[1] === cc) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: true, enPassant: true });
      }
    } else if (type === 'N') {
      const deltas = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]];
      for (const [dr,dc] of deltas) { const rr = r + dr, cc = c + dc; if (rr < 0 || rr > 7 || cc < 0 || cc > 7) continue; const t = board[rr][cc]; if (!t || pieceColor(t) !== color) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: !!t }); }
    } else if (type === 'B' || type === 'R' || type === 'Q') {
      const dirs = []; if (type === 'B' || type === 'Q') dirs.push([-1,-1],[-1,1],[1,-1],[1,1]); if (type === 'R' || type === 'Q') dirs.push([-1,0],[1,0],[0,-1],[0,1]);
      for (const [dr,dc] of dirs) { let rr = r + dr, cc = c + dc; while (rr >= 0 && rr < 8 && cc >= 0 && cc < 8) { const t = board[rr][cc]; if (!t) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: false }); else { if (pieceColor(t) !== color) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: true }); break; } rr += dr; cc += dc; } }
    } else if (type === 'K') {
      const deltas = [[-1,-1],[-1,0],[-1,1],[0,-1],[0,1],[1,-1],[1,0],[1,1]];
      for (const [dr,dc] of deltas) { const rr = r + dr, cc = c + dc; if (rr < 0 || rr > 7 || cc < 0 || cc > 7) continue; const t = board[rr][cc]; if (!t || pieceColor(t) !== color) moves.push({ fromR: r, fromC: c, toR: rr, toC: cc, capture: !!t }); }
      if (color === 'w') {
        if (state.castling.wK && !board[7][5] && !board[7][6]) moves.push({ castle: 'wK', fromR: 7, fromC: 4, toR: 7, toC: 6 });
        if (state.castling.wQ && !board[7][1] && !board[7][2] && !board[7][3]) moves.push({ castle: 'wQ', fromR: 7, fromC: 4, toR: 7, toC: 2 });
      } else {
        if (state.castling.bK && !board[0][5] && !board[0][6]) moves.push({ castle: 'bK', fromR: 0, fromC: 4, toR: 0, toC: 6 });
        if (state.castling.bQ && !board[0][1] && !board[0][2] && !board[0][3]) moves.push({ castle: 'bQ', fromR: 0, fromC: 4, toR: 0, toC: 2 });
      }
    }
  }}
  return moves;
}
function isSquareAttacked(state, r, c, byColor) {
  const board = state.board;
  for (let rr = 0; rr < 8; rr++) { for (let cc = 0; cc < 8; cc++) {
    const piece = board[rr][cc]; if (!piece || pieceColor(piece) !== byColor) continue;
    const type = pieceType(piece); const dr = r - rr, dc = c - cc;
    if (type === 'P') { const dir = (byColor === 'w' ? -1 : 1); if (r === rr + dir && (c === cc - 1 || c === cc + 1)) return true; }
    else if (type === 'N') { const d = [[-2,-1],[-2,1],[-1,-2],[-1,2],[1,-2],[1,2],[2,-1],[2,1]]; for (const [drr,dcc] of d) if (rr + drr === r && cc + dcc === c) return true; }
    else if (type === 'B' || type === 'R' || type === 'Q') {
      const dirs = []; if (type === 'B' || type === 'Q') dirs.push([-1,-1],[-1,1],[1,-1],[1,1]); if (type === 'R' || type === 'Q') dirs.push([-1,0],[1,0],[0,-1],[0,1]);
      for (const [drr,dcc] of dirs) { let tr = rr + drr, tc = cc + dcc; while (tr >= 0 && tr < 8 && tc >= 0 && tc < 8) { if (tr === r && tc === c) return true; if (board[tr][tc]) break; tr += drr; tc += dcc; } }
    } else if (type === 'K') { if (Math.max(Math.abs(dr), Math.abs(dc)) === 1) return true; }
  }}
  return false;
}
function isKingInCheck(state, color) {
  const board = state.board; let kr = -1, kc = -1;
  for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++) if (board[r][c] && pieceColor(board[r][c]) === color && pieceType(board[r][c]) === 'K') { kr = r; kc = c; break; }
  if (kr < 0) return false;
  return isSquareAttacked(state, kr, kc, color === 'w' ? 'b' : 'w');
}
function applyMoveToState(state, mv) {
  const ns = cloneState(state), b = ns.board, piece = b[mv.fromR][mv.fromC], col = pieceColor(piece), type = pieceType(piece);
  const capturedPiece = (mv.castle || mv.enPassant) ? null : b[mv.toR][mv.toC];
  ns.castling = { ...state.castling }; ns.enPassant = null;
  const isCapture = mv.capture || mv.enPassant || (b[mv.toR][mv.toC] !== null);
  ns.halfmoveClock = (type === 'P' || isCapture) ? 0 : ns.halfmoveClock + 1;
  if (col === 'b') ns.fullmoveNumber++;
  if (mv.castle) {
    if (mv.castle === 'wK') { b[7][4] = null; b[7][6] = 'wK'; b[7][7] = null; b[7][5] = 'wR'; }
    else if (mv.castle === 'wQ') { b[7][4] = null; b[7][2] = 'wK'; b[7][0] = null; b[7][3] = 'wR'; }
    else if (mv.castle === 'bK') { b[0][4] = null; b[0][6] = 'bK'; b[0][7] = null; b[0][5] = 'bR'; }
    else if (mv.castle === 'bQ') { b[0][4] = null; b[0][2] = 'bK'; b[0][0] = null; b[0][3] = 'bR'; }
    mv.castle.startsWith('w') ? (ns.castling.wK = ns.castling.wQ = false) : (ns.castling.bK = ns.castling.bQ = false);
  } else {
    if (mv.enPassant) { const dir = (col === 'w' ? -1 : 1); b[mv.fromR][mv.fromC] = null; b[mv.toR + (-dir)][mv.toC] = null; b[mv.toR][mv.toC] = piece; }
    else { b[mv.fromR][mv.fromC] = null; b[mv.toR][mv.toC] = piece; }
    if (mv.promotion) b[mv.toR][mv.toC] = col + mv.promotion;
    if (type === 'K') { ns.castling[col + 'K'] = false; ns.castling[col + 'Q'] = false; }
    if (type === 'R') {
      if (col === 'w') { if (mv.fromR === 7 && mv.fromC === 0) ns.castling.wQ = false; if (mv.fromR === 7 && mv.fromC === 7) ns.castling.wK = false; }
      else { if (mv.fromR === 0 && mv.fromC === 0) ns.castling.bQ = false; if (mv.fromR === 0 && mv.fromC === 7) ns.castling.bK = false; }
    }
    if (capturedPiece && pieceType(capturedPiece) === 'R') {
      const ccol = pieceColor(capturedPiece);
      if (ccol === 'w') { if (mv.toR === 7 && mv.toC === 0) ns.castling.wQ = false; if (mv.toR === 7 && mv.toC === 7) ns.castling.wK = false; }
      else { if (mv.toR === 0 && mv.toC === 0) ns.castling.bQ = false; if (mv.toR === 0 && mv.toC === 7) ns.castling.bK = false; }
    }
    if (mv.doublePawn) ns.enPassant = [(mv.fromR + mv.toR) >> 1, mv.fromC];
  }
  ns.lastMove = { fromR: mv.fromR, fromC: mv.fromC, toR: mv.toR, toC: mv.toC }; ns.turn = (state.turn === 'w' ? 'b' : 'w'); return ns;
}
function parseSAN(san) { let s = san.trim(); if (/^(O-O-O|0-0-0)$/.test(s)) return { castle: 'Q' }; if (/^(O-O|0-0)$/.test(s)) return { castle: 'K' }; s = s.replace(/[+#?!]+/g, ''); let promo = null; const pm = s.match(/=([QRBN])/); if (pm) { promo = pm[1]; s = s.replace(/=([QRBN])/, ''); } let piece = 'P'; if (/^[KQRBN]/.test(s)) { piece = s[0]; s = s.slice(1); } const capture = s.includes('x'); s = s.replace('x', ''); const target = s.slice(-2), dis = s.slice(0, -2); let fh = null, rh = null; if (dis.length === 1) { if (/[a-h]/.test(dis)) fh = dis; else if (/[1-8]/.test(dis)) rh = dis; } else if (dis.length === 2) { fh = dis[0]; rh = dis[1]; } return { castle: null, piece, capture, target, promotion: promo, fileHint: fh, rankHint: rh }; }
function isCastlingLegal(state, color, castle) { if (isKingInCheck(state, color)) return false; const enemy = color === 'w' ? 'b' : 'w', kingRow = color === 'w' ? 7 : 0; let inter = []; if (castle.endsWith('K')) { inter.push([kingRow, 5]); inter.push([kingRow, 6]); } else { inter.push([kingRow, 3]); inter.push([kingRow, 2]); } for (const [r, c] of inter) if (isSquareAttacked(state, r, c, enemy)) return false; return true; }
function sanToMove(state, san) { const desc = parseSAN(san), color = state.turn; if (desc.castle) { const wanted = (color === 'w' ? (desc.castle === 'K' ? 'wK' : 'wQ') : (desc.castle === 'K' ? 'bK' : 'bQ')); const moves = generatePseudoMoves(state, color).filter(mv => mv.castle === wanted); const legal = moves.filter(mv => { if (!isCastlingLegal(state, color, mv.castle)) return false; const tmp = applyMoveToState(state, mv); return !isKingInCheck(tmp, color); }); if (!legal.length) throw new Error('Illegal castle ' + san); return legal[0]; } const all = generatePseudoMoves(state, color); const [tR, tC] = coordsFromSquare(desc.target); const pieceMap = { P: 'P', N: 'N', B: 'B', R: 'R', Q: 'Q', K: 'K' }; const candidates = all.filter(mv => { const pc = state.board[mv.fromR][mv.fromC]; if (!pc) return false; if (pieceColor(pc) !== color || pieceType(pc) !== pieceMap[desc.piece]) return false; if (mv.toR !== tR || mv.toC !== tC) return false; if (desc.capture && !mv.capture) return false; if (!desc.capture && mv.capture) return false; if (desc.promotion && mv.promotion !== desc.promotion) return false; if (desc.fileHint) { const f = String.fromCharCode(97 + mv.fromC); if (f !== desc.fileHint) return false; } if (desc.rankHint) { const rk = (8 - mv.fromR).toString(); if (rk !== desc.rankHint) return false; } return true; }); const legal = candidates.filter(mv => { const tmp = applyMoveToState(state, mv); return !isKingInCheck(tmp, color); }); if (!legal.length) throw new Error('No legal move for SAN ' + san); return legal[0]; }

/* ===== FIXED moveToSAN – proper disambiguation ===== */
function moveToSAN(state, mv) {
  const board = state.board, piece = board[mv.fromR][mv.fromC], type = pieceType(piece), col = pieceColor(piece);
  if (mv.castle) return mv.toC === 6 ? 'O-O' : 'O-O-O';
  const ff = String.fromCharCode(97 + mv.fromC), rf = (8 - mv.fromR).toString(), ft = String.fromCharCode(97 + mv.toC), rt = (8 - mv.toR).toString(), capture = !!mv.capture || !!mv.enPassant;
  let disFile = false, disRank = false;
  if (type !== 'P') {
    const all = generatePseudoMoves(state, col).filter(m => { const tmp = applyMoveToState(state, m); return !isKingInCheck(tmp, col); });
    const same = all.filter(m => {
      if (m.fromR === mv.fromR && m.fromC === mv.fromC) return false;
      const pc = board[m.fromR][m.fromC];
      return pc && pieceType(pc) === type && pieceColor(pc) === col && m.toR === mv.toR && m.toC === mv.toC;
    });
    if (same.length) {
      const sameFile = same.some(m => m.fromC === mv.fromC);
      const sameRank = same.some(m => m.fromR === mv.fromR);
      if (sameFile && sameRank) { disFile = true; disRank = true; }
      else if (sameFile) { disRank = true; }
      else if (sameRank) { disFile = true; }
      else { disFile = true; }
    }
  }
  let san = '';
  if (type !== 'P') { san += type; if (disFile) san += ff; if (disRank) san += rf; if (capture) san += 'x'; san += ft + rt; }
  else { if (capture) san += ff + 'x' + ft + rt; else san += ft + rt; }
  if (mv.promotion) san += '=' + mv.promotion;
  return san;
}

function stateToFEN(state) {
  let fen = ''; for (let r = 0; r < 8; r++) { let empty = 0, row = ''; for (let c = 0; c < 8; c++) { const piece = state.board[r][c]; if (!piece) empty++; else { if (empty > 0) { row += empty; empty = 0; } const col = pieceColor(piece), t = pieceType(piece); row += (col === 'w' ? t : t.toLowerCase()); } } if (empty) row += empty; fen += (r > 0 ? '/' : '') + row; }
  fen += ' ' + state.turn; let castling = ''; if (state.castling.wK) castling += 'K'; if (state.castling.wQ) castling += 'Q'; if (state.castling.bK) castling += 'k'; if (state.castling.bQ) castling += 'q'; if (!castling) castling = '-';
  fen += ' ' + castling; if (state.enPassant) fen += ' ' + String.fromCharCode(97 + state.enPassant[1]) + (8 - state.enPassant[0]); else fen += ' -';
  fen += ' ' + (state.halfmoveClock ?? 0) + ' ' + (state.fullmoveNumber ?? 1); return fen;
}


/* ===== Phase-1 server-backed tree support ===== */

function uciToMoveObj(state, uci) {
  if (!state || typeof uci !== 'string' || uci.length < 4) {
    throw new Error('Invalid UCI move: ' + uci);
  }

  const fromFile = uci.charCodeAt(0) - 97;
  const fromRank = 8 - parseInt(uci[1], 10);
  const toFile = uci.charCodeAt(2) - 97;
  const toRank = 8 - parseInt(uci[3], 10);
  const promotion = uci.length >= 5 ? uci[4].toUpperCase() : null;

  if (
    fromFile < 0 || fromFile > 7 ||
    toFile < 0 || toFile > 7 ||
    fromRank < 0 || fromRank > 7 ||
    toRank < 0 || toRank > 7
  ) {
    throw new Error('Invalid UCI squares: ' + uci);
  }

  const color = state.turn;
  const pseudo = generatePseudoMoves(state, color);

  const candidates = pseudo.filter(mv =>
    mv.fromR === fromRank &&
    mv.fromC === fromFile &&
    mv.toR === toRank &&
    mv.toC === toFile &&
    ((mv.promotion || null) === promotion)
  );

  const legal = candidates.filter(mv => {
    if (mv.castle && !isCastlingLegal(state, color, mv.castle)) return false;
    const next = applyMoveToState(state, mv);
    return !isKingInCheck(next, color);
  });

  if (!legal.length) {
    throw new Error('No legal move for UCI ' + uci);
  }

  return legal[0];
}

function serverNodeFromMoveData(moveData, parentNode) {
  if (!moveData || !parentNode) {
    throw new Error('serverNodeFromMoveData requires moveData and parentNode');
  }

  const uci = String(moveData.uci || '').trim();
  const san = String(moveData.san || '').trim();

  if (!uci || !san) {
    throw new Error('Server move is missing UCI or SAN');
  }

  const parentState = stateFromNode(parentNode);
  const mv = uciToMoveObj(parentState, uci);
  const key = `${mv.fromR},${mv.fromC}-${mv.toR},${mv.toC}${mv.promotion || ''}`;
  const childState = applyMoveToState(parentState, mv);
  const childFen = stateToFEN(childState);

  const games = Number(moveData.games) || 0;
  const winPct = Number(moveData.win_pct) || 0;
  const drawPct = Number(moveData.draw_pct) || 0;
  const lossPct = Number(moveData.loss_pct) || 0;
  const avgElo = Number(moveData.avg_elo) || 0;
  const meWhite = Number(moveData.my_white_games) || 0;
  const meBlack = Number(moveData.my_black_games) || 0;
  const meWhiteW = Number(moveData.my_white_w) || 0;
  const meWhiteD = Number(moveData.my_white_d) || 0;
  const meWhiteB = Number(moveData.my_white_b) || 0;
  const meBlackW = Number(moveData.my_black_w) || 0;
  const meBlackD = Number(moveData.my_black_d) || 0;
  const meBlackB = Number(moveData.my_black_b) || 0;
  const meWhiteElo = Number(moveData.my_white_avg_elo) || 0;
  const meBlackElo = Number(moveData.my_black_avg_elo) || 0;

  const node = {
    move: san,
    uci: uci,
    key: key,
    fen: childFen,

    count: games,
    positions: Number(moveData.positions) || games,

    stats: {
      w: Math.round(games * winPct / 100),
      d: Math.round(games * drawPct / 100),
      b: Math.round(games * lossPct / 100)
    },

    scores: {
      engine: moveData.engine_score ?? null,
      engine_depth: moveData.engine_depth ?? null,
      engine_score_type: moveData.engine_score_type ?? 'cp',
      engine_mate_moves: moveData.engine_mate_moves ?? null,
      engine_mate_sign: moveData.engine_mate_sign ?? 1,
      engine_source: moveData.engine_source ?? null,
      sf: moveData.sf_score ?? null,
      sf_depth: moveData.sf_depth ?? null,
      sf_score_type: moveData.sf_score_type ?? 'cp',
      sf_mate_moves: moveData.sf_mate_moves ?? null,
      sf_mate_sign: moveData.sf_mate_sign ?? 1,
      sf_source: moveData.sf_source ?? null,
      neural: null
    },

    eloSum: avgElo > 0 ? avgElo * games : 0,
    eloCount: avgElo > 0 ? games : 0,

    serverNode: true,
    meWhite: meWhite,
    meBlack: meBlack,
    meWhiteW: meWhiteW,
    meWhiteD: meWhiteD,
    meWhiteB: meWhiteB,
    meBlackW: meBlackW,
    meBlackD: meBlackD,
    meBlackB: meBlackB,
    meWhiteElo: meWhiteElo,
    meBlackElo: meBlackElo,

    children: new Map(),
    games: [],

    parent: parentNode,
    state: childState,

    serverLoaded: false,
    serverLoading: false
  };

  return node;
}

if (!window._serverChildrenInflight) {
  window._serverChildrenInflight = new WeakMap();
}

async function loadServerChildren(node) {
  if (!node) return false;

  const ctx = window._CUSTOM_FEN_CONTEXT;
  let inCustomTree = false;

  if (ctx && ctx.root) {
    let current = node;
    while (current) {
      if (current === ctx.root) {
        inCustomTree = true;
        break;
      }
      current = current.parent;
    }
  }

  if (!inCustomTree &&
      window._DATA_SOURCE &&
      window._DATA_SOURCE !== 'database') {
    return false;
  }

  if (node.serverLoaded) return true;

  const existing = window._serverChildrenInflight.get(node);
  if (existing) return existing;

  node.serverLoading = true;
  node.serverError = false;

  const request = fetch('/api/tree', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      fen: node.fen || stateToFEN(stateFromNode(node))
    })
  })
    .then(function(res) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    })
    .then(function(data) {
      if (!data || !Array.isArray(data.moves)) {
        throw new Error('Invalid /api/tree response: expected moves array');
      }

      node.children.clear();

      const moves = data.moves;
      for (let i = 0; i < moves.length; i++) {
        try {
          const child = serverNodeFromMoveData(moves[i], node);
          node.children.set(child.key, child);
        } catch (err) {
          console.warn('Skipping invalid server move:', moves[i], err);
        }
      }

      node.serverLoaded = true;
      node.serverError = false;
      return true;
    })
    .catch(function(err) {
      console.warn('Server tree load failed:', err);
      node.serverError = true;
      node.serverLoaded = false;
      return false;
    })
    .finally(function() {
      node.serverLoading = false;
      window._serverChildrenInflight.delete(node);
    });

  window._serverChildrenInflight.set(node, request);
  return request;
}

/* ===== Tree nodes with precomputed Elo ===== */
function makeNode(move) { return { move: move || null, count: 0, children: new Map(), games: [], parent: null, stats: { w: 0, b: 0, d: 0 }, state: null, eloSum: 0, eloCount: 0 }; }
function addGameToTree(root, gameObj, gameIndex) {
  let node = root, state = initialBoardState();
  node.count++; node.games.push(gameIndex);
  const res = (gameObj.tags.Result || '').trim();
  if (res === '1-0') node.stats.w++; else if (res === '0-1') node.stats.b++; else if (res === '1/2-1/2') node.stats.d++;
  if (!node.state) node.state = cloneState(state);
  const eloStr = state.turn === 'w' ? gameObj.tags.WhiteElo : gameObj.tags.BlackElo; const eloVal = parseInt(eloStr, 10);
  if (!isNaN(eloVal) && eloVal > 0) { node.eloSum += eloVal; node.eloCount++; }
  for (let i = 0; i < gameObj.moves.length; i++) {
    const san = gameObj.moves[i]; let mv, key;
    try { mv = sanToMove(state, san); key = mv.fromR + ',' + mv.fromC + '-' + mv.toR + ',' + mv.toC + (mv.promotion || ''); }
    catch (e) { console.warn('Skipping invalid SAN in game #' + (gameIndex + 1) + ' at ply ' + i + ': ' + san, e); break; }
    if (!node.children.has(key)) { const child = makeNode(san); child.parent = node; node.children.set(key, child); }
    node = node.children.get(key);
    node.count++; node.games.push(gameIndex);
    if (res === '1-0') node.stats.w++; else if (res === '0-1') node.stats.b++; else if (res === '1/2-1/2') node.stats.d++;
    state = applyMoveToState(state, mv);
    if (!node.state) node.state = cloneState(state);
    const eloHere = state.turn === 'w' ? gameObj.tags.WhiteElo : gameObj.tags.BlackElo; const ev = parseInt(eloHere, 10);
    if (!isNaN(ev) && ev > 0) { node.eloSum += ev; node.eloCount++; }
  }
}
function buildTreeFromGames(games) { const root = makeNode(null); games.forEach((g, i) => addGameToTree(root, g, i)); return root; }

/* ===== Helpers ===== */
function getPathFromNode(node) { const p = []; let cur = node; while (cur && cur.move) { p.push(cur.move); cur = cur.parent; } return p.reverse(); }
function computeNodeResults(node) { const w = node.stats.w, b = node.stats.b, d = node.stats.d, t = w + b + d; return { total: node.count, counted: t, w1: w, b1: b, dr: d, whiteScorePct: t ? ((w + 0.5 * d) / t * 100) : 0, blackScorePct: t ? ((b + 0.5 * d) / t * 100) : 0 }; }
function computeNodeAverageElo(node) { return node.eloCount ? Math.round(node.eloSum / node.eloCount) : null; }
function stateFromNode(node) { if (!node) return initialBoardState(); if (node.state) return cloneState(node.state); return playLine(getPathFromNode(node), 999).state; }
function playLine(moves, upto, baseState) { let s = baseState ? cloneState(baseState) : initialBoardState(); const lim = Math.min(upto, moves.length); let i; for (i = 0; i < lim; i++) { try { s = applyMoveToState(s, sanToMove(s, moves[i])); } catch (e) { break; } } return { state: s, ply: i }; }
function findPlyOfNodeInGame(game, node) {
  const path = getPathFromNode(node); if (!path.length) return 0;
  const moves = game.moves; let baseState = initialBoardState();
  for (let i = 0; i < moves.length; i++) {
    let state = cloneState(baseState); let matched = true;
    for (let j = 0; j < path.length; j++) {
      if (i + j >= moves.length) { matched = false; break; }
      try {
        const mv1 = sanToMove(state, moves[i + j]), mv2 = sanToMove(state, path[j]);
        const key1 = mv1.fromR + ',' + mv1.fromC + '-' + mv1.toR + ',' + mv1.toC + (mv1.promotion || '');
        const key2 = mv2.fromR + ',' + mv2.fromC + '-' + mv2.toR + ',' + mv2.toC + (mv2.promotion || '');
        if (key1 !== key2) { matched = false; break; }
        state = applyMoveToState(state, mv1);
      } catch (e) { matched = false; break; }
    }
    if (matched) return i + path.length;
    try { const mv = sanToMove(baseState, moves[i]); baseState = applyMoveToState(baseState, mv); } catch (e) {}
  }
  return 0;
}

/* ===== Global state ===== */
window._WHITE_BOTTOM = true;
window._CURRENT_STATE = initialBoardState();
window._SELECTED_SQUARE = null;
window._LINE_MOVES_SAN = [];
window._CURRENT_PLY = 0;
window._CURRENT_NODE = null;
window._ENGINE_ARROW_BLUE = null;
window._ENGINE_ARROW_GREEN = null;
window._LINE_SOURCE = 'tree';
window._TREE = null;
window._PARSED_GAMES = null;
window._PGN_GAMES = null;
window._ARROWS_ENABLED = true;
window._SELECTED_OPENING_LINE = null;
window._openingsSortCol = 'games';
window._openingsSortDir = 'desc';
window._gamesSortCol = 'index';
window._gamesSortDir = 'asc';

/* ===== Board rendering with arrows ===== */
function pieceChar(piece) { if (!piece) return ''; const col = pieceColor(piece), t = pieceType(piece); const chars = { P: { w: '♙', b: '♟' }, N: { w: '♘', b: '♞' }, B: { w: '♗', b: '♝' }, R: { w: '♖', b: '♜' }, Q: { w: '♕', b: '♛' }, K: { w: '♔', b: '♚' } }; return chars[t][col]; }
function squareCenterForCoords(r, c) { const sz = 50, half = sz / 2; let fi, ri; if (window._WHITE_BOTTOM) { fi = c; ri = r; } else { fi = 7 - c; ri = 7 - r; } return { x: fi * sz + half, y: ri * sz + half }; }
function clearArrowLines(svg) { svg.querySelectorAll('.arrow-line, .arrow-head-line, .arrow-outline').forEach(l => l.remove()); }
function ensureArrowMarker(svg, hl, hw, ho) {
  const ns = 'http://www.w3.org/2000/svg'; let defs = svg.querySelector('defs'); if (!defs) { defs = document.createElementNS(ns, 'defs'); svg.appendChild(defs); }
  let marker = svg.querySelector('#arrowHead'); if (marker) marker.remove();
  marker = document.createElementNS(ns, 'marker'); marker.setAttribute('id', 'arrowHead'); marker.setAttribute('markerUnits', 'userSpaceOnUse'); marker.setAttribute('orient', 'auto'); marker.setAttribute('markerWidth', String(hl)); marker.setAttribute('markerHeight', String(hw)); marker.setAttribute('refX', String(hl)); marker.setAttribute('refY', String(hw / 2));
  const path = document.createElementNS(ns, 'path'); path.setAttribute('d', `M0 0 L ${hl} ${hw / 2} L 0 ${hw} Z`); path.setAttribute('fill', `rgba(249,115,22,${ho})`); path.setAttribute('stroke', 'rgba(255,255,255,0.5)'); path.setAttribute('stroke-width', '1'); path.setAttribute('class', 'arrow-head'); marker.appendChild(path); defs.appendChild(marker);
}
function renderArrowsForCurrentNode() {
  const svg = document.getElementById('boardArrowsInline');
  if (!svg) return; clearArrowLines(svg);
  if (window._SELECTED_SQUARE) return; // Hide opening-tree arrows during move selection.
  if (!window._ARROWS_ENABLED || !window._TREE) return;
  if (!window._CURRENT_NODE || !window._CURRENT_NODE.children) return;
  const node = window._CURRENT_NODE, baseState = stateFromNode(node);
  const children = Array.from(node.children.values());
  if (!children.length) return;
  const ns = 'http://www.w3.org/2000/svg'; const count = children.length;
  const hl = 24, hw = 35, ho = 0.8, to = 0.6;
  const ntw = count > 50 ? 4 : count > 20 ? 6 : 10;
  const btw = count > 50 ? 6 : count > 20 ? 8 : 12;
  const gap = hl * 0.7;
  ensureArrowMarker(svg, hl, hw, ho);
  let bestChild = null, bestCount = -1;
  children.forEach(ch => { if (ch.count > bestCount) { bestCount = ch.count; bestChild = ch; } });
  const shaftFragment = document.createDocumentFragment();
  const headFragment = document.createDocumentFragment();
  for (const child of children) {
    let mv; try { mv = sanToMove(baseState, child.move); } catch (e) { continue; }
    const fc = squareCenterForCoords(mv.fromR, mv.fromC), tc = squareCenterForCoords(mv.toR, mv.toC);
    const dx = tc.x - fc.x, dy = tc.y - fc.y, dist = Math.hypot(dx, dy) || 1, ux = dx / dist, uy = dy / dist;
    const dynamicGap = gap + (children.length > 30 ? 8 : 0);
    const tx = tc.x - ux * dynamicGap, ty = tc.y - uy * dynamicGap;
    const tailOutline = document.createElementNS(ns, 'line');
    tailOutline.setAttribute('x1', fc.x); tailOutline.setAttribute('y1', fc.y); tailOutline.setAttribute('x2', tx); tailOutline.setAttribute('y2', ty);
    tailOutline.setAttribute('class', 'arrow-outline');
    tailOutline.setAttribute('stroke', 'rgba(255,255,255,0.4)');
    tailOutline.setAttribute('stroke-width', String(child === bestChild ? btw + 1 : ntw + 1));
    tailOutline.setAttribute('stroke-linecap', 'round');
    shaftFragment.appendChild(tailOutline);

    const tail = document.createElementNS(ns, 'line');
    tail.setAttribute('x1', fc.x); tail.setAttribute('y1', fc.y); tail.setAttribute('x2', tx); tail.setAttribute('y2', ty);
    tail.setAttribute('class', 'arrow-line'); tail.setAttribute('stroke', `rgba(249,115,22,${to})`);
    tail.setAttribute('stroke-width', child === bestChild ? String(btw + 2) : String(ntw));
    shaftFragment.appendChild(tail);
    const headLine = document.createElementNS(ns, 'line');
    headLine.setAttribute('x1', tx); headLine.setAttribute('y1', ty); headLine.setAttribute('x2', tc.x); headLine.setAttribute('y2', tc.y);
    headLine.setAttribute('class', 'arrow-head-line'); headLine.setAttribute('stroke', 'rgba(249,115,22,0)');
    headLine.setAttribute('stroke-width', child === bestChild ? String(btw + 2) : String(ntw));
    headLine.setAttribute('marker-end', 'url(#arrowHead)');
    headFragment.appendChild(headLine);
  }
  svg.appendChild(shaftFragment);
  return headFragment;
}

function renderBoard(state) {
  const boardDiv = document.getElementById('board'), filesRow = document.getElementById('board-files');
  boardDiv.innerHTML = ''; filesRow.innerHTML = '';
  const squaresContainer = document.createElement('div');
  let legalTargets = [];
  if (window._SELECTED_SQUARE) {
    const sel = window._SELECTED_SQUARE;
    const moves = generatePseudoMoves(state, state.turn).filter(
      m => m.fromR === sel.r && m.fromC === sel.c
    );
    legalTargets = moves.filter(mv => {
      if (mv.castle && !isCastlingLegal(state, state.turn, mv.castle)) {
        return false;
      }
      const tmp = applyMoveToState(state, mv);
      return !isKingInCheck(tmp, state.turn);
    });
  }
  const rankIndices = window._WHITE_BOTTOM ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
  const fileIndices = window._WHITE_BOTTOM ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
  for (let ri = 0; ri < 8; ri++) {
    const r = rankIndices[ri]; const rowDiv = document.createElement('div'); rowDiv.className = 'board-row';
    const rankLabel = document.createElement('div'); rankLabel.className = 'board-rank-label'; rankLabel.textContent = 8 - r; rowDiv.appendChild(rankLabel);
    for (let fi = 0; fi < 8; fi++) {
      const c = fileIndices[fi]; const sq = document.createElement('div');
      sq.className = 'square ' + (((r + c) % 2 === 0) ? 'light' : 'dark');
      const piece = state.board[r][c];
      if (piece) { const span = document.createElement('span'); span.className = 'piece ' + (pieceColor(piece) === 'w' ? 'piece-white' : 'piece-black'); span.textContent = pieceChar(piece); sq.appendChild(span); }
      if (state.lastMove) { if (state.lastMove.fromR === r && state.lastMove.fromC === c) sq.classList.add('highlight-from'); if (state.lastMove.toR === r && state.lastMove.toC === c) sq.classList.add('highlight-to'); }
      if (window._SELECTED_SQUARE && window._SELECTED_SQUARE.r === r && window._SELECTED_SQUARE.c === c) { sq.classList.add('highlight-from'); }
      if (legalTargets.some(m => m.toR === r && m.toC === c)) {
        const indicator = document.createElement('div');
        if (state.board[r][c]) {
          indicator.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;'+ 'border:4px solid rgba(0,0,0,0.25);border-radius:50%;'+ 'box-sizing:border-box;pointer-events:none;';
        } else {
          indicator.style.cssText = 'position:absolute;top:50%;left:50%;width:16px;height:16px;'
          + 'background:rgba(0,0,0,0.20);border-radius:50%;'
          + 'transform:translate(-50%,-50%);pointer-events:none;';
        }
        sq.style.position = 'relative';
        sq.appendChild(indicator);
      }
      (function(rr, cc) { sq.addEventListener('click', () => onSquareClick(rr, cc)); })(r, c);
      rowDiv.appendChild(sq);
    }
    squaresContainer.appendChild(rowDiv);
  }
  boardDiv.appendChild(squaresContainer);
  let arrowsSvg = document.getElementById('boardArrowsInline'); if (arrowsSvg) arrowsSvg.remove();
  const ns = 'http://www.w3.org/2000/svg';
  arrowsSvg = document.createElementNS(ns, 'svg');
  arrowsSvg.id = 'boardArrowsInline'; arrowsSvg.setAttribute('class', 'board-arrows'); arrowsSvg.setAttribute('viewBox', '0 0 400 400');
  boardDiv.appendChild(arrowsSvg);
  const treeHeadFragment = renderArrowsForCurrentNode();
  // Engine arrows are separate from opening-tree arrows.
  // Hide both engines' arrows during move selection.
  if (!window._SELECTED_SQUARE) {
    const engineArrowFen = stateToFEN(state);
    const engineShaftFragment = document.createDocumentFragment();
    const engineHeadFragment = document.createDocumentFragment();
    [window._ENGINE_ARROW_BLUE, window._ENGINE_ARROW_GREEN].forEach(function(ea) {
      if (!ea || ea.fen !== engineArrowFen) return;
      try {
        const fc = squareCenterForCoords(ea.fromR, ea.fromC);
        const tc = squareCenterForCoords(ea.toR, ea.toC);
        const dx = tc.x - fc.x, dy = tc.y - fc.y;
        const dist = Math.hypot(dx, dy) || 1;
        const ux = dx / dist, uy = dy / dist;
        const isBlue = ea.source === 'my-engine';
        const color = isBlue ? 'rgba(59, 130, 246, 0.9)' : 'rgba(34, 197, 94, 0.9)';
        const fillColor = isBlue ? '#3b82f6' : '#22c55e';
        const markerId = isBlue ? 'engineArrowHeadBlue' : 'engineArrowHeadGreen';
        const offset = isBlue ? -8 : 8;
        const ox = -uy * offset, oy = ux * offset;
        const fx = fc.x + ox, fy = fc.y + oy;
        const ex = tc.x + ox, ey = tc.y + oy;
        const gap = 24;
        const tx = ex - ux * gap, ty = ey - uy * gap;
        const ns = 'http://www.w3.org/2000/svg';
        let defs = arrowsSvg.querySelector('defs');
        if (!defs) {
          defs = document.createElementNS(ns, 'defs');
          arrowsSvg.appendChild(defs);
        }
        let marker = defs.querySelector('#' + markerId);
        if (!marker) {
          marker = document.createElementNS(ns, 'marker');
          marker.setAttribute('id', markerId);
          marker.setAttribute('markerUnits', 'userSpaceOnUse');
          marker.setAttribute('orient', 'auto');
          marker.setAttribute('markerWidth', '24');
          marker.setAttribute('markerHeight', '30');
          marker.setAttribute('refX', '24');
          marker.setAttribute('refY', '15');
          const path = document.createElementNS(ns, 'path');
          path.setAttribute('d', 'M0 0 L 24 15 L 0 30 Z');
          path.setAttribute('fill', fillColor);
          path.setAttribute('fill-opacity', '0.95');
          path.setAttribute('stroke', 'rgba(255,255,255,0.7)');
          path.setAttribute('stroke-width', '1');
          path.setAttribute('stroke-linejoin', 'round');
          marker.appendChild(path);
          defs.appendChild(marker);
        }
        // White outline underneath the shaft.
        const tailOutline = document.createElementNS(ns, 'line');
        tailOutline.setAttribute('x1', fx); tailOutline.setAttribute('y1', fy);
        tailOutline.setAttribute('x2', tx); tailOutline.setAttribute('y2', ty);
        tailOutline.setAttribute('stroke', 'rgba(255,255,255,0.6)');
        tailOutline.setAttribute('stroke-width', '9');
        tailOutline.setAttribute('stroke-linecap', 'round');
        tailOutline.setAttribute('class', 'engine-arrow');
        engineShaftFragment.appendChild(tailOutline);

        const tail = document.createElementNS(ns, 'line');
        tail.setAttribute('x1', fx); tail.setAttribute('y1', fy);
        tail.setAttribute('x2', tx); tail.setAttribute('y2', ty);
        tail.setAttribute('stroke', color);
        tail.setAttribute('stroke-width', '8');
        tail.setAttribute('stroke-linecap', 'round');
        tail.setAttribute('class', 'engine-arrow');
        engineShaftFragment.appendChild(tail);
        const head = document.createElementNS(ns, 'line');
        head.setAttribute('x1', tx); head.setAttribute('y1', ty);
        head.setAttribute('x2', ex); head.setAttribute('y2', ey);
        head.setAttribute('stroke', 'rgba(0,0,0,0)');
        head.setAttribute('stroke-width', '8');
        head.setAttribute('marker-end', 'url(#' + markerId + ')');
        head.setAttribute('class', 'engine-arrow');
        engineHeadFragment.appendChild(head);
      } catch (e) {
        console.warn('Engine arrow render failed:', e);
      }
    });
    arrowsSvg.appendChild(engineShaftFragment);
    if (treeHeadFragment) arrowsSvg.appendChild(treeHeadFragment);
    arrowsSvg.appendChild(engineHeadFragment);
  } else if (treeHeadFragment) {
    arrowsSvg.appendChild(treeHeadFragment);
  }
  for (let fi = 0; fi < 8; fi++) { const c = fileIndices[fi]; const f = document.createElement('div'); f.className = 'board-file-label'; f.textContent = String.fromCharCode(97 + c); filesRow.appendChild(f); }
}

/* ===== FIXED onSquareClick – arrows update immediately ===== */
function onSquareClick(r, c) {
  const state = window._CURRENT_STATE || initialBoardState();
  const piece = state.board[r][c];

  if (!window._SELECTED_SQUARE) {
    if (!piece || pieceColor(piece) !== state.turn) return;
    window._SELECTED_SQUARE = { r, c };
    renderBoard(state);
    return;
  }

  const sel = window._SELECTED_SQUARE;
  if (sel.r === r && sel.c === c) {
    window._SELECTED_SQUARE = null;
    renderBoard(state);
    return;
  }

  const moves = generatePseudoMoves(state, state.turn);
  const cand = moves.filter(
    m => m.fromR === sel.r && m.fromC === sel.c &&
         m.toR === r && m.toC === c
  );

  if (!cand.length) {
    window._SELECTED_SQUARE = null;
    renderBoard(state);
    return;
  }

  const legalCand = cand.filter(mv => {
    if (mv.castle && !isCastlingLegal(state, state.turn, mv.castle)) {
      return false;
    }
    const tmp = applyMoveToState(state, mv);
    return !isKingInCheck(tmp, state.turn);
  });

  if (!legalCand.length) {
    window._SELECTED_SQUARE = null;
    renderBoard(state);
    return;
  }

  let mv = legalCand[0];
  if (legalCand.length > 1 && legalCand[0].promotion) {
    const choice = prompt(
      'Promote pawn to? Type: Q = Queen, R = Rook, B = Bishop, N = Knight',
      'Q'
    );
    const chosen = (choice || 'Q').toUpperCase();
    mv = legalCand.find(m => m.promotion === chosen) || legalCand[0];
  }

  const newState = applyMoveToState(state, mv);
  const san = moveToSAN(state, mv);

  if (!Array.isArray(window._LINE_MOVES_SAN)) {
    window._LINE_MOVES_SAN = [];
  }

  if (window._CURRENT_PLY < window._LINE_MOVES_SAN.length) {
    window._LINE_MOVES_SAN =
      window._LINE_MOVES_SAN.slice(0, window._CURRENT_PLY);
  }

  window._LINE_MOVES_SAN.push(san);
  window._CURRENT_PLY = window._LINE_MOVES_SAN.length;
  window._LINE_SOURCE = 'manual';
  window._SELECTED_SQUARE = null;
  window._CURRENT_STATE = newState;
  window._ENGINE_ARROW_BLUE = null;
  window._ENGINE_ARROW_GREEN = null;

  if (window._DATA_SOURCE === 'database') {
    updateBoardFromLine();
  } else if (window._CUSTOM_FEN_CONTEXT) {
    const boardSeq = invalidateBoardUpdate();

    renderBoard(newState);
    renderCurrentLineMoves();
    updateCurrentLineLabel();
    updateMoveInfo();
    clearOpeningsSelection();

    const newFen = stateToFEN(newState);
    if (typeof onPositionChanged === 'function') {
      onPositionChanged(newFen);
    } else if (typeof runUnifiedAnalysis === 'function') {
      runUnifiedAnalysis(newFen);
    }

    syncCustomFenPath(
      window._LINE_MOVES_SAN,
      window._CURRENT_PLY,
      boardSeq
    ).catch(function(err) {
      console.warn('Custom FEN sync failed:', err);
    });
  } else {
    syncCurrentNodeWithLine();
    renderBoard(newState);
    renderCurrentLineMoves();
    updateCurrentLineLabel();
    updateMoveInfo();
    clearOpeningsSelection();

    if (typeof onPositionChanged === 'function') {
      onPositionChanged(stateToFEN(newState));
    }
  }
}

function updateMoveInfo() {
  const info = document.getElementById('moveInfo');
  if (!info) return;

  const isCustom = !!window._CUSTOM_FEN_CONTEXT;
  const baseTurn = isCustom
    ? window._CUSTOM_FEN_CONTEXT.baseState.turn
    : 'w';
  const baseFm = isCustom
    ? window._CUSTOM_FEN_CONTEXT.baseState.fullmoveNumber
    : 1;
  const plyOffset = baseTurn === 'b' ? 1 : 0;

  if (!window._LINE_MOVES_SAN.length) {
    info.textContent = isCustom ? 'Custom FEN position' : 'Start position';
    return;
  }

  const currentMoveNum =
    Math.floor((window._CURRENT_PLY + plyOffset - 1) / 2) + baseFm;

  info.textContent =
    `Move ${currentMoveNum} | Ply ${window._CURRENT_PLY}/${window._LINE_MOVES_SAN.length}`;
}
function renderCurrentLineMoves() {
  const container = document.getElementById('currentLineMoves');
  if (!container) return;

  container.innerHTML = '';

  const moves = window._LINE_MOVES_SAN || [];
  const ply = window._CURRENT_PLY || 0;
  const isCustom = !!window._CUSTOM_FEN_CONTEXT;
  const baseTurn = isCustom
    ? window._CUSTOM_FEN_CONTEXT.baseState.turn
    : 'w';
  const baseFm = isCustom
    ? window._CUSTOM_FEN_CONTEXT.baseState.fullmoveNumber
    : 1;
  const plyOffset = baseTurn === 'b' ? 1 : 0;

  if (!moves.length) {
    const span = document.createElement('span');
    span.className = 'small-muted';
    span.textContent = isCustom
      ? 'Custom FEN position (no moves yet).'
      : 'Start position (no moves yet).';
    container.appendChild(span);
    return;
  }

  for (let i = 0; i < moves.length; i++) {
    const move = moves[i];
    const moveNum = Math.floor((i + plyOffset) / 2) + baseFm;

    const label = ((i + plyOffset) % 2 === 0)
      ? (moveNum + '. ' + move)
      : ((isCustom && i === 0 && baseTurn === 'b')
          ? (moveNum + '... ' + move)
          : move);

    const chip = document.createElement('div');
    chip.className = 'current-move-chip';
    if (i + 1 === ply) chip.classList.add('active');
    chip.textContent = label;

    chip.addEventListener('click', () => {
      window._CURRENT_PLY = i + 1;
      updateBoardFromLine();
    });

    container.appendChild(chip);
  }
}

/* ===== Sync & navigation ===== */
function syncCurrentNodeWithLine() {
  if (!window._TREE || !window._LINE_MOVES_SAN) return;
  let node = window._TREE, state = initialBoardState(); const upto = window._CURRENT_PLY;
  for (let i = 0; i < upto; i++) {
    const san = window._LINE_MOVES_SAN[i];
    try {
      const mv = sanToMove(state, san);
      const key = mv.fromR + ',' + mv.fromC + '-' + mv.toR + ',' + mv.toC + (mv.promotion || '');
      if (!node.children.has(key)) { window._CURRENT_NODE = null; renderTree(); renderNodeDetails(null); document.getElementById('nodeDetails').innerHTML = '<div class="small-muted">Position not found in your repertoire tree.</div>'; return; }
      node = node.children.get(key);
      state = applyMoveToState(state, mv);
    } catch (e) { window._CURRENT_NODE = null; renderTree(); renderNodeDetails(null); document.getElementById('nodeDetails').innerHTML = '<div class="small-muted">Position not found in your repertoire tree.</div>'; return; }
  }
  window._CURRENT_NODE = node; renderTree(); renderNodeDetails(node);
}

async function syncCustomFenPath(line, ply, boardSeq) {
  const ctx = window._CUSTOM_FEN_CONTEXT;
  if (!ctx) return { matched: false, reason: 'no-context' };

  window._customFenSyncSeq =
    Number.isSafeInteger(window._customFenSyncSeq)
      ? window._customFenSyncSeq + 1
      : 1;

  const treeSeq = window._customFenSyncSeq;
  const ownerSeq = Number.isSafeInteger(boardSeq)
    ? boardSeq
    : _updateBoardSeq;

  const isCurrent = function() {
    return (
      treeSeq === window._customFenSyncSeq &&
      window._CUSTOM_FEN_CONTEXT === ctx &&
      ownerSeq === _updateBoardSeq
    );
  };

  const moves = Array.isArray(line) ? line : [];
  const requestedPly = Number.isInteger(ply) ? ply : 0;
  const upto = Math.max(0, Math.min(requestedPly, moves.length));

  let node = ctx.root;
  let state = ctx.baseState
    ? cloneState(ctx.baseState)
    : initialBoardState();

  for (let i = 0; i < upto; i++) {
    if (!isCurrent()) {
      return { matched: false, reason: 'stale' };
    }

    let move;
    try {
      move = sanToMove(state, moves[i]);
    } catch (err) {
      if (!isCurrent()) {
        return { matched: false, reason: 'stale' };
      }

      ctx.lookupError = false;
      window._CURRENT_NODE = null;

      if (typeof renderTree === 'function') renderTree();
      if (typeof renderNodeDetails === 'function') renderNodeDetails(null);
      if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
      if (typeof renderBoard === 'function' && window._CURRENT_STATE) {
        renderBoard(window._CURRENT_STATE);
      }

      return { matched: false, reason: 'invalid-move' };
    }

    const key =
      move.fromR + ',' + move.fromC + '-' +
      move.toR + ',' + move.toC +
      (move.promotion || '');

    let child = node.children.get(key);

    if (!child) {
      const loaded = await loadServerChildren(node);

      if (!isCurrent()) {
        return { matched: false, reason: 'stale' };
      }

      if (!loaded) {
        ctx.lookupError = true;
        window._CURRENT_NODE = null;

        if (typeof renderTree === 'function') renderTree();
        if (typeof renderNodeDetails === 'function') renderNodeDetails(null);
        if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
        if (typeof renderBoard === 'function' && window._CURRENT_STATE) {
          renderBoard(window._CURRENT_STATE);
        }

        return { matched: false, reason: 'tree-load-failed' };
      }

      child = node.children.get(key);
    }

    if (!child) {
      if (!isCurrent()) {
        return { matched: false, reason: 'stale' };
      }

      ctx.lookupError = false;
      window._CURRENT_NODE = null;

      if (typeof renderTree === 'function') renderTree();
      if (typeof renderNodeDetails === 'function') renderNodeDetails(null);
      if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
      if (typeof renderBoard === 'function' && window._CURRENT_STATE) {
        renderBoard(window._CURRENT_STATE);
      }

      return { matched: false, reason: 'outside-repertoire' };
    }

    node = child;
    state = applyMoveToState(state, move);
  }

  if (!isCurrent()) {
    return { matched: false, reason: 'stale' };
  }

  ctx.lookupError = false;
  window._CURRENT_NODE = node;

  if (typeof renderTree === 'function') renderTree();
  if (typeof renderNodeDetails === 'function') renderNodeDetails(node);
  if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
  if (typeof renderBoard === 'function' && window._CURRENT_STATE) {
    renderBoard(window._CURRENT_STATE);
  }

  return { matched: true, node: node };
}

let _pausedLine = null;
let _dbSyncSeq = 0;

async function syncDatabasePositionFromLine() {
  if (window._DATA_SOURCE !== 'database' || !window._TREE) return;
  const seq = ++_dbSyncSeq;
  const line = window._LINE_MOVES_SAN || [];
  const upto = Math.max(0, Math.min(window._CURRENT_PLY || 0, line.length));
  let node = window._TREE;
  let state = initialBoardState();
  let outside = false;

  for (let i = 0; i < upto; i++) {
    if (seq !== _dbSyncSeq) return;
    const san = line[i];
    let mv;
    try {
      mv = sanToMove(state, san);
    } catch (e) {
      outside = true;
      break;
    }
    const key = mv.fromR + ',' + mv.fromC + '-' + mv.toR + ',' + mv.toC + (mv.promotion || '');
    let child = node.children.get(key) || null;
    if (!child) {
      await loadServerChildren(node);
      if (seq !== _dbSyncSeq) return;
      child = node.children.get(key) || null;
    }
    if (!child) {
      outside = true;
      break;
    }
    node = child;
    state = applyMoveToState(state, mv);
  }

  if (seq !== _dbSyncSeq) return;

  if (outside) {
    // FEN-based recovery for DB mode. The move-key walk can fail when
    // the current line reaches a position by a path that is absent from
    // this client node, while the server tree already merges that same
    // position by canonical FEN.
    const _curState = window._CURRENT_STATE || state;
    const _fen = stateToFEN(_curState);
    const _synth = {
      move: null,
      uci: null,
      fen: _fen,
      state: cloneState(_curState),
      children: new Map(),
      count: 0,
      stats: { w: 0, b: 0, d: 0 },
      parent: node,
      serverNode: false,
      serverLoaded: false,
      serverLoading: false,
      eloSum: 0,
      eloCount: 0,
      scores: { engine: null, neural: null }
    };

    try {
      await loadServerChildren(_synth);
    } catch (e) {}

    if (seq !== _dbSyncSeq) return;

    if (_synth.children && _synth.children.size > 0) {
      _synth.serverLoaded = true;
      window._CURRENT_NODE = _synth;
      window._CURRENT_STATE = cloneState(_curState);
      renderTree();
      renderNodeDetails(_synth);
      updateCurrentLineLabel();
      return;
    }

    window._CURRENT_NODE = null;
    renderTree();
    const details = document.getElementById('nodeDetails');
    if (details) details.innerHTML = '<div class="small-muted">Position not found in your repertoire tree.</div>';
    const list = document.getElementById('nodeGameList');
    if (list) list.textContent = 'Games in this node will appear here.';
    const buckets = document.getElementById('nodeResultBuckets');
    if (buckets) buckets.innerHTML = '';
    const sample = document.getElementById('sampleGames');
    if (sample) sample.value = '';
    updateCurrentLineLabel();
    return;
  }

  if (!node.serverLoaded) {
    await loadServerChildren(node);
    if (seq !== _dbSyncSeq) return;
  }

  window._CURRENT_NODE = node;
  window._CURRENT_STATE = cloneState(state);
  renderTree();
  renderNodeDetails(node);
  updateCurrentLineLabel();
}

function freezeCurrentLine() {
    if (!_pausedLine) {
        _pausedLine = (window._LINE_MOVES_SAN || []).slice();
    }
}
function unfreezeCurrentLine() {
    _pausedLine = null;
}

let _updateBoardSeq = 0;

function invalidateBoardUpdate() {
  _updateBoardSeq += 1;
  _dbSyncSeq += 1;
  return _updateBoardSeq;
}

window.invalidateBoardUpdate = invalidateBoardUpdate;
window._isBoardUpdateCurrent = function(seq) {
  return seq === _updateBoardSeq;
};

async function updateBoardFromLine() {
  const seq = ++_updateBoardSeq;
  const databaseMode = window._DATA_SOURCE === 'database';

  if (window._CUSTOM_FEN_CONTEXT) {
    const source = window._LINE_SOURCE || '';
    if (
      source !== 'custom-fen' &&
      source !== 'manual' &&
      source !== 'tree'
    ) {
      window._CUSTOM_FEN_CONTEXT = null;
      window._customFenSyncSeq =
        Number.isSafeInteger(window._customFenSyncSeq)
          ? window._customFenSyncSeq + 1
          : 1;
      if (window._bumpFenLoadSeq) window._bumpFenLoadSeq();
    }
  }

  const customContext =
    (!databaseMode) ? window._CUSTOM_FEN_CONTEXT : null;

  let line;
  if (databaseMode || customContext) {
    line = window._LINE_MOVES_SAN;
  } else {
    line = (
      window.batchAutoFollow === false && _pausedLine
    ) ? _pausedLine : window._LINE_MOVES_SAN;
  }

  const baseState = customContext ? customContext.baseState : null;
  const res = playLine(line, window._CURRENT_PLY, baseState);

  window._CURRENT_STATE = res.state;
  if (window._CURRENT_PLY !== res.ply) {
    window._CURRENT_PLY = res.ply;
  }

  if (databaseMode) {
    await syncDatabasePositionFromLine();
    if (seq !== _updateBoardSeq) return;
  } else if (customContext) {
    await syncCustomFenPath(line, window._CURRENT_PLY, seq);
    if (seq !== _updateBoardSeq) return;
  } else {
    syncCurrentNodeWithLine();
  }

  if (seq !== _updateBoardSeq) return;

  const renderState = databaseMode
    ? (window._CURRENT_STATE || res.state)
    : res.state;

  renderBoard(renderState);
  updateMoveInfo();
  renderCurrentLineMoves();
  updateCurrentLineLabel();

  if (seq !== _updateBoardSeq) return;

  const fen = stateToFEN(renderState);
  if (typeof onPositionChanged === 'function') {
    onPositionChanged(fen);
  } else if (typeof runUnifiedAnalysis === 'function') {
    runUnifiedAnalysis(fen);
  }
}
function setLineFromNode(node) { const line = getPathFromNode(node); window._LINE_MOVES_SAN = line; window._CURRENT_PLY = line.length; window._LINE_SOURCE = 'tree'; updateBoardFromLine(); }
function updateCurrentLineLabel() {
  const el = document.getElementById('currentLineLabel');
  if (!el) return;

  const ctx = window._CUSTOM_FEN_CONTEXT;
  if (ctx) {
    if (window._CURRENT_NODE === null) {
      el.textContent = ctx.lookupError
        ? 'Current line: (tree lookup failed)'
        : 'Current line: (outside repertoire)';
      return;
    }

    const moves = window._LINE_MOVES_SAN || [];
    const ply = window._CURRENT_PLY || 0;

    if (!moves.length) {
      el.textContent = 'Current line: (custom FEN position)';
      return;
    }

    const baseTurn = ctx.baseState.turn;
    const baseFm = ctx.baseState.fullmoveNumber;
    const offset = baseTurn === 'b' ? 1 : 0;

    const path = moves.slice(0, ply).map((move, i) => {
      const moveNum = Math.floor((i + offset) / 2) + baseFm;
      if ((i + offset) % 2 === 0) return moveNum + '. ' + move;
      if (i === 0 && baseTurn === 'b') return moveNum + '... ' + move;
      return move;
    }).join(' ');

    el.textContent = 'Current line: ' + path;
    return;
  }

  if (!window._TREE) {
    el.textContent = 'Current line: (no games)';
    return;
  }

  if (window._CURRENT_NODE === null) {
    el.textContent = 'Current line: (outside repertoire)';
    return;
  }

  const node = window._CURRENT_NODE || window._TREE;
  const path = getPathFromNode(node);

  el.textContent = path.length
    ? 'Current line: ' + path.map((m, i) =>
        ((i % 2 === 0)
          ? (Math.floor(i / 2) + 1) + '. '
          : '') + m
      ).join(' ')
    : 'Current line: (start position)';
}

/* ===== Node details ===== */
function loadGameAtNode(gameIndex, node, sourceLabel) { const game = window._PARSED_GAMES[gameIndex]; if (!game) return; window._LINE_MOVES_SAN = game.moves.slice(); const plyAtNode = findPlyOfNodeInGame(game, node); window._CURRENT_PLY = plyAtNode > 0 ? plyAtNode : game.moves.length; window._LINE_SOURCE = sourceLabel || 'game'; updateBoardFromLine(); }
function renderNodeResultBuckets(node) {
  const bucketsRoot = document.getElementById('nodeResultBuckets'); if (!bucketsRoot) return; if (!node || !node.games || !node.games.length) { bucketsRoot.innerHTML = 'No games to split by result yet.'; return; }
  const allGames = window._PARSED_GAMES || [], buckets = { white: [], black: [], draw: [] };
  node.games.forEach(idx => { const g = allGames[idx]; if (!g) return; const res = (g.tags.Result || '').trim(); if (res === '1-0') buckets.white.push(idx); else if (res === '0-1') buckets.black.push(idx); else if (res === '1/2-1/2') buckets.draw.push(idx); });
  function buildColumn(label, idxList) {
    const col = document.createElement('div'); col.className = 'node-results-column'; const h = document.createElement('h4'); h.textContent = label; col.appendChild(h);
    if (!idxList.length) { const none = document.createElement('div'); none.className = 'small-muted'; none.textContent = '—'; col.appendChild(none); return col; }
    const listDiv = document.createElement('div'); listDiv.className = 'node-results-list'; const limit = Math.min(idxList.length, 20);
    for (let i = 0; i < limit; i++) { const gameIndex = idxList[i], g = allGames[gameIndex] || { tags: {} }, w = g.tags.White || '?', b = g.tags.Black || '?', r = g.tags.Result || '?'; const e = document.createElement('div'); e.className = 'node-results-entry'; e.textContent = `${gameIndex + 1}. ${w} vs ${b} (${r})`; e.dataset.gameIndex = gameIndex; e.addEventListener('click', () => { document.querySelectorAll('tr.games-row-selected').forEach(el => el.classList.remove('games-row-selected')); const row = document.querySelector(`tr[data-game-index="${gameIndex}"]`); if (row) row.classList.add('games-row-selected'); document.querySelectorAll('.node-game-entry.selected').forEach(el => el.classList.remove('selected')); loadGameAtNode(gameIndex, node, 'node-bucket'); clearOpeningsSelection(); }); listDiv.appendChild(e); }
    if (limit < idxList.length) { const more = document.createElement('div'); more.className = 'small-muted'; more.textContent = `+ ${idxList.length - limit} more…`; listDiv.appendChild(more); }
    col.appendChild(listDiv); return col;
  }
  bucketsRoot.innerHTML = ''; const wrap = document.createElement('div'); wrap.className = 'node-results-wrapper'; const title = document.createElement('div'); title.className = 'node-results-title'; title.textContent = 'Games by result at this node'; wrap.appendChild(title);
  const bucketsGrid = document.createElement('div'); bucketsGrid.className = 'node-results-buckets'; bucketsGrid.appendChild(buildColumn('White wins', buckets.white)); bucketsGrid.appendChild(buildColumn('Black wins', buckets.black)); bucketsGrid.appendChild(buildColumn('Draws', buckets.draw)); wrap.appendChild(bucketsGrid); bucketsRoot.appendChild(wrap);
}
function renderNodeDetails(node) {
  const details = document.getElementById('nodeDetails'), sample = document.getElementById('sampleGames'), nodeGameList = document.getElementById('nodeGameList');
  if (!node && window._CUSTOM_FEN_CONTEXT) {
    const ctx = window._CUSTOM_FEN_CONTEXT;
    if (ctx.lookupError) {
      details.innerHTML =
        '<div class="small-muted"><strong>Tree lookup failed</strong></div>' +
        '<div class="small-muted" style="margin-top:4px;">The repertoire request could not be completed. Your board position and engine analysis remain available.</div>';
    } else {
      details.innerHTML =
        '<div class="small-muted"><strong>Outside repertoire</strong></div>' +
        '<div class="small-muted" style="margin-top:4px;">This move sequence is not present in your recorded games.</div>';
    }
    nodeGameList.textContent = '';
    sample.value = '';
    renderNodeResultBuckets(null);
    return;
  }

  if (!node) {
    details.innerHTML = 'Select a move in the tree to see stats, line, and FEN.';
    nodeGameList.textContent = 'Games in this node will appear here.';
    sample.value = '';
    renderNodeResultBuckets(null);
    return;
  }
  const movePath = getPathFromNode(node);
  const isCustom = !!window._CUSTOM_FEN_CONTEXT;
  const baseTurn = isCustom ? window._CUSTOM_FEN_CONTEXT.baseState.turn : 'w';
  const baseFm = isCustom ? window._CUSTOM_FEN_CONTEXT.baseState.fullmoveNumber : 1;
  const offset = baseTurn === 'b' ? 1 : 0;
  const lineStr = movePath.map((move, i) => {
    const moveNum = Math.floor((i + offset) / 2) + baseFm;
    if ((i + offset) % 2 === 0) return moveNum + '. ' + move;
    if (isCustom && i === 0 && baseTurn === 'b') return moveNum + '... ' + move;
    return move;
  }).join(' ');
  const stats = filteredNodeResults(node, node);
  const ws = stats.whiteScorePct.toFixed(1);
  const bs = stats.blackScorePct.toFixed(1);
  let fen = '';
  try { fen = stateToFEN(stateFromNode(node)); } catch (e) {}
  if (window._CUSTOM_FEN_CONTEXT &&
      node === window._CUSTOM_FEN_CONTEXT.root) {
    const ctx = window._CUSTOM_FEN_CONTEXT;
    const turn = ctx.baseState.turn === 'w'
      ? 'White to move'
      : 'Black to move';
    const error = node.serverError
      ? '<div class="small-muted" style="color:#ef5350;margin-top:4px;">Tree lookup failed — repertoire continuations are temporarily unavailable.</div>'
      : '';
    details.innerHTML =
      '<div class="small-muted"><strong>Custom FEN position</strong> (' + turn + ')</div>' +
      '<div class="small-muted" style="margin-top:4px;">Recorded repertoire continuations from this position.</div>' +
      error +
      '<div class="small-muted" style="margin-top:4px;font-family:monospace;font-size:11px;word-break:break-all;">FEN: ' +
      ctx.fen + '</div>';
  } else if (!node.move) {
    details.innerHTML = `<div class="small-muted"><strong>Root position</strong> (start)</div><div class="small-muted">All games begin here. Use the moves list to branch out.</div><div class="small-muted" style="margin-top:4px;">Total games: ${stats.total} • White score: ${ws}% • Black score: ${bs}%</div><div class="small-muted" style="margin-top:4px;">FEN: ${fen}</div>`;
  }
  else details.innerHTML = `<div class="small-muted">Move: <strong>${node.move}</strong></div><div class="small-muted">Games reaching this node: <strong>${node.count}</strong></div><div class="small-muted">White score here: ${ws}% • Black score: ${bs}%</div><div class="small-muted" style="margin-top:4px;">Line: ${lineStr || '—'}</div><div class="small-muted" style="margin-top:4px;">FEN: ${fen}</div>`;
  const allGames = window._PARSED_GAMES || [];
  const _filteredGames = gamesForPerspective(node.games || [], node);
  nodeGameList.innerHTML = '';
  if (!_filteredGames.length) nodeGameList.textContent = 'Games in this node: 0.';
  else {
    const summary = document.createElement('div'); summary.className = 'small-muted'; summary.textContent = `Games in this node: ${_filteredGames.length}`; nodeGameList.appendChild(summary);
    const list = document.createElement('div'); const sortedIdx = _filteredGames.slice().sort((a, b) => a - b); const limit = Math.min(sortedIdx.length, 25);
    for (let j = 0; j < limit; j++) {
      const gameIndex = sortedIdx[j], g = allGames[gameIndex] || { tags: {} }, w = g.tags.White || '?', b = g.tags.Black || '?', r = g.tags.Result || '?';
      const entry = document.createElement('div'); entry.className = 'node-game-entry'; entry.textContent = `${j + 1}. [#${gameIndex + 1}] ${w} vs ${b} (${r})`; entry.dataset.gameIndex = gameIndex;
      entry.addEventListener('click', () => { document.querySelectorAll('.node-game-entry.selected').forEach(el => el.classList.remove('selected')); entry.classList.add('selected'); document.querySelectorAll('tr.games-row-selected').forEach(el => el.classList.remove('games-row-selected')); const row = document.querySelector(`tr[data-game-index="${gameIndex}"]`); if (row) row.classList.add('games-row-selected'); loadGameAtNode(gameIndex, node, 'node-list'); clearOpeningsSelection(); });
      list.appendChild(entry);
    }
    if (limit < sortedIdx.length) { const more = document.createElement('div'); more.className = 'small-muted'; more.textContent = `+ ${sortedIdx.length - limit} more…`; list.appendChild(more); }
    nodeGameList.appendChild(list);
  }
  const samples = _filteredGames.slice(0, 100).map(i => window._PGN_GAMES[i]).join('\n\n---\n\n'); sample.value = samples || '';
  renderNodeResultBuckets(node);
}

/* ===== Tree rendering ===== */
/* ===== Opening Tree perspective (T2a) ===== */
window._PERSPECTIVE = 'all';
window._PLAYER_ALIASES = null;
window._PLAYER_ALIASES_ERROR = null;

function nodeDepth(node) {
  let d = 0, n = node;
  while (n && n.parent) { d++; n = n.parent; }
  return d;
}

function _sideToMoveOfNode(node) {
  if (!node) return 'white';
  if (node.fen) {
    const parts = String(node.fen).trim().split(/\s+/);
    if (parts.length > 1) return (parts[1] === 'b') ? 'black' : 'white';
  }
  if (node.state && node.state.turn) {
    return (node.state.turn === 'b') ? 'black' : 'white';
  }
  return 'white';
}

function loadPlayerAliases() {
  if (window._PLAYER_ALIASES && window._PLAYER_ALIASES.loaded) {
    return Promise.resolve(window._PLAYER_ALIASES);
  }

  return fetch('/api/provenance/audit').then(function(r) {
    if (!r.ok) throw new Error('Provenance audit HTTP ' + r.status);
    return r.json();
  }).then(function(d) {
    const set = new Set();
    const ci = (d && d.canonical_identity) || {};

    (ci.players || []).forEach(function(p) {
      const n = p && p.canonical_name;
      if (n) set.add(String(n).trim().toLowerCase());
    });

    (ci.aliases || []).forEach(function(a) {
      const n = a && a.alias;
      if (n) set.add(String(n).trim().toLowerCase());
    });

    if (!set.size) {
      throw new Error('No canonical player identities are available');
    }

    set.loaded = true;
    window._PLAYER_ALIASES_ERROR = null;
    window._PLAYER_ALIASES = set;
    return set;
  }).catch(function(err) {
    window._PLAYER_ALIASES_ERROR = err;
    window._PLAYER_ALIASES = null;
    throw err;
  });
}

function _aliasSet() {
  const a = window._PLAYER_ALIASES;
  return (a && a.size) ? a : null;
}

function _isMyGameAtSide(gameIndex, side) {
  const aliases = _aliasSet();
  if (!aliases) return false;

  const g = (window._PARSED_GAMES || [])[gameIndex];
  if (!g || !g.tags) return false;

  const name = side === 'white' ? g.tags.White : g.tags.Black;
  if (!name) return false;

  return aliases.has(String(name).trim().toLowerCase());
}

function gamesForPerspective(gameIndices, positionNode) {
  const mode = window._PERSPECTIVE || 'all';
  if (mode === 'all') return gameIndices || [];
  const sideToMove = _sideToMoveOfNode(positionNode);
  const oppSide = (sideToMove === 'white') ? 'black' : 'white';
  return (gameIndices || []).filter(function(i) {
    if (mode === 'my-white') return _isMyGameAtSide(i, 'white');
    if (mode === 'my-black') return _isMyGameAtSide(i, 'black');
    if (mode === 'my-games') return _isMyGameAtSide(i, sideToMove);
    if (mode === 'opp-games') return _isMyGameAtSide(i, oppSide);
    return false;
  });
}

function filteredNodeResults(node, positionNode) {
  const mode = window._PERSPECTIVE || 'all';
  if (mode === 'all') return computeNodeResults(node);

  const idxs = gamesForPerspective(node.games || [], positionNode || node);
  const all = window._PARSED_GAMES || [];

  let w = 0, b = 0, d = 0;

  for (const i of idxs) {
    const g = all[i];
    if (!g || !g.tags) continue;

    const r = (g.tags.Result || '').trim();

    if (r === '1-0') w++;
    else if (r === '0-1') b++;
    else if (r === '1/2-1/2') d++;
  }

  const t = w + b + d;

  return {
    total: idxs.length,
    counted: t,
    w1: w,
    b1: b,
    dr: d,
    whiteScorePct: t ? ((w + 0.5 * d) / t * 100) : 0,
    blackScorePct: t ? ((b + 0.5 * d) / t * 100) : 0
  };
}

function filteredNodeAverageElo(node, positionNode) {
  const mode = window._PERSPECTIVE || 'all';
  if (mode === 'all') return computeNodeAverageElo(node);
  const position = positionNode || node;
  const sideToMove = _sideToMoveOfNode(position);
  const oppSide = (sideToMove === 'white') ? 'black' : 'white';
  let eloSide;
  if (mode === 'my-white') eloSide = 'white';
  else if (mode === 'my-black') eloSide = 'black';
  else if (mode === 'my-games') eloSide = sideToMove;
  else if (mode === 'opp-games') eloSide = oppSide;
  else return null;
  const idxs = gamesForPerspective(node.games || [], position);
  const all = window._PARSED_GAMES || [];
  let sum = 0, n = 0;
  for (const i of idxs) {
    const g = all[i];
    if (!g || !g.tags) continue;
    const raw = (eloSide === 'white') ? g.tags.WhiteElo : g.tags.BlackElo;
    const e = parseInt(raw, 10);
    if (!isNaN(e)) { sum += e; n++; }
  }
  return n ? Math.round(sum / n) : null;
}

function roleLabelForMove(positionNode) {
  const mode = window._PERSPECTIVE || 'all';
  if (mode === 'all') return null;
  const sideToMove = _sideToMoveOfNode(positionNode);
  if (mode === 'my-white') return (sideToMove === 'white') ? 'YOU' : 'OPPONENT';
  if (mode === 'my-black') return (sideToMove === 'black') ? 'YOU' : 'OPPONENT';
  if (mode === 'my-games') return 'YOU';
  if (mode === 'opp-games') return 'OPPONENT';
  return null;
}

function modeCountsFor(node, positionNode) {
  const mode = window._PERSPECTIVE || 'all';
  if (node.serverNode) {
    if (mode === 'all') {
      return {
        count: node.count,
        w: node.stats ? node.stats.w : 0,
        d: node.stats ? node.stats.d : 0,
        b: node.stats ? node.stats.b : 0,
        elo: node.eloCount ? Math.round(node.eloSum / node.eloCount) : null
      };
    }
    const sideToMove = _sideToMoveOfNode(positionNode || node);
    if (mode === 'my-white') return { count: node.meWhite, w: node.meWhiteW, d: node.meWhiteD, b: node.meWhiteB, elo: node.meWhiteElo || null };
    if (mode === 'my-black') return { count: node.meBlack, w: node.meBlackW, d: node.meBlackD, b: node.meBlackB, elo: node.meBlackElo || null };
    if (mode === 'my-games') {
      return (sideToMove === 'white')
        ? { count: node.meWhite, w: node.meWhiteW, d: node.meWhiteD, b: node.meWhiteB, elo: node.meWhiteElo || null }
        : { count: node.meBlack, w: node.meBlackW, d: node.meBlackD, b: node.meBlackB, elo: node.meBlackElo || null };
    }
    if (mode === 'opp-games') {
      return (sideToMove === 'white')
        ? { count: node.meBlack, w: node.meBlackW, d: node.meBlackD, b: node.meBlackB, elo: node.meBlackElo || null }
        : { count: node.meWhite, w: node.meWhiteW, d: node.meWhiteD, b: node.meWhiteB, elo: node.meWhiteElo || null };
    }
    return { count: 0, w: 0, d: 0, b: 0, elo: null };
  }
  const stats = filteredNodeResults(node, positionNode || node);
  const elo = filteredNodeAverageElo(node, positionNode || node);
  return { count: stats.total, w: stats.w1, d: stats.dr, b: stats.b1, elo: elo };
}

function ensurePerspectiveBar() {
  if (document.getElementById('perspectiveBar')) return;

  const tree = document.querySelector('.tree');
  if (!tree || !tree.parentElement) return;

  const bar = document.createElement('div');
  bar.id = 'perspectiveBar';
  bar.style.marginTop = '12px';
  bar.style.marginBottom = '14px';
  bar.style.display = 'flex';
  bar.style.flexWrap = 'nowrap';
  bar.style.gap = '3px';
  bar.style.overflowX = 'auto';

  bar.innerHTML =
    '<button class="secondary" data-persp="all" style="padding:3px 6px;font-size:10px;white-space:nowrap;flex:0 0 auto;">All Games</button>' +
    '<button class="secondary" data-persp="my-games" style="padding:3px 6px;font-size:10px;white-space:nowrap;flex:0 0 auto;">My Games</button>' +
    '<button class="secondary" data-persp="opp-games" style="padding:3px 6px;font-size:10px;white-space:nowrap;flex:0 0 auto;">Opponent Games</button>' +
    '<button class="secondary" data-persp="my-white" style="padding:3px 6px;font-size:10px;white-space:nowrap;flex:0 0 auto;">My White</button>' +
    '<button class="secondary" data-persp="my-black" style="padding:3px 6px;font-size:10px;white-space:nowrap;flex:0 0 auto;">My Black</button>';

  bar.addEventListener('click', function(e) {
    const btn = e.target.closest('button[data-persp]');
    if (!btn) return;

    const requested = btn.dataset.persp;
    window._PERSPECTIVE = requested;
    updatePerspectiveBar();

    if (requested === 'all') {
      renderTree();
      renderNodeDetails(window._CURRENT_NODE || window._TREE);
      return;
    }

    loadPlayerAliases().then(function() {
      updatePerspectiveBar();
      renderTree();
      renderNodeDetails(window._CURRENT_NODE || window._TREE);
    }).catch(function(err) {
      console.error('Opening Tree perspective failed:', err);
      window._PERSPECTIVE = 'all';
      updatePerspectiveBar();
      renderTree();
      renderNodeDetails(window._CURRENT_NODE || window._TREE);
    });
  });

  tree.parentElement.insertBefore(bar, tree);
  updatePerspectiveBar();
}

function updatePerspectiveBar() {
  const bar = document.getElementById('perspectiveBar');
  if (!bar) return;

  bar.querySelectorAll('button[data-persp]').forEach(function(btn) {
    if (btn.dataset.persp === window._PERSPECTIVE) {
      btn.style.background = '#22c55e';
      btn.style.color = '#022c22';
    } else {
      btn.style.background = '';
      btn.style.color = '';
    }
  });
}

function renderTree() {
  ensurePerspectiveBar();
  const treeBody = document.getElementById('treeBody'); treeBody.innerHTML = '';
  const customContext = window._CUSTOM_FEN_CONTEXT;
  const treeRoot = (customContext && customContext.root)
    ? customContext.root
    : window._TREE;

  if (!treeRoot) {
    const empty = document.createElement('div');
    empty.className = 'small-muted';
    empty.style.padding = '4px 6px';
    empty.textContent = 'No tree yet — upload or paste PGN to begin.';
    treeBody.appendChild(empty);
    updateCurrentLineLabel();
    return;
  }

  if (window._CURRENT_NODE === null) {
    treeBody.innerHTML = customContext && customContext.lookupError
      ? '<div class="small-muted" style="padding:6px;">Tree lookup failed. Your position can still be analysed.</div>'
      : '<div class="small-muted" style="padding:6px;">Position not in repertoire tree.</div>';
    updateCurrentLineLabel();
    return;
  }

  const node = window._CURRENT_NODE || treeRoot;

  const _roleEl = document.getElementById('treeMoveRole');
  const _cntEl = document.getElementById('treeMoveCount');
  const _totEl = document.getElementById('treeTotalGames');
  const _hr = (window._PERSPECTIVE === 'all') ? null : roleLabelForMove(node);
  if (_roleEl) {
    _roleEl.textContent = _hr || '';
    _roleEl.style.display = _hr ? 'block' : 'none';
    _roleEl.style.color = (_hr === 'YOU') ? '#22c55e' : '#9ca3af';
  }
  if (_cntEl || _totEl) {
    let _legal = null;
    try {
      if (typeof generatePseudoMoves === 'function' && typeof stateFromNode === 'function') {
        const _st = stateFromNode(node);
        _legal = generatePseudoMoves(_st, _st.turn).length;
      }
    } catch (e) { _legal = null; }
    let _inTree = 0;
    let _total = 0;
    if (node && node.children) {
      for (const _c of node.children.values()) {
        const _cm = modeCountsFor(_c, node).count;
        if ((_c.count || 0) > 0) _inTree++;
        _total += _cm;
      }
    }
    if (_cntEl) {
      _cntEl.textContent = _legal != null ? ('[' + _inTree + ']/' + _legal) : ('[' + _inTree + ']');
    }
    if (_totEl) {
      _totEl.textContent = _total.toLocaleString();
    }
  }
  const minCount = Number(document.getElementById('minCount').value) || 1, search = document.getElementById('searchMove').value.trim().toLowerCase() || null;
  const ul = document.createElement('ul'); let children = Array.from(node.children.entries());
  const _pdc = new Map();
  for (const [_k, _c] of children) {
    _pdc.set(_k, modeCountsFor(_c, node).count);
  }
  children.sort((a, b) => _pdc.get(b[0]) - _pdc.get(a[0]));
  if (!children.length) { const empty = document.createElement('div'); empty.className = 'small-muted'; empty.style.padding = '4px 6px'; empty.textContent = node.serverError ? 'Tree lookup failed — try the position again.' : 'No further recorded moves from this position.'; treeBody.appendChild(empty); updateCurrentLineLabel(); return; }
  let any = false;
  for (const [, child] of children) {
    const counts = modeCountsFor(child, node);
    const displayCount = counts.count;
    if (displayCount < minCount) continue;
    if (search && !child.move.toLowerCase().includes(search)) continue;
    any = true;
    const denom = (counts.w + counts.d + counts.b) || 1;
    const wFrac = counts.w / denom, dFrac = counts.d / denom, bFrac = counts.b / denom;
    const avgEloText = counts.elo ? counts.elo.toString() : '—';
    const _role = roleLabelForMove(node);
    const _roleTag = _role ? (' <span style="font-size:9px;color:' + (_role === 'YOU' ? '#22c55e' : '#9ca3af') + ';">' + _role + '</span>') : '';
    const _gamesDisplay = counts.count;
    const _positionsDisplay = (window._PERSPECTIVE === 'all') ? (child.positions ?? child.count) : counts.count;
    const li = document.createElement('li'); li.className = 'node';
    const _wp = Math.round(wFrac * 100);
    const _bp = Math.round(bFrac * 100);
    const _dp = Math.max(0, 100 - _wp - _bp);

    let engStr = '—';
    if (child.scores) {
        const t = child.scores.engine_score_type || 'cp';
        if (t === 'mate') {
            if (Number.isFinite(child.scores.engine_mate_moves)) {
                const m = child.scores.engine_mate_moves;
                const s = child.scores.engine_mate_sign || 1;
                engStr = (s > 0 ? '+M' : '-M') + m;
            }
        } else if (t === 'cp' && child.scores.engine != null) {
            engStr = (child.scores.engine > 0 ? '+' : '') + (child.scores.engine / 100).toFixed(2);
            if (child.scores.engine_depth != null) engStr += '/D' + child.scores.engine_depth;
        }
    }

    let sfStr = '—';
    if (child.scores) {
        const t = child.scores.sf_score_type || 'cp';
        if (t === 'mate') {
            if (Number.isFinite(child.scores.sf_mate_moves)) {
                const m = child.scores.sf_mate_moves;
                const s = child.scores.sf_mate_sign || 1;
                sfStr = (s > 0 ? '+M' : '-M') + m;
            }
        } else if (t === 'cp' && child.scores.sf != null) {
            sfStr = (child.scores.sf > 0 ? '+' : '') + (child.scores.sf / 100).toFixed(2);
            if (child.scores.sf_depth != null) sfStr += '/D' + child.scores.sf_depth;
        }
    }

    li.innerHTML = `<div class="tree-row"><div class="tree-col-move">${child.move}</div><div class="tree-col-games">${_gamesDisplay}</div><div class="tree-col-engine" style="font-size:10px;line-height:1.1;"><div class="score-eng" style="color:#d1d5db;">${engStr}</div><div class="score-sf" style="color:#9ca3af;">${sfStr}</div></div><div class="tree-col-results"><div class="results-bar-wrapper"><div class="results-bar"><div class="results-win" style="flex:${wFrac || 0.001};"><span>${_wp}%</span></div><div class="results-draw" style="flex:${dFrac || 0.001};"></div><div class="results-loss" style="flex:${bFrac || 0.001};"><span>${_bp}%</span></div></div><div class="results-counts"><span>${_wp}% / ${_dp}% / ${_bp}%</span><span>W ${counts.w} · ${counts.d} · B ${counts.b}</span></div></div></div></div>`;

    const engEl = li.querySelector('.score-eng');
    if (engEl && child.scores && child.scores.engine_source) {
        engEl.title = `Position-level (unknown history)\nModel: ${child.scores.engine_source}`;
    }
    const sfEl = li.querySelector('.score-sf');
    if (sfEl && child.scores && child.scores.sf_source) {
        sfEl.title = `Position-level (unknown history)\nStockfish: ${child.scores.sf_source}`;
    }

    li.addEventListener('click', async () => {
      if (window._CURRENT_NODE === child) return;
      window._CURRENT_NODE = child;

      if (child.state) {
        applyDatabaseNode(child);
      } else {
        setLineFromNode(child);
        updateCurrentLineLabel();
        clearOpeningsSelection();
      }

      if (
        (window._DATA_SOURCE === 'database' || window._CUSTOM_FEN_CONTEXT) &&
        child.serverLoaded === false
      ) {
        try {
          await loadServerChildren(child);
        } finally {
          renderTree();
          if (window._CURRENT_NODE === child &&
              typeof renderNodeDetails === 'function') {
            renderNodeDetails(child);
          }
          if (typeof renderBoard === 'function' && window._CURRENT_STATE) {
            renderBoard(window._CURRENT_STATE);
          }
        }
      } else {
        renderTree();
      }
    });
    ul.appendChild(li);
  }
  if (!any) { const empty = document.createElement('div'); empty.className = 'small-muted'; empty.style.padding = '4px 6px'; empty.textContent = 'No moves match the current filters.'; treeBody.appendChild(empty); } else treeBody.appendChild(ul);
  updateCurrentLineLabel();
}

/* ===== Filters / export ===== */
function subtreeHasMatch(node, search) { if (node.move && node.move.toLowerCase().includes(search.toLowerCase())) return true; for (const child of node.children.values()) if (subtreeHasMatch(child, search)) return true; return false; }
function collectGamesForFilter(root, minCount, search, currentOnly = false) { const result = new Set(); function walk(node) { for (const child of node.children.values()) { if (child.count >= minCount) { if (!search || subtreeHasMatch(child, search)) { child.games.forEach(i => result.add(i)); } walk(child); } } } if (currentOnly) { if (!window._CURRENT_NODE) { alert('No current node selected for branch export.'); return []; } walk(window._CURRENT_NODE); if (window._CURRENT_NODE.count >= minCount && (!search || subtreeHasMatch(window._CURRENT_NODE, search))) window._CURRENT_NODE.games.forEach(i => result.add(i)); } else { walk(root); if (root.count > 0 && minCount <= 1 && !search) for (let i = 0; i < window._PARSED_GAMES.length; i++) result.add(i); } return Array.from(result).sort((a, b) => a - b); }
function download(filename, text) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = filename; document.body.appendChild(a); a.click(); a.remove(); }

/* ===== Games overview ===== */
function sortGames(col) { if (window._gamesSortCol === col) window._gamesSortDir = (window._gamesSortDir === 'asc' ? 'desc' : 'asc'); else { window._gamesSortCol = col; window._gamesSortDir = 'asc'; } rebuildGamesTable(); updateGameTableHeaderArrows(); }
function buildGameRowData(g, idx) { const firstMoves = g.moves.slice(0, 12).join(' '); return { index: idx, white: g.tags.White || '', black: g.tags.Black || '', result: g.tags.Result || '', whiteElo: parseInt(g.tags.WhiteElo || '0', 10) || 0, blackElo: parseInt(g.tags.BlackElo || '0', 10) || 0, date: g.tags.Date || '', moves: g.moves && g.moves.length ? Math.ceil(g.moves.length / 2) : '', firstMoves }; }
function rebuildGamesTable() { const body = document.getElementById('gamesTableBody'), summary = document.getElementById('gamesSummary'); body.innerHTML = ''; if (!window._PARSED_GAMES || !window._PARSED_GAMES.length) { summary.textContent = 'No games loaded.'; return; } const games = window._PARSED_GAMES; const rows = games.map((g, i) => buildGameRowData(g, i)); const col = window._gamesSortCol, dir = window._gamesSortDir === 'asc' ? 1 : -1; rows.sort((a, b) => { const va = a[col], vb = b[col]; if (typeof va === 'string') return va.localeCompare(vb) * dir; return (va - vb) * dir; }); rows.forEach((r, pos) => { const tr = document.createElement('tr'); tr.dataset.gameIndex = r.index; tr.innerHTML = `<td>${pos + 1}</td><td>${r.white}</td><td>${r.black}</td><td>${r.result}</td><td>${r.whiteElo || ''}</td><td>${r.blackElo || ''}</td><td>${r.date}</td><td>${r.moves}</td><td class="first-moves-cell">${r.firstMoves}</td>`; tr.addEventListener('click', () => { document.querySelectorAll('tr.games-row-selected').forEach(el => el.classList.remove('games-row-selected')); tr.classList.add('games-row-selected'); window._LINE_MOVES_SAN = games[r.index].moves.slice(); window._CURRENT_PLY = games[r.index].moves.length; window._LINE_SOURCE = 'game'; updateBoardFromLine(); clearOpeningsSelection(); }); body.appendChild(tr); }); summary.textContent = `${games.length} games loaded. Click a row to show its final position.`; }

/* ===== Openings list ===== */
const MAX_OPENING_ROWS = 500;
function sortOpenings(col) { if (window._openingsSortCol === col) window._openingsSortDir = (window._openingsSortDir === 'asc' ? 'desc' : 'asc'); else { window._openingsSortCol = col; window._openingsSortDir = 'asc'; } updateOpeningsList(); }
function clearOpeningsSelection() { document.querySelectorAll('tr.openings-row-selected').forEach(el => el.classList.remove('openings-row-selected')); window._SELECTED_OPENING_LINE = null; document.getElementById('copyOpeningLineBtn').disabled = true; }
function initPlyDropdown() { const select = document.getElementById('openingsPlySelect'); if (!select) return; select.innerHTML = ''; for (let i = 1; i <= 30; i++) { const opt = document.createElement('option'); opt.value = i; const moves = (i / 2).toFixed(1).replace('.0', ''); opt.textContent = `${i} ply (~${moves} moves)`; select.appendChild(opt); } select.value = '12'; }
function updateOpeningsList() {
  const body = document.getElementById('openingsTableBody'), summary = document.getElementById('openingsSummary'), statsDiv = document.getElementById('openingsStats');
  body.innerHTML = ''; const games = window._PARSED_GAMES || []; if (!games.length) { summary.textContent = 'No openings yet (no games loaded).'; statsDiv.innerHTML = ''; clearOpeningsSelection(); updatePlyAnalysis(); updateShortOpeningsTable(); return; }
  const select = document.getElementById('openingsPlySelect'); let plies = 12; if (select) { const v = parseInt(select.value, 10); if (!isNaN(v) && v > 0) plies = v; }
  const gamesWithEnoughMoves = games.filter(g => g.moves && g.moves.length >= plies);
  const openingsMap = new Map();
  gamesWithEnoughMoves.forEach((g) => {
    const prefixMoves = g.moves.slice(0, plies); const key = prefixMoves.join(' '), res = (g.tags.Result || '').trim();
    if (!openingsMap.has(key)) openingsMap.set(key, { key, count: 0, wWins: 0, bWins: 0, draws: 0, wEloSum: 0, wEloN: 0, bEloSum: 0, bEloN: 0, pliesSum: 0 });
    const o = openingsMap.get(key); o.count++; if (res === '1-0') o.wWins++; else if (res === '0-1') o.bWins++; else if (res === '1/2-1/2') o.draws++;
    const we = parseInt(g.tags.WhiteElo || '', 10), be = parseInt(g.tags.BlackElo || '', 10); if (!isNaN(we) && we > 0) { o.wEloSum += we; o.wEloN++; } if (!isNaN(be) && be > 0) { o.bEloSum += be; o.bEloN++; }
    if (g.moves && g.moves.length) o.pliesSum += g.moves.length;
  });
  let openings = Array.from(openingsMap.values());
  openings.forEach((o, i) => { o._origIndex = i; });
  const col = window._openingsSortCol, dir = window._openingsSortDir === 'asc' ? 1 : -1;
  openings.sort((a, b) => { let va, vb; switch (col) { case 'index': va = a._origIndex; vb = b._origIndex; break; case 'line': va = a.key; vb = b.key; break; case 'games': va = a.count; vb = b.count; break; case 'wWins': va = a.wWins; vb = b.wWins; break; case 'draws': va = a.draws; vb = b.draws; break; case 'bWins': va = a.bWins; vb = b.bWins; break; case 'whiteWinPct': va = a.count ? (a.wWins / a.count * 100) : 0; vb = b.count ? (b.wWins / b.count * 100) : 0; break; case 'drawPct': va = a.count ? (a.draws / a.count * 100) : 0; vb = b.count ? (b.draws / b.count * 100) : 0; break; case 'blackWinPct': va = a.count ? (a.bWins / a.count * 100) : 0; vb = b.count ? (b.bWins / b.count * 100) : 0; break; case 'wElo': va = a.wEloN ? (a.wEloSum / a.wEloN) : 0; vb = b.wEloN ? (b.wEloSum / b.wEloN) : 0; break; case 'bElo': va = a.bEloN ? (a.bEloSum / a.bEloN) : 0; vb = b.bEloN ? (b.bEloSum / b.bEloN) : 0; break; case 'avgMoves': va = a.pliesSum ? (a.pliesSum / a.count) : 0; vb = b.pliesSum ? (b.pliesSum / b.count) : 0; break; default: return 0; } if (typeof va === 'string') return va.localeCompare(vb) * dir; return (va - vb) * dir; });
  openings = openings.slice(0, MAX_OPENING_ROWS);
  openings.forEach((o, idx) => {
    const movesArray = o.key.split(' '), lineStr = movesArray.map((m, i) => ((i % 2 === 0) ? (Math.floor(i / 2) + 1) + '. ' : '') + m).join(' '); const total = o.count || 0;
    const whiteWinPct = total ? (o.wWins / total * 100).toFixed(1) : '0.0', drawPct = total ? (o.draws / total * 100).toFixed(1) : '0.0', blackWinPct = total ? (o.bWins / total * 100).toFixed(1) : '0.0';
    const wAvg = o.wEloN ? Math.round(o.wEloSum / o.wEloN).toString() : '—', bAvg = o.bEloN ? Math.round(o.bEloSum / o.bEloN).toString() : '—', avgMoves = o.pliesSum ? (o.pliesSum / o.count / 2).toFixed(1) : '—';
    const tr = document.createElement('tr'); tr.innerHTML = `<td>${idx + 1}</td><td class="opening-line-cell">${lineStr}</td><td>${o.count}</td><td>${o.wWins}</td><td>${o.draws}</td><td>${o.bWins}</td><td>${whiteWinPct}</td><td>${drawPct}</td><td>${blackWinPct}</td><td>${wAvg}</td><td>${bAvg}</td><td>${avgMoves}</td>`;
    tr.addEventListener('click', () => { document.querySelectorAll('tr.openings-row-selected').forEach(el => el.classList.remove('openings-row-selected')); tr.classList.add('openings-row-selected'); const moves = o.key.split(' ').filter(Boolean); window._LINE_MOVES_SAN = moves; window._CURRENT_PLY = moves.length; window._LINE_SOURCE = 'opening-list'; updateBoardFromLine(); window._SELECTED_OPENING_LINE = lineStr; document.getElementById('copyOpeningLineBtn').disabled = false; });
    body.appendChild(tr);
  });
  const approxMoves = (plies / 2).toFixed(1).replace('.0', '');
  summary.textContent = `${openings.length} most frequent opening branches by first ${plies} plies (~${approxMoves} moves).`;
  let statsHtml = ''; if (openings.length > 0) { const distinct = openingsMap.size, totalGamesWithPly = gamesWithEnoughMoves.length, avgGames = (totalGamesWithPly / distinct).toFixed(1); const topOpening = openings[0]; const topLineStr = topOpening.key.split(' ').map((m, i) => ((i % 2 === 0) ? (Math.floor(i / 2) + 1) + '. ' : '') + m).join(' '); statsHtml = `<strong>Opening list statistics:</strong><br>Total distinct openings (by ${plies} plies): <strong>${distinct}</strong><br>Average games per opening: <strong>${avgGames}</strong><br>Most popular opening: <strong>${topLineStr}</strong> (${topOpening.count} games)`; }
  statsDiv.innerHTML = statsHtml;
  clearOpeningsSelection(); updatePlyAnalysis(); updateShortOpeningsTable(); updateOpeningsHeaderArrows();
}
function updateShortOpeningsTable() {
  const tbody = document.getElementById('shortOpeningsTableBody'), summary = document.getElementById('shortOpeningsSummary'), section = document.getElementById('shortOpeningsSection');
  tbody.innerHTML = '';
  if (!window._PARSED_GAMES || !window._PARSED_GAMES.length) { summary.textContent = ''; section.style.display = 'none'; return; }
  const games = window._PARSED_GAMES;
  const select = document.getElementById('openingsPlySelect'); let plies = 12; if (select) { const v = parseInt(select.value, 10); if (!isNaN(v) && v > 0) plies = v; }
  const lineMap = new Map();
  games.forEach((g, gIdx) => {
    if (!g.moves || g.moves.length >= plies) return;
    const moves = g.moves; if (!moves.length) return;
    const key = moves.join(' '); const res = (g.tags.Result || '').trim();
    if (!lineMap.has(key)) lineMap.set(key, { key, count: 0, wWins: 0, bWins: 0, draws: 0, wEloSum: 0, wEloN: 0, bEloSum: 0, bEloN: 0, pliesSum: 0, firstGameIdx: gIdx });
    const o = lineMap.get(key); o.count++;
    if (res === '1-0') o.wWins++; else if (res === '0-1') o.bWins++; else if (res === '1/2-1/2') o.draws++;
    const we = parseInt(g.tags.WhiteElo || '', 10), be = parseInt(g.tags.BlackElo || '', 10); if (!isNaN(we) && we > 0) { o.wEloSum += we; o.wEloN++; } if (!isNaN(be) && be > 0) { o.bEloSum += be; o.bEloN++; }
    if (g.moves && g.moves.length) o.pliesSum += g.moves.length;
  });
  const shortCount = Array.from(lineMap.values()).reduce((sum, o) => sum + o.count, 0);
  if (shortCount === 0) { section.style.display = 'none'; return; }
  section.style.display = '';
  const lines = Array.from(lineMap.values()).sort((a, b) => b.count - a.count).slice(0, MAX_OPENING_ROWS);
  lines.forEach((o, idx) => {
    const movesArray = o.key.split(' '); const lineStr = movesArray.map((m, i) => ((i % 2 === 0) ? (Math.floor(i / 2) + 1) + '. ' : '') + m).join(' ');
    const total = o.count || 0;
    const whiteWinPct = total ? (o.wWins / total * 100).toFixed(1) : '0.0';
    const drawPct = total ? (o.draws / total * 100).toFixed(1) : '0.0';
    const blackWinPct = total ? (o.bWins / total * 100).toFixed(1) : '0.0';
    const wAvg = o.wEloN ? Math.round(o.wEloSum / o.wEloN).toString() : '—';
    const bAvg = o.bEloN ? Math.round(o.bEloSum / o.bEloN).toString() : '—';
    const avgMoves = o.pliesSum ? (o.pliesSum / o.count / 2).toFixed(1) : '—';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${idx + 1}</td><td class="opening-line-cell">${lineStr}</td><td>${o.count}</td><td>${o.wWins}</td><td>${o.draws}</td><td>${o.bWins}</td><td>${whiteWinPct}</td><td>${drawPct}</td><td>${blackWinPct}</td><td>${wAvg}</td><td>${bAvg}</td><td>${avgMoves}</td>`;
    tr.addEventListener('click', () => {
      document.querySelectorAll('tr.openings-row-selected').forEach(el => el.classList.remove('openings-row-selected'));
      tr.classList.add('openings-row-selected');
      const game = games[o.firstGameIdx];
      if (game) { window._LINE_MOVES_SAN = game.moves.slice(); window._CURRENT_PLY = game.moves.length; window._LINE_SOURCE = 'short-openings'; updateBoardFromLine(); }
      window._SELECTED_OPENING_LINE = lineStr; document.getElementById('copyOpeningLineBtn').disabled = false;
    });
    tbody.appendChild(tr);
  });
  summary.textContent = `${shortCount} games shorter than ${plies} plies, grouped into ${lines.length} unique lines.`;
}
function updatePlyAnalysis() {
  const container = document.getElementById('plyAnalysisTableContainer'); if (!container) return;
  container.innerHTML = '';
  let games = window._PARSED_GAMES || [];
  if (window._DATA_SOURCE === 'database' && window._DB_GAMES && window._DB_GAMES.length) {
    games = window._DB_GAMES.map(g => ({
      moves: Array.isArray(g.first_moves) ? g.first_moves : [],
      tags: {
        Result: g.result || '',
        Date: g.date || '',
        ECO: g.eco || '',
        White: g.white || '',
        Black: g.black || '',
        WhiteElo: String(g.whiteElo || ''),
        BlackElo: String(g.blackElo || '')
      }
    }));
  }
  if (!games.length) { container.innerHTML = '<div class="small-muted">No games loaded.</div>'; return; }
  let html = '<table class="ply-analysis-table"><thead><tr><th>Ply</th><th>Distinct</th><th>Games</th><th>Avg/Opening</th><th>Most Popular Line</th></tr></thead><tbody>';
  for (let p = 1; p <= 30; p++) {
    const map = new Map(); let totalGamesWithPly = 0;
    games.forEach(g => { if (g.moves && g.moves.length >= p) { totalGamesWithPly++; const key = g.moves.slice(0, p).join(' '); if (!map.has(key)) map.set(key, { count: 0, key }); map.get(key).count++; } });
    const distinct = map.size; const avgGames = distinct ? (totalGamesWithPly / distinct).toFixed(1) : '—'; let topLine = '—'; let topKey = '';
    if (distinct > 0) { const sorted = Array.from(map.values()).sort((a, b) => b.count - a.count); topKey = sorted[0].key; topLine = sorted[0].count + ' ← ' + sorted[0].key.split(' ').map((m, i) => ((i % 2 === 0) ? (Math.floor(i / 2) + 1) + '. ' : '') + m).join(' '); }
    html += `<tr class="clickable" data-ply="${p}" data-line="${topKey}"><td>${p}</td><td>${distinct}</td><td>${totalGamesWithPly}</td><td>${avgGames}</td><td style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;">${topLine}</td></tr>`;
  }
  html += '</tbody></table>'; container.innerHTML = html;
  container.querySelectorAll('tr.clickable').forEach(row => {
    row.addEventListener('click', () => {
      const ply = parseInt(row.dataset.ply, 10);
      const line = row.dataset.line || '';
      const select = document.getElementById('openingsPlySelect');
      if (select) { select.value = ply; window._openingsSortCol = 'games'; window._openingsSortDir = 'desc'; }
      if (window._DATA_SOURCE === 'database' && line) {
        const moves = line.split(' ').filter(Boolean);
        window._LINE_MOVES_SAN = moves;
        window._CURRENT_PLY = Math.min(moves.length, ply);
        window._LINE_SOURCE = 'ply-analysis';
        if (typeof unfreezeCurrentLine === 'function') unfreezeCurrentLine();
        window.batchAutoFollow = true;
        updateBoardFromLine();
      }
      if (typeof window.updateOpeningsList === 'function') window.updateOpeningsList();
    });
  });
}
function updateOpeningsHeaderArrows() {
  const table = document.getElementById('openingsTable'); if (!table) return;
  const headers = table.querySelectorAll('th'); headers.forEach(th => { const col = th.dataset.sort; if (!col) return; let txt = th.textContent.replace(/ [▼▲]/g, ''); if (col === window._openingsSortCol) txt += ' ' + (window._openingsSortDir === 'asc' ? '▲' : '▼'); th.textContent = txt; });
}
function updateGameTableHeaderArrows() {
  const table = document.getElementById('gamesTable'); if (!table) return;
  const headers = table.querySelectorAll('th'); headers.forEach(th => { const col = th.dataset.sort; if (!col) return; let txt = th.textContent.replace(/ [▼▲]/g, ''); if (col === window._gamesSortCol) txt += ' ' + (window._gamesSortDir === 'asc' ? '▲' : '▼'); th.textContent = txt; });
}

/* ===== Statistics & Charts ===== */
function updateStats() {
  const overviewEl = document.getElementById('statsOverview'), resultsEl = document.getElementById('statsResults'), yearsEl = document.getElementById('statsYears'), firstMovesEl = document.getElementById('statsFirstMoves'), playersEl = document.getElementById('statsPlayers');
  const games = window._PARSED_GAMES || [], total = games.length; if (!total) { overviewEl.textContent = 'No games loaded.'; resultsEl.textContent = ''; yearsEl.textContent = ''; firstMovesEl.textContent = ''; playersEl.textContent = ''; updateCharts({}, 0, 0, 0, 0); return; }
  let years = {}, wWins = 0, bWins = 0, draws = 0; let firstMoves = {}, whitePlayers = {}, blackPlayers = {}; let gameLengths = [];
  for (const g of games) { const res = (g.tags.Result || '').trim(); if (res === '1-0') wWins++; else if (res === '0-1') bWins++; else if (res === '1/2-1/2') draws++; const dateTag = g.tags.Date || ''; const yMatch = dateTag.match(/(\d{4})/); if (yMatch) { const y = yMatch[1]; years[y] = (years[y] || 0) + 1; } if (g.moves && g.moves.length) { firstMoves[g.moves[0]] = (firstMoves[g.moves[0]] || 0) + 1; gameLengths.push(g.moves.length); } const w = g.tags.White || '', b = g.tags.Black || ''; if (w) whitePlayers[w] = (whitePlayers[w] || 0) + 1; if (b) blackPlayers[b] = (blackPlayers[b] || 0) + 1; }
  const yearKeys = Object.keys(years).sort(); let yearStr = 'Years: unknown', yearsDetail = ''; if (yearKeys.length) { const minY = yearKeys[0], maxY = yearKeys[yearKeys.length - 1]; yearStr = `Games span: ${minY}–${maxY}`; yearsDetail = 'Games per year: ' + yearKeys.map(y => `${y}: ${years[y]}`).join(', '); }
  const topFirst = Object.entries(firstMoves).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([m, c]) => `${m} (${c})`).join(', ') || '—', topW = Object.entries(whitePlayers).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([p, c]) => `${p} (${c})`).join(', ') || '—', topB = Object.entries(blackPlayers).sort((a, b) => b[1] - a[1]).slice(0, 5).map(([p, c]) => `${p} (${c})`).join(', ') || '—';
  let lengthInfo = ''; if (gameLengths.length) { const sum = gameLengths.reduce((a, b) => a + b, 0), avgMoves = (sum / gameLengths.length / 2).toFixed(1), minMoves = (Math.min(...gameLengths) / 2).toFixed(1), maxMoves = (Math.max(...gameLengths) / 2).toFixed(1); let short = 0, medium = 0, long = 0; gameLengths.forEach(v => { const m = v / 2; if (m < 25) short++; else if (m <= 40) medium++; else long++; }); lengthInfo = `<strong>Typical game length:</strong> ~${avgMoves} moves (shortest ${minMoves}, longest ${maxMoves}).<br>Short games (<25 moves): ${short}, Standard (25–40): ${medium}, Long (>40): ${long}.<br>`; }
  overviewEl.innerHTML = `<strong>Total games:</strong> ${total}<br>${yearStr}<br>${lengthInfo}`;
  const wScorePct = total ? ((wWins + 0.5 * draws) / total * 100).toFixed(1) : '0.0', bScorePct = total ? ((bWins + 0.5 * draws) / total * 100).toFixed(1) : '0.0';
  resultsEl.innerHTML = `<strong>Results breakdown</strong><br>White wins: ${wWins} (${(wWins / total * 100).toFixed(1)}%), Black wins: ${bWins} (${(bWins / total * 100).toFixed(1)}%), Draws: ${draws} (${(draws / total * 100).toFixed(1)}%).<br>White score (overall): ${wScorePct}% • Black score (overall): ${bScorePct}%.`;
  yearsEl.innerHTML = `<strong>Activity by year</strong><br>${yearsDetail || 'No date tags found in PGN.'}`;
  firstMovesEl.innerHTML = `<strong>Most common first moves (overall)</strong><br>${topFirst}<br>`;
  playersEl.innerHTML = `<strong>Your main opponents / players</strong><br><em>As White:</em> ${topW}<br><em>As Black:</em> ${topB}<br>`;
  updateCharts(years, wWins, bWins, draws, total);
}
function updateCharts(years, wWins, bWins, draws, total) {
  const emptyEl = document.getElementById('chartsEmpty'), svgYears = document.getElementById('chartYears'), svgResults = document.getElementById('chartResults');
  if (!total) { emptyEl.textContent = 'No games loaded.'; svgYears.style.display = 'none'; svgResults.style.display = 'none'; return; }
  emptyEl.textContent = ''; const ns = 'http://www.w3.org/2000/svg';
  svgYears.innerHTML = ''; const yearKeys = Object.keys(years).sort();
  if (yearKeys.length) {
    const barW = 32, gap = 10, h = 120, maxCount = Math.max(...yearKeys.map(y => years[y])), w = yearKeys.length * (barW + gap) + gap;
    svgYears.setAttribute('viewBox', `0 0 ${w} ${h}`); svgYears.style.display = 'block';
    yearKeys.forEach((y, i) => {
      const count = years[y]; const barH = maxCount ? (count / maxCount) * 80 : 0; const x = gap + i * (barW + gap), yTop = h - 20 - barH;
      const rect = document.createElementNS(ns, 'rect'); rect.setAttribute('x', x); rect.setAttribute('y', yTop); rect.setAttribute('width', barW); rect.setAttribute('height', barH); rect.setAttribute('rx', 4); rect.setAttribute('fill', 'rgba(56,189,248,0.8)'); svgYears.appendChild(rect);
      const lbl = document.createElementNS(ns, 'text'); lbl.setAttribute('x', x + barW / 2); lbl.setAttribute('y', h - 6); lbl.setAttribute('text-anchor', 'middle'); lbl.setAttribute('font-size', '10'); lbl.setAttribute('fill', '#e5e7eb'); lbl.textContent = y; svgYears.appendChild(lbl);
      const cntLbl = document.createElementNS(ns, 'text'); cntLbl.setAttribute('x', x + barW / 2); cntLbl.setAttribute('y', yTop - 4); cntLbl.setAttribute('text-anchor', 'middle'); cntLbl.setAttribute('font-size', '9'); cntLbl.setAttribute('fill', '#f9fafb'); cntLbl.textContent = count; svgYears.appendChild(cntLbl);
    });
  } else svgYears.style.display = 'none';
  svgResults.innerHTML = ''; const labels = ['White', 'Draw', 'Black'], counts = [wWins, draws, bWins]; const barR = 40, gapR = 18, hR = 120, maxR = Math.max(...counts, 1), wR = labels.length * (barR + gapR) + gapR;
  svgResults.setAttribute('viewBox', `0 0 ${wR} ${hR}`); svgResults.style.display = 'block';
  labels.forEach((lbl, i) => {
    const count = counts[i]; const barH = (count / maxR) * 80; const x = gapR + i * (barR + gapR), yTop = hR - 20 - barH;
    const rect = document.createElementNS(ns, 'rect'); rect.setAttribute('x', x); rect.setAttribute('y', yTop); rect.setAttribute('width', barR); rect.setAttribute('height', barH); rect.setAttribute('rx', 4);
    rect.setAttribute('fill', i === 0 ? 'rgba(34,197,94,0.85)' : i === 1 ? 'rgba(234,179,8,0.85)' : 'rgba(248,113,113,0.85)'); svgResults.appendChild(rect);
    const tLbl = document.createElementNS(ns, 'text'); tLbl.setAttribute('x', x + barR / 2); tLbl.setAttribute('y', hR - 6); tLbl.setAttribute('text-anchor', 'middle'); tLbl.setAttribute('font-size', '10'); tLbl.setAttribute('fill', '#e5e7eb'); tLbl.textContent = lbl; svgResults.appendChild(tLbl);
    const cntLbl = document.createElementNS(ns, 'text'); cntLbl.setAttribute('x', x + barR / 2); cntLbl.setAttribute('y', yTop - 4); cntLbl.setAttribute('text-anchor', 'middle'); cntLbl.setAttribute('font-size', '9'); cntLbl.setAttribute('fill', '#ffffff'); cntLbl.textContent = count; svgResults.appendChild(cntLbl);
  });
}

/* ===== Insights ===== */
function updateInsights() {
  const ratingEl = document.getElementById('insightsRatingAdv'), ecoEl = document.getElementById('insightsECO'), games = window._PARSED_GAMES || [];
  if (!games.length) { ratingEl.textContent = 'No games loaded.'; ecoEl.textContent = ''; return; }
  let wHi = { w1: 0, b1: 0, d: 0 }, bHi = { w1: 0, b1: 0, d: 0 }, eq = { w1: 0, b1: 0, d: 0 };
  for (const g of games) {
    const we = parseInt(g.tags.WhiteElo, 10), be = parseInt(g.tags.BlackElo, 10), res = (g.tags.Result || '').trim();
    let bucket;
    if (isNaN(we) || isNaN(be)) bucket = eq; else if (we > be) bucket = wHi; else if (be > we) bucket = bHi; else bucket = eq;
    if (res === '1-0') bucket.w1++; else if (res === '0-1') bucket.b1++; else if (res === '1/2-1/2') bucket.d++;
  }
  const pct = b => { const t = b.w1 + b.b1 + b.d; return t ? ((b.w1 + 0.5 * b.d) / t * 100).toFixed(1) : '—'; };
  const moveMap = new Map();
  for (const g of games) {
    if (!g.moves || !g.moves.length) continue;
    const move = g.moves[0];
    if (!moveMap.has(move)) moveMap.set(move, { count: 0, score: 0 });
    const obj = moveMap.get(move); obj.count++;
    const r = (g.tags.Result || '').trim();
    if (r === '1-0') obj.score += 1; else if (r === '1/2-1/2') obj.score += 0.5;
  }
  const moveStats = Array.from(moveMap.entries()).map(([m, v]) => ({ move: m, count: v.count, score: v.score / v.count * 100 })).filter(x => x.count >= 5).sort((a, b) => b.score - a.score);
  const bestMove = moveStats[0], worstMove = moveStats[moveStats.length - 1];
  let decisive = 0; games.forEach(g => { const r = (g.tags.Result || '').trim(); if (r === '1-0' || r === '0-1') decisive++; });
  const decisiveness = games.length ? (decisive / games.length * 100).toFixed(1) : 0;
  ratingEl.innerHTML = `<strong>Result by rating advantage</strong><br>White higher: W ${wHi.w1} D ${wHi.d} B ${wHi.b1} → White score: ${pct(wHi)}% (${wHi.w1 + wHi.b1 + wHi.d} games)<br>Black higher: W ${bHi.w1} D ${bHi.d} B ${bHi.b1} → White score: ${pct(bHi)}% (${bHi.w1 + bHi.b1 + bHi.d} games)<br>Equal/unknown: W ${eq.w1} D ${eq.d} B ${eq.b1} (${eq.w1 + eq.b1 + eq.d} games)`;
  ratingEl.innerHTML += `<br><br><strong>First move performance:</strong><br>Best: ${bestMove ? bestMove.move + ' (' + bestMove.score.toFixed(1) + '%)' : '—'}<br>Weakest: ${worstMove ? worstMove.move + ' (' + worstMove.score.toFixed(1) + '%)' : '—'}`;
  ratingEl.innerHTML += `<br><br><strong>Game style:</strong><br>Decisive games: ${decisiveness}%`;
  const ecoMap = new Map();
  for (const g of games) { const eco = (g.tags.ECO || '').trim(); if (eco) ecoMap.set(eco, (ecoMap.get(eco) || 0) + 1); }
  const ecoStats = Array.from(ecoMap.entries()).map(([eco, c]) => ({ eco, c })).sort((a, b) => b.c - a.c);
  const mostPlayed = ecoStats[0];
  if (ecoMap.size > 0) { const sorted = ecoStats.slice(0, 10); ecoEl.innerHTML = `<strong>Top ECO codes:</strong> ${sorted.map(o => `${o.eco} (${o.c})`).join(', ')}`; ecoEl.innerHTML += `<br> Most played ECO: ${mostPlayed ? mostPlayed.eco + ' (' + mostPlayed.c + ' games)' : '—'}`; }
  else ecoEl.innerHTML = '<strong>Top ECO codes:</strong> No ECO tags found.<br> Most played ECO: —';
}

/* ===== Parse & build ===== */
function parseAndBuild(pgnText) {
  if (!pgnText || !pgnText.trim()) return;
  const parts = splitGames(pgnText);
  const parsed = parts.map(p => parsePGN(p));
  const validParts = [], validGames = [];
  parsed.forEach((g, i) => { if (!g.skip) { validGames.push(g); validParts.push(parts[i]); } else console.warn('Skipping game #' + (i + 1) + ': ' + g.reason); });
  if (validParts.length === 0 && parts.length > 0) { alert('No valid standard-start games found.'); return; }
  window._DATA_SOURCE = 'pgn';
  window._PARSED_GAMES = validGames;
  window._PGN_GAMES = validParts;
  window._TREE = buildTreeFromGames(validGames);
  window._CURRENT_NODE = window._TREE;
  window._LINE_SOURCE = 'tree';
  window._openingsSortCol = 'games'; window._openingsSortDir = 'desc';
  window._gamesSortCol = 'index'; window._gamesSortDir = 'asc';
  updateStats(); updateInsights(); rebuildGamesTable(); updateOpeningsList();
  renderTree(); renderNodeDetails(window._TREE);
  window._LINE_MOVES_SAN = []; window._CURRENT_PLY = 0; window._SELECTED_SQUARE = null;
  window._CURRENT_STATE = initialBoardState(); renderBoard(window._CURRENT_STATE);
  renderCurrentLineMoves(); updateMoveInfo(); updateCurrentLineLabel(); clearOpeningsSelection();
  updateGameTableHeaderArrows(); updateOpeningsHeaderArrows();
}

/* ===== DOM events ===== */
document.getElementById('pgnFiles').addEventListener('change', async e => { const files = Array.from(e.target.files); let content = ''; for (const f of files) { try { content += '\n\n' + await readFileAsText(f); } catch (err) { console.error(err); } } content = content.trim(); document.getElementById('rawPgn').value = content; parseAndBuild(content); e.target.value = ''; });
document.getElementById('parsePgnBtn').addEventListener('click', () => { const raw = document.getElementById('rawPgn').value; if (!raw.trim()) { alert('Paste PGN into the text box first.'); return; } parseAndBuild(raw); });
document.getElementById('searchMove').addEventListener('input', debounce(() => { renderTree(); }, 300));
document.getElementById('applyFilter').addEventListener('click', () => { renderTree(); });
document.getElementById('minCount').addEventListener('change', () => { renderTree(); });
document.getElementById('exportJSON').addEventListener('click', () => { if (!window._TREE || !window._PARSED_GAMES) { alert('No tree to export.'); return; } const currentOnly = document.getElementById('exportCurrentBranch').checked; function nodeToObj(node) { const o = { move: node.move, count: node.count, games: node.games.length > 20 ? node.games.slice(0, 20) : node.games, children: [] }; for (const child of node.children.values()) o.children.push(nodeToObj(child)); return o; } const root = currentOnly ? (window._CURRENT_NODE || window._TREE) : window._TREE; const obj = { generated: new Date().toISOString(), totalGames: window._PARSED_GAMES.length, tree: nodeToObj(root) }; download('opening-tree.json', JSON.stringify(obj, null, 2)); });
document.getElementById('downloadPGN').addEventListener('click', () => { if (!window._PGN_GAMES || !window._TREE) { alert('No PGNs loaded.'); return; } const minCount = Number(document.getElementById('minCount').value) || 1, search = document.getElementById('searchMove').value.trim() || null, currentOnly = document.getElementById('exportCurrentBranch').checked; if (currentOnly && !window._CURRENT_NODE) { alert('Select a node in the tree first.'); return; } const idxs = collectGamesForFilter(window._TREE, minCount, search, currentOnly); if (!idxs.length) { alert('No games match the current filter.'); return; } const out = idxs.map(i => window._PGN_GAMES[i]).join('\n\n'); download('filtered.pgn', out); });
document.getElementById('clearBtn').addEventListener('click', () => {
  document.getElementById('rawPgn').value = ''; document.getElementById('sampleGames').value = '';
  document.getElementById('nodeDetails').textContent = 'Select a move in the tree to see stats, line, and FEN.'; document.getElementById('nodeGameList').textContent = 'Games in this node will appear here.'; document.getElementById('nodeResultBuckets').textContent = 'Result buckets (White / Black / Draws) will appear here.';
  document.getElementById('insightsRatingAdv').textContent = 'No games loaded.'; document.getElementById('insightsECO').textContent = '';
  window._TREE = null; window._PARSED_GAMES = null; window._PGN_GAMES = null; window._CURRENT_NODE = null;
  document.getElementById('treeBody').innerHTML = ''; document.getElementById('gamesTableBody').innerHTML = ''; document.getElementById('gamesSummary').textContent = 'No games loaded.';
  document.getElementById('statsOverview').textContent = 'No games loaded.'; document.getElementById('statsResults').textContent = ''; document.getElementById('statsYears').textContent = '';
  document.getElementById('statsFirstMoves').textContent = ''; document.getElementById('statsPlayers').textContent = '';
  document.getElementById('openingsTableBody').innerHTML = ''; document.getElementById('openingsSummary').textContent = 'No openings yet (no games loaded).'; document.getElementById('openingsStats').innerHTML = '';
  document.getElementById('shortOpeningsTableBody').innerHTML = ''; document.getElementById('shortOpeningsSummary').textContent = ''; document.getElementById('shortOpeningsSection').style.display = 'none';
  document.getElementById('plyAnalysisTableContainer').innerHTML = ''; updateCharts({}, 0, 0, 0, 0);
  window._LINE_MOVES_SAN = []; window._CURRENT_PLY = 0; window._LINE_SOURCE = 'tree'; window._WHITE_BOTTOM = true;
  window._CURRENT_STATE = initialBoardState(); window._SELECTED_SQUARE = null;
  renderBoard(window._CURRENT_STATE); renderCurrentLineMoves(); updateMoveInfo(); updateCurrentLineLabel(); renderTree(); clearOpeningsSelection();
  window._DATA_SOURCE = 'database';
  window.batchAutoFollow = false;
  initDatabaseRepertoire();
});
document.getElementById('treeRootBtn').addEventListener('click', () => {
  const ctx = window._CUSTOM_FEN_CONTEXT;

  if (ctx) {
    if (
      window._CURRENT_NODE === ctx.root &&
      window._CURRENT_PLY === 0 &&
      (!Array.isArray(window._LINE_MOVES_SAN) ||
       window._LINE_MOVES_SAN.length === 0)
    ) return;

    invalidateBoardUpdate();
    window._customFenSyncSeq =
      Number.isSafeInteger(window._customFenSyncSeq)
        ? window._customFenSyncSeq + 1
        : 1;

    window._CURRENT_NODE = ctx.root;
    setLineFromNode(ctx.root);
    renderTree();
    updateMoveInfo();
    return;
  }

  if (!window._TREE) return;

  invalidateBoardUpdate();
  window._customFenSyncSeq =
    Number.isSafeInteger(window._customFenSyncSeq)
      ? window._customFenSyncSeq + 1
      : 1;
  if (window._bumpFenLoadSeq) window._bumpFenLoadSeq();

  window._CURRENT_NODE = window._TREE;
  if (window._DATA_SOURCE === 'database') {
    applyDatabaseNode(window._TREE);
  } else {
    setLineFromNode(window._TREE);
  }

  renderTree();
  updateMoveInfo();
});
document.getElementById('treeBackBtn').addEventListener('click', () => {
  if (window._CUSTOM_FEN_CONTEXT) {
    const ctx = window._CUSTOM_FEN_CONTEXT;
    const current = window._CURRENT_NODE;
    const target = (!current || !current.parent)
      ? ctx.root
      : current.parent;

    window._CURRENT_NODE = target;
    setLineFromNode(target);
    renderTree();
    updateMoveInfo();
    return;
  }

  if (!window._TREE) return;
  if (!window._CURRENT_NODE) {
    window._CURRENT_NODE = window._TREE;
  } else if (window._CURRENT_NODE.parent) {
    window._CURRENT_NODE = window._CURRENT_NODE.parent;
  }

  if (window._DATA_SOURCE === 'database') {
    applyDatabaseNode(window._CURRENT_NODE);
  } else {
    setLineFromNode(window._CURRENT_NODE);
  }

  renderTree();
  updateMoveInfo();
});
document.getElementById('firstBtn').addEventListener('click', () => { window._CURRENT_PLY = 0; if (window._DATA_SOURCE === 'database') { unfreezeCurrentLine(); window.batchAutoFollow = true; } else { freezeCurrentLine(); window.batchAutoFollow = false; } updateBoardFromLine(); });
document.getElementById('prevBtn').addEventListener('click', () => { if (window._CURRENT_PLY > 0) window._CURRENT_PLY--; if (window._DATA_SOURCE === 'database') { unfreezeCurrentLine(); window.batchAutoFollow = true; } else { freezeCurrentLine(); window.batchAutoFollow = false; } updateBoardFromLine(); });
document.getElementById('nextBtn').addEventListener('click', () => { if (window._CURRENT_PLY < window._LINE_MOVES_SAN.length) window._CURRENT_PLY++; if (window._DATA_SOURCE === 'database') { unfreezeCurrentLine(); window.batchAutoFollow = true; } else { freezeCurrentLine(); window.batchAutoFollow = false; } updateBoardFromLine(); });
document.getElementById('lastBtn').addEventListener('click', () => { unfreezeCurrentLine(); window.batchAutoFollow = true; window._CURRENT_PLY = window._LINE_MOVES_SAN.length; updateBoardFromLine(); });
document.getElementById('flipBtn').addEventListener('click', () => { window._WHITE_BOTTOM = !window._WHITE_BOTTOM; renderBoard(window._CURRENT_STATE || initialBoardState()); });
document.getElementById('resetBtn').addEventListener('click', () => {
  const ctx = window._CUSTOM_FEN_CONTEXT;

  if (ctx) {
    invalidateBoardUpdate();
    window._customFenSyncSeq =
      Number.isSafeInteger(window._customFenSyncSeq)
        ? window._customFenSyncSeq + 1
        : 1;

    window._LINE_MOVES_SAN = [];
    window._CURRENT_PLY = 0;
    window._CURRENT_NODE = ctx.root;
    window._SELECTED_SQUARE = null;
    window._ENGINE_ARROW_BLUE = null;
    window._ENGINE_ARROW_GREEN = null;
    window._LINE_SOURCE = 'custom-fen';
    window._CURRENT_STATE = cloneState(ctx.baseState);

    document.querySelectorAll('tr.games-row-selected')
      .forEach(el => el.classList.remove('games-row-selected'));
    document.querySelectorAll('.node-game-entry.selected')
      .forEach(el => el.classList.remove('selected'));

    renderBoard(window._CURRENT_STATE);
    renderCurrentLineMoves();
    updateMoveInfo();
    updateCurrentLineLabel();
    renderTree();
    renderNodeDetails(ctx.root);
    clearOpeningsSelection();

    if (typeof onPositionChanged === 'function') {
      onPositionChanged(ctx.fen);
    } else if (typeof runUnifiedAnalysis === 'function') {
      runUnifiedAnalysis(ctx.fen);
    }
    return;
  }

  invalidateBoardUpdate();
  window._customFenSyncSeq =
    Number.isSafeInteger(window._customFenSyncSeq)
      ? window._customFenSyncSeq + 1
      : 1;
  if (window._bumpFenLoadSeq) window._bumpFenLoadSeq();

  window._LINE_MOVES_SAN = [];
  window._CURRENT_PLY = 0;
  window._CURRENT_NODE = window._TREE;
  window._SELECTED_SQUARE = null;

  document.querySelectorAll('tr.games-row-selected')
    .forEach(el => el.classList.remove('games-row-selected'));
  document.querySelectorAll('.node-game-entry.selected')
    .forEach(el => el.classList.remove('selected'));

  window._CURRENT_STATE = initialBoardState();
  renderBoard(window._CURRENT_STATE);
  renderCurrentLineMoves();
  updateMoveInfo();
  updateCurrentLineLabel();

  if (window._TREE) {
    renderTree();
    renderNodeDetails(window._CURRENT_NODE);
  }

  clearOpeningsSelection();
});
document.getElementById('toggleArrowsBtn').addEventListener('click', () => { window._ARROWS_ENABLED = !window._ARROWS_ENABLED; document.getElementById('toggleArrowsBtn').textContent = window._ARROWS_ENABLED ? 'Hide arrows' : 'Show arrows'; renderBoard(window._CURRENT_STATE); });
document.getElementById('copyFenBtn').addEventListener('click', () => { const fen = stateToFEN(window._CURRENT_STATE); navigator.clipboard.writeText(fen).then(() => alert('FEN copied to clipboard')).catch(() => prompt('FEN:', fen)); });
document.getElementById('openingsPlySelect').addEventListener('change', () => { window._openingsSortCol = 'games'; window._openingsSortDir = 'desc'; updateOpeningsList(); });
document.getElementById('copyOpeningLineBtn').addEventListener('click', () => { const line = window._SELECTED_OPENING_LINE; if (line) { navigator.clipboard.writeText(line).then(() => { const btn = document.getElementById('copyOpeningLineBtn'); const orig = btn.textContent; btn.textContent = 'Copied!'; btn.disabled = true; setTimeout(() => { btn.textContent = orig; btn.disabled = false; }, 1500); }).catch(() => { prompt('Copy this line:', line); }); } });
document.getElementById('openingsTable').addEventListener('click', e => { const th = e.target.closest('th'); if (!th || !th.dataset.sort) return; sortOpenings(th.dataset.sort); });
document.getElementById('gamesTable').addEventListener('click', e => { const th = e.target.closest('th'); if (!th || !th.dataset.sort) return; sortGames(th.dataset.sort); });

/* ===== Startup ===== */
try {
  initPlyDropdown();
  window._CURRENT_STATE = initialBoardState();
  renderBoard(window._CURRENT_STATE);
  renderCurrentLineMoves();
  updateMoveInfo();
  updateCurrentLineLabel();
} catch (err) { console.error('Startup error:', err); document.getElementById('board').innerHTML = '<div class="small-muted">Board failed to load. Check console.</div>'; }


function applyDatabaseNode(node) {
  if (!node) return;
  window._LINE_MOVES_SAN = getPathFromNode(node).slice();
  window._CURRENT_PLY = window._LINE_MOVES_SAN.length;
  window._LINE_SOURCE = 'tree';
  window._CURRENT_NODE = node;
  if (typeof unfreezeCurrentLine === 'function') unfreezeCurrentLine();
  window.batchAutoFollow = true;
  clearOpeningsSelection();
  updateBoardFromLine();
}

/* ===== Phase-1 database repertoire startup ===== */
async function initDatabaseRepertoire() {
  window._DATA_SOURCE = 'database';
  window.batchAutoFollow = false;
  try {
    const startState = initialBoardState();
    const root = makeNode(null);
    root.uci = null;
    root.fen = stateToFEN(startState);
    root.scores = { engine: null, neural: null };
    root.state = cloneState(startState);
    root.serverLoaded = false;
    root.serverLoading = false;

    await loadServerChildren(root);

    window._TREE = root;
    window._CURRENT_NODE = root;
    renderTree();
    renderBoard(window._CURRENT_STATE);
    updateCurrentLineLabel();
  } catch (err) {
    console.warn('Database repertoire load failed:', err);
  }
}

initDatabaseRepertoire();

