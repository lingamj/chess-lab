
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
