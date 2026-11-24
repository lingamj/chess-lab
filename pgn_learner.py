#!/usr/bin/env python3
"""
PGN Learner – robust import from Lichess / Chess.com (unlimited) or local PGN.
APPENDS new positions to the existing pgn_data.pkl instead of overwriting.
Value convention: side-to-move perspective.
"""

import re, os, pickle, requests, sys, datetime
from database_v2 import insert_games_from_pgn_text
from concurrent.futures import ThreadPoolExecutor, as_completed
from board import ChessBoard

def _remove_variations(text):
    result = []
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            if depth > 0:
                depth -= 1
        elif depth == 0:
            result.append(ch)
    return ''.join(result)

def parse_pgn_content(content):
    games = []
    current = []
    for line in content.split('\n'):
        if line.startswith('[Event ') and current:
            games.append('\n'.join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        games.append('\n'.join(current))
    parsed = []
    for game_text in games:
        headers = dict(re.findall(r'\[(\w+)\s+"([^"]*)"\]', game_text))
        result = headers.get('Result', '*')
        moves_text = re.sub(r'\[.*?\]', '', game_text)
        moves_text = re.sub(r'\{[^}]*\}', '', moves_text, flags=re.DOTALL)
        moves_text = _remove_variations(moves_text)
        moves_text = re.sub(r'\d+\.\.\.', '', moves_text)
        moves_text = re.sub(r'\d+\.', ' ', moves_text)
        moves_text = moves_text.replace('1-0', '').replace('0-1', '').replace('1/2-1/2', '').replace('*', '')
        moves_text = re.sub(r'[!?+#]*', '', moves_text)
        move_strings = moves_text.split()
        board = ChessBoard()
        internal_moves = []
        valid = True
        for ms in move_strings:
            move = pgn_to_move(ms, board)
            if move is None:
                valid = False
                break
            internal_moves.append(move)
            board.make_move(move)
        if valid and internal_moves:
            parsed.append({'moves': internal_moves, 'result': result})
    return parsed

def pgn_to_move(pgn_move, board):
    pgn = pgn_move.replace('+', '').replace('#', '').replace('x', '')
    if pgn in ('O-O', 'O-O-O', '0-0', '0-0-0'):
        row = 7 if board.white_turn else 0
        target = (row, 6) if pgn in ('O-O', '0-0') else (row, 2)
        for move in board.generate_legal_moves():
            if move[:2] == (row, 4) and move[2:4] == target:
                return move
        return None
    promo = None
    if '=' in pgn:
        parts = pgn.split('=')
        pgn = parts[0]
        promo = parts[1].upper()
    elif len(pgn) > 3 and pgn[-1] in 'QRBN':
        promo = pgn[-1].upper()
        pgn = pgn[:-1]
    piece_type = 'P'
    if pgn[0] in 'KQRBN':
        piece_type = pgn[0]
        pgn = pgn[1:]
    from_file = None
    from_rank = None
    if len(pgn) == 3:
        if pgn[0].isalpha():
            from_file = pgn[0]
        else:
            from_rank = pgn[0]
        to_square = pgn[1:]
    elif len(pgn) == 4:
        from_file = pgn[0]
        from_rank = pgn[1]
        to_square = pgn[2:]
    else:
        to_square = pgn
    to_col = ord(to_square[0]) - ord('a')
    to_row = 8 - int(to_square[1])
    for move in board.generate_legal_moves():
        fr, fc, tr, tc = move[:4]
        if tr != to_row or tc != to_col:
            continue
        piece = board.board[fr][fc]
        if piece_type == 'P' and piece.upper() != 'P':
            continue
        if piece_type != 'P' and piece.upper() != piece_type:
            continue
        if from_file and fc != ord(from_file) - ord('a'):
            continue
        if from_rank and fr != 8 - int(from_rank):
            continue
        if promo and (len(move) < 5 or move[4] != promo):
            continue
        return move
    return None

def extract_training_data_from_pgn(pgn_content):
    games = parse_pgn_content(pgn_content)
    positions = []
    results = []
    for game in games:
        res = game['result']
        white_result = 1.0 if res == '1-0' else (-1.0 if res == '0-1' else 0.0)
        board = ChessBoard()
        for move in game['moves']:
            positions.append(board.copy())
            if white_result == 0.0:
                value = 0.0
            else:
                value = white_result if board.white_turn else -white_result
            results.append(value)
            board.make_move(move)
    return positions, results

def download_all_lichess_games(username):
    url = f"https://lichess.org/api/games/user/{username}"
    params = {"max": 999999, "moves": True, "pgnInJson": False}
    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessAI/1.0 (personal chess analysis application)",
    }
    print(f"Downloading all games for Lichess user: {username} ...")
    try:
        with requests.get(url, params=params, headers=headers, timeout=(10, 300), stream=True) as resp:
            resp.raise_for_status()
            total_size = int(resp.headers.get('content-length', 0))
            downloaded = 0
            pgn_data = ""
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    pgn_data += chunk.decode('utf-8', errors='replace')
                    downloaded += len(chunk)
                    if total_size:
                        percent = int(downloaded / total_size * 100)
                        print(f"\r  Downloading... {percent}% ({downloaded // 1024}KB)", end='')
            print()
        num_games = pgn_data.count("[Event ")
        print(f"  Downloaded {num_games} games.")
        return pgn_data
    except Exception as e:
        print(f"\nError: {e}")
        return ""

