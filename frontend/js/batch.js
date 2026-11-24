(function() {
  function debugMsg(msg) {
    return;  // silenced: debug bar covered the page
    let d = document.getElementById("debugBox");
    if (!d) {
      d = document.createElement("div");
      d.id = "debugBox";
      d.style.cssText = "position:fixed;top:0;left:0;right:0;background:#000;color:#0f0;padding:8px;z-index:99999;font-size:14px;white-space:pre-wrap;";
      document.body.appendChild(d);
    }
    d.textContent = msg;
  }

  const toggleBtn = document.getElementById('modeToggleBtn');
  const pgnPanel = document.getElementById('test-pgn-panel');
  const pgnContent = document.getElementById('test-pgn-content');
  const batchPanel = document.getElementById('test-batch-panel');
  const startBtn = document.getElementById('start-batch-btn');
  const stopBtn = document.getElementById('stop-batch-btn');
window.batchAutoFollow = true;
let batchTotalMoves = 0;
  const numGamesInput = document.getElementById('batch-num-games');
  const depthInput = document.getElementById('batch-depth');
  const opponentSelect = document.getElementById('batch-opponent');

  const _fenInput = document.getElementById('test-fen-input');
  const _fenBtn = document.getElementById('test-load-fen-btn');
  const _fenErr = document.getElementById('test-fen-error');

  let _fenLoadSeq = 0;
  window._bumpFenLoadSeq = function() {
    _fenLoadSeq = Number.isSafeInteger(_fenLoadSeq)
      ? _fenLoadSeq + 1
      : 1;
    return _fenLoadSeq;
  };

  function _validateFenParts(parts) {
    if (parts.length !== 6) return 'FEN must have exactly six fields.';

    const rows = parts[0].split('/');
    if (rows.length !== 8) return 'Piece placement must have eight ranks.';

    let whiteKing = 0;
    let blackKing = 0;
    const board = [];

    for (let r = 0; r < 8; r++) {
      const cells = [];
      let count = 0;
      let previousDigit = false;

      for (let i = 0; i < rows[r].length; i++) {
        const ch = rows[r][i];

        if (ch >= '1' && ch <= '8') {
          if (previousDigit) {
            return 'Consecutive empty-square digits in rank ' + (8 - r) + '.';
          }
          const n = parseInt(ch, 10);
          for (let j = 0; j < n; j++) cells.push(null);
          count += n;
          previousDigit = true;
        } else if ('PNBRQKpnbrqk'.includes(ch)) {
          if ((ch === 'P' || ch === 'p') && (r === 0 || r === 7)) {
            return 'A pawn cannot be on rank 1 or rank 8.';
          }

          cells.push(ch);
          count += 1;
          previousDigit = false;

          if (ch === 'K') whiteKing++;
          if (ch === 'k') blackKing++;
        } else {
          return 'Invalid piece character: ' + ch;
        }
      }

      if (count !== 8) {
        return 'Rank ' + (8 - r) + ' must contain exactly eight squares.';
      }

      board.push(cells);
    }

    if (whiteKing !== 1) return 'FEN must contain exactly one white king.';
    if (blackKing !== 1) return 'FEN must contain exactly one black king.';

    const turn = parts[1];
    if (turn !== 'w' && turn !== 'b') {
      return 'Side to move must be w or b.';
    }

    const castling = parts[2];
    if (castling !== '-') {
      if (!/^(K?Q?k?q?)$/.test(castling) || castling.length === 0) {
        return 'Invalid castling rights or order.';
      }
      if (castling.includes('K') &&
          (board[7][4] !== 'K' || board[7][7] !== 'R')) {
        return 'Castling K requires the white king on e1 and rook on h1.';
      }
      if (castling.includes('Q') &&
          (board[7][4] !== 'K' || board[7][0] !== 'R')) {
        return 'Castling Q requires the white king on e1 and rook on a1.';
      }
      if (castling.includes('k') &&
          (board[0][4] !== 'k' || board[0][7] !== 'r')) {
        return 'Castling k requires the black king on e8 and rook on h8.';
      }
      if (castling.includes('q') &&
          (board[0][4] !== 'k' || board[0][0] !== 'r')) {
        return 'Castling q requires the black king on e8 and rook on a8.';
      }
    }

    const ep = parts[3];
    if (ep !== '-') {
      if (!/^[a-h][36]$/.test(ep)) {
        return 'En passant square must be a file a-h on rank 3 or 6.';
      }

      const epRank = parseInt(ep[1], 10);
      const epFile = ep.charCodeAt(0) - 97;
      const epRow = 8 - epRank;

      if (turn === 'w' && epRank !== 6) {
        return 'White to move requires an en passant target on rank 6.';
      }
      if (turn === 'b' && epRank !== 3) {
        return 'Black to move requires an en passant target on rank 3.';
      }
      if (board[epRow][epFile] !== null) {
        return 'En passant target square must be empty.';
      }

      const pawnRow = turn === 'w' ? epRow + 1 : epRow - 1;
      const expectedPawn = turn === 'w' ? 'p' : 'P';
      if (board[pawnRow][epFile] !== expectedPawn) {
        return 'En passant target requires the opposing pawn behind it.';
      }
    }

    if (!/^\d+$/.test(parts[4])) {
      return 'Halfmove clock must be a non-negative integer.';
    }
    const halfmove = Number(parts[4]);
    if (!Number.isSafeInteger(halfmove) || halfmove < 0) {
      return 'Halfmove clock is out of range.';
    }

    if (!/^\d+$/.test(parts[5])) {
      return 'Fullmove number must be a positive integer.';
    }
    const fullmove = Number(parts[5]);
    if (!Number.isSafeInteger(fullmove) || fullmove < 1) {
      return 'Fullmove number is out of range.';
    }

    return null;
  }

  function _loadFenFromInput() {
    if (!_fenInput || !_fenErr) return;

    if (pollMode !== 'test') {
      _fenErr.textContent = 'Switch to Test mode to load a custom FEN.';
      return;
    }

    if (_fenBtn && _fenBtn.disabled) return;

    const raw = String(_fenInput.value || '').trim();
    if (!raw) {
      _fenErr.textContent = 'Enter a FEN.';
      return;
    }

    const normalized = raw.split(/\s+/).join(' ');
    const parts = normalized.split(' ');
    const validationError = _validateFenParts(parts);

    if (validationError) {
      _fenErr.textContent = validationError;
      return;
    }

    let parsed;
    try {
      parsed = stateFromFEN(normalized);
    } catch (err) {
      _fenErr.textContent = 'FEN parse error: ' + err.message;
      return;
    }

    const seq = ++_fenLoadSeq;
    const boardSeq = window.invalidateBoardUpdate();

    window._customFenSyncSeq =
      Number.isSafeInteger(window._customFenSyncSeq)
        ? window._customFenSyncSeq + 1
        : 1;

    const canonicalFen = stateToFEN(parsed);

    window._LINE_MOVES_SAN = [];
    window._CURRENT_PLY = 0;
    window._SELECTED_SQUARE = null;
    window._ENGINE_ARROW_BLUE = null;
    window._ENGINE_ARROW_GREEN = null;
    window._LINE_SOURCE = 'custom-fen';
    window._CURRENT_STATE = parsed;
    window.batchAutoFollow = false;

    const syntheticRoot = {
      move: null,
      uci: null,
      key: 'custom-fen-root',
      fen: canonicalFen,
      state: parsed,
      children: new Map(),
      games: [],
      count: 0,
      stats: { w: 0, b: 0, d: 0 },
      parent: null,
      serverNode: true,
      serverLoaded: false,
      serverLoading: false,
      serverError: false,
      eloSum: 0,
      eloCount: 0,
      scores: { engine: null, neural: null }
    };

    const ctx = {
      root: syntheticRoot,
      baseState: cloneState(parsed),
      fen: canonicalFen,
      lookupError: false
    };

    window._CUSTOM_FEN_CONTEXT = ctx;
    window._CURRENT_NODE = syntheticRoot;

    if (typeof renderBoard === 'function') renderBoard(parsed);
    if (typeof renderCurrentLineMoves === 'function') renderCurrentLineMoves();
    if (typeof updateMoveInfo === 'function') updateMoveInfo();
    if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
    if (typeof renderTree === 'function') renderTree();
    if (typeof renderNodeDetails === 'function') renderNodeDetails(syntheticRoot);

    if (typeof window.onPositionChanged === 'function') {
      window.onPositionChanged(canonicalFen);
    } else if (typeof window.runUnifiedAnalysis === 'function') {
      window.runUnifiedAnalysis(canonicalFen);
    }

    loadServerChildren(syntheticRoot).then(function(success) {
      if (seq !== _fenLoadSeq) return;
      if (window._CUSTOM_FEN_CONTEXT !== ctx) return;

      if (typeof renderTree === 'function') renderTree();

      const stillOwnsBoard =
        typeof window._isBoardUpdateCurrent === 'function' &&
        window._isBoardUpdateCurrent(boardSeq);

      if (stillOwnsBoard && window._CURRENT_NODE === syntheticRoot &&
          typeof renderNodeDetails === 'function') {
        renderNodeDetails(syntheticRoot);
      }

      if (stillOwnsBoard && typeof renderBoard === 'function' &&
          window._CURRENT_STATE) {
        renderBoard(window._CURRENT_STATE);
      }

      if (!success) {
        ctx.lookupError = true;
        if (_fenErr) {
          _fenErr.textContent =
            'Tree lookup failed; board and engine analysis are still available.';
        }
      } else if (_fenErr) {
        _fenErr.textContent = '';
      }
    }).catch(function(err) {
      if (seq !== _fenLoadSeq ||
          window._CUSTOM_FEN_CONTEXT !== ctx) return;
      syntheticRoot.serverLoaded = false;
      syntheticRoot.serverLoading = false;
      syntheticRoot.serverError = true;
      ctx.lookupError = true;
      if (_fenErr) {
        _fenErr.textContent =
          'Tree lookup failed; board and engine analysis are still available.';
      }
      console.warn('Custom FEN tree request failed:', err);
    });
  }

  if (_fenBtn) {
    _fenBtn.addEventListener('click', _loadFenFromInput);
  }

  if (_fenInput) {
    _fenInput.addEventListener('keydown', function(event) {
      if (event.key === 'Enter') {
        event.preventDefault();
        _loadFenFromInput();
      }
    });
  }
  const humanBlackCheckbox = document.getElementById('human-black');
  const progressDiv = document.getElementById('test-batch-progress');
  const statsDiv = document.getElementById('test-batch-stats');
  const rawPgn = document.getElementById('rawPgn');

  let pollMode = 'live';
  let pollInterval = null, batchPollInterval = null, batchLoaded = false;
  let humanGameActive = false;
  window.batchAutoFollow = true;
  
  // ---- Override onSquareClick for human mode ----
  const origOnSquareClick = window.onSquareClick;
  window.onSquareClick = function(r, c) {
    if (!humanGameActive) {
      if (origOnSquareClick) origOnSquareClick(r, c);
      return;
    }
    const state = window._CURRENT_STATE || window.initialBoardState();
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
    const cand = moves.filter(m => m.fromR === sel.r && m.fromC === sel.c && m.toR === r && m.toC === c);
    if (!cand.length) {
      window._SELECTED_SQUARE = null;
      renderBoard(state);
      return;
    }
    const legalCand = cand.filter(mv => {
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
      const choice = prompt('Promote pawn to? Type: Q=Queen, R=Rook, B=Bishop, N=Knight', 'Q');
      const chosen = (choice || 'Q').toUpperCase();
      mv = legalCand.find(m => m.promotion === chosen) || legalCand[0];
    }
    const uci = String.fromCharCode(97 + mv.fromC) + (8 - mv.fromR) +
                String.fromCharCode(97 + mv.toC) + (8 - mv.toR) +
                (mv.promotion || '');
    const fenBefore = stateToFEN(state);
    window._SELECTED_SQUARE = null;

    fetch('/api/human_move', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ uci: uci, fen: fenBefore })
    })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        alert('Illegal move: ' + data.error);
        renderBoard(state);
      } else {
        if (data.current_fen) {
          window._CURRENT_STATE = stateFromFEN(data.current_fen);
          renderBoard(window._CURRENT_STATE);
        }
        if (data.pgn) {
          pgnContent.textContent = data.pgn;
        }
        if (data.result) {
          progressDiv.innerHTML = 'Game ended: ' + data.result;
          humanGameActive = false;
        }
      }
    })
    .catch(err => {
      console.error('Human move failed:', err);
      renderBoard(state);
    });
  };

  function stateFromFEN(fen) {
    const parts = fen.trim().split(' ');
    if (parts.length < 4) return window.initialBoardState();
    const board = Array.from({length:8}, () => Array(8).fill(null));
    const rows = parts[0].split('/');
    for (let r = 0; r < 8; r++) {
      let c = 0;
      for (const ch of rows[r]) {
        if (ch >= '1' && ch <= '8') { c += parseInt(ch, 10); }
        else {
          const map = { P:'wP',N:'wN',B:'wB',R:'wR',Q:'wQ',K:'wK',
                       p:'bP',n:'bN',b:'bB',r:'bR',q:'bQ',k:'bK' };
          board[r][c] = map[ch] || null; c++;
        }
      }
    }
    const turn = parts[1] === 'w' ? 'w' : 'b';
    const castling = { wK: parts[2].includes('K'), wQ: parts[2].includes('Q'),
                       bK: parts[2].includes('k'), bQ: parts[2].includes('q') };
    let enPassant = null;
    if (parts[3] !== '-') {
      const file = parts[3].charCodeAt(0) - 97;
      const rank = 8 - parseInt(parts[3][1], 10);
      enPassant = [rank, file];
    }
    const halfmove = parts.length >= 5 ? parseInt(parts[4], 10) || 0 : 0;
    const fullmove = parts.length >= 6 ? parseInt(parts[5], 10) || 1 : 1;
    return { board, turn, castling, enPassant, lastMove: null,
             halfmoveClock: halfmove, fullmoveNumber: fullmove };
  }

  function startLivePolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => {
      if (window._DATA_SOURCE === 'database') return;
      fetch('/api/current_fen')
        .then(r => r.json())
        .then(data => { if (window._DATA_SOURCE === 'database') return; if (data.current_fen && window.batchAutoFollow) { window._CURRENT_STATE = stateFromFEN(data.current_fen); renderBoard(window._CURRENT_STATE); } });
    }, 500);
  }
  function stopLivePolling() { if (pollInterval) { clearInterval(pollInterval); pollInterval = null; } }

  function syncTestPositionFromStatus(data) {
    if (!data || !Array.isArray(data.moves)) return false;

    if (window._CUSTOM_FEN_CONTEXT) return false;

    const incoming = data.moves;
    // Preserve manually entered moves when no test game is running.
    if (!data.running &&
        (incoming.length === 0 || window._LINE_SOURCE === 'manual')) {
      return false;
    }

    const current = Array.isArray(window._LINE_MOVES_SAN)
      ? window._LINE_MOVES_SAN : [];

    let lineChanged = current.length !== incoming.length;
    if (!lineChanged) {
      for (let i = 0; i < incoming.length; i++) {
        if (current[i] !== incoming[i]) {
          lineChanged = true;
          break;
        }
      }
    }

    const follow = !!window.batchAutoFollow;
    let stateChanged = false;

    if (follow && data.current_fen) {
      let oldFen = '';
      try {
        if (window._CURRENT_STATE) {
          oldFen = stateToFEN(window._CURRENT_STATE);
        }
      } catch (_) {}

      if (oldFen !== data.current_fen) {
        window._CURRENT_STATE = stateFromFEN(data.current_fen);
        stateChanged = true;
      }
    } else if (
      follow && data.running && incoming.length === 0 && lineChanged
    ) {
      // A newly started batch may briefly report an empty FEN.
      window._CURRENT_STATE = initialBoardState();
      stateChanged = true;
    }

    if (!lineChanged && !stateChanged) return false;

    if (lineChanged) {
      window._LINE_MOVES_SAN = incoming.slice();
      batchTotalMoves = incoming.length;

      if (follow) {
        const reportedPly = Number(data.current_ply);
        window._CURRENT_PLY =
          Number.isInteger(reportedPly) && reportedPly >= 0
            ? Math.min(reportedPly, incoming.length)
            : incoming.length;
      } else {
        const oldPly = Math.max(0, Number(window._CURRENT_PLY) || 0);
        window._CURRENT_PLY = Math.min(oldPly, incoming.length);
      }

      // Synchronise the tree without invoking the engine-analysis path.
      if (typeof syncCurrentNodeWithLine === 'function') {
        syncCurrentNodeWithLine();
      }
      if (typeof renderCurrentLineMoves === 'function') {
        renderCurrentLineMoves();
      }
      if (typeof updateMoveInfo === 'function') updateMoveInfo();
      if (typeof updateCurrentLineLabel === 'function') {
        updateCurrentLineLabel();
      }
    }

    // Repaint only when the actual position or SAN history changed.
    // renderBoard redraws arrows but does not start engine analysis.
    if (lineChanged || stateChanged) {
      if (typeof renderBoard === 'function') {
        renderBoard(window._CURRENT_STATE || initialBoardState());
      }
    }

    return true;
  }

  function startBatchPolling() {
    if (batchPollInterval) clearInterval(batchPollInterval);
    batchLoaded = false;
    humanGameActive = false;
    window.batchAutoFollow = true;
    batchPollInterval = setInterval(() => {
      fetch('/api/test_batch_status')
        .then(r => r.json())
        .then(data => {
          if (window._DATA_SOURCE === 'database') return;

          if (_fenBtn) {
            _fenBtn.disabled = !!data.running;
            _fenBtn.title = data.running
              ? 'Stop the batch before loading a FEN'
              : '';
          }
          if (_fenInput) {
            _fenInput.disabled = !!data.running;
          }

          if (data.opponent === 'human') {
            humanGameActive = data.running;
            syncTestPositionFromStatus(data);
            if (data.pgn) {
              pgnContent.textContent = data.pgn;
              pgnPanel.style.display = 'block';
            }
            const side = data.human_side || 'white';
            progressDiv.innerHTML = data.running ? ('Playing as ' + side + (data.human_move_pending ? ' (your turn)' : '')) : 'Game finished';
            startBtn.disabled = data.running;
            stopBtn.disabled = !data.running;
            return;
          }
          if (data.current_pgn) { pgnContent.textContent = data.current_pgn; pgnPanel.style.display = 'block'; }
          syncTestPositionFromStatus(data);
          if (data.running) {
            progressDiv.innerHTML = `Game <strong>${data.games_completed + 1}</strong> of ${data.num_games} – Engine: ${data.engine_color === 'white' ? 'White' : 'Black'}`; if (data.current_pgn) { pgnContent.textContent = data.current_pgn; pgnPanel.style.display = 'block'; }
            statsDiv.innerHTML = `Engine wins: ${data.wins} | Opponent wins: ${data.losses} | Draws: ${data.draws}`;
            startBtn.disabled = true; stopBtn.disabled = false;
        window.batchAutoFollow = true; if (data.current_pgn) { pgnContent.textContent = data.current_pgn; pgnPanel.style.display = 'block'; }
          } else {
            if (data.num_games > 0) {
              progressDiv.innerHTML = `Batch completed: ${data.num_games} games.`;
              statsDiv.innerHTML = `Engine wins: ${data.wins} | Opponent wins: ${data.losses} | Draws: ${data.draws}`;
              if (!batchLoaded && data.all_pgns_count > 0) {
                batchLoaded = true;
                fetch('/api/test_batch_games')
                  .then(r => r.json())
                  .then(res => { if (res.pgn) { rawPgn.value = res.pgn; if (typeof parseAndBuild === 'function') parseAndBuild(res.pgn); } });
              }
            } else { progressDiv.innerHTML = ''; statsDiv.innerHTML = ''; }
            if (data.current_pgn) { pgnContent.textContent = data.current_pgn; pgnPanel.style.display = 'block'; } startBtn.disabled = false; stopBtn.disabled = true;
          if (window.sseSource) { window.sseSource.close(); window.sseSource = null; }
          }
        });
    }, 500);
  }
  function stopBatchPolling() {
    if (batchPollInterval) { clearInterval(batchPollInterval); batchPollInterval = null; }
    humanGameActive = false;
  }

  const _dbPanels = [
    document.getElementById('gamesTable')?.closest('.panel'),
    document.getElementById('openingsTable')?.closest('.panel'),
    document.getElementById('insightsRatingAdv')?.closest('.panel'),
    document.getElementById('provenanceAudit')?.closest('.panel'),
    document.getElementById('exportJSON')?.closest('.panel')
  ].filter(Boolean);

  let _savedLiveState = null;
  let _everEnteredTest = false;

  function setDbPanelsInactive(flag) {
    _dbPanels.forEach(p => p.classList.toggle('inactive', flag));
  }

  function snapshotLiveState() {
    return {
      dataSource: window._DATA_SOURCE,
      tree: window._TREE,
      currentNode: window._CURRENT_NODE,
      lineMoves: Array.isArray(window._LINE_MOVES_SAN) ? window._LINE_MOVES_SAN.slice() : [],
      currentPly: window._CURRENT_PLY,
      currentState: window._CURRENT_STATE,
      selectedSquare: window._SELECTED_SQUARE,
      lineSource: window._LINE_SOURCE,
      parsedGames: window._PARSED_GAMES,
      pgnGames: window._PGN_GAMES,
      autoFollow: window.batchAutoFollow
    };
  }

  function restoreLiveState(s) {
    if (!s) return;
    window._DATA_SOURCE = s.dataSource;
    window._TREE = s.tree;
    window._CURRENT_NODE = s.currentNode;
    window._LINE_MOVES_SAN = s.lineMoves;
    window._CURRENT_PLY = s.currentPly;
    window._CURRENT_STATE = s.currentState;
    window._SELECTED_SQUARE = s.selectedSquare;
    window._LINE_SOURCE = s.lineSource;
    window._PARSED_GAMES = s.parsedGames;
    window._PGN_GAMES = s.pgnGames;
    window.batchAutoFollow = s.autoFollow;
  }

  function renderBoardState() {
    if (window._CURRENT_STATE && typeof renderBoard === 'function') renderBoard(window._CURRENT_STATE);
    if (typeof renderCurrentLineMoves === 'function') renderCurrentLineMoves();
    if (typeof updateMoveInfo === 'function') updateMoveInfo();
    if (typeof updateCurrentLineLabel === 'function') updateCurrentLineLabel();
  }

  function renderDbPanelsFromState() {
    if (typeof rebuildGamesTable === 'function') rebuildGamesTable();
    if (typeof updateStats === 'function') updateStats();
    if (typeof updateInsights === 'function') updateInsights();
    if (typeof updateOpeningsList === 'function') updateOpeningsList();
  }

  function setMode(mode) {
    // debugMsg('SETMODE: ' + mode);  // removed: fixed bar covered the page
    console.log('setMode called with:', mode);

    if (window.invalidateBoardUpdate) {
      window.invalidateBoardUpdate();
    }
    if (window._bumpFenLoadSeq) {
      window._bumpFenLoadSeq();
    }
    if (window._CUSTOM_FEN_CONTEXT) {
      window._CUSTOM_FEN_CONTEXT = null;
      window._customFenSyncSeq =
        Number.isSafeInteger(window._customFenSyncSeq)
          ? window._customFenSyncSeq + 1
          : 1;
    }

    pollMode = mode;
    toggleBtn.textContent = 'Mode: ' + (mode === 'live' ? 'Live' : 'Test');

    if (mode === 'test') {
      if (!_everEnteredTest) {
        _savedLiveState = snapshotLiveState();
        _everEnteredTest = true;
      }
      window._RUNTIME_MODE = 'test';
      window._DATA_SOURCE = 'test';
      window._LINE_MOVES_SAN = [];
      window._CURRENT_PLY = 0;
      window._CURRENT_NODE = null;
      window._CURRENT_STATE = (typeof initialBoardState === 'function') ? initialBoardState() : null;
      window.batchAutoFollow = true;
      renderBoardState();
      setDbPanelsInactive(true);
      pgnPanel.style.display = 'block';
      batchPanel.style.display = 'block';
      stopLivePolling();
      startBatchPolling();
    } else {
      if (_everEnteredTest && _savedLiveState) {
        restoreLiveState(_savedLiveState);
        _savedLiveState = null;
        _everEnteredTest = false;
      }
      window._RUNTIME_MODE = 'live';
      setDbPanelsInactive(false);
      pgnPanel.style.display = 'none';
      batchPanel.style.display = 'none';
      stopBatchPolling();
      if (window.sseSource) {
        window.sseSource.close();
        window.sseSource = null;
      }
      startLivePolling();
      renderBoardState();
      if (typeof renderTree === 'function') renderTree();
      if (typeof renderNodeDetails === 'function') {
        renderNodeDetails(window._CURRENT_NODE || window._TREE);
      }
      renderDbPanelsFromState();
    }
  }

  toggleBtn.addEventListener('click', () => { setMode(pollMode === 'live' ? 'test' : 'live'); });

  startBtn.addEventListener('click', () => {
    if (window.invalidateBoardUpdate) {
      window.invalidateBoardUpdate();
    }

    if (_fenBtn) _fenBtn.disabled = true;
    if (_fenInput) _fenInput.disabled = true;

    if (window._CUSTOM_FEN_CONTEXT) {
      if (window._bumpFenLoadSeq) window._bumpFenLoadSeq();

      window._customFenSyncSeq =
        Number.isSafeInteger(window._customFenSyncSeq)
          ? window._customFenSyncSeq + 1
          : 1;

      window._CUSTOM_FEN_CONTEXT = null;
      window._LINE_MOVES_SAN = [];
      window._CURRENT_PLY = 0;
      window._CURRENT_NODE = null;
      window._CURRENT_STATE =
        (typeof initialBoardState === 'function')
          ? initialBoardState()
          : null;
      window._LINE_SOURCE = 'batch';
      window._SELECTED_SQUARE = null;
      window._ENGINE_ARROW_BLUE = null;
      window._ENGINE_ARROW_GREEN = null;
      window.batchAutoFollow = true;

      if (window._CURRENT_STATE && typeof renderBoard === 'function') {
        renderBoard(window._CURRENT_STATE);
      }
      if (typeof renderCurrentLineMoves === 'function') {
        renderCurrentLineMoves();
      }
      if (typeof updateMoveInfo === 'function') updateMoveInfo();
      if (typeof updateCurrentLineLabel === 'function') {
        updateCurrentLineLabel();
      }
      if (typeof renderTree === 'function') renderTree();
      if (typeof renderNodeDetails === 'function') {
        renderNodeDetails(null);
      }
      if (typeof clearOpeningsSelection === 'function') {
        clearOpeningsSelection();
      }
    }

    const opponent = opponentSelect.value;
    const numGames = opponent === 'human' ? 1 : (parseInt(numGamesInput.value) || 10);
    const depth = parseInt(depthInput.value) || 4;
    const humanColor = humanBlackCheckbox && humanBlackCheckbox.checked ? 'black' : 'white';
    const body = {num_games: numGames, depth: depth, opponent: opponent};
    if (opponent === 'human') body.human_color = humanColor;
    // ----- Live Game Mode (1 game, Live toggle) -----
    if (pollMode === "live" && numGames === 1) {
      const opponent = opponentSelect.value;
      let white = "engine", black = "engine";
      if (opponent === "random") black = "random";
      else if (opponent === "human") black = "human";
      else if (opponent === "self") { white = "engine"; black = "engine"; }
      fetch("/api/start_live_game", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ white, black })
      }).then(r => r.json()).then(data => {
        if (data.status === "started") {
          console.log("Live game started");
          // The existing polling (which fetches /api/current_fen) will update the board.
        }
      });
      return;
    }
    // Use SSE for live single-game updates
    if (pollMode === "test" && numGames === 1) {
      if (window.sseSource) window.sseSource.close();
      window.sseSource = new EventSource("/api/stream_game");
      window.sseSource.onmessage = function(event) {
        if (window._DATA_SOURCE === 'database') return;
        const fen = event.data;
        if (window.batchAutoFollow) {
          window._CURRENT_STATE = stateFromFEN(fen);
          renderBoard(window._CURRENT_STATE);
        }
      };
    }
    fetch('/api/start_test_batch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)
    }).then(r => r.json()).then(data => { if (data.error) alert(data.error); });
  });

  stopBtn.addEventListener('click', () => {
    Promise.all([
      fetch('/api/stop_test_batch').then(r => r.json()).catch(() => ({})),
      fetch('/api/stop_live_game', { method: 'POST' }).then(r => r.json()).catch(() => ({}))
    ]).then(() => { stopBtn.disabled = true; });
  });

  const loadBtn = document.createElement('button');
  loadBtn.textContent = 'Load batch games into tree';
  loadBtn.className = 'secondary';
  loadBtn.style.marginTop = '8px';
  loadBtn.addEventListener('click', () => {
    fetch('/api/test_batch_games').then(r => r.json()).then(res => {
      if (res.pgn) { rawPgn.value = res.pgn; if (typeof parseAndBuild === 'function') parseAndBuild(res.pgn); }
    });
  });
  batchPanel.appendChild(loadBtn);

  


