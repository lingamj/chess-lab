#!/bin/bash
set -e
echo "🔧 Applying final fixes..."

# 1. Ensure we have a PGN file (sample if none)
if [ ! -f last_import.pgn ]; then
    echo "📄 Creating sample PGN..."
    cat > last_import.pgn << 'PGN'
[Event "Sample"]
[Site "?"]
[Date "2025.01.01"]
[Round "1"]
[White "Player"]
[Black "Computer"]
[Result "1-0"]
1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 10. d4 Nbd7 11. c4 c6 12. cxb5 axb5 13. Nc3 Bb7 14. Bg5 b4 15. Na4 c5 16. dxe5 dxe5 17. Bxf6 Bxf6 18. Qxd8 Raxd8 19. Rad1 Rxd1 20. Rxd1 Bc8 21. Nxe5 Bxe5 22. Bxf7+ Kh8 23. Rxd7 Bxd7 24. Bxg6 hxg6 25. Nc5 Bc8 26. Ne6 Rf4 27. Nxf4 Bxf4 28. b3 Be5 29. f4 Bf6 30. Kf2 Kg8 31. Ke3 Kf8 32. Ke4 Ke7 33. Kf5 Kd6 34. g4 Bxg4 35. Kxg4 Ke5 36. h4 Ke4 37. h5 Ke5 38. Kf3 Kd4 39. h6 Ke5 40. h7 Kf5 41. h8=Q Ke5 42. Qe8+ Kd4 43. Qxe7 Kc3 44. Qe3+ Kc2 45. Ke4 Kb2 46. Kd4 Kxb3 47. Qe2 Ka4 48. Kc4 Ka5 49. Qa2+ Kb6 50. Qb3+ Ka7 51. Kc5 Ka6 52. Qb6# 1-0
PGN
fi

# 2. Build the opening tree
echo "🌳 Building opening tree..."
python build_tree.py

