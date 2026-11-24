
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
