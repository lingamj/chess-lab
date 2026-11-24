
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