def download_all_chesscom_games(username):
    headers = {"User-Agent": "ChessAI Mobile/1.0"}
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
    print(f"Fetching all games for Chess.com user: {username} ...")
    try:
        resp = requests.get(archives_url, headers=headers, timeout=30)
        resp.raise_for_status()
        archives = resp.json().get("archives", [])
    except Exception as e:
        print(f"Error: {e}")
        return ""
    if not archives:
        print("No games found or user doesn't exist.")
        return ""
    print(f"Found {len(archives)} monthly archives. Downloading in parallel (4 at a time)...")
    all_pgn = ""
    total_games = 0
    def fetch_archive(url):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()
            games = r.json().get("games", [])
            pgn_chunk = ""
            for g in games:
                pgn = g.get("pgn", "")
                if pgn:
                    pgn_chunk += pgn + "\n\n"
            return pgn_chunk, len(games)
        except Exception as e:
            print(f"    Error fetching {url}: {e}")
            return "", 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_archive, url): url for url in archives}
        for future in as_completed(futures):
            pgn_chunk, count = future.result()
            all_pgn += pgn_chunk
            total_games += count
            print(f"    Completed {total_games} games so far...")
    print(f"  Downloaded {total_games} games total.")
    return all_pgn


def download_lichess_games_since(username, since_ms):
    """Download Lichess games strictly newer than since_ms.

    Returns:
        (pgn_text, count, error)
        error is None on success; otherwise a human-readable failure reason.
    """
    url = f"https://lichess.org/api/games/user/{username}"
    params = {
        "since": int(since_ms),
        "max": 999999,
        "moves": True,
        "pgnInJson": False,
    }
    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessAI/1.0 (personal chess analysis application)",
    }
    print(f"Downloading new Lichess games for {username} since {since_ms} ...")

    try:
        with requests.get(
            url,
            params=params,
            headers=headers,
            timeout=(10, 300),
            stream=True,
        ) as resp:
            if resp.status_code == 200:
                chunks = []
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        chunks.append(chunk.decode("utf-8", errors="replace"))
                pgn_data = "".join(chunks)
                count = pgn_data.count("[Event ")
                print(f"  Incremental Lichess download: {count} games.")
                return pgn_data, count, None

            body = resp.text[:200].strip()
            error = f"HTTP {resp.status_code}: {body}"
            print(f"  Lichess incremental download error: {error}")
            return "", 0, error

    except requests.exceptions.HTTPError as e:
        status = getattr(e.response, "status_code", "unknown")
        error = f"HTTP error {status}: {e}"
        print(f"  Lichess incremental download error: {error}")
        return "", 0, error

    except Exception as e:
        error = f"network/exception: {e}"
        print(f"  Lichess incremental download error: {error}")
        return "", 0, error