# 3. Replace frontend/index.html with the corrected version (ensures correct START_FEN)
cat > frontend/index.html << 'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chess Study</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        #app { max-width: 700px; margin: 0 auto; }
        #board-area { position: relative; width: 100%; max-width: 600px; margin: 0 auto; }
        #board-wrapper { display: flex; align-items: flex-start; }
        #rank-labels { display: flex; flex-direction: column; justify-content: space-around; padding-right: 6px; font-size: 14px; height: 100%; min-height: 100%; }
        #rank-labels span { display: flex; align-items: center; justify-content: center; height: 12.5%; }
        #board-container { flex: 1; }
        #board { width: 100%; aspect-ratio: 1; display: grid; grid-template-columns: repeat(8, 1fr); position: relative; z-index: 1; }
        .square { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; font-size: 48px; font-weight: bold; cursor: pointer; user-select: none; position: relative; }
        .light { background: #f0d9b5; }
        .dark { background: #b58863; }
        #file-labels { display: flex; justify-content: space-around; padding-left: 24px; font-size: 14px; margin-top: 2px; }
        #file-labels span { flex: 1; text-align: center; }
        #fen-display { font-size: 12px; color: #888; margin: 4px 0; }
        #info { background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-top: 16px; }
        button { margin: 4px 2px; padding: 4px 12px; cursor: pointer; }
        #tree { list-style: none; padding: 0; }
        #tree li { padding: 4px 0; border-bottom: 1px solid #eee; display: flex; gap: 8px; align-items: center; cursor: pointer; }
        #tree li:hover { background: #f0f0f0; }
        .popularity-bar { flex: 1; height: 6px; background: #ddd; border-radius: 3px; overflow: hidden; }
        .popularity-fill { height: 100%; background: #2c3e50; border-radius: 3px; }
        .stat { font-size: 12px; color: #555; white-space: nowrap; }
        .error { color: red; padding: 10px; background: #ffeeee; border: 1px solid red; border-radius: 4px; margin: 10px 0; display: none; }
    </style>
</head>
<body>
    <div id="app">
        <div id="error-box" class="error"></div>

        <div id="board-area">
            <div id="board-wrapper">
                <div id="rank-labels"></div>
                <div id="board-container">
                    <div id="board"></div>
                </div>
            </div>
            <div id="file-labels"></div>
            <div id="fen-display">FEN: ...</div>
        </div>

        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
            <button id="flip-btn">Flip</button>
            <button id="reset-btn">Reset</button>
            <button id="export-pgn">Export PGN</button>
        </div>

        <div id="info">
            <h2>Opening Explorer</h2>
            <div id="eco-display">ECO: -</div>
            <ul id="tree">Loading...</ul>
        </div>
    </div>

    <script>
        // ---- Correct START_FEN ----
        const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
        let currentFen = START_FEN;
        let flipped = false;

        const pieceSymbols = {
            'r': '♜','n':'♞','b':'♝','q':'♛','k':'♚','p':'♟',
            'R': '♖','N':'♘','B':'♗','Q':'♕','K':'♔','P':'♙'
        };

        function parseFen(fen) {
            const rows = fen.split(' ')[0].split('/');
            const board = [];
            for (const row of rows) {
                const line = [];
                for (const ch of row) {
                    if (ch >= '1' && ch <= '8') {
                        for (let i = 0; i < parseInt(ch, 10); i++) line.push(null);
                    } else {
                        line.push(ch);
                    }
                }
                board.push(line);
            }
            return board;
        }

        function renderBoard(fen) {
            const board = parseFen(fen);
            const container = document.getElementById('board');
            if (!container) return;
            container.innerHTML = '';

            const rows = flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];
            const cols = flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];

            for (const r of rows) {
                for (const c of cols) {
                    const sq = document.createElement('div');
                    const isLight = (r + c) % 2 === 0;
                    sq.className = 'square ' + (isLight ? 'light' : 'dark');
                    const piece = board[r]?.[c];
                    if (piece) sq.textContent = pieceSymbols[piece] || piece;
                    sq.dataset.row = r;
                    sq.dataset.col = c;
                    container.appendChild(sq);
                }
            }

            const fileContainer = document.getElementById('file-labels');
            const rankContainer = document.getElementById('rank-labels');
            if (fileContainer && rankContainer) {
                const files = flipped ? ['h','g','f','e','d','c','b','a'] : ['a','b','c','d','e','f','g','h'];
                const ranks = flipped ? ['1','2','3','4','5','6','7','8'] : ['8','7','6','5','4','3','2','1'];
                fileContainer.innerHTML = files.map(f => `<span>${f}</span>`).join('');
                rankContainer.innerHTML = ranks.map(r => `<span>${r}</span>`).join('');
            }
            document.getElementById('fen-display').textContent = 'FEN: ' + fen;
        }

        function flipBoard() {
            flipped = !flipped;
            renderBoard(currentFen);
        }
        document.getElementById('flip-btn').addEventListener('click', flipBoard);

        function resetBoard() {
            currentFen = START_FEN;
            flipped = false;
            renderBoard(currentFen);
        }
        document.getElementById('reset-btn').addEventListener('click', resetBoard);

        async function loadTree(fen) {
            const list = document.getElementById('tree');
            const ecoEl = document.getElementById('eco-display');
            if (!list) return;
            try {
                const res = await fetch('/api/tree', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ fen })
                });
                const data = await res.json();
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
                    li.addEventListener('click', () => {
                        fetch('/api/move', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ fen: currentFen, uci: m.uci })
                        })
                        .then(r => r.json())
                        .then(data => {
                            if (data.fen) {
                                currentFen = data.fen;
                                renderBoard(currentFen);
                                loadTree(currentFen);
                            }
                        })
                        .catch(e => showError(e.message));
                    });
                    list.appendChild(li);
                }
            } catch (e) {
                showError(e.message);
            }
        }

        function showError(msg) {
            const el = document.getElementById('error-box');
            if (el) {
                el.textContent = 'Error: ' + msg;
                el.style.display = 'block';
            }
        }

        renderBoard(currentFen);
        loadTree(currentFen);
    </script>
</body>
</html>
HTML

echo "✅ All fixes applied."
echo "▶️  Restart Flask with: python web_control.py"
echo "🌐 Then open: http://localhost:5000/frontend/index.html"
echo ""
echo "💡 If you still see 'No moves in database', run: python build_tree.py"
