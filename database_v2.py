#!/usr/bin/env python3
"""Phase-A audited importer (final corrected)."""

import os, sqlite3, datetime
from pathlib import Path
from board import ChessBoard
from move_helpers import move_to_str, move_to_san
from pgn_utils_v2 import parse_pgn_content_detailed
from opening import normalize_position_key

CHESS_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("CHESS_AI_TEST_DB", str(CHESS_DIR / "chess_ai.db"))
SCHEMA_VERSION = 6

CREATE_GAMES = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_username TEXT,
    site TEXT,
    event TEXT,
    date TEXT,
    round TEXT,
    white TEXT NOT NULL,
    black TEXT NOT NULL,
    white_elo INTEGER,
    black_elo INTEGER,
    result TEXT NOT NULL,
    eco TEXT,
    opening TEXT,
    time_control TEXT,
    termination TEXT,
    raw_pgn TEXT NOT NULL,
    game_hash TEXT UNIQUE NOT NULL,
    imported_at TEXT NOT NULL,
    canonical_game_hash TEXT,
    platform_game_id TEXT,
    structural_game_hash TEXT,
    source_class TEXT NOT NULL DEFAULT 'production'
);
"""

CREATE_POSITIONS = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fen TEXT UNIQUE NOT NULL,
    canonical_fen TEXT
);
"""

CREATE_GAME_MOVES = """
CREATE TABLE IF NOT EXISTS game_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    position_id INTEGER NOT NULL,
    ply INTEGER NOT NULL,
    uci TEXT,
    san TEXT,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (position_id) REFERENCES positions(id),
    UNIQUE(game_id, ply)
);
"""

CREATE_IMPORT_BATCHES = """
CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_username TEXT,
    source_file TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source_records INTEGER,
    accepted INTEGER,
    new_games INTEGER,
    duplicate_exact INTEGER,
    duplicate_semantic INTEGER,
    duplicate_platform INTEGER,
    possible_duplicate INTEGER,
    metadata_conflict INTEGER,
    zero_move INTEGER,
    invalid INTEGER,
    error INTEGER,
    status TEXT NOT NULL
);
"""

CREATE_IMPORT_RECORDS = """
CREATE TABLE IF NOT EXISTS import_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER,
    source_file TEXT,
    source_game_number INTEGER,
    raw_pgn_hash TEXT,
    canonical_game_hash TEXT,
    platform_game_id TEXT,
    structural_game_hash TEXT,
    parser_status TEXT NOT NULL,
    database_status TEXT,
    database_game_id INTEGER,
    failure_reason TEXT,
    failing_ply INTEGER,
    failing_token TEXT,
    imported_at TEXT NOT NULL
);
"""

CREATE_SYNC_STATE = """
CREATE TABLE IF NOT EXISTS sync_state (
    source TEXT NOT NULL,
    source_username TEXT NOT NULL,
    last_successful_sync_at INTEGER,
    last_batch_id INTEGER,
    tree_dirty INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT,
    PRIMARY KEY (source, source_username)
);
"""

CREATE_SYNC_JOBS = """
CREATE TABLE IF NOT EXISTS sync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_username TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    phase TEXT,
    cursor_before INTEGER,
    cursor_after INTEGER,
    batch_id INTEGER,
    downloaded_count INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    imported_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    zero_move_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    fatal_count INTEGER NOT NULL DEFAULT 0,
    tree_new_count INTEGER NOT NULL DEFAULT 0,
    tree_rebuilt INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    heartbeat_at TEXT,
    worker_pid INTEGER,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    updated_at TEXT,
    finished_at TEXT
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_game_moves_game_id ON game_moves(game_id);",
    "CREATE INDEX IF NOT EXISTS idx_game_moves_position_id ON game_moves(position_id);",
    "CREATE INDEX IF NOT EXISTS idx_games_game_hash ON games(game_hash);",
    "CREATE INDEX IF NOT EXISTS idx_games_canonical_game_hash ON games(canonical_game_hash);",
    "CREATE INDEX IF NOT EXISTS idx_games_platform_game_id ON games(platform_game_id);",
    "CREATE INDEX IF NOT EXISTS idx_games_structural_game_hash ON games(structural_game_hash);",
    "CREATE INDEX IF NOT EXISTS idx_games_white ON games(white);",
    "CREATE INDEX IF NOT EXISTS idx_games_black ON games(black);",
    "CREATE INDEX IF NOT EXISTS idx_games_date ON games(date);",
    "CREATE INDEX IF NOT EXISTS idx_games_eco ON games(eco);",
    "CREATE INDEX IF NOT EXISTS idx_import_records_batch_id ON import_records(batch_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_jobs_active ON sync_jobs(source, source_username) WHERE status IN ('queued', 'running');",
]

CREATE_POSITION_ANALYSIS = """
CREATE TABLE IF NOT EXISTS position_analysis (
    position_id               INTEGER NOT NULL,
    model_id                  TEXT    NOT NULL,
    model_sha256              TEXT    NOT NULL,
    eval_semantic_version     INTEGER NOT NULL,
    search_semantic_version   INTEGER NOT NULL,
    tt_semantic_version       INTEGER NOT NULL,
    multipv                   INTEGER NOT NULL DEFAULT 1,
    analysis_mode             TEXT    NOT NULL DEFAULT 'unlimited',
    history_context           TEXT    NOT NULL DEFAULT 'unknown',
    accepted_depth            INTEGER NOT NULL,
    best_move                 TEXT,
    best_score                REAL,
    accepted_root_json        TEXT,
    nodes                     INTEGER,
    q_nodes                   INTEGER,
    elapsed_seconds           REAL,
    created_at                TEXT    NOT NULL,
    updated_at                TEXT    NOT NULL,
    PRIMARY KEY (
        position_id,
        model_sha256,
        eval_semantic_version,
        search_semantic_version,
        tt_semantic_version,
        multipv,
        analysis_mode,
        history_context
    ),
    FOREIGN KEY (position_id) REFERENCES positions(id)
);
"""

SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
"""



