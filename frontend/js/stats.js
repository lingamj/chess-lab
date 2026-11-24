
    try {
        const stats = await getRepertoireStats();
        state.stats = {
            total_positions: stats.total_positions || 0,
            due_positions: stats.due_positions || 0,
            accuracy: stats.accuracy || 0,
            white_count: stats.white_count || 0,
            black_count: stats.black_count || 0,
        };
        const el = document.getElementById('rep-stats');
        if (el) {
            el.textContent = `Total: ${state.stats.total_positions} | Due: ${state.stats.due_positions} | Accuracy: ${state.stats.accuracy}% | White: ${state.stats.white_count} | Black: ${state.stats.black_count}`;
        }
        return state.stats;
    } catch { return null; }
}
