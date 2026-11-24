
    const tree = await getTree(state.currentFen);
    if (!tree.moves) return;
    const listItems = document.querySelectorAll('#tree li');
    listItems.forEach((li, idx) => {
        const m = tree.moves[idx];
        if (!m) return;
        const pop = m.popularity || 0;
        let color = '';
        if (pop > 60) color = 'rgba(0,200,0,0.25)';
        else if (pop > 40) color = 'rgba(200,200,0,0.25)';
        else if (pop > 20) color = 'rgba(255,150,0,0.25)';
        else color = 'rgba(200,0,0,0.15)';
        li.style.backgroundColor = color;
        const bar = li.querySelector('.popularity-fill');
        if (bar) bar.style.width = pop + '%';
    });
}
