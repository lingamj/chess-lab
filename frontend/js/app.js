
// Register callbacks
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
    // Buttons – using the IDs from index.html
    document.getElementById('trainer-button')?.addEventListener('click', startTraining);
    document.getElementById('trainer-submit')?.addEventListener('click', submitTrainingAnswer);
    document.getElementById('trainer-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitTrainingAnswer();
    });
    document.getElementById('rep-save')?.addEventListener('click', saveCurrentRepertoire);
    document.getElementById('rep-delete')?.addEventListener('click', deleteCurrentRepertoire);
    document.getElementById('flip-btn')?.addEventListener('click', flipBoard);
    document.getElementById('reset-btn')?.addEventListener('click', goToStart);
    document.getElementById('back-btn')?.addEventListener('click', goBack);
    document.getElementById('forward-btn')?.addEventListener('click', goForward);
    document.getElementById('export-pgn')?.addEventListener('click', exportPGN);
    document.getElementById('analyze-btn')?.addEventListener('click', () => {
        analyzePosition(state.currentFen);
    });

    // Import buttons
    document.getElementById('import-lichess')?.addEventListener('click', () => importGames('lichess'));
    document.getElementById('import-chesscom')?.addEventListener('click', () => importGames('chesscom'));

    // Init drag & drop (piece movement)
    initDragDrop();

    // Initial load
    (async () => {
        try {
            // await renderBoard(state.currentFen);
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
