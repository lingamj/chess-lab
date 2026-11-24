// Unified Analysis: quick path (My Engine + Stockfish) and deep My Engine job.
(function() {
  // Quick-path state
  var sfCache = new Map();
  var SF_CACHE_MAX = 200;
  var sfRunning = false, engineRunning = false;
  var sfPending = null, enginePending = null;
  var _engineQuickId = 0;
  var _sfQuickId = 0;

  // Deep-job state
  var _deepJobId = null;
  var _deepStartPending = false;
  var _deepCancelPending = false;
  var _deepPollTimer = null;
  var _deepPollMs = 500;
  var _deepGeneration = 0;

  // Deep-session state — user intent, independent of job lifecycle.
  // Start sets true; Stop sets false. Navigation does not change it.
  var _deepSessionActive = false;
  // Guards against an infinite retry loop if the server somehow
  // keeps returning session_not_found for a sessionless POST.
  var _retryingNoSession = false;

  // Server-side session handle for the CURRENT FEN only.
  var _deepSessionId = null;
  var _deepSessionFen = null;
  var SESSION_STORE_KEY = "chessai_sessions_v1";
  var SESSION_STORE_MAX = 64;

  function _loadSessionStore() {
    try { return JSON.parse(localStorage.getItem(SESSION_STORE_KEY)) || {}; }
    catch(e) { return {}; }
  }
  function _saveSessionStore(m) {
    try { localStorage.setItem(SESSION_STORE_KEY, JSON.stringify(m)); } catch(e) {}
  }
  function _rememberSession(fen, sid) {
    if (!fen || !sid) return;
    var m = _loadSessionStore();
    m[fen] = sid;
    var keys = Object.keys(m);
    while (keys.length > SESSION_STORE_MAX) {
      delete m[keys.shift()];
    }
    _saveSessionStore(m);
  }
  function _forgetSession(fen) {
    if (!fen) return;
    var m = _loadSessionStore();
    if (m[fen]) { delete m[fen]; _saveSessionStore(m); }
  }
  function _lookupSession(fen) {
    if (!fen) return null;
    return _loadSessionStore()[fen] || null;
  }

  // Last accepted analysis result for the current position. Populated
  // from GET /api/session (accepted_root) and from any live job result.
  // Used as a UI fallback so the panel is never blanked when a Resume
  // job has not yet accepted its first iteration.
  var _lastAcceptedRoot = null;

  // Deep job id -> originating FEN. Prevents a stale poll from an
  // older position from repopulating the accepted-result fallback
  // after the board has moved on.
  var _deepJobFens = {};
  var _reattachSeq = 0;
  var _deepPollInFlight = Object.create(null);
  var _deepJobGeneration = null;
  var _STARTPOS_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  function _normalizeAnalysisFen(fen) { return fen === 'startpos' ? _STARTPOS_FEN : fen; }
  function _currentAnalysisFen() { return _normalizeAnalysisFen(window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : 'startpos'); }

  // Set when a Start POST is in flight and another start is requested
  // (Stop->immediate-Start, or navigation during pending start). When the
  // in-flight POST resolves, this triggers exactly one follow-up start.
  var _deepPendingRestart = false;

  // Position-change debounce + deep-restart debounce
  var _posDebounceTimer = null;
  var POS_DEBOUNCE_MS = 400;
  var _deepRestartTimer = null;
  var DEEP_RESTART_DEBOUNCE_MS = 400;

  // Unified cancellation tracker. Every job the browser asks to cancel is
  // registered here. A single background poller drives each tracked job
  // to terminal, retrying cancel if needed.
  var _staleJobs = {};
  var _stalePollTimer = null;
  var _stalePollMs = 1000;

  var SF_SETTINGS_KEY = "sfSettings_v2";
  function loadSfSettings() {
    try {
      var s = JSON.parse(localStorage.getItem(SF_SETTINGS_KEY));
      if (s) { setVal("sfMultiPV", s.multi_pv, 3); setVal("sfMovetime", s.movetime, 1500); setVal("sfThreads", s.threads, 2); setVal("sfHash", s.hash_mb, 256); }
    } catch(e) {}
  }
  function saveSfSettings() {
    try { localStorage.setItem(SF_SETTINGS_KEY, JSON.stringify({ multi_pv: intVal("sfMultiPV",3), movetime: intVal("sfMovetime",1500), threads: intVal("sfThreads",2), hash_mb: intVal("sfHash",256) })); } catch(e) {}
  }
  function intVal(id, def) { return parseInt(document.getElementById(id)?.value) || def; }
  function setVal(id, val, def) { var el = document.getElementById(id); if (el) el.value = (val !== undefined) ? val : def; }
  function getSfSettings() { return { multi_pv: intVal("sfMultiPV",3), movetime: intVal("sfMovetime",1500), threads: intVal("sfThreads",2), hash_mb: intVal("sfHash",256) }; }

  // ============================================================
  // Quick path
  // ============================================================
  window.runUnifiedAnalysis = function(fen) {
    if (!fen) return;
    var mode = document.getElementById("analysisEngine")?.value || "engine";
    if (mode === "engine" || mode === "both") {
      if (engineRunning) { enginePending = fen; return; }
      _runEngineAnalysis(fen);
    }
    if (mode === "stockfish" || mode === "both") {
      if (sfRunning) { sfPending = fen; return; }
      _runStockfishAnalysis(fen);
    }
  };

  function _runEngineAnalysis(fen, fresh) {
    if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return;
    engineRunning = true;
    var id = ++_engineQuickId;
    var _reqBody = {fen: fen};
    if (fresh) _reqBody.fresh = true;
    fetch("/api/analyze", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(_reqBody) })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (id !== _engineQuickId) return;
      if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return; // STRICT FEN MATCH
      if (data.error) { document.getElementById("engineResult").innerHTML = '<span style="color:#ef5350;">Engine error: '+data.error+'</span>'; return; }
      var html = '<div style="margin-bottom:8px;"><span style="color:#4fc3f7;">My Engine (quick)</span>  ';
      html += '<span style="color:#fff;">'+data.score+'</span>  ';
      html += '<span style="color:#888;">depth '+data.depth+'</span></div>';
      if (data.reused_from_depth && data.reused_from_depth > 0) {
        html += '<div style="color:#9ca3af;font-size:11px;">resumed from depth ' + data.reused_from_depth + '</div>';
      }
      var _qFen = (fen === 'startpos')
        ? 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
        : fen;
      if (data.best_move) {
        html += '<div style="color:#d0d0d0;">Best: '+uciToSan(_qFen, data.best_move);
        if (data.pv && data.pv.length) html += '  <span style="color:#aaa;">'+uciToSan(_qFen, data.pv.join(' '))+'</span>';
        html += '</div>';
      }
      if (data.multipv && data.multipv.length > 1) {
        html += '<div style="margin-top:4px; color:#aaa; font-size:12px;">';
        data.multipv.forEach(function(mv,i) {
          var _sanMv = uciToSan(_qFen, mv.move);
          var _cp = Number(mv.score) || 0;
          var _sc;
          if (Math.abs(_cp) > 29000) {
            var _mate = Math.ceil((30000 - Math.abs(_cp)) / 2);
            _sc = (_cp > 0 ? 'M' : '-M') + _mate;
          } else {
            _sc = (_cp >= 0 ? '+' : '') + (_cp / 100).toFixed(2);
          }
          html += (i+1)+'. '+_sanMv+' ('+_sc+') ';
        });
        html += '</div>';
      }
      document.getElementById("engineResult").innerHTML = html;
      if (data.best_move) {
        try {
          var arrowTargetFen = _normalizeAnalysisFen(fen);
          if (arrowTargetFen === _currentAnalysisFen()) {
            var arrowState = stateFromFEN(arrowTargetFen);
            var arrowMove = uciToMoveObj(arrowState, data.best_move);
            var arrowDepth = Number(data.depth) || 0;
            var oldArrow = window._ENGINE_ARROW_BLUE;
            if (arrowMove && (!oldArrow || oldArrow.fen !== arrowTargetFen ||
                arrowDepth >= (Number(oldArrow.depth) || 0))) {
              window._ENGINE_ARROW_BLUE = {
                fromR: arrowMove.fromR, fromC: arrowMove.fromC,
                toR: arrowMove.toR, toC: arrowMove.toC,
                fen: arrowTargetFen, depth: arrowDepth, source: 'my-engine'
              };
              setTimeout(function() {
                if (_currentAnalysisFen() === arrowTargetFen &&
                    typeof renderBoard === 'function') {
                  renderBoard(window._CURRENT_STATE);
                }
              }, 0);
            }
          }
        } catch (e) { console.warn('My Engine quick arrow failed:', e); }
      }
    })
    .catch(function() { if (id !== _engineQuickId) return; if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return; document.getElementById("engineResult").innerHTML = '<span style="color:#ef5350;">Engine request failed.</span>'; })
    .finally(function() { engineRunning = false; if (enginePending) { var n = enginePending; enginePending = null; _runEngineAnalysis(n); } });
  }

  function _runStockfishAnalysis(fen) {
    if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return;
    var s = getSfSettings();
    var key = fen+'|'+s.multi_pv+'|'+s.movetime+'|'+s.threads+'|'+s.hash_mb;
    if (sfCache.has(key)) { _displayStockfishLines(sfCache.get(key), fen); return; }
    sfRunning = true;
    var id = ++_sfQuickId;
    fetch("/api/analyze_sf", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(Object.assign({fen: fen}, s)) })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (id !== _sfQuickId) return;
      if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return; // STRICT FEN MATCH
      if (data.error) { document.getElementById("stockfishResult").innerHTML = '<span style="color:#ef5350;">Stockfish error: '+data.error+'</span>'; return; }
      var lines = data.lines || [];
      if (sfCache.size >= SF_CACHE_MAX) { sfCache.delete(sfCache.keys().next().value); }
      sfCache.set(key, lines);
      _displayStockfishLines(lines, fen);
    })
    .catch(function() { if (id !== _sfQuickId) return; if (_normalizeAnalysisFen(fen) !== _currentAnalysisFen()) return; document.getElementById("stockfishResult").innerHTML = '<span style="color:#ef5350;">Stockfish request failed.</span>'; })
    .finally(function() { sfRunning = false; if (sfPending) { var n = sfPending; sfPending = null; _runStockfishAnalysis(n); } });
  }

  function _displayStockfishLines(lines, fen) {
    var html = '<div style="margin-bottom:4px;"><span style="color:#66bb6a;">Stockfish</span></div>';
    lines.forEach(function(line) {
      var score = line.score;
      var sc = "#ccc";
      if (score.indexOf("+") === 0) sc = "#4fc3f7";
      else if (score.indexOf("-") === 0) sc = "#ef5350";
      html += '<div style="margin-bottom:2px;"><span style="color:#888;">'+line.multipv+'.</span> <span style="color:'+sc+';">'+score+'</span>  <span style="color:#d0d0d0;">'+uciToSan(fen, line.uci_pv)+'</span></div>';
    });
    document.getElementById("stockfishResult").innerHTML = html;

    // Green engine arrow from Stockfish's top PV.
    // API returns {multipv, score, uci_pv}; uci_pv is a space-separated string.
    // No depth is returned, so the rule is FEN-only: replace whenever the
    // result belongs to the current board position.
    if (lines && lines.length > 0 && lines[0] && lines[0].uci_pv) {
      var stockfishArrowFen = _normalizeAnalysisFen(fen);
      if (stockfishArrowFen === _currentAnalysisFen()) {
        try {
          var stockfishBestMove = String(lines[0].uci_pv).trim().split(/\s+/)[0];
          if (stockfishBestMove) {
            var stockfishState = stateFromFEN(stockfishArrowFen);
            var stockfishMove = uciToMoveObj(stockfishState, stockfishBestMove);
            if (stockfishMove) {
              window._ENGINE_ARROW_GREEN = {
                fromR: stockfishMove.fromR, fromC: stockfishMove.fromC,
                toR: stockfishMove.toR, toC: stockfishMove.toC,
                fen: stockfishArrowFen, source: 'stockfish'
              };
              setTimeout(function() {
                if (_currentAnalysisFen() === stockfishArrowFen &&
                    typeof renderBoard === 'function') {
                  renderBoard(window._CURRENT_STATE);
                }
              }, 0);
            }
          }
        } catch (e) { console.warn('Stockfish arrow failed:', e); }
      }
    }
  }

  function uciToSan(fen, uciStr) {
    try {
      var moves = uciStr.split(/\s+/);
      var state = stateFromFEN(fen);
      var result = [];
      for (var i = 0; i < moves.length; i++) {
        var m = uciToMoveObj(state, moves[i]);
        if (!m) { result.push(moves[i]); continue; }
        result.push(moveToSAN(state, m));
        state = applyMoveToState(state, m);
      }
      return result.join(' ');
    } catch(e) { return uciStr; }
  }

  // ============================================================
  // Deep job — robust state model
  // ============================================================
  function _updateDeepButtons() {
    var startB = document.getElementById("startDeepBtn");
    var stopB = document.getElementById("stopDeepBtn");
    var resumeB = document.getElementById("resumeDeepBtn");
    var active = _deepSessionActive;
    if (startB) startB.disabled = active;
    if (stopB) stopB.disabled = !active;
    if (resumeB) {
      var busy = active ||
                  _deepCancelPending ||
                  _deepStartPending ||
                  (_deepJobId !== null) ||
                  (Object.keys(_staleJobs).length > 0);
      resumeB.disabled = busy;
    }
    if (typeof window._refreshToggleLabel === 'function') window._refreshToggleLabel();
  }

  function _renderDeepIdle() {
    var el = document.getElementById("deepResult");
    if (el) el.innerHTML = '<span class="small-muted">Deep analysis: idle</span>';
  }

  function _renderDeepStatus(job) {
    var el = document.getElementById("deepResult");
    if (!el) return;
    var p = job.progress || {};
    var r = job.result || {};

    var currentFen = _currentAnalysisFen();
    if (_normalizeAnalysisFen(_deepJobFens[job.job_id]) !== currentFen) return; // STRICT GUARD

    // Cache a live accepted result only when this job belongs to the
    // current board position. Stale polls must never repopulate it.
    if (r.depth !== undefined && r.depth !== null && r.depth > 0
        && _normalizeAnalysisFen(_deepJobFens[job.job_id]) === currentFen) {
      _lastAcceptedRoot = {
        root: {
          best_move: r.move,
          best_score: r.cp,
          depth: r.depth,
          pv: r.pv || []
        },
        fen: currentFen
      };
    }

    // Prefer the server session root whenever it is newer than the
    // current job result. Keeps the accepted display synchronized
    // even while a resumed job searches its next iteration.
    var usingFallback = false;
    var currentResultDepth = Number(r.depth) || 0;
    if (p.session_accepted_root
        && Number(p.session_accepted_root.depth) > currentResultDepth) {
      var sar = p.session_accepted_root;
      var scp = sar.best_score || 0;
      var sscoreStr;
      if (Math.abs(scp) > 29000) {
        var smate = Math.ceil((30000 - Math.abs(scp)) / 2);
        sscoreStr = (scp > 0 ? 'M' : '-M') + smate;
      } else {
        sscoreStr = (scp >= 0 ? '+' : '') + (scp / 100).toFixed(2);
      }
      r = {
        depth: sar.depth,
        move: sar.best_move,
        score: sscoreStr,
        cp: scp,
        pv: sar.pv || []
      };
      _lastAcceptedRoot = { root: sar, fen: currentFen };
      usingFallback = true;
    } else if ((r.depth === undefined || r.depth === null || r.depth <= 0)
        && _lastAcceptedRoot
        && _lastAcceptedRoot.fen === currentFen
        && _lastAcceptedRoot.root
        && _lastAcceptedRoot.root.depth > 0) {
      var lr = _lastAcceptedRoot.root;
      var cp = lr.best_score || 0;
      var scoreStr;
      if (Math.abs(cp) > 29000) {
        var mate = Math.ceil((30000 - Math.abs(cp)) / 2);
        scoreStr = (cp > 0 ? 'M' : '-M') + mate;
      } else {
        scoreStr = (cp >= 0 ? '+' : '') + (cp / 100).toFixed(2);
      }
      r = {
        depth: lr.depth,
        move: lr.best_move,
        score: scoreStr,
        cp: cp,
        pv: lr.pv || []
      };
      usingFallback = true;
    }

    if (r.move && Number(r.depth) > 0) {
      try {
        var deepArrowTargetFen = currentFen;
        var oldDeepArrow = window._ENGINE_ARROW_BLUE;
        if (!oldDeepArrow || oldDeepArrow.fen !== deepArrowTargetFen ||
            (Number(r.depth) || 0) >= (Number(oldDeepArrow.depth) || 0)) {
          var deepArrowState = stateFromFEN(deepArrowTargetFen);
          var deepArrowMove = uciToMoveObj(deepArrowState, r.move);
          if (deepArrowMove) {
            window._ENGINE_ARROW_BLUE = {
              fromR: deepArrowMove.fromR, fromC: deepArrowMove.fromC,
              toR: deepArrowMove.toR, toC: deepArrowMove.toC,
              fen: deepArrowTargetFen, depth: Number(r.depth) || 0, source: 'my-engine'
            };
            setTimeout(function() {
              if (_currentAnalysisFen() === deepArrowTargetFen &&
                  typeof renderBoard === 'function') {
                renderBoard(window._CURRENT_STATE);
              }
            }, 0);
          }
        }
      } catch (e) { console.warn('My Engine deep arrow failed:', e); }
    }

    var depths = p.accepted_depths || [];
    var html = '';
    html += '<div style="margin-bottom:6px;"><span style="color:#4fc3f7;">My Engine (deep)</span>  ';
    html += '<span style="color:#888;">' + job.status + '</span></div>';
    if (r.depth !== undefined && r.depth !== null && r.depth > 0) {
      html += '<div>Score: <span style="color:#fff;">' + (r.score || '—') + '</span>';
      html += '  Depth: <span style="color:#fff;">' + r.depth + '</span>';
      if (usingFallback) {
        html += ' <span style="color:#888;font-size:12px;">(last accepted)</span>';
      }
      html += '</div>';
      // Use the FEN the job was created for. The accepted PV belongs
      // to that position, not necessarily to whatever the board is
      // currently showing after navigation.
      var _sanFen = (_deepJobFens && _deepJobFens[job.job_id])
        || currentFen
        || 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
      if (_sanFen === 'startpos') {
        _sanFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
      }
      var _bestSan = r.move ? uciToSan(_sanFen, r.move) : '—';
      html += '<div>Best: <span style="color:#d0d0d0;">' + _bestSan + '</span></div>';
      if (r.pv && r.pv.length) {
        var _pvSan = uciToSan(_sanFen, r.pv.join(' '));
        html += '<div style="color:#aaa;font-size:12px;">PV: ' + _pvSan + '</div>';
      }
    }
    if (depths.length) {
      html += '<div style="color:#888;font-size:12px;">Accepted depths: [' + depths.join(', ') + ']</div>';
    }
    if (p.nodes || p.nps) {
      html += '<div style="color:#888;font-size:12px;">Nodes: ' + (p.nodes || 0) +
              '   NPS: ' + (p.nps || 0) +
              '   last-iter NPS: ' + (p.last_iteration_nps || 0) + '</div>';
    }
    if (p.searching && job.status === 'running') {
      html += '<div style="color:#aaa;font-size:12px;margin-top:4px;">';
      html += 'Searching depth ' + (p.searching.depth || 1);
      html += '   elapsed ' + (p.searching.elapsed || 0) + 's';
      html += '   nodes ' + (p.searching.nodes || 0);
      html += '</div>';
    }
    el.innerHTML = html;
  }

  function _renderDeepError(msg) {
    var el = document.getElementById("deepResult");
    if (el) el.innerHTML = '<span style="color:#ef5350;">Deep error: ' + msg + '</span>';
  }

  function _stopDeepPoll() {
    if (_deepPollTimer) { clearTimeout(_deepPollTimer); _deepPollTimer = null; }
  }

  function _pollDeep() {
    if (!_deepJobId) return;
    var id = _deepJobId;
    if (_deepPollInFlight[id]) return;
    _deepPollInFlight[id] = true;
    fetch("/api/jobs/" + id)
    .then(function(r) { return r.json(); })
    .then(function(job) {
      delete _deepPollInFlight[id];
      if (id !== _deepJobId) return;
      if (_deepSessionActive) _renderDeepStatus(job);
      var terminal = (job.status === 'stopped' ||
                      job.status === 'completed' ||
                      job.status === 'error' ||
                      job.status === 'safety_limit');
      if (terminal) {
        _deepJobId = null;
        _deepCancelPending = false;
        _stopDeepPoll();
        if (_deepSessionActive &&
            !_deepStartPending &&
            !_deepRestartTimer &&
            !_deepPendingRestart &&
            _deepJobGeneration === _deepGeneration &&
            (job.status === 'completed' ||
             job.status === 'error' ||
             job.status === 'safety_limit')) {
          _deepSessionActive = false;
          if (_deepRestartTimer) {
            clearTimeout(_deepRestartTimer);
            _deepRestartTimer = null;
          }
        }
        _deepJobGeneration = null;
        _updateDeepButtons();
      } else {
        if (_deepSessionActive || _deepCancelPending) {
          _deepPollTimer = setTimeout(_pollDeep, _deepPollMs);
        }
      }
    })
    .catch(function() {
      delete _deepPollInFlight[id];
      if (id !== _deepJobId) return;
      if (_deepSessionActive || _deepCancelPending) {
        _deepPollTimer = setTimeout(_pollDeep, _deepPollMs);
      }
    });
  }

  function _sendCancel(jobId) {
    fetch("/api/jobs/" + jobId + "/cancel", { method: "POST" })
      .then(function(r) {
        if (!r.ok) console.warn('Deep cancel HTTP', r.status, jobId);
      })
      .catch(function(e) { console.warn('Deep cancel network', jobId, e); });
  }

  function _trackStaleJob(jobId) {
    if (!jobId) return;
    _staleJobs[jobId] = true;
    if (_stalePollTimer) return;
    _stalePollTimer = setTimeout(_drainStaleJobs, _stalePollMs);
  }

  function _cancelAndTrack(jobId) {
    if (!jobId) return;
    _trackStaleJob(jobId);
    _sendCancel(jobId);
  }

  function _drainStaleJobs() {
    _stalePollTimer = null;
    var ids = Object.keys(_staleJobs);
    if (!ids.length) return;
    ids.forEach(function(jid) {
      fetch("/api/jobs/" + jid)
        .then(function(r) {
          if (!r.ok) return null;
          return r.json();
        })
        .then(function(job) {
          if (!job || job.error || !job.status) { return; }
          if (job.status === 'stopped' ||
              job.status === 'completed' ||
              job.status === 'error' ||
              job.status === 'safety_limit') {
            delete _staleJobs[jid];
            _updateDeepButtons();
            return;
          }
          if (job.status === 'queued' || job.status === 'running') {
            _sendCancel(jid);
          }
        })
        .catch(function() { /* retry next tick */ });
    });
    if (Object.keys(_staleJobs).length) {
      _stalePollTimer = setTimeout(_drainStaleJobs, _stalePollMs);
    }
  }

  // Pre-flight: if a stored session exists for this FEN but its
  // accepted_root has not been cached yet, fetch the session first
  // so the Resume panel has a result to show while the new job's
  // first iteration is being computed. Falls through to the inner
  // start if there is no stored session or the fetch fails.
  function _startJobForCurrentPosition() {
    if (!_deepSessionActive) return;
    var fen = window._CURRENT_STATE
      ? stateToFEN(window._CURRENT_STATE) : 'startpos';
    var sid = (_deepSessionFen === fen && _deepSessionId)
      ? _deepSessionId
      : _lookupSession(fen);
    var needFetch = sid
      && (!_lastAcceptedRoot || _lastAcceptedRoot.fen !== fen);
    if (!needFetch) {
      _startJobForCurrentPosition_inner();
      return;
    }
    var requestGeneration = _deepGeneration;
    fetch('/api/session/' + encodeURIComponent(sid))
      .then(function(r) {
        if (requestGeneration !== _deepGeneration) return null;
        if (r.status === 404) {
          _forgetSession(fen);
          _deepSessionId = null;
          _deepSessionFen = null;
          return null;
        }
        return r.json();
      })
      .then(function(sess) {
        if (requestGeneration !== _deepGeneration) return;
        if (sess && !sess.error && sess.accepted_root
            && sess.accepted_root.depth > 0) {
          _lastAcceptedRoot = { root: sess.accepted_root, fen: fen };
          _deepSessionId = sess.session_id;
          _deepSessionFen = fen;
        }
        _startJobForCurrentPosition_inner();
      })
      .catch(function() {
        if (requestGeneration !== _deepGeneration) return;
        _startJobForCurrentPosition_inner();
      });
  }

  // Start a deep job for the current position. Called by the Start button
  // and by the restart debounce when the session stays active across
  // navigation.
  function _startJobForCurrentPosition_inner() {
    if (!_deepSessionActive) return;
    if (_deepStartPending) {
      _deepPendingRestart = true;
      return;
    }
    _stopDeepPoll();
    var myGen = ++_deepGeneration;
    _deepStartPending = true;
    _updateDeepButtons();
    _engineQuickId++;
    _sfQuickId++;
    var fen = window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : 'startpos';
    var _postBody = { job_type: "analysis", payload: { fen: fen } };

    // Never carry a session handle across positions.
    var _storedSid =
      (_deepSessionFen === fen && _deepSessionId)
        ? _deepSessionId
        : _lookupSession(fen);

    if (_storedSid) _postBody.session_id = _storedSid;

    fetch("/api/jobs", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(_postBody)
    })
    .then(function(r) { return r.json(); })
    .then(function(job) {
      _deepStartPending = false;
      if (job.error) {
        // The server can forget a session across a Flask restart.
        // Drop the stale handle and retry once without it, so the
        // user gets a fresh analysis instead of a hard error.
        if (job.error === 'session_not_found' && !_retryingNoSession) {
          _retryingNoSession = true;
          _deepSessionId = null;
          _deepSessionFen = null;
          _forgetSession(fen);
          _startJobForCurrentPosition();
          return;
        }
        _retryingNoSession = false;
        if (myGen === _deepGeneration) {
          _renderDeepError(job.error);
          _deepSessionActive = false;
        }
        _updateDeepButtons();
        if (_deepPendingRestart && _deepSessionActive) {
          _deepPendingRestart = false;
          _startJobForCurrentPosition();
        }
        return;
      }
      _retryingNoSession = false;
      var superseded = (myGen !== _deepGeneration) ||
                       !_deepSessionActive ||
                       _deepPendingRestart;
      if (superseded) {
        _cancelAndTrack(job.job_id);
        _updateDeepButtons();
        if (_deepPendingRestart && _deepSessionActive) {
          _deepPendingRestart = false;
          _startJobForCurrentPosition();
        }
        return;
      }
      _deepJobId = job.job_id;
      _deepJobGeneration = myGen;
      _deepJobFens[job.job_id] = fen;
      if (job.session_id) {
        _deepSessionId = job.session_id;
        _deepSessionFen = fen;
        _rememberSession(fen, job.session_id);
      }
      _deepCancelPending = false;
      _renderDeepStatus(job);
      _updateDeepButtons();
      _pollDeep();
    })
    .catch(function(e) {
      _deepStartPending = false;
      if (myGen === _deepGeneration) {
        _renderDeepError(String(e));
        _deepSessionActive = false;
      }
      _updateDeepButtons();
      if (_deepPendingRestart && _deepSessionActive) {
        _deepPendingRestart = false;
        _startJobForCurrentPosition();
      }
    });
  }

  window.startDeepAnalysis = function() {
    if (_deepSessionActive) return;
    _reattachSeq++;
    _deepSessionActive = true;
    _startJobForCurrentPosition();
  };

  window.resumeDeepAnalysis = function() {
    if (_deepSessionActive) return;
    _reattachSeq++;
    _deepSessionActive = true;
    _startJobForCurrentPosition();
  };

  // On load: if a stored session exists for the current position and
  // the server still has it, offer to reattach (running) or resume
  // (stopped). Never auto-start a new search from a stored handle.
  function _attemptReattach(targetFen, seq) {
    if (_deepSessionActive) return;
    if (seq === undefined) seq = ++_reattachSeq;
    var fen = targetFen || (window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : 'startpos');
    var sid = _lookupSession(fen);
    if (!sid) {
      if (seq !== _reattachSeq) return;
      if (_currentAnalysisFen() !== _normalizeAnalysisFen(fen)) return;
      _renderDeepIdle();
      _updateDeepButtons();
      return;
    }

    fetch("/api/session/" + encodeURIComponent(sid))
      .then(function(r) {
        if (seq !== _reattachSeq) return null;
        if (r.status === 404) {
          if (_currentAnalysisFen() !== _normalizeAnalysisFen(fen)) return null;
          _forgetSession(fen);
          _deepSessionId = null;
          _deepSessionFen = null;
          return null;
        }
        return r.json();
      })
      .then(function(sess) {
        if (seq !== _reattachSeq) return;
        if (_currentAnalysisFen() !== _normalizeAnalysisFen(fen)) return;
        if (!sess || sess.error) {
          _renderDeepIdle();
          _updateDeepButtons();
          return;
        }

        _deepSessionId = sess.session_id;
        _deepSessionFen = fen;

        // Cache the last accepted result so that Resume can show it
        // immediately while the new job searches for the next depth.
        if (sess.accepted_root && sess.accepted_root.depth > 0) {
          _lastAcceptedRoot = { root: sess.accepted_root, fen: fen };
        }

        if (!sess.active_job_id &&
            !(sess.accepted_root && sess.accepted_root.depth > 0)) {
          _renderDeepIdle();
          _updateDeepButtons();
          return;
        }

        if (sess.active_job_id) {
          // Running on the server: reattach.
          _deepJobId = sess.active_job_id;
          _deepJobGeneration = _deepGeneration;
          _deepJobFens[_deepJobId] = fen;
          _deepSessionActive = true;
          _updateDeepButtons();
          _pollDeep();

          var el = document.getElementById("deepResult");
          if (el) {
            el.innerHTML =
              '<span class="small-muted">Reattached to running analysis (' +
              sess.session_id + ')</span>';
          }
        } else if (sess.accepted_root &&
                   sess.accepted_root.depth > 0) {
          // Stopped with a saved result: show Resume.
          var el2 = document.getElementById("deepResult");
          if (el2) {
            var d = sess.accepted_root;
            var html =
              '<div><span style="color:#4fc3f7;">My Engine (deep)</span> ' +
              '<span style="color:#888;">stopped</span></div>';

            html +=
              '<div>Score: <span style="color:#fff;">' +
              ((Math.abs(d.best_score) > 29000 ? ((d.best_score > 0 ? 'M' : '-M') + Math.ceil((30000 - Math.abs(d.best_score)) / 2)) : ((d.best_score >= 0 ? '+' : '') + (d.best_score / 100).toFixed(2)))) +
              '</span> Depth: <span style="color:#fff;">' +
              d.depth + '</span></div>';

            if (d.best_move) {
              html +=
                '<div style="color:#d0d0d0;">Best: ' +
                uciToSan(fen, d.best_move) +
                '</div>';
            }

            if (d.pv && d.pv.length) {
              html +=
                '<div style="color:#aaa;font-size:12px;">PV: ' +
                uciToSan(fen, d.pv.join(' ')) +
                '</div>';
            }

            html +=
              '<div style="margin-top:6px;">' +
              '<button id="resumeDeepBtn">Resume</button></div>';

            el2.innerHTML = html;

            var rb = document.getElementById("resumeDeepBtn");
            if (rb) {
              rb.addEventListener(
                "click",
                window.resumeDeepAnalysis
              );
            }
          }
        }
      })
      .catch(function() {
        if (seq !== _reattachSeq) return;
        if (_currentAnalysisFen() !== _normalizeAnalysisFen(fen)) return;
        _renderDeepIdle();
        _updateDeepButtons();
      });
  }

  function _renderResumeState() {
    var el = document.getElementById("deepResult");
    if (!el) return;
    var last = _lastAcceptedRoot;
    if (!last || !last.root || !last.root.depth || last.root.depth <= 0) {
      _renderDeepIdle();
      _updateDeepButtons();
      return;
    }
    if (_normalizeAnalysisFen(last.fen) !== _currentAnalysisFen()) {
      _renderDeepIdle();
      _updateDeepButtons();
      return;
    }
    var root = last.root;
    var html = '<div><span style="color:#4fc3f7;">My Engine (deep)</span> ' +
               '<span style="color:#888;">idle</span></div>';
    var cp = root.best_score || 0;
    var scoreStr = (Math.abs(cp) > 29000)
      ? ((cp > 0 ? 'M' : '-M') + Math.ceil((30000 - Math.abs(cp)) / 2))
      : ((cp >= 0 ? '+' : '') + (cp / 100).toFixed(2));
    html += '<div>Score: <span style="color:#fff;">' + scoreStr + '</span>';
    html += '  Depth: <span style="color:#fff;">' + root.depth + '</span></div>';
    var fen = last.fen;
    if (root.best_move) {
      var bestSan;
      try { bestSan = uciToSan(fen, root.best_move); }
      catch (e) { bestSan = root.best_move; }
      html += '<div style="color:#d0d0d0;">Best: ' + bestSan + '</div>';
    }
    if (root.pv && root.pv.length) {
      var pvSan;
      try { pvSan = uciToSan(fen, root.pv.join(' ')); }
      catch (e) { pvSan = root.pv.join(' '); }
      html += '<div style="color:#aaa;font-size:12px;">PV: ' + pvSan + '</div>';
    }
    html += '<div style="margin-top:6px;"><button id="resumeDeepBtn" disabled>Resume</button></div>';
    el.innerHTML = html;
    var rb = document.getElementById("resumeDeepBtn");
    if (rb) rb.addEventListener("click", window.resumeDeepAnalysis);
    _updateDeepButtons();
  }

  window.stopDeepAnalysis = function() {
    _reattachSeq++;
    _deepPendingRestart = false;
    if (!_deepSessionActive) return;
    _deepSessionActive = false;
    if (_deepRestartTimer) {
      clearTimeout(_deepRestartTimer);
      _deepRestartTimer = null;
    }
    _cancelCurrentJob();
    _renderResumeState();
    _updateDeepButtons();
  };

  // Cancel the currently tracked job without touching session state.
  // If a Start POST is still in flight, bump generation so the returned
  // job auto-cancels via the mismatch branch.
  function _cancelCurrentJob() {
    _deepGeneration++;
    if (_deepJobId === null) {
      return;
    }
    if (_deepCancelPending) return;
    _deepCancelPending = true;
    _cancelAndTrack(_deepJobId);
    _pollDeep();
  }

  // Debounced restart of the deep job after navigation, only while the
  // session is active. Rapid taps collapse into one restart for the
  // final position.
  function _scheduleDeepRestart() {
    if (_deepRestartTimer) {
      clearTimeout(_deepRestartTimer);
      _deepRestartTimer = null;
    }
    if (!_deepSessionActive) return;
    _deepRestartTimer = setTimeout(function() {
      _deepRestartTimer = null;
      if (!_deepSessionActive) return;
      _startJobForCurrentPosition();
    }, DEEP_RESTART_DEBOUNCE_MS);
  }

  // ============================================================
  // Position-change entry point
  // ============================================================
  window.onPositionChanged = function(fen) {
    _engineQuickId++;
    _sfQuickId++;
    _reattachSeq++;
    enginePending = null;
    sfPending = null;
    _lastAcceptedRoot = null;
    var engineArrowTargetFen = _normalizeAnalysisFen(fen);
    if (window._ENGINE_ARROW_BLUE && window._ENGINE_ARROW_BLUE.fen !== engineArrowTargetFen) {
      window._ENGINE_ARROW_BLUE = null;
    }
    if (window._ENGINE_ARROW_GREEN && window._ENGINE_ARROW_GREEN.fen !== engineArrowTargetFen) {
      window._ENGINE_ARROW_GREEN = null;
    }
    var _erEl = document.getElementById("engineResult");
    if (_erEl) _erEl.innerHTML = '';
    var _sfEl = document.getElementById("stockfishResult");
    if (_sfEl) _sfEl.innerHTML = '';
    var _drEl = document.getElementById("deepResult");
    if (_drEl) _drEl.innerHTML = '<span class="small-muted">Deep analysis: checking...</span>';

    if (_deepSessionActive) {
      _cancelCurrentJob();
      _scheduleDeepRestart();
    } else {
      _attemptReattach(fen, _reattachSeq);
    }
    if (_posDebounceTimer) clearTimeout(_posDebounceTimer);
    _posDebounceTimer = setTimeout(function() {
      _posDebounceTimer = null;
      window.runUnifiedAnalysis(fen);
    }, POS_DEBOUNCE_MS);
  };

  // ============================================================
  // UI wiring
  // ============================================================
  loadSfSettings();
  ['sfMultiPV','sfMovetime','sfThreads','sfHash'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', saveSfSettings);
  });

  var toggleBtn = document.getElementById("toggleAnalysis");
  var panel = document.getElementById("analysisPanel");
  function _refreshToggleLabel() {
    if (!toggleBtn || !panel) return;
    if (panel.style.display === "none") {
      toggleBtn.textContent = _deepSessionActive ? "Show (running)" : "Show";
    } else {
      toggleBtn.textContent = "Hide";
    }
  }
  window._refreshToggleLabel = _refreshToggleLabel;

  if (toggleBtn && panel) {
    toggleBtn.addEventListener("click", function() {
      if (panel.style.display === "none") { panel.style.display = "block"; }
      else { panel.style.display = "none"; }
      _refreshToggleLabel();
    });
  }

  var engineSel = document.getElementById("analysisEngine");
  var sfSet = document.getElementById("sfSettingsRow");
  if (engineSel && sfSet) {
    engineSel.addEventListener("change", function() {
      sfSet.style.display = (engineSel.value === "stockfish" || engineSel.value === "both") ? "flex" : "none";
      var fen = window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : null;
      if (fen) window.runUnifiedAnalysis(fen);
    });
    sfSet.style.display = (engineSel.value === "stockfish" || engineSel.value === "both") ? "flex" : "none";
  }

  var reanalyzeBtn = document.getElementById("sfReanalyzeBtn");
  if (reanalyzeBtn) reanalyzeBtn.addEventListener("click", function() {
    sfCache.clear();
    var fen = window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : null;
    if (fen) window.runUnifiedAnalysis(fen);
  });

  var freshBtn = document.getElementById("engineFreshBtn");
  if (freshBtn) freshBtn.addEventListener("click", function() {
    var fen = window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : null;
    if (!fen || engineRunning) return;
    _runEngineAnalysis(fen, true);
  });

  var copyBtn = document.getElementById("sfCopyBtn");
  if (copyBtn) copyBtn.addEventListener("click", function() {
    var res = document.getElementById("analysisResults").innerText;
    if (navigator.clipboard) { navigator.clipboard.writeText(res).then(function() { copyBtn.textContent = "Copied!"; setTimeout(function() { copyBtn.textContent = "Copy"; }, 1500); }).catch(function() { prompt("Copy:", res); }); }
    else prompt("Copy:", res);
  });

  ["sfMultiPV","sfMovetime","sfThreads","sfHash"].forEach(function(id) {
    var timeout;
    var el = document.getElementById(id);
    if (el) el.addEventListener("input", function() {
      clearTimeout(timeout);
      timeout = setTimeout(function() { sfCache.clear(); var fen = window._CURRENT_STATE ? stateToFEN(window._CURRENT_STATE) : null; if (fen) window.runUnifiedAnalysis(fen); }, 600);
    });
  });

  var startB = document.getElementById("startDeepBtn");
  if (startB) startB.addEventListener("click", window.startDeepAnalysis);
  var stopB = document.getElementById("stopDeepBtn");
  if (stopB) stopB.addEventListener("click", window.stopDeepAnalysis);

  _renderDeepIdle();
  _updateDeepButtons();

  try { window.runUnifiedAnalysis('startpos'); } catch(e) {}

  // Deferred so board.js has time to set window._CURRENT_STATE.
  var _pageLoadReattachSeq = _reattachSeq;
  setTimeout(function() {
    if (!_deepSessionActive && _reattachSeq === _pageLoadReattachSeq) {
      _attemptReattach(null, ++_reattachSeq);
    }
  }, 400);
})();