def _migrate_schema_5(conn):
    """Migrate schema 4 -> 5: canonical identity tables + seed data.

    Runs inside the caller's transaction. Does not commit itself.
    """
    now = datetime.datetime.utcnow().isoformat()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS canonical_players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL UNIQUE,
            display_name TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_player_id INTEGER NOT NULL
                REFERENCES canonical_players(id)
                ON DELETE CASCADE,
            alias TEXT NOT NULL UNIQUE,
            source TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_player_aliases_canonical_player_id
        ON player_aliases(canonical_player_id)
    """)

    conn.execute("""
        INSERT OR IGNORE INTO canonical_players
            (canonical_name, display_name, created_at)
        VALUES (?, ?, ?)
    """, ("jothi", "Jothi", now))

    conn.execute("""
        INSERT OR IGNORE INTO player_aliases
            (canonical_player_id, alias, source, created_at)
        VALUES
            (
                (SELECT id FROM canonical_players WHERE canonical_name = ?),
                ?,
                ?,
                ?
            )
    """, ("jothi", "jothilingam", "lichess", now))

    conn.execute("""
        INSERT OR IGNORE INTO player_aliases
            (canonical_player_id, alias, source, created_at)
        VALUES
            (
                (SELECT id FROM canonical_players WHERE canonical_name = ?),
                ?,
                ?,
                ?
            )
    """, ("jothi", "jothi_lingam", "chesscom", now))

    # Seed validation
    canonical_count = conn.execute(
        "SELECT COUNT(*) FROM canonical_players"
    ).fetchone()[0]

    alias_count = conn.execute(
        "SELECT COUNT(*) FROM player_aliases"
    ).fetchone()[0]

    if canonical_count != 1 or alias_count != 2:
        raise RuntimeError(
            f"canonical identity seed validation failed: "
            f"players={canonical_count}, aliases={alias_count}"
        )

    rows = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT alias, source FROM player_aliases ORDER BY alias"
        )
    }

    expected = {
        "jothilingam": "lichess",
        "jothi_lingam": "chesscom",
    }

    if rows != expected:
        raise RuntimeError(f"alias mapping validation failed: {rows}")



def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute(CREATE_GAMES)
    conn.execute(CREATE_POSITIONS)
    conn.execute(CREATE_GAME_MOVES)
    conn.execute(CREATE_IMPORT_BATCHES)
    conn.execute(CREATE_IMPORT_RECORDS)
    conn.execute(CREATE_SYNC_STATE)
    conn.execute(CREATE_SYNC_JOBS)
    conn.execute(CREATE_POSITION_ANALYSIS)
    _ensure_sync_state_tree_dirty(conn)
    for idx in INDEXES:
        conn.execute(idx)
    conn.execute(SCHEMA_VERSION_TABLE)

    cur = conn.execute("SELECT version FROM schema_version")
    row = cur.fetchone()
    current_version = int(row[0]) if row is not None else 0

    if current_version < SCHEMA_VERSION:
        try:
            conn.execute("BEGIN IMMEDIATE")

            if current_version < 5:
                _migrate_schema_5(conn)

            if row is None:
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            else:
                conn.execute(
                    "UPDATE schema_version SET version = ?",
                    (SCHEMA_VERSION,),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return conn


def create_sync_job(source, source_username):
    """Create a queued sync job for one source/user.

    Returns the new job_id, or None if an active job already exists.
    """
    if source not in ("lichess", "chesscom"):
        raise ValueError(f"invalid source: {source}")

    conn = _get_db()
    try:
        existing = conn.execute(
            """
            SELECT id FROM sync_jobs
            WHERE source = ? AND source_username = ?
              AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (source, source_username),
        ).fetchone()

        if existing:
            return None

        now = datetime.datetime.utcnow().isoformat()
        cur = conn.execute(
            """
            INSERT INTO sync_jobs
                (source, source_username, status, phase, created_at, updated_at)
            VALUES (?, ?, 'queued', 'queued', ?, ?)
            """,
            (source, source_username, now, now),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_sync_job(job_id):
    """Return a sync_jobs row as a dict, or None."""
    conn = _get_db()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM sync_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_sync_job(job_id, **fields):
    """Update mutable sync_jobs fields.

    Only whitelisted columns may be updated to avoid accidental schema drift.
    """
    allowed = {
        'status', 'phase', 'cursor_before', 'cursor_after', 'batch_id',
        'downloaded_count', 'parsed_count', 'imported_count',
        'duplicate_count', 'zero_move_count', 'skipped_count',
        'fatal_count', 'tree_new_count', 'tree_rebuilt', 'error',
        'cancel_requested', 'heartbeat_at', 'worker_pid', 'retry_count',
        'last_error', 'chunk_index', 'started_at', 'updated_at', 'finished_at',
    }

    if not fields:
        return

    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f'Unknown sync_jobs fields: {sorted(unknown)}')

    if 'updated_at' not in fields:
        fields['updated_at'] = datetime.datetime.utcnow().isoformat()

    assignments = ', '.join(f'{k} = ?' for k in fields)
    values = list(fields.values())
    values.append(job_id)

    conn = _get_db()
    try:
        conn.execute(
            f"UPDATE sync_jobs SET {assignments} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def mark_stale_sync_jobs_interrupted(stale_after_seconds=300):
    """Mark stale active jobs as interrupted.

    Rules:
      running + stale heartbeat   -> interrupted
      queued   + stale created_at -> interrupted
      fresh queued                -> remain queued
    """
    now = datetime.datetime.utcnow()
    now_iso = now.isoformat()
    cutoff = (
        now - datetime.timedelta(seconds=stale_after_seconds)
    ).isoformat()

    conn = _get_db()
    try:
        cur_running = conn.execute(
            """
            UPDATE sync_jobs
            SET status = 'interrupted',
                phase = 'interrupted',
                error = COALESCE(error, 'stale heartbeat'),
                finished_at = ?,
                updated_at = ?
            WHERE status = 'running'
              AND (heartbeat_at IS NULL OR heartbeat_at < ?)
            """,
            (now_iso, now_iso, cutoff),
        )

        cur_queued = conn.execute(
            """
            UPDATE sync_jobs
            SET status = 'interrupted',
                phase = 'interrupted',
                error = COALESCE(error, 'stale queued job'),
                finished_at = ?,
                updated_at = ?
            WHERE status = 'queued'
              AND created_at < ?
            """,
            (now_iso, now_iso, cutoff),
        )

        conn.commit()
        return cur_running.rowcount + cur_queued.rowcount
    finally:
        conn.close()


def claim_sync_job(job_id, worker_pid):
    """Claim a queued job atomically.

    Returns True only if exactly one queued job was changed to running.
    """
    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        cur = conn.execute(
            """
            UPDATE sync_jobs
            SET status = 'running',
                phase = 'downloading',
                started_at = ?,
                worker_pid = ?,
                heartbeat_at = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'queued'
            """,
            (now, int(worker_pid), now, now, int(job_id)),
        )

        if cur.rowcount != 1:
            return False

        conn.commit()
        return True
    finally:
        conn.close()


def heartbeat_sync_job(job_id, worker_pid):
    """Refresh a running job's heartbeat.

    This must never modify game, cursor, tree, or chunk state.
    worker_pid is required and must match the claimed worker.

    Returns True if exactly one running job was updated.
    """
    if worker_pid is None:
        raise ValueError('worker_pid is required for heartbeat_sync_job')

    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        cur = conn.execute(
            """
            UPDATE sync_jobs
            SET heartbeat_at = ?,
                updated_at = ?
            WHERE id = ?
              AND status = 'running'
              AND worker_pid = ?
            """,
            (now, now, int(job_id), int(worker_pid)),
        )

        if cur.rowcount != 1:
            return False

        conn.commit()
        return True
    finally:
        conn.close()


FATAL_SYNC_PARSER_STATUSES = {
    "invalid_pgn",
    "illegal_move",
}


def reject_fatal_sync_records(records):
    """Raise ValueError if any record has a fatal parser status.

    Non-fatal statuses:
      accepted
      zero_move
      unsupported_variant

    Fatal statuses:
      invalid_pgn
      illegal_move

    The background-sync worker must call this BEFORE insert_game_audited()
    so a chunk containing a fatal parser record is never partially imported.
    """
    if not records:
        return

    fatal = [
        r for r in records
        if r.get("parser_status") in FATAL_SYNC_PARSER_STATUSES
    ]

    if fatal:
        first = fatal[0]
        raise ValueError(
            "fatal parser record in sync chunk: "
            f"status={first.get('parser_status')} "
            f"reason={first.get('failure_reason')} "
            f"source_index={first.get('source_index')}"
        )

    return


def _get_or_create_position(conn, fen):
    cur = conn.execute("SELECT id FROM positions WHERE fen = ?", (fen,))
    row = cur.fetchone()
    if row:
        return row[0]
    canonical_fen = normalize_position_key(fen)
    cur = conn.execute(
        "INSERT INTO positions (fen, canonical_fen) VALUES (?, ?)",
        (fen, canonical_fen),
    )
    return cur.lastrowid


def get_sync_state(source, source_username):
    """Return the sync cursor for one source/username, or None."""
    conn = _get_db()
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT source, source_username, last_successful_sync_at,
                   last_batch_id, tree_dirty, updated_at
            FROM sync_state
            WHERE source = ? AND source_username = ?
            """,
            (source, source_username),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def finalize_sync_job_success(
    job_id,
    worker_pid,
    source,
    source_username,
    cursor_after,
    last_batch_id,
    tree_rebuilt,
):
    """Atomically finalize a successful background sync job.

    This requires the calling worker to be the current owner:

      sync_jobs.worker_pid == worker_pid

    and the job must still be running.

    One SQLite transaction updates both durable states:

      sync_state:
        last_successful_sync_at = cursor_after
        last_batch_id           = last_batch_id
        tree_dirty              = 0

      sync_jobs:
        status         = completed
        phase          = complete
        cursor_after   = cursor_after
        tree_rebuilt   = tree_rebuilt
        finished_at    = now
        updated_at     = now
        worker_pid     = NULL
        heartbeat_at   = NULL
        error          = NULL

    If the job update affects anything other than exactly one row,
    the entire transaction rolls back.
    """
    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO sync_state
                (source, source_username, last_successful_sync_at,
                 last_batch_id, tree_dirty, updated_at)
            VALUES (?, ?, ?, ?, 0, ?)
            ON CONFLICT(source, source_username)
            DO UPDATE SET
                last_successful_sync_at = excluded.last_successful_sync_at,
                last_batch_id = excluded.last_batch_id,
                tree_dirty = excluded.tree_dirty,
                updated_at = excluded.updated_at
            """,
            (source, source_username, int(cursor_after), last_batch_id, now),
        )

        cur = conn.execute(
            """
            UPDATE sync_jobs
            SET status = 'completed',
                phase = 'complete',
                cursor_after = ?,
                tree_rebuilt = ?,
                finished_at = ?,
                updated_at = ?,
                worker_pid = NULL,
                heartbeat_at = NULL,
                error = NULL
            WHERE id = ?
              AND source = ?
              AND source_username = ?
              AND status = 'running'
              AND worker_pid = ?
            """,
            (
                int(cursor_after),
                1 if tree_rebuilt else 0,
                now,
                now,
                int(job_id),
                source,
                source_username,
                int(worker_pid),
            ),
        )

        if cur.rowcount != 1:
            raise RuntimeError(
                'sync job finalization rejected: '
                'job not running, identity mismatch, or owner mismatch'
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fail_sync_job_with_fatal_audit(
    job_id,
    worker_pid,
    source,
    source_username,
    records,
    fatal_records,
    error="fatal parser record in sync chunk",
):
    """Atomically record fatal parser failures and mark the job failed."""
    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        cur = conn.execute(
            """
            INSERT INTO import_batches
                (source, source_username, source_file, started_at, status)
            VALUES (?, ?, ?, ?, 'running')
            """,
            (
                source,
                source_username,
                f"sync_job_{int(job_id)}_fatal.pgn",
                now,
            ),
        )
        batch_id = cur.lastrowid

        for rec in records:
            status = rec.get("parser_status", "invalid")

            if status in FATAL_SYNC_PARSER_STATUSES:
                db_status = "not_inserted"
                failure_reason = rec.get("failure_reason")
                failing_ply = rec.get("failing_ply")
                failing_token = rec.get("failing_token")
            else:
                db_status = "not_inserted_due_to_batch_failure"
                failure_reason = "batch rejected because one or more games failed parsing"
                failing_ply = None
                failing_token = None

            conn.execute(
                """
                INSERT INTO import_records
                    (batch_id, source_file, source_game_number, raw_pgn_hash,
                     canonical_game_hash, platform_game_id, structural_game_hash,
                     parser_status, database_status, failure_reason,
                     failing_ply, failing_token, imported_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    f"sync_job_{int(job_id)}_fatal.pgn",
                    rec.get("source_index"),
                    rec.get("raw_pgn_hash"),
                    rec.get("canonical_game_hash"),
                    rec.get("platform_game_id"),
                    rec.get("structural_game_hash"),
                    status,
                    db_status,
                    failure_reason,
                    failing_ply,
                    failing_token,
                    now,
                ),
            )

        accepted_count = 0
        zero_move_count = 0
        skipped_count = 0
        fatal_count = 0

        for r in records:
            status = r.get("parser_status")

            if status == "accepted":
                accepted_count += 1
            elif status == "zero_move":
                zero_move_count += 1
            elif status == "unsupported_variant":
                skipped_count += 1
            elif status in FATAL_SYNC_PARSER_STATUSES:
                fatal_count += 1
            else:
                skipped_count += 1

        # import_batches.invalid is the broad non-inserted/error bucket.
        # For a rejected chunk, include both unsupported variants and fatal records.
        invalid_count = skipped_count + fatal_count

        conn.execute(
            """
            UPDATE import_batches
            SET source_records = ?,
                finished_at = ?,
                status = 'complete',
                accepted = ?,
                new_games = 0,
                duplicate_exact = 0,
                duplicate_semantic = 0,
                duplicate_platform = 0,
                possible_duplicate = 0,
                metadata_conflict = 0,
                zero_move = ?,
                invalid = ?,
                error = 0
            WHERE id = ?
            """,
            (
                len(records),
                now,
                accepted_count,
                zero_move_count,
                invalid_count,
                batch_id,
            ),
        )

        cur2 = conn.execute(
            """
            UPDATE sync_jobs
            SET status = 'failed',
                phase = 'failed',
                fatal_count = fatal_count + ?,
                error = ?,
                last_error = ?,
                worker_pid = NULL,
                heartbeat_at = NULL,
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
              AND source = ?
              AND source_username = ?
              AND status = 'running'
              AND worker_pid = ?
            """,
            (
                len(fatal_records),
                error,
                error,
                now,
                now,
                int(job_id),
                source,
                source_username,
                int(worker_pid),
            ),
        )

        if cur2.rowcount != 1:
            raise RuntimeError(
                'fatal sync job failure rejected: job not running or owner mismatch'
            )

        conn.commit()

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def terminate_sync_job_with_owner(
    job_id,
    worker_pid,
    source,
    source_username,
    terminal_status,
    phase,
    error=None,
):
    """Safely move a running job to a terminal state.

    The update is conditional on:

      id, source, source_username, status='running', worker_pid

    If anything fails, the transaction rolls back and no terminal state is
    written. This prevents a stale worker from updating a newly owned job.
    """
    if terminal_status not in ("failed", "canceled"):
        raise ValueError(f"invalid terminal_status: {terminal_status}")

    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        cur = conn.execute(
            """
            UPDATE sync_jobs
            SET status = ?,
                phase = ?,
                error = ?,
                last_error = ?,
                worker_pid = NULL,
                heartbeat_at = NULL,
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
              AND source = ?
              AND source_username = ?
              AND status = 'running'
              AND worker_pid = ?
            """,
            (
                terminal_status,
                phase,
                error,
                error,
                now,
                now,
                int(job_id),
                source,
                source_username,
                int(worker_pid),
            ),
        )

        if cur.rowcount != 1:
            raise RuntimeError(
                'sync job terminal update rejected: '
                'job not running, identity mismatch, or owner mismatch'
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_active_sync_job(source, source_username):
    """Return the active job_id for source/user, or None."""
    conn = _get_db()
    try:
        row = conn.execute(
            """
            SELECT id
            FROM sync_jobs
            WHERE source = ?
              AND source_username = ?
              AND status IN ('queued', 'running')
            ORDER BY id
            LIMIT 1
            """,
            (source, source_username),
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def request_cancel_sync_job(job_id):
    """Ask a running job to cancel at the next safe boundary.

    Returns True only if exactly one running job was updated.
    """
    now = datetime.datetime.utcnow().isoformat()

    conn = _get_db()
    try:
        cur = conn.execute(
            """
            UPDATE sync_jobs
            SET cancel_requested = 1,
                updated_at = ?
            WHERE id = ?
              AND status = 'running'
            """,
            (now, int(job_id)),
        )

        if cur.rowcount != 1:
            return False

        conn.commit()
        return True
    finally:
        conn.close()


def set_sync_state(source, source_username, last_successful_sync_at=None, last_batch_id=None, tree_dirty=None):
    """Create or update the sync cursor for one source/username.

    tree_dirty=None means preserve the existing value.
    tree_dirty=0 explicitly clears the dirty flag.
    tree_dirty=1 explicitly marks the tree as needing a rebuild.
    """
    conn = _get_db()
    try:
        now = datetime.datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT tree_dirty FROM sync_state WHERE source=? AND source_username=?",
            (source, source_username),
        ).fetchone()

        if existing is None:
            flag = 0 if tree_dirty is None else int(tree_dirty)
            conn.execute(
                """
                INSERT INTO sync_state
                    (source, source_username, last_successful_sync_at, last_batch_id, tree_dirty, updated_at)
                VALUES (?,?,?,?,?,?)
                """,
                (source, source_username, last_successful_sync_at, last_batch_id, flag, now),
            )
        else:
            flag = existing[0] if tree_dirty is None else int(tree_dirty)
            conn.execute(
                """
                UPDATE sync_state
                SET last_successful_sync_at = ?,
                    last_batch_id = ?,
                    tree_dirty = ?,
                    updated_at = ?
                WHERE source = ? AND source_username = ?
                """,
                (last_successful_sync_at, last_batch_id, flag, now, source, source_username),
            )

        conn.commit()
    finally:
        conn.close()



def _ensure_sync_state_tree_dirty(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sync_state)")]
    if 'tree_dirty' not in cols:
        conn.execute(
            "ALTER TABLE sync_state "
            "ADD COLUMN tree_dirty INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()


def set_sync_tree_dirty(source, source_username, batch_id=None, dirty=True):
    """Set or clear tree_dirty without advancing the sync cursor."""
    conn = _get_db()
    try:
        now = datetime.datetime.utcnow().isoformat()
        existing = conn.execute(
            "SELECT tree_dirty FROM sync_state WHERE source=? AND source_username=?",
            (source, source_username),
        ).fetchone()

        flag = 1 if dirty else 0

        if existing is None:
            conn.execute(
                """
                INSERT INTO sync_state
                    (source, source_username, last_successful_sync_at, last_batch_id, tree_dirty, updated_at)
                VALUES (?,?,NULL,?,?,?)
                """,
                (source, source_username, batch_id, flag, now),
            )
        else:
            conn.execute(
                """
                UPDATE sync_state
                SET tree_dirty = ?,
                    last_batch_id = COALESCE(?, last_batch_id),
                    updated_at = ?
                WHERE source = ? AND source_username = ?
                """,
                (flag, batch_id, now, source, source_username),
            )

        conn.commit()
    finally:
        conn.close()


def record_parser_failure_batch(records, source="test", source_file=None, source_username=None):
    """Record a failed parser batch without inserting any games."""
    conn = _get_db()
    try:
        now = datetime.datetime.utcnow().isoformat()

        cur = conn.execute(
            "INSERT INTO import_batches (source, source_username, source_file, started_at, status) VALUES (?,?,?,?,'running')",
            (source, source_username, source_file, now),
        )
        batch_id = cur.lastrowid

        failed = 0
        for rec in records:
            status = rec.get("parser_status", "invalid")

            if status != "accepted":
                failed += 1
                db_status = "not_inserted"
                failure_reason = rec.get("failure_reason")
                failing_ply = rec.get("failing_ply")
                failing_token = rec.get("failing_token")
            else:
                db_status = "not_inserted_due_to_batch_failure"
                failure_reason = "batch rejected because one or more games failed parsing"
                failing_ply = None
                failing_token = None

            conn.execute(
                """INSERT INTO import_records
                   (batch_id, source_file, source_game_number, raw_pgn_hash,
                    canonical_game_hash, platform_game_id, structural_game_hash,
                    parser_status, database_status, failure_reason,
                    failing_ply, failing_token, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch_id,
                    source_file,
                    rec.get("source_index"),
                    rec.get("raw_pgn_hash"),
                    rec.get("canonical_game_hash"),
                    rec.get("platform_game_id"),
                    rec.get("structural_game_hash"),
                    status,
                    db_status,
                    failure_reason,
                    failing_ply,
                    failing_token,
                    now,
                ),
            )

        accepted_count = len(records) - failed
        conn.execute(
            """UPDATE import_batches
               SET source_records = ?, finished_at = ?, status = 'complete',
                   accepted = ?, new_games = 0,
                   duplicate_exact = 0, duplicate_semantic = 0,
                   duplicate_platform = 0, possible_duplicate = 0,
                   metadata_conflict = 0, zero_move = 0, invalid = ?, error = 0
               WHERE id = ?""",
            (len(records), now, accepted_count, failed, batch_id),
        )
        conn.commit()

        return {
            "status": "import_failed",
            "batch_id": batch_id,
            "source_records": len(records),
            "accepted": accepted_count,
            "failed": failed,
            "new": 0,
            "duplicate_exact": 0,
            "duplicate_semantic": 0,
            "duplicate_platform": 0,
            "possible_duplicate": 0,
            "metadata_conflict": 0,
            "zero_move": 0,
            "invalid": failed,
            "error": 0,
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _insert_game_row(conn, rec, source="test", source_username=None):
    headers = rec["headers"]

    def _elo(key):
        try: return int(headers.get(key)) if headers.get(key) else None
        except (ValueError, TypeError): return None

    cur = conn.execute(
        """INSERT INTO games
           (source, source_username, site, event, date, round, white, black, white_elo, black_elo,
            result, eco, opening, time_control, termination, raw_pgn, game_hash,
            imported_at, canonical_game_hash, platform_game_id, structural_game_hash,
            source_class)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            source,
            source_username,
            headers.get("site"),
            headers.get("event"),
            rec.get("normalized_date") or headers.get("date") or headers.get("utcdate"),
            headers.get("round"),
            headers.get("white", "?"),
            headers.get("black", "?"),
            _elo("whiteelo"),
            _elo("blackelo"),
            headers.get("result", "*"),
            headers.get("eco"),
            headers.get("opening"),
            headers.get("timecontrol"),
            headers.get("termination"),
            rec["raw_pgn"],
            rec["raw_pgn_hash"],
            datetime.datetime.utcnow().isoformat(),
            rec["canonical_game_hash"],
            rec["platform_game_id"],
            rec["structural_game_hash"],
            "test" if source == "test" else "production",
        ),
    )
    return cur.lastrowid


def insert_game_audited(
    records,
    source="test",
    source_file=None,
    source_username=None,
    mark_tree_dirty=False,
    job_id=None,
    chunk_index=None,
    previous_chunk_index=None,
    chunk_downloaded_count=None,
    chunk_parsed_count=None,
):
    summary = {
        "source_records": len(records),
        "new": 0,
        "tree_new": 0,
        "duplicate_exact": 0,
        "duplicate_semantic": 0,
        "duplicate_platform": 0,
        "possible_duplicate": 0,
        "metadata_conflict": 0,
        "zero_move": 0,
        "invalid": 0,
        "error": 0,
    }

    if job_id is not None:
        try:
            _job_id = int(job_id)
            _chunk_index = int(chunk_index)
            _previous_chunk_index = int(previous_chunk_index)
        except (TypeError, ValueError) as e:
            raise ValueError(f'Invalid background job checkpoint field: {e}') from e

        if _job_id < 1:
            raise ValueError('job_id must be >= 1')

        if chunk_downloaded_count is None or chunk_parsed_count is None:
            raise ValueError(
                'chunk_downloaded_count and chunk_parsed_count are required when job_id is provided'
            )

        _chunk_downloaded = int(chunk_downloaded_count)
        _chunk_parsed = int(chunk_parsed_count)

        if _chunk_index < 1:
            raise ValueError('chunk_index must be >= 1')

        if _previous_chunk_index < 0:
            raise ValueError('previous_chunk_index must be >= 0')

        if _chunk_index != _previous_chunk_index + 1:
            raise ValueError('chunk_index must equal previous_chunk_index + 1')

        if _chunk_downloaded < 0 or _chunk_parsed < 0:
            raise ValueError('chunk_downloaded_count and chunk_parsed_count must be >= 0')

        if _chunk_parsed > _chunk_downloaded:
            raise ValueError('chunk_parsed_count cannot exceed chunk_downloaded_count')

    conn = _get_db()
    try:
        now = datetime.datetime.utcnow().isoformat()
        cur = conn.execute(
            "INSERT INTO import_batches (source, source_username, source_file, started_at, status) VALUES (?,?,?,?,'running')",
            (source, source_username, source_file, now),
        )
        batch_id = cur.lastrowid

        for rec in records:
            status = rec["parser_status"]

            # zero_move is insertable as a game record with one ply-0 row.
            if status == "zero_move":
                summary["zero_move"] += 1
            elif status != "accepted":
                summary["invalid"] += 1
                conn.execute(
                    """INSERT INTO import_records
                       (batch_id, source_file, source_game_number, raw_pgn_hash,
                        canonical_game_hash, platform_game_id, structural_game_hash,
                        parser_status, database_status, failure_reason,
                        failing_ply, failing_token, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        batch_id,
                        source_file,
                        rec["source_index"],
                        rec["raw_pgn_hash"],
                        rec["canonical_game_hash"],
                        rec["platform_game_id"],
                        rec["structural_game_hash"],
                        status,
                        "not_inserted",
                        rec["failure_reason"],
                        rec["failing_ply"],
                        rec["failing_token"],
                        now,
                    ),
                )
                continue

            # Exact raw hash
            row = conn.execute(
                "SELECT id FROM games WHERE game_hash = ?", (rec["raw_pgn_hash"],)
            ).fetchone()
            if row:
                summary["duplicate_exact"] += 1
                conn.execute(
                    """INSERT INTO import_records
                       (batch_id, source_file, source_game_number, raw_pgn_hash,
                        canonical_game_hash, platform_game_id, structural_game_hash,
                        parser_status, database_status, database_game_id, imported_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        batch_id, source_file, rec["source_index"], rec["raw_pgn_hash"],
                        rec["canonical_game_hash"], rec["platform_game_id"],
                        rec["structural_game_hash"], "accepted", "duplicate_exact",
                        row[0], now,
                    ),
                )
                continue

            if rec["platform_game_id"]:
                row = conn.execute(
                    """SELECT id, white, black, date, result, structural_game_hash
                       FROM games WHERE platform_game_id = ?""",
                    (rec["platform_game_id"],),
                ).fetchone()
                if row:
                    db_id, db_white, db_black, db_date, db_result, db_structural = row
                    conflict_reasons = []
                    if db_white != rec["headers"].get("white", "?"):
                        conflict_reasons.append("players differ")
                    if db_black != rec["headers"].get("black", "?"):
                        conflict_reasons.append("players differ")
                    if db_date != rec.get("normalized_date", ""):
                        conflict_reasons.append("date differs")
                    if db_result != rec["headers"].get("result", "*"):
                        conflict_reasons.append("result differs")
                    if db_structural != rec["structural_game_hash"]:
                        conflict_reasons.append("moves differ")

                    if not conflict_reasons:
                        summary["duplicate_platform"] += 1
                        db_status = "duplicate_platform"
                    else:
                        summary["metadata_conflict"] += 1
                        db_status = "metadata_conflict"
                        db_id = None
                        failure_reason = "; ".join(dict.fromkeys(conflict_reasons))

                    conn.execute(
                        """INSERT INTO import_records
                           (batch_id, source_file, source_game_number, raw_pgn_hash,
                            canonical_game_hash, platform_game_id, structural_game_hash,
                            parser_status, database_status, database_game_id,
                            failure_reason, imported_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            batch_id, source_file, rec["source_index"], rec["raw_pgn_hash"],
                            rec["canonical_game_hash"], rec["platform_game_id"],
                            rec["structural_game_hash"], "accepted", db_status,
                            db_id, failure_reason if db_status == "metadata_conflict" else None,
                            now,
                        ),
                    )
                    continue

            if rec["canonical_game_hash"]:
                row = conn.execute(
                    "SELECT id FROM games WHERE canonical_game_hash = ?",
                    (rec["canonical_game_hash"],),
                ).fetchone()
                if row:
                    summary["duplicate_semantic"] += 1
                    conn.execute(
                        """INSERT INTO import_records
                           (batch_id, source_file, source_game_number, raw_pgn_hash,
                            canonical_game_hash, platform_game_id, structural_game_hash,
                            parser_status, database_status, database_game_id, imported_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            batch_id, source_file, rec["source_index"], rec["raw_pgn_hash"],
                            rec["canonical_game_hash"], rec["platform_game_id"],
                            rec["structural_game_hash"], "accepted", "duplicate_semantic",
                            row[0], now,
                        ),
                    )
                    continue

            if rec["structural_game_hash"]:
                row = conn.execute(
                    "SELECT id FROM games WHERE structural_game_hash = ?",
                    (rec["structural_game_hash"],),
                ).fetchone()
                if row:
                    summary["possible_duplicate"] += 1
                    conn.execute(
                        """INSERT INTO import_records
                           (batch_id, source_file, source_game_number, raw_pgn_hash,
                            canonical_game_hash, platform_game_id, structural_game_hash,
                            parser_status, database_status, database_game_id, imported_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            batch_id, source_file, rec["source_index"], rec["raw_pgn_hash"],
                            rec["canonical_game_hash"], rec["platform_game_id"],
                            rec["structural_game_hash"], "accepted", "possible_duplicate",
                            row[0], now,
                        ),
                    )
                    continue

            # New game
            game_id = _insert_game_row(conn, rec, source=source, source_username=source_username)
            board = ChessBoard()
            start_fen = board.to_fen()
            start_pos_id = _get_or_create_position(conn, start_fen)
            conn.execute(
                "INSERT INTO game_moves (game_id, position_id, ply, uci, san) VALUES (?,?,0,NULL,NULL)",
                (game_id, start_pos_id),
            )
            for ply, move in enumerate(rec["moves"], 1):
                uci = move_to_str(move)
                san = move_to_san(move, board)
                board.make_move(move)
                fen = board.to_fen()
                pos_id = _get_or_create_position(conn, fen)
                conn.execute(
                    "INSERT INTO game_moves (game_id, position_id, ply, uci, san) VALUES (?,?,?,?,?)",
                    (game_id, pos_id, ply, uci, san),
                )

            summary["new"] += 1
            if rec.get("parser_status") == "accepted":
                summary["tree_new"] += 1

            conn.execute(
                """INSERT INTO import_records
                   (batch_id, source_file, source_game_number, raw_pgn_hash,
                    canonical_game_hash, platform_game_id, structural_game_hash,
                    parser_status, database_status, database_game_id, imported_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    batch_id, source_file, rec["source_index"], rec["raw_pgn_hash"],
                    rec["canonical_game_hash"], rec["platform_game_id"],
                    rec["structural_game_hash"], rec.get("parser_status", "accepted"),
                    "new", game_id, now,
                ),
            )

        accepted = (
            summary["new"] + summary["duplicate_exact"] + summary["duplicate_semantic"] +
            summary["duplicate_platform"] + summary["possible_duplicate"] +
            summary["metadata_conflict"]
        )

        conn.execute(
            """UPDATE import_batches
               SET source_records = ?, finished_at = ?, status = 'complete',
                   accepted = ?,
                   new_games = ?, duplicate_exact = ?, duplicate_semantic = ?,
                   duplicate_platform = ?, possible_duplicate = ?, metadata_conflict = ?,
                   zero_move = ?, invalid = ?, error = 0
               WHERE id = ?""",
            (
                summary["source_records"],
                datetime.datetime.utcnow().isoformat(),
                accepted,
                summary["new"],
                summary["duplicate_exact"],
                summary["duplicate_semantic"],
                summary["duplicate_platform"],
                summary["possible_duplicate"],
                summary["metadata_conflict"],
                summary["zero_move"],
                summary["invalid"],
                batch_id,
            ),
        )
        # When requested by the background-sync chunk path, mark the
        # opening tree dirty inside THIS SAME SQLite transaction.
        #
        # Existing callers keep mark_tree_dirty=False and therefore retain
        # their current behavior.
        if mark_tree_dirty and summary.get("tree_new", 0) > 0:
            now_tree = datetime.datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO sync_state
                    (
                        source,
                        source_username,
                        last_successful_sync_at,
                        last_batch_id,
                        tree_dirty,
                        updated_at
                    )
                VALUES (?, ?, NULL, ?, 1, ?)
                ON CONFLICT(source, source_username)
                DO UPDATE SET
                    tree_dirty = 1,
                    last_batch_id = excluded.last_batch_id,
                    updated_at = excluded.updated_at
                """,
                (
                    source,
                    source_username,
                    batch_id,
                    now_tree,
                ),
            )

        if job_id is not None:
            new_imported = int(summary.get('new', 0))
            new_duplicate = (
                int(summary.get('duplicate_exact', 0))
                + int(summary.get('duplicate_semantic', 0))
                + int(summary.get('duplicate_platform', 0))
                + int(summary.get('possible_duplicate', 0))
                + int(summary.get('metadata_conflict', 0))
            )
            new_zero_move = int(summary.get('zero_move', 0))
            new_skipped = int(summary.get('invalid', 0))
            new_tree_new = int(summary.get('tree_new', 0))

            cur = conn.execute(
                """
                UPDATE sync_jobs
                SET chunk_index = ?,
                    batch_id = ?,
                    downloaded_count = downloaded_count + ?,
                    parsed_count = parsed_count + ?,
                    imported_count = imported_count + ?,
                    duplicate_count = duplicate_count + ?,
                    zero_move_count = zero_move_count + ?,
                    skipped_count = skipped_count + ?,
                    tree_new_count = tree_new_count + ?,
                    heartbeat_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND source = ?
                  AND source_username = ?
                  AND status = 'running'
                  AND chunk_index = ?
                """,
                (
                    _chunk_index,
                    batch_id,
                    _chunk_downloaded,
                    _chunk_parsed,
                    new_imported,
                    new_duplicate,
                    new_zero_move,
                    new_skipped,
                    new_tree_new,
                    now,
                    now,
                    _job_id,
                    source,
                    source_username,
                    _previous_chunk_index,
                ),
            )

            if cur.rowcount != 1:
                raise RuntimeError(
                    'sync_jobs checkpoint rejected: '
                    'job not running, wrong identity, or unexpected chunk_index'
                )

        # Critical transaction boundary:
        # games + game_moves + import_records + tree_dirty
        # + sync_jobs checkpoint all commit together.
        conn.commit()
        summary["batch_id"] = batch_id
        return summary
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_games_from_pgn_text(
    pgn_text,
    source="manual",
    source_username=None,
    source_file=None,
):
    """Parse raw PGN text and insert it through the audited importer.

    Returns the number of newly inserted games.
    """
    from pgn_utils_v2 import parse_pgn_content_detailed

    if not pgn_text or not pgn_text.strip():
        return 0

    records = parse_pgn_content_detailed(pgn_text)
    if not records:
        return 0

    summary = insert_game_audited(
        records,
        source=source,
        source_file=source_file,
        source_username=source_username,
    )
    return int(summary.get("new", 0))