def _chesscom_game_timestamp_ms(pgn):
    """Return Chess.com game UTC timestamp in milliseconds, or None."""
    date_match = re.search(r'\[UTCDate\s+"(\d{4}\.\d{2}\.\d{2})"\]', pgn)
    if not date_match:
        return None

    time_match = re.search(r'\[UTCTime\s+"(\d{2}:\d{2}:\d{2})"\]', pgn)
    date_text = date_match.group(1).replace(".", "-")
    time_text = time_match.group(1) if time_match else "00:00:00"

    try:
        dt = datetime.datetime.strptime(
            f"{date_text}T{time_text}",
            "%Y-%m-%dT%H:%M:%S",
        )
        return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    except ValueError:
        return None


def download_chesscom_games_since(username, since_ms):
    """Download Chess.com games newer than since_ms.

    Returns:
        (pgn_text, count, newest_seen_ms, error)

        error is None on success; otherwise a human-readable failure reason.
        newest_seen_ms is None when no new games were found.
    """
    headers = {"User-Agent": "ChessAI Mobile/1.0"}
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"

    print(f"Downloading new Chess.com games for {username} since {since_ms} ...")

    try:
        resp = requests.get(archives_url, headers=headers, timeout=60)
        if resp.status_code != 200:
            error = f"archive list HTTP {resp.status_code}: {resp.text[:120]}"
            print(f"  {error}")
            return "", 0, None, error

        archives = resp.json().get("archives", [])
    except Exception as e:
        error = f"archive list network/exception: {e}"
        print(f"  {error}")
        return "", 0, None, error

    if not archives:
        return "", 0, None, "no archives found"

    cursor_dt = datetime.datetime.fromtimestamp(
        int(since_ms) / 1000,
        tz=datetime.timezone.utc,
    )

    candidate_archives = []
    for archive_url in archives:
        m = re.search(r"/(\d{4})/(\d{2})$", archive_url.rstrip("/"))
        if not m:
            continue

        year = int(m.group(1))
        month = int(m.group(2))
        archive_month = datetime.datetime(
            year,
            month,
            1,
            tzinfo=datetime.timezone.utc,
        )
        next_month = (
            datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
            if month == 12
            else datetime.datetime(
                year,
                month + 1,
                1,
                tzinfo=datetime.timezone.utc,
            )
        )

        if next_month > cursor_dt:
            candidate_archives.append(archive_url)

    candidate_archives.sort()
    print(f"  Candidate Chess.com archives: {len(candidate_archives)}")

    all_pgn = []
    total_new = 0
    newest_seen_ms = int(since_ms)

    for archive_url in candidate_archives:
        try:
            resp = requests.get(
                archive_url,
                headers=headers,
                timeout=120,
            )
            if resp.status_code != 200:
                error = f"archive {archive_url} HTTP {resp.status_code}: {resp.text[:120]}"
                print(f"  {error}")
                return "", 0, None, error

            games = resp.json().get("games", [])
            archive_new = 0

            for game in games:
                pgn = game.get("pgn", "")
                if not pgn:
                    continue

                game_ts_ms = _chesscom_game_timestamp_ms(pgn)
                if game_ts_ms is None:
                    continue

                if game_ts_ms > int(since_ms):
                    all_pgn.append(pgn)
                    total_new += 1
                    archive_new += 1
                    newest_seen_ms = max(newest_seen_ms, game_ts_ms)

            print(
                f"  {archive_url.rsplit('/', 2)[-2:] if archive_url else archive_url}: "
                f"{archive_new} new games"
            )

        except Exception as e:
            error = f"archive {archive_url} network/exception: {e}"
            print(f"  {error}")
            return "", 0, None, error

    pgn_data = "\n\n".join(all_pgn)

    final_newest = newest_seen_ms if total_new else None

    print(
        f"  Incremental Chess.com download: {total_new} games; "
        f"newest timestamp: {final_newest if final_newest is not None else 'unchanged'}"
    )

    return pgn_data, total_new, final_newest, None
