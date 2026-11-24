
    const res = await fetch(API_BASE + url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    let data;
    try { data = await res.json(); } catch { throw new Error(`Invalid JSON (${res.status})`); }
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
}

    return api('/api/move', { method: 'POST', body: JSON.stringify({ fen, uci }) });
}

    return api('/api/tree', { method: 'POST', body: JSON.stringify({ fen }) });
}

    return api('/api/repertoire?fen=' + encodeURIComponent(fen));
}

    return api('/api/repertoire', { method: 'POST', body: JSON.stringify({ fen, data }) });
}

    return api('/api/repertoire/' + encodeURIComponent(fen), { method: 'DELETE' });
}

    return api('/api/train/next');
}

    return api('/api/train/review', { method: 'POST', body: JSON.stringify({ fen, move }) });
}

    return api('/api/repertoire/stats');
}

    return api('/api/repertoire/export');
}

    return api('/api/repertoire/import', { method: 'POST', body: JSON.stringify(data) });
}
