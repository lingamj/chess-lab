
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


    if (callbacks.renderBoard) await callbacks.renderBoard(state.currentFen);
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
