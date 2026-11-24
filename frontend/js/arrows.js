
    const container = document.getElementById('arrows-container');
    if (!container) return;
    container.innerHTML = '';
    const arrows = state.arrows || [];
    if (arrows.length === 0) return;

    const board = document.getElementById('board');
    const size = board ? board.clientWidth : 400;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';

    arrows.forEach(a => {
        const from = squareToPixels(a.from);
        const to = squareToPixels(a.to);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', from.x);
        line.setAttribute('y1', from.y);
        line.setAttribute('x2', to.x);
        line.setAttribute('y2', to.y);
        line.setAttribute('stroke', a.color || '#ff0000');
        line.setAttribute('stroke-width', Math.max(2, a.weight / 10));
        line.setAttribute('opacity', 0.7);
        const dx = to.x - from.x, dy = to.y - from.y;
        const angle = Math.atan2(dy, dx);
        const size2 = 8;
        const points = [
            [to.x, to.y],
            [to.x - size2 * Math.cos(angle - 0.5), to.y - size2 * Math.sin(angle - 0.5)],
            [to.x - size2 * Math.cos(angle + 0.5), to.y - size2 * Math.sin(angle + 0.5)],
        ];
        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        arrow.setAttribute('points', points.map(p => p.join(',')).join(' '));
        arrow.setAttribute('fill', a.color || '#ff0000');
        svg.appendChild(line);
        svg.appendChild(arrow);
    });
    container.appendChild(svg);
}
