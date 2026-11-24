
    try {
        const data = await getRepertoire(fen);
        state.repertoire = data.entry || null;
        document.getElementById('rep-main-move').value = state.repertoire?.main_move || '';
        document.getElementById('rep-alternatives').value = state.repertoire?.alternatives?.join(',') || '';
        document.getElementById('rep-notes').value = state.repertoire?.notes || '';
        document.getElementById('rep-tags').value = state.repertoire?.tags?.join(',') || '';
        document.getElementById('rep-color').value = state.repertoire?.color || 'white';
    } catch (e) { setError(e.message); }
}

    const data = {
        color: document.getElementById('rep-color').value || 'white',
        main_move: document.getElementById('rep-main-move').value.trim() || '',
        alternatives: document.getElementById('rep-alternatives').value.split(',').map(s=>s.trim()).filter(Boolean),
        notes: document.getElementById('rep-notes').value.trim(),
        tags: document.getElementById('rep-tags').value.split(',').map(s=>s.trim()).filter(Boolean),
    };
    try {
        await saveRepertoire(state.currentFen, data);
        await loadRepertoire(state.currentFen);
        await updateStats();
        alert('Repertoire saved.');
    } catch (e) { setError(e.message); }
}

    if (!confirm('Delete this entry?')) return;
    try {
        await deleteRepertoireEntry(state.currentFen);
        state.repertoire = null;
        await loadRepertoire(state.currentFen);
        await updateStats();
        alert('Deleted.');
    } catch (e) { setError(e.message); }
}
