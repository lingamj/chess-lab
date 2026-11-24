
    const moves = state.moveHistory;
    if (moves.length === 0) return '';
    let pgn = '[Event "Chess Study"]\n[Date "' + new Date().toISOString().slice(0,10) + '"]\n[White "User"]\n[Black "Study"]\n';
    let moveText = '';
    for (let i = 0; i < moves.length; i++) {
        const m = moves[i];
        if (i % 2 === 0) moveText += `${m.ply}. `;
        moveText += m.san + ' ';
    }
    pgn += moveText.trim();
    return pgn;
}

    const pgn = generatePGN();
    const blob = new Blob([pgn], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'chess_study.pgn';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
