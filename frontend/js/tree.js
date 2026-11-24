
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
