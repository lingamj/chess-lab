
    const canvas = document.getElementById('eval-graph');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width = canvas.parentElement.clientWidth || 400;
    const h = canvas.height = 120;

    let evals = state.evaluations || [];
    if (evals.length < 2) {
        ctx.fillStyle = '#aaa';
        ctx.font = '14px sans-serif';
        ctx.fillText('No evaluation data.', 10, h/2);
        return;
    }
    if (evals.length > MAX_GRAPH_POINTS) {
        state.evaluations = evals.slice(-MAX_GRAPH_POINTS);
        state.depths = (state.depths || []).slice(-MAX_GRAPH_POINTS);
        evals = state.evaluations;
    }

    const maxAbs = Math.max(5, ...evals.map(Math.abs));
    const range = maxAbs * 2;
    const mid = h / 2;

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(w, mid);
    ctx.stroke();

    ctx.strokeStyle = '#2c3e50';
    ctx.lineWidth = 2;
    const step = (w - 20) / (evals.length - 1);
    ctx.beginPath();
    for (let i = 0; i < evals.length; i++) {
        const x = 10 + i * step;
        const y = mid - (evals[i] / range) * (h * 0.4);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
}