def _pgn_blocks_from_text(text):
    """Split PGN text into individual game blocks."""
    normalized = text.replace('\r\n', '\n').replace('\r', '\n')
    parts = re.split(r"\n(?=\[Event\s)", normalized)
    return [p.strip() for p in parts if p.strip()]


def _chunk_pgn_blocks(block_iter, chunk_size=100):
    """Group PGN blocks into bounded chunks."""
    batch = []
    for block in block_iter:
        if not block or not block.strip():
            continue
        batch.append(block)
        if len(batch) >= chunk_size:
            yield '\n\n'.join(batch), len(batch)
            batch = []
    if batch:
        yield '\n\n'.join(batch), len(batch)


def iter_lichess_game_blocks(username, since_ms):
    """Stream Lichess games and yield one PGN block at a time.

    This function does NOT return early with an error tuple.
    It raises an exception on HTTP/network failure so the future
    background worker can mark the job failed without advancing cursor.
    """
    url = f"https://lichess.org/api/games/user/{username}"
    params = {
        "since": int(since_ms),
        "max": 999999,
        "moves": True,
        "pgnInJson": False,
    }
    headers = {
        "Accept": "application/x-chess-pgn",
        "User-Agent": "ChessAI/1.0 (personal chess analysis application)",
    }

    with requests.get(
        url,
        params=params,
        headers=headers,
        timeout=(10, 300),
        stream=True,
    ) as resp:
        if resp.status_code != 200:
            raise RuntimeError(
                f"Lichess HTTP {resp.status_code}: {resp.text[:160]}"
            )

        buffer = ""
        for raw_chunk in resp.iter_content(chunk_size=8192):
            if not raw_chunk:
                continue
            buffer += raw_chunk.decode("utf-8", errors="replace")

            while True:
                idx = buffer.find("\n[Event ", 1)
                if idx == -1:
                    break
                block = buffer[:idx]
                buffer = buffer[idx:]
                if block.strip():
                    yield block.strip()

        if buffer.strip():
            yield buffer.strip()


def iter_chesscom_game_blocks(username, since_ms):
    """Iterate Chess.com games newer than since_ms, yielding one PGN at a time.

    Raises an exception on HTTP/network failure instead of returning an
    early error tuple, so the future worker can mark the job failed.
    """
    headers = {"User-Agent": "ChessAI Mobile/1.0"}
    archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"

    resp = requests.get(archives_url, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Chess.com archive list HTTP {resp.status_code}: {resp.text[:160]}"
        )

    archives = resp.json().get("archives", [])
    if not archives:
        return

    cursor_dt = datetime.datetime.fromtimestamp(
        int(since_ms) / 1000,
        tz=datetime.timezone.utc,
    )

    candidate_archives = []
    for archive_url in archives:
        m = re.search(r"/(\d{4})/(\d{2})$", archive_url.rstrip("/"))
        if not m:
            continue

        year = int(m.group(1))
        month = int(m.group(2))
        archive_month = datetime.datetime(
            year,
            month,
            1,
            tzinfo=datetime.timezone.utc,
        )
        next_month = (
            datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
            if month == 12
            else datetime.datetime(
                year,
                month + 1,
                1,
                tzinfo=datetime.timezone.utc,
            )
        )

        if next_month > cursor_dt:
            candidate_archives.append(archive_url)

    candidate_archives.sort()

    for archive_url in candidate_archives:
        resp = requests.get(archive_url, headers=headers, timeout=120)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Chess.com archive HTTP {resp.status_code}: {resp.text[:160]}"
            )

        games = resp.json().get("games", [])
        for game in games:
            pgn = game.get("pgn", "")
            if not pgn:
                continue

            game_ts_ms = _chesscom_game_timestamp_ms(pgn)
            if game_ts_ms is None:
                continue

            if game_ts_ms > int(since_ms):
                yield pgn