// ========== UNIFIED ANALYSIS (My Engine + Stockfish) ==========
let analysisPanelHidden = false;

setMode('live');

// ---- Auto-follow toggle via navigation buttons ----
document.addEventListener('DOMContentLoaded', function() {
    function afterNav() {
        if (window._DATA_SOURCE === 'database') return;
        if (batchTotalMoves > 0) {
            // If user manually navigated to a move before the latest, pause auto-follow
            if (window._CURRENT_PLY < batchTotalMoves) {
                window.batchAutoFollow = false;
            } else {
                // If they're at the latest move, resume auto-follow
                window.batchAutoFollow = true;
            }
        }
    }
    // Hook into the buttons after they've been defined
    const firstBtn = document.getElementById('firstBtn');
    const prevBtn  = document.getElementById('prevBtn');
    const nextBtn  = document.getElementById('nextBtn');
    const lastBtn  = document.getElementById('lastBtn');

    if (firstBtn) firstBtn.addEventListener('click', afterNav);
    if (prevBtn)  prevBtn.addEventListener('click', afterNav);
    if (nextBtn)  nextBtn.addEventListener('click', afterNav);
    if (lastBtn)  lastBtn.addEventListener('click', afterNav);
});

// Expose stateFromFEN for analysis.js (uciToSan). The IIFE
// scope hides it from other scripts loaded after batch.js,
// which made uciToSan throw ReferenceError on its first line
// and fall back to raw UCI in both the deep and Stockfish panels.
window.stateFromFEN = stateFromFEN;

})();