def iter_lichess_pgn_chunks(username, since_ms, chunk_size=100):
    """Yield (pgn_chunk, game_count) for bounded Lichess import."""
    yield from _chunk_pgn_blocks(
        iter_lichess_game_blocks(username, since_ms),
        chunk_size=chunk_size,
    )


def iter_chesscom_pgn_chunks(username, since_ms, chunk_size=100):
    """Yield (pgn_chunk, game_count) for bounded Chess.com import."""
    yield from _chunk_pgn_blocks(
        iter_chesscom_game_blocks(username, since_ms),
        chunk_size=chunk_size,
    )

def main():
    print("=" * 50)
    print("   PGN LEARNER – UNLIMITED IMPORT (APPEND MODE)")
    print("=" * 50)
    print("1. Import from local PGN file")
    print("2. Import ALL games from Lichess (by username)")
    print("3. Import ALL games from Chess.com (by username)")
    choice = input("\nChoose an option (1-3): ").strip()
    pgn_content = ""
    if choice == '1':
        filepath = input("PGN file path [~/chess_ai/games.pgn]: ").strip()
        if not filepath:
            filepath = os.path.expanduser('~/chess_ai/games.pgn')
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            return
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            pgn_content = f.read()
    elif choice == '2':
        username = input("Lichess username: ").strip()
        if not username:
            print("Username required.")
            return
        pgn_content = download_all_lichess_games(username)
    elif choice == '3':
        username = input("Chess.com username: ").strip()
        if not username:
            print("Username required.")
            return
        pgn_content = download_all_chesscom_games(username)
    else:
        print("Invalid choice.")
        return
    if not pgn_content.strip():
        print("No games retrieved. Aborting.")
        return
    pgn_file = os.path.expanduser('~/chess_ai/last_import.pgn')
    with open(pgn_file, 'w', encoding='utf-8') as f:
        f.write(pgn_content)
    print(f"\nRaw PGN saved to {pgn_file}")

    # --- Phase-1: store in persistent database ---
    try:
        source_map = {'1': 'local', '2': 'lichess', '3': 'chesscom'}
        src_label = source_map.get(choice, 'unknown')
        user = username if choice in ('2', '3') else None
        new_games = insert_games_from_pgn_text(
            pgn_content,
            source=src_label,
            source_username=user,
            source_file="last_import.pgn",
        )
        print(f"Database: {new_games} new games added (duplicates skipped)")
    except Exception as e:
        print(f"Database insert skipped (error: {e})")

    print("Parsing games...")
    new_positions, new_results = extract_training_data_from_pgn(pgn_content)
    if not new_positions:
        print("No positions extracted.")
        return
    outfile = os.path.expanduser('~/chess_ai/pgn_data.pkl')
    if os.path.exists(outfile):
        with open(outfile, 'rb') as f:
            old_positions, old_results = pickle.load(f)
        print(f"Appending to existing {len(old_positions)} positions...")
        all_positions = old_positions + new_positions
        all_results = old_results + new_results
    else:
        all_positions = new_positions
        all_results = new_results
    with open(outfile, 'wb') as f:
        pickle.dump((all_positions, all_results), f)
    print(f"Extracted {len(new_positions)} new positions.")
    print(f"Total positions in pgn_data.pkl: {len(all_positions)}")
    print("Now run time_train.py to start/continue incremental training.")

if __name__ == '__main__':
    main()
