import threading, time, random
#!/usr/bin/env python3
"""Web control for Chess AI – multi‑opponent batch testing (full)."""

import os, json, time, math, threading, subprocess, random, sqlite3, datetime, uuid, hashlib
from collections import OrderedDict
from dataclasses import dataclass, field
from flask import Response, Flask, request, jsonify, send_from_directory
from functools import wraps

from board import ChessBoard
from nn import DualNet
from static_eval import EVAL_SEMANTIC_VERSION
from search import SearchEngine, SEARCH_SEMANTIC_VERSION, CURRENT_TT_VERSION
from move_helpers import move_to_str, str_to_move, move_to_san
from opening import get_moves, get_eco, get_examples, normalize_position_key
from repertoire import (
    load_repertoire, save_repertoire, get_entry_by_fen, set_entry_by_fen,
    delete_entry_by_fen, get_all_entries, get_due_positions, calculate_interval,
    normalize_move, export_repertoire, reload_repertoire
)

HOME = os.path.expanduser("~")
CHESS_DIR = os.path.join(HOME, "chess_ai")
MODEL_PATH = os.environ.get(
    "CHESS_AI_MODEL_PATH",
    os.path.join(CHESS_DIR, "distilled_nn.pkl")
)
app = Flask(__name__, static_folder='.')

analysis_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
DB_PATH = os.environ.get(
    "CHESS_AI_DB_PATH",
    os.path.join(CHESS_DIR, 'chess_ai.db')
)


# ---------------------------------------------------------------------------
# Job Control Plane — in-memory job registry.
#
# The public Job record is JSON-safe only. Private runtime state (threads,
# SearchEngine instances, subprocesses, cancel events) lives in separate
# dicts keyed by job_id — not inside the public record.
#
# payload    = validated, non-secret job parameters
# provenance = informational trace (model path, sha256, source)
# ---------------------------------------------------------------------------
@dataclass
class Job:
    job_id: str
    job_type: str
    status: str
    created_at: float
    payload: dict = field(default_factory=dict)
    session_id: str | None = None
    reservation_token: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    cancel_requested: bool = False
    progress: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    provenance: dict = field(default_factory=dict)

    def to_json(self):
        return {
            'job_id': self.job_id,
            'job_type': self.job_type,
            'session_id': self.session_id,
            'status': self.status,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at,
            'cancel_requested': self.cancel_requested,
            'payload': self.payload,
            'progress': self.progress,
            'result': self.result,
            'error': self.error,
            'provenance': self.provenance,
        }


JOB_REGISTRY_MAX = 64
job_registry = OrderedDict()
job_registry_lock = threading.Lock()

VALID_JOB_TYPES = (
    'analysis', 'sf_analysis', 'training',
    'benchmark', 'test_batch', 'dataset',
)
JOB_ID_PREFIXES = {
    'analysis':   'ana',
    'sf_analysis': 'sfa',
    'training':   'trn',
    'benchmark':  'bench',
    'test_batch': 'test',
    'dataset':    'data',
}
TERMINAL_JOB_STATUSES = ('stopped', 'completed', 'error', 'safety_limit')

_DISPATCHABLE_JOB_TYPES = ('analysis',)


job_engines = {}
job_threads = {}
_job_sessions = {}
_job_runtime_lock = threading.Lock()

_CPU_HEAVY_SEMAPHORE = threading.Semaphore(1)


_legacy_analysis_job_id = None
_legacy_analysis_lock = threading.Lock()

# ===========================================================================
# AnalysisSession — Phase 2 foundation.
#
# Persistent analysis context for one canonical position. The job registry
# remains the execution ledger; a session survives job completion and, while
# HOT, retains its SearchEngine (TT, NN cache, heuristics) so that a stopped
# analysis can be resumed instead of restarted.
#
# Foundation only. No routes, workers, or threads touch this yet.
# ===========================================================================

HOT_MAX = 1
WARM_TTL_SEC = 1800
COLD_TTL_SEC = 86400

session_registry = OrderedDict()   # session_id -> AnalysisSession
session_lock = threading.RLock()


def _canonical_current_position(board):
    # Placement + side + castling + effective EP.
    # Effective EP: only include the EP square when a capturer exists,
    # using the board's own rule (same check used by _compute_hash).
    # halfmove_clock is a separate identity field.
    parts = board.to_fen().split()
    placement = parts[0]
    side = parts[1]
    castling = parts[2]
    if (board.en_passant is not None
            and board._ep_hash_component(
                board.en_passant, board.white_turn, board.board
            ) != 0):
        ep = parts[3]
    else:
        ep = '-'
    return (placement, side, castling, ep)


def _compute_session_identity(board, model_id, model_sha256):
    # Frozen at session creation. Does NOT include repetition history:
    # position_counts keys are process-random Zobrist hashes and cannot
    # form a restart-stable fingerprint. Repetition is retained on the
    # session's own board and never reconstructed from a browser FEN.
    return (
        _canonical_current_position(board),
        int(board.halfmove_clock),
        model_id,
        model_sha256,
        SEARCH_SEMANTIC_VERSION,
        EVAL_SEMANTIC_VERSION,
        CURRENT_TT_VERSION,
    )


def session_identity_matches(sess, board, model_id, model_sha256):
    return sess.identity == _compute_session_identity(
        board, model_id, model_sha256
    )


class AnalysisSession:
    __slots__ = (
        'session_id',
        'identity',
        'board',
        'model', 'model_id', 'model_sha256',
        'engine',
        'stop_event',
        'stop_requested',
        'status',
        'active_job_id',
        'reservation_token',
        'accepted_root',
        'last_result',
        'pending_resume_source',
        'history_context',
        'created_at', 'last_access_at',
        'lock',
    )

    def __init__(self, session_id, identity, board, model, model_id, model_sha256):
        self.session_id = session_id
        self.identity = identity
        self.board = board
        self.model = model
        self.model_id = model_id
        self.model_sha256 = model_sha256
        self.engine = None
        self.stop_event = threading.Event()
        self.stop_requested = False
        self.status = 'idle'
        self.active_job_id = None
        self.reservation_token = None
        self.accepted_root = None
        self.last_result = None
        self.pending_resume_source = 'NONE'
        self.history_context = 'unknown'
        self.created_at = time.time()
        self.last_access_at = self.created_at
        self.lock = threading.RLock()

    def tier(self):
        # HOT: engine retained. WARM: engine released, metadata retained.
        # COLD (persistent checkpoint) is Phase 4; not represented yet.
        return 'HOT' if self.engine is not None else 'WARM'

    def to_json(self):
        ar = self.accepted_root
        if ar is None:
            ar_json = None
        else:
            bm = ar.get('best_move')
            raw_pv = ar.get('pv') or []
            if not raw_pv and bm:
                raw_pv = [bm]
            ar_json = {
                'best_move': move_to_str(bm) if bm else None,
                'best_score': ar.get('best_score', 0),
                'depth': ar.get('depth', 0),
                'scores': {
                    move_to_str(k): v
                    for k, v in (ar.get('scores') or {}).items()
                },
                'source_type': ar.get('source_type'),
                'source_depth': ar.get('source_depth'),
                'pv': [
                    move_to_str(m) for m in raw_pv
                ],
            }
        return {
            'session_id': self.session_id,
            'identity_digest': hashlib.sha256(
                repr(self.identity).encode('utf-8')
            ).hexdigest()[:8],
            'status': self.status,
            'tier': self.tier(),
            'active_job_id': self.active_job_id,
            'accepted_root': ar_json,
            'last_result': self.last_result,
            'model_id': self.model_id,
            'model_sha256': self.model_sha256,
            'created_at': self.created_at,
            'last_access_at': self.last_access_at,
        }


SESSION_CHECKPOINT_DIR = os.environ.get(
    "CHESS_AI_CHECKPOINT_DIR",
    os.path.join(CHESS_DIR, 'session_checkpoints')
)
SESSION_CHECKPOINT_MAX = 64
SESSION_CHECKPOINT_VERSION = 1
_HEXCHARS = set('0123456789abcdef')


def _valid_session_id(session_id):
    if not isinstance(session_id, str):
        return False
    if len(session_id) != 16:
        return False
    if not session_id.startswith('ses_'):
        return False
    for c in session_id[4:]:
        if c not in _HEXCHARS:
            return False
    return True


def _checkpoint_path(session_id):
    return os.path.join(SESSION_CHECKPOINT_DIR, session_id + '.json')


def _identity_to_json(x):
    if isinstance(x, tuple):
        return [_identity_to_json(i) for i in x]
    if isinstance(x, list):
        return [_identity_to_json(i) for i in x]
    return x


def _identity_from_json(x):
    if isinstance(x, list):
        return tuple(_identity_from_json(i) for i in x)
    return x


def _accepted_root_to_json(ar):
    if ar is None:
        return None
    bm = ar.get('best_move')
    bs = ar.get('best_score')

    if type(bs) is int:
        pass
    elif type(bs) is float and math.isfinite(bs) and bs.is_integer():
        bs = int(bs)
    else:
        raise ValueError("Invalid best_score")

    if abs(bs) > 30000:
        raise ValueError("Invalid best_score range")

    mate_moves = None
    mate_sign = 1
    score_type = "cp"
    if abs(bs) > 29000:
        plies = 30000 - abs(bs)
        mate_moves = (plies + 1) // 2
        mate_sign = 1 if bs > 0 else -1
        score_type = "mate"

    return {
        'best_move': move_to_str(bm) if bm else None,
        'best_score': bs,
        'score_type': score_type,
        'mate_moves': mate_moves,
        'mate_sign': mate_sign,
        'depth': ar.get('depth', 0),
        'scores': {
            move_to_str(k): v
            for k, v in (ar.get('scores') or {}).items()
        },
        'source_type': ar.get('source_type'),
        'source_depth': ar.get('source_depth'),
        'pv': [move_to_str(m) for m in (ar.get('pv') or [])],
    }


def _accepted_root_from_json(data):
    if data is None:
        return None
    if not isinstance(data, dict):
        return None
    bm_str = data.get('best_move')
    bm = str_to_move(bm_str) if bm_str else None
    scores = {}
    try:
        for k, v in (data.get('scores') or {}).items():
            mk = str_to_move(str(k))
            if mk:
                scores[mk] = v
    except Exception:
        return None
    pv = []
    try:
        for m in (data.get('pv') or []):
            mm = str_to_move(m)
            if mm:
                pv.append(mm)
    except Exception:
        return None
    bs = data.get('best_score')

    if type(bs) is int:
        pass
    elif type(bs) is float and math.isfinite(bs) and bs.is_integer():
        bs = int(bs)
    else:
        return None

    if abs(bs) > 30000:
        return None
    bs = int(bs)

    if "score_type" not in data:
        if abs(bs) > 29000:
            score_type = "mate"
            plies = 30000 - abs(bs)
            mate_moves = (plies + 1) // 2
            mate_sign = 1 if bs > 0 else -1
        else:
            score_type = "cp"
            mate_moves = None
            mate_sign = 1
    else:
        score_type = data["score_type"]
        if score_type not in ("cp", "mate"):
            return None

        mate_moves = data.get("mate_moves")
        mate_sign = data.get("mate_sign")

        if score_type == "cp":
            if abs(bs) > 29000:
                return None
            if (
                mate_moves is not None
                or type(mate_sign) is not int
                or mate_sign != 1
            ):
                return None
        elif score_type == "mate":
            if not (29000 < abs(bs) <= 30000):
                return None
            plies = 30000 - abs(bs)
            expected_moves = (plies + 1) // 2
            expected_sign = 1 if bs > 0 else -1

            if type(mate_moves) is not int or isinstance(mate_moves, bool) or mate_moves != expected_moves:
                return None
            if type(mate_sign) is not int or isinstance(mate_sign, bool) or mate_sign != expected_sign:
                return None

    return {
        'best_move': bm,
        'best_score': bs,
        'score_type': score_type,
        'mate_moves': mate_moves,
        'mate_sign': mate_sign,
        'depth': data.get('depth', 0),
        'scores': scores,
        'source_type': data.get('source_type'),
        'source_depth': data.get('source_depth'),
        'pv': pv,
    }


def _evict_old_checkpoints():
    try:
        entries = []
        for name in os.listdir(SESSION_CHECKPOINT_DIR):
            if not name.endswith('.json'):
                continue
            full = os.path.join(SESSION_CHECKPOINT_DIR, name)
            try:
                entries.append((os.path.getmtime(full), full))
            except OSError:
                pass
        if len(entries) <= SESSION_CHECKPOINT_MAX:
            return
        entries.sort()
        for _, full in entries[: len(entries) - SESSION_CHECKPOINT_MAX]:
            try:
                os.remove(full)
            except OSError:
                pass
    except OSError:
        pass


def _save_checkpoint(session):
    if session is None:
        return
    try:
        os.makedirs(SESSION_CHECKPOINT_DIR, exist_ok=True)
    except OSError:
        return
    with session.lock:
        try:
            board_fen = session.board.to_fen()
            halfmove = int(session.board.halfmove_clock)
            rep_count = 0
            if session.board.track_repetition:
                rep_count = int(session.board.position_counts.get(
                    session.board.hash, 0))
        except Exception:
            return
        try:
            ar_json = _accepted_root_to_json(session.accepted_root)
        except Exception:
            return

        data = {
            'checkpoint_version': SESSION_CHECKPOINT_VERSION,
            'session_id': session.session_id,
            'identity': _identity_to_json(session.identity),
            'board_fen': board_fen,
            'halfmove_clock': halfmove,
            'repetition_count': rep_count,
            'repetition_note': 'frontier_count_only',
            'accepted_root': ar_json,
            'model_id': session.model_id,
            'model_sha256': session.model_sha256,
            'search_semantic_version': SEARCH_SEMANTIC_VERSION,
            'eval_semantic_version': EVAL_SEMANTIC_VERSION,
            'tt_semantic_version': CURRENT_TT_VERSION,
            'created_at': session.created_at,
            'last_access_at': session.last_access_at,
        }
    path = _checkpoint_path(session.session_id)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
        _evict_old_checkpoints()
    except OSError:
        pass


def _persist_position_analysis(session, snap):
    """M1a: persist the accepted frontier for this exact position.

    Upsert into position_analysis keyed on the semantic identity tuple.
    Never downgrade a deeper stored frontier. All failures are swallowed;
    persistence must not fail the analysis job.
    """
    if session is None or snap is None:
        return
    if snap.get('depth', 0) <= 0:
        return
    engine = session.engine
    if engine is None:
        return
    try:
        import database_v2
        database_v2.DB_PATH = DB_PATH
        fen = session.board.to_fen()
        conn = database_v2._get_db()
        try:
            row = conn.execute(
                "SELECT id FROM positions WHERE fen = ?", (fen,)
            ).fetchone()
            if row is None:
                cur = conn.execute(
                    "INSERT INTO positions (fen, canonical_fen) VALUES (?, ?)",
                    (fen, normalize_position_key(fen)),
                )
                position_id = cur.lastrowid
            else:
                position_id = row[0]

            stats = getattr(engine, 'iteration_stats', []) or []
            nodes_total = int(sum(s[2] for s in stats))
            q_total = int(sum(s[3] for s in stats))
            elapsed_total = float(sum(s[1] for s in stats))

            best_move_uci = None
            bm = snap.get('best_move')
            if bm is not None:
                try:
                    best_move_uci = move_to_str(bm)
                except Exception:
                    best_move_uci = None

            now_iso = datetime.datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT INTO position_analysis (
                    position_id, model_id, model_sha256,
                    eval_semantic_version, search_semantic_version,
                    tt_semantic_version,
                    multipv, analysis_mode, history_context,
                    accepted_depth, best_move, best_score,
                    accepted_root_json,
                    nodes, q_nodes, elapsed_seconds,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    position_id, model_sha256,
                    eval_semantic_version, search_semantic_version,
                    tt_semantic_version,
                    multipv, analysis_mode, history_context
                ) DO UPDATE SET
                    model_id = excluded.model_id,
                    accepted_depth = excluded.accepted_depth,
                    best_move = excluded.best_move,
                    best_score = excluded.best_score,
                    accepted_root_json = excluded.accepted_root_json,
                    nodes = excluded.nodes,
                    q_nodes = excluded.q_nodes,
                    elapsed_seconds = excluded.elapsed_seconds,
                    updated_at = excluded.updated_at
                WHERE excluded.accepted_depth
                    > position_analysis.accepted_depth
                """,
                (
                    position_id,
                    session.model_id,
                    session.model_sha256,
                    EVAL_SEMANTIC_VERSION,
                    SEARCH_SEMANTIC_VERSION,
                    CURRENT_TT_VERSION,
                    1,
                    'unlimited',
                    session.history_context,
                    int(snap['depth']),
                    best_move_uci,
                    float(snap.get('best_score', 0)),
                    json.dumps(_accepted_root_to_json(snap)),
                    nodes_total,
                    q_total,
                    elapsed_total,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _load_checkpoint(session_id):
    if not _valid_session_id(session_id):
        return None
    path = _checkpoint_path(session_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get('checkpoint_version') != SESSION_CHECKPOINT_VERSION:
        return None
    if data.get('session_id') != session_id:
        return None
    mg = CURRENT_MODEL_GENERATION
    if mg is None:
        return None
    if data.get('model_sha256') != mg.model_sha256:
        return None
    if data.get('search_semantic_version') != SEARCH_SEMANTIC_VERSION:
        return None
    if data.get('eval_semantic_version') != EVAL_SEMANTIC_VERSION:
        return None
    if data.get('tt_semantic_version') != CURRENT_TT_VERSION:
        return None
    try:
        board = ChessBoard()
        board.set_fen(data['board_fen'])
    except Exception:
        return None
    try:
        fen_halfmove = int(data['board_fen'].split()[4])
        stored_halfmove = int(data.get('halfmove_clock', -1))
        stored_rep = int(data.get('repetition_count', 0))
    except (IndexError, ValueError, TypeError, AttributeError):
        return None
    if stored_halfmove != fen_halfmove:
        return None
    if stored_rep < 0:
        return None
    if stored_rep > 1 and board.track_repetition:
        board.position_counts[board.hash] = stored_rep
    snap = _accepted_root_from_json(data.get('accepted_root'))
    if data.get('accepted_root') is not None and snap is None:
        return None
    try:
        sess = AnalysisSession(
            session_id=data['session_id'],
            identity=_identity_from_json(data['identity']),
            board=board,
            model=mg.model,
            model_id=data['model_id'],
            model_sha256=data['model_sha256'],
        )
        sess.accepted_root = snap
        sess.created_at = data.get('created_at', time.time())
        sess.last_access_at = data.get('last_access_at', time.time())
        sess.status = 'stopped'
        sess.history_context = 'frontier_only'
        sess.pending_resume_source = 'WARM'
    except Exception:
        return None
    try:
        os.utime(path, None)
    except OSError:
        pass
    with session_lock:
        session_registry[sess.session_id] = sess
    return sess


def _new_session_id():
    return 'ses_' + uuid.uuid4().hex[:12]


def create_session(board, model, model_id, model_sha256):
    identity = _compute_session_identity(board, model_id, model_sha256)
    sess = AnalysisSession(
        session_id=_new_session_id(),
        identity=identity,
        board=board,
        model=model,
        model_id=model_id,
        model_sha256=model_sha256,
    )
    with session_lock:
        session_registry[sess.session_id] = sess
    _save_checkpoint(sess)
    return sess


def get_session(session_id):
    if not session_id:
        return None
    with session_lock:
        sess = session_registry.get(session_id)
        if sess is not None:
            sess.last_access_at = time.time()
            session_registry.move_to_end(session_id)
        return sess


def attach_engine(session, engine):
    # At most HOT_MAX sessions retain an *idle/retained* engine.
    # Sessions that are running, stopping, or queued -- or that have an
    # active job -- are exempt from demotion until their job reaches a
    # terminal state. During cancellation handoff, one protected engine
    # plus one newly attached engine can legitimately coexist.
    #
    # Lock discipline:
    #   * session.engine read/write: under that session's session.lock.
    #   * session_registry read/write: under session_lock.
    #   * victim.status / victim.active_job_id / victim.engine: read
    #     under victim.lock, not under session_lock.
    # session_lock is never held while acquiring a per-session lock.
    if engine.stop_event is not session.stop_event:
        engine.stop_event = session.stop_event
    with session.lock:
        session.engine = engine

    # Snapshot candidate victims under the registry lock; per-session
    # state is re-checked below under each victim's own lock.
    with session_lock:
        candidates = [
            s for s in session_registry.values()
            if s is not session
        ]

    if len(candidates) + 1 <= HOT_MAX:
        return

    candidates.sort(key=lambda s: s.last_access_at)
    to_demote = len(candidates) + 1 - HOT_MAX
    for victim in candidates:
        if to_demote <= 0:
            break
        with victim.lock:
            if victim.engine is None:
                continue
            if victim.status in ('running', 'stopping', 'queued'):
                continue
            if victim.active_job_id is not None:
                continue
            victim.engine = None
            to_demote -= 1


def release_engine(session):
    with session_lock:
        session.engine = None



def _new_job_id(prefix):
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    return f'{prefix}_{ts}_{uuid.uuid4().hex[:6]}'


def _evict_old_jobs_locked():
    while len(job_registry) > JOB_REGISTRY_MAX:
        removed = False
        for k, j in list(job_registry.items()):
            if j.status in TERMINAL_JOB_STATUSES:
                del job_registry[k]
                removed = True
                break
        if not removed:
            break


class ModelGeneration:
    """Immutable (model object, canonical path, sha256) snapshot.

    Exactly one of these exists per loaded model. A future model reload
    creates a new ModelGeneration rather than mutating the current one,
    so any HOT session keeps evaluating with the weights it started on.
    """
    __slots__ = ('model', 'model_id', 'model_sha256')

    def __init__(self, model, model_id, model_sha256):
        self.model = model
        self.model_id = model_id
        self.model_sha256 = model_sha256


CURRENT_MODEL_GENERATION = None


class SessionResolutionError(Exception):
    def __init__(self, code, message=''):
        super().__init__(message or code)
        self.code = code
        self.message = message or code


def _lookup_reusable_frontier(board, mg):
    """M1b: find a compatible stored frontier for a fresh-FEN request.

    Returns (snap_dict, stored_depth) or (None, 0).

    The lookup mirrors the M1a write key (exact FEN) and requires exact
    semantic-identity match on every field. Any mismatch means the stored
    row is informational history, not a reusable frontier.
    """
    try:
        import database_v2
        database_v2.DB_PATH = DB_PATH
        fen = board.to_fen()
        conn = database_v2._get_db()
        try:
            row = conn.execute(
                "SELECT id FROM positions WHERE fen = ?", (fen,)
            ).fetchone()
            if row is None:
                return None, 0
            position_id = row[0]
            pa = conn.execute(
                """
                SELECT accepted_root_json, accepted_depth
                FROM position_analysis
                WHERE position_id = ?
                  AND model_sha256 = ?
                  AND eval_semantic_version = ?
                  AND search_semantic_version = ?
                  AND tt_semantic_version = ?
                  AND multipv = 1
                  AND analysis_mode = 'unlimited'
                  AND history_context = 'unknown'
                ORDER BY accepted_depth DESC
                LIMIT 1
                """,
                (
                    position_id,
                    mg.model_sha256,
                    EVAL_SEMANTIC_VERSION,
                    SEARCH_SEMANTIC_VERSION,
                    CURRENT_TT_VERSION,
                ),
            ).fetchone()
            if pa is None:
                return None, 0
            root_json, stored_depth = pa
            if not root_json or int(stored_depth) <= 0:
                return None, 0
            snap = _accepted_root_from_json(json.loads(root_json))
            if not isinstance(snap, dict):
                return None, 0
            if int(snap.get('depth', 0)) != int(stored_depth):
                return None, 0
            scratch = SearchEngine(nn=mg.model)
            try:
                scratch.restore_continuation_snapshot(snap)
            except Exception:
                return None, 0
            return snap, int(stored_depth)
        finally:
            conn.close()
    except Exception:
        return None, 0


def _resolve_fresh_session(board, mg):
    """M1b: fresh session, optionally seeded from a compatible stored frontier."""
    snap, stored_depth = _lookup_reusable_frontier(board, mg)
    sess = create_session(board, mg.model, mg.model_id, mg.model_sha256)
    if snap is not None and stored_depth > 0:
        with sess.lock:
            sess.accepted_root = snap
            sess.pending_resume_source = 'COLD'
            _save_checkpoint(sess)
    return sess


def resolve_session_for_request(fen, session_id):
    """Resolve or create an AnalysisSession for a deep-analysis request.

    Rule (frozen): an explicit session_id is authoritative. A FEN alone
    never adopts an existing session. When session_id is supplied, the
    requested current position must match the session's frozen identity
    (current position, halfmove, canonical model path, model SHA,
    semantic versions), else SessionResolutionError with code in:
      - 'session_not_found'
      - 'session_position_mismatch'
      - 'model_generation_unavailable'
    """
    if CURRENT_MODEL_GENERATION is None:
        raise SessionResolutionError(
            'model_generation_unavailable',
            'CURRENT_MODEL_GENERATION has not been initialized',
        )

    board = ChessBoard()
    if fen and fen != 'startpos':
        board.set_fen(fen)

    mg = CURRENT_MODEL_GENERATION

    if not session_id:
        return _resolve_fresh_session(board, mg)

    sess = get_session(session_id)
    if sess is None:
        sess = _load_checkpoint(session_id)
    if sess is None:
        raise SessionResolutionError('session_not_found')
    if not session_identity_matches(sess, board, mg.model_id, mg.model_sha256):
        raise SessionResolutionError('session_position_mismatch')
    return sess


def _create_job(job_type, payload=None, provenance=None, session_id=None):
    if job_type not in VALID_JOB_TYPES:
        raise ValueError(f'invalid job_type: {job_type!r}')
    jid = _new_job_id(JOB_ID_PREFIXES[job_type])
    job = Job(
        job_id=jid,
        job_type=job_type,
        status='queued',
        created_at=time.time(),
        payload=dict(payload or {}),
        session_id=session_id,
        provenance=dict(provenance or {}),
    )
    with job_registry_lock:
        job_registry[jid] = job
        _evict_old_jobs_locked()
    return job


def _create_session_job(job_type, payload, provenance, session):
    """Atomically create or reattach a job for a session.

    Lock order: job_registry_lock -> session.lock. Never the reverse.

    If the session already has a live analysis job in
    running/stopping/queued, returns that job with reattached=True
    without creating anything. Otherwise creates a new job, reserves
    the session under the same critical section, and returns the new
    job with reattached=False.
    """
    with job_registry_lock:
        with session.lock:
            ajid = session.active_job_id
            if ajid is not None:
                existing = job_registry.get(ajid)
                if existing is not None and existing.status in (
                    'running', 'stopping', 'queued'
                ):
                    return existing, True
                session.active_job_id = None
                session.reservation_token = None

            jid = _new_job_id(JOB_ID_PREFIXES[job_type])
            token = uuid.uuid4().hex
            job = Job(
                job_id=jid,
                job_type=job_type,
                status='queued',
                created_at=time.time(),
                payload=dict(payload or {}),
                session_id=session.session_id,
                reservation_token=token,
                provenance=dict(provenance or {}),
            )
            job_registry[jid] = job
            _evict_old_jobs_locked()
            session.active_job_id = jid
            session.reservation_token = token
            session.stop_requested = False
            session.stop_event.clear()
            session.status = 'queued'
            session.last_access_at = time.time()
            return job, False


def _get_job(job_id):
    with job_registry_lock:
        return job_registry.get(job_id)


def _list_jobs(limit=32):
    with job_registry_lock:
        items = list(job_registry.values())
    return list(reversed(items[-limit:]))


def _owns_session(session, job):
    """True iff `job` currently owns the session reservation.

    Caller must hold session.lock. A stale worker/job must never mutate
    or signal a newer session reservation.
    """
    return (
        session.active_job_id == job.job_id
        and session.reservation_token == job.reservation_token
    )


def _cancel_job(job_id):
    with job_registry_lock:
        job = job_registry.get(job_id)
        if job is None:
            return None
        if job.status in TERMINAL_JOB_STATUSES:
            return job
        job.cancel_requested = True
        if job.status == 'queued':
            job.status = 'stopped'
            job.finished_at = time.time()
        elif job.status == 'running':
            job.status = 'stopping'
        j_status = job.status
        j_session_id = job.session_id

    with _job_runtime_lock:
        eng = job_engines.get(job_id)
        sess = _job_sessions.get(job_id)

    if sess is None and j_session_id:
        sess = get_session(j_session_id)

    owns = False
    if sess is not None:
        with sess.lock:
            owns = _owns_session(sess, job)
            if owns:
                sess.stop_requested = True
                if j_status == 'stopped':
                    sess.status = 'stopped'
                    sess.active_job_id = None
                    sess.reservation_token = None
                elif j_status == 'stopping':
                    sess.status = 'stopping'
                sess.last_access_at = time.time()

        # The session event is shared by the session's engine. Only
        # the current reservation owner may signal that shared event.
        if owns:
            sess.stop_event.set()

    # A legacy/sessionless job has its own engine event. For a session
    # job, only signal the engine when this job still owns that session.
    if eng is not None and (sess is None or owns):
        eng.stop_event.set()

    return job


def _run_analysis_job(job, session=None):
    job_id = job.job_id

    def _finalize_session(status):
        if session is None:
            return
        with session.lock:
            if not _owns_session(session, job):
                return
            try:
                snap = engine.get_continuation_snapshot()
            except Exception:
                snap = None
            if snap and snap.get('depth', 0) > 0:
                session.accepted_root = snap
            session.status = status
            session.active_job_id = None
            session.reservation_token = None
            session.last_access_at = time.time()
            # After a job runs, subsequent jobs see WARM (or HOT
            # if the engine is retained), never COLD again.
            session.pending_resume_source = 'WARM'
        try:
            final_snap = session.accepted_root
            if final_snap and final_snap.get('depth', 0) > 0:
                _persist_position_analysis(session, final_snap)
        except Exception:
            pass
        _save_checkpoint(session)

    try:
        if session is not None:
            board = session.board
        else:
            board = ChessBoard()
            fen = job.payload.get('fen', 'startpos') if isinstance(job.payload, dict) else 'startpos'
            if fen and fen != 'startpos':
                board.set_fen(fen)

        with _CPU_HEAVY_SEMAPHORE:
            with job_registry_lock:
                if job.cancel_requested:
                    job.status = 'stopped'
                    job.finished_at = time.time()
                    if session is not None:
                        with session.lock:
                            if _owns_session(session, job):
                                session.status = 'stopped'
                                session.active_job_id = None
                                session.reservation_token = None
                    return

            engine = None
            resume_source = 'NONE'
            resume_from_depth = 0
            if session is not None:
                with session.lock:
                    if not _owns_session(session, job):
                        job.status = 'error'
                        job.error = 'session reservation lost before start'
                        job.finished_at = time.time()
                        return
                    if session.stop_requested:
                        job.status = 'stopped'
                        job.finished_at = time.time()
                        session.status = 'stopped'
                        session.active_job_id = None
                        session.reservation_token = None
                        return
                    session.stop_event.clear()
                    session.status = 'running'
                    session.last_access_at = time.time()
                    engine = session.engine

                    # M1d: compute resume provenance for this job.
                    if engine is not None:
                        resume_source = 'HOT'
                    else:
                        resume_source = session.pending_resume_source
                    _ar = session.accepted_root
                    resume_from_depth = (
                        int(_ar.get('depth', 0)) if _ar else 0
                    )

                if engine is None:
                    new_engine = SearchEngine(nn=session.model)
                    if session.accepted_root:
                        try:
                            new_engine.restore_continuation_snapshot(
                                session.accepted_root
                            )
                        except Exception:
                            pass
                    attach_engine(session, new_engine)
                    try:
                        board._nn_cache = None
                    except Exception:
                        pass
                    engine = new_engine
                else:
                    engine.nn = session.model
            else:
                engine = SearchEngine(nn=nn)
                engine.stop_event.clear()

            with _job_runtime_lock:
                job_engines[job_id] = engine
            cancel_after_registry = False
            with job_registry_lock:
                if job.cancel_requested:
                    if session is not None:
                        with session.lock:
                            if _owns_session(session, job):
                                session.status = 'stopped'
                                session.active_job_id = None
                                session.reservation_token = None
                    job.status = 'stopped'
                    job.finished_at = time.time()
                    cancel_after_registry = True
                else:
                    job.status = 'running'
                    job.started_at = time.time()
                    job.progress = {
                        'accepted_depths': [],
                        'completed_depth': 0,
                        'resume_source': resume_source,
                        'resume_from_depth': resume_from_depth,
                        'searching': {
                            'depth': 1,
                            'elapsed': 0.0,
                            'nodes': 0,
                        },
                    }
            if cancel_after_registry:
                if session is not None:
                    session.stop_event.set()
                engine.stop_event.set()
                return

            start_time = time.time()
            state = {'prev_nodes': 0, 'prev_elapsed': 0.0}

            def _heartbeat():
                while True:
                    time.sleep(1.0)
                    # 1. Snapshot session accepted_root under
                    #    session.lock only. Ownership gate prevents
                    #    a stale worker from reading a newer
                    #    session's state.
                    sar_snap = None
                    if session is not None:
                        with session.lock:
                            if _owns_session(session, job):
                                ar = session.accepted_root
                                if ar:
                                    bm = ar.get('best_move')
                                    raw_pv = ar.get('pv') or []
                                    if not raw_pv and bm:
                                        # Read-time floor: legacy
                                        # accepted_root written before
                                        # pv_floor may have empty pv.
                                        raw_pv = [bm]
                                    sar_snap = {
                                        'depth': ar.get('depth', 0),
                                        'best_move': (
                                            move_to_str(bm)
                                            if bm else None
                                        ),
                                        'best_score': (
                                            ar.get('best_score', 0)
                                        ),
                                        'pv': [
                                            move_to_str(m)
                                            for m in raw_pv
                                        ],
                                    }
                    # 2. Publish under job_registry_lock. session.lock
                    #    was released first: no nesting.
                    with job_registry_lock:
                        if job.status not in ('running', 'stopping'):
                            return
                        try:
                            elapsed_hb = max(
                                time.time() - start_time, 0.001
                            )
                            job.progress['searching'] = {
                                'depth': max(engine.current_depth, 1),
                                'elapsed': round(elapsed_hb, 2),
                                'nodes': engine.nodes,
                            }
                            if sar_snap is not None:
                                job.progress[
                                    'session_accepted_root'
                                ] = sar_snap
                        except Exception:
                            return

            hb = threading.Thread(target=_heartbeat, daemon=True)
            hb.start()

            def _cb(d, move, score, pv):
                elapsed = max(time.time() - start_time, 0.001)
                cp = score
                if abs(cp) > 29000:
                    mate = math.ceil((30000 - abs(cp)) / 2)
                    score_text = f'M{mate}' if cp > 0 else f'-M{mate}'
                else:
                    score_text = f'{cp/100:+.2f}'
                overall_nps = int(engine.nodes / elapsed)
                d_nodes = engine.nodes - state['prev_nodes']
                d_elapsed = max(elapsed - state['prev_elapsed'], 0.001)
                iter_nps = int(d_nodes / d_elapsed)
                state['prev_nodes'] = engine.nodes
                state['prev_elapsed'] = elapsed
                snapshot = {
                    'depth': d,
                    'move': move_to_str(move) if move else None,
                    'score': score_text,
                    'cp': cp,
                    'pv': [move_to_str(m) for m in pv],
                    'nodes': engine.nodes,
                    'nps': overall_nps,
                    'last_iteration_nps': iter_nps,
                    'elapsed': round(elapsed, 3),
                }
                if session is not None:
                    with session.lock:
                        if _owns_session(session, job):
                            try:
                                snap = engine.get_continuation_snapshot()
                            except Exception:
                                snap = None
                            if snap and snap.get('depth', 0) > 0:
                                # Floor: never store an empty pv in
                                # accepted_root when a best move is
                                # known. _extract_pv can return []
                                # if the root TT entry is not exact
                                # at the moment of the callback.
                                if pv:
                                    snap['pv'] = list(pv)
                                elif move:
                                    snap['pv'] = [move]
                                else:
                                    snap['pv'] = []
                                session.accepted_root = snap
                            session.last_result = snapshot
                            session.last_access_at = time.time()
                    _save_checkpoint(session)
                with job_registry_lock:
                    job.result = snapshot
                    depths = list(job.progress.get('accepted_depths', []))
                    depths.append(d)
                    job.progress = {
                        'accepted_depths': depths,
                        'completed_depth': d,
                        'resume_source': resume_source,
                        'resume_from_depth': resume_from_depth,
                        'nodes': engine.nodes,
                        'nps': overall_nps,
                        'last_iteration_nps': iter_nps,
                        'elapsed': round(elapsed, 3),
                        'searching': job.progress.get('searching'),
                    }
                if job.cancel_requested:
                    engine.stop_event.set()

            continue_from = None
            if engine.accepted_root_depth > 0:
                continue_from = engine.accepted_root_depth

            try:
                engine.search(board, time_limit=None,
                              unlimited=True,
                              on_accepted_iteration=_cb,
                              continue_from=continue_from)
            except Exception as e:
                with job_registry_lock:
                    if job.cancel_requested or job.status == 'stopping':
                        job.status = 'stopped'
                    else:
                        job.status = 'error'
                        job.error = str(e)
                    job.finished_at = time.time()
                _finalize_session(job.status)
                return
            with job_registry_lock:
                if job.cancel_requested or job.status == 'stopping':
                    job.status = 'stopped'
                else:
                    job.status = 'completed'
                job.finished_at = time.time()
            _finalize_session(job.status)
    except Exception as e:
        final_status = 'error'
        with job_registry_lock:
            if job.cancel_requested or job.status == 'stopping':
                if job.status not in TERMINAL_JOB_STATUSES:
                    job.status = 'stopped'
                    job.finished_at = time.time()
            elif job.status not in TERMINAL_JOB_STATUSES:
                job.status = 'error'
                job.error = str(e)
                job.finished_at = time.time()
            final_status = job.status
        if session is not None:
            with session.lock:
                if _owns_session(session, job):
                    session.status = final_status
                    session.active_job_id = None
                    session.reservation_token = None
                    session.last_access_at = time.time()
    finally:
        with _job_runtime_lock:
            job_engines.pop(job_id, None)
            job_threads.pop(job_id, None)
            _job_sessions.pop(job_id, None)


def _cancel_other_analysis_jobs(keep_job_id):
    """Cancel any analysis job in running/stopping/queued other than
    keep_job_id. Prevents an orphaned browser session from holding the
    single CPU-heavy slot indefinitely."""
    to_signal = []
    with job_registry_lock:
        keep_job = job_registry.get(keep_job_id)
        keep_session_id = keep_job.session_id if keep_job else None
        for j in job_registry.values():
            if j.job_id == keep_job_id:
                continue
            if j.job_type != 'analysis':
                continue
            if j.status not in ('running', 'stopping', 'queued'):
                continue
            if keep_session_id is not None and j.session_id == keep_session_id:
                continue
            j.cancel_requested = True
            if j.status == 'queued':
                j.status = 'stopped'
                j.finished_at = time.time()
            elif j.status == 'running':
                j.status = 'stopping'
            to_signal.append((j.job_id, j.session_id, j.status, j))
    for jid, sid, jstatus, jref in to_signal:
        with _job_runtime_lock:
            eng = job_engines.get(jid)
            sess = _job_sessions.get(jid)
        if sess is None and sid:
            sess = get_session(sid)
        owns = False
        if sess is not None:
            with sess.lock:
                owns = _owns_session(sess, jref)
                if owns:
                    sess.stop_requested = True
                    sess.status = jstatus
                    sess.last_access_at = time.time()
            if owns:
                sess.stop_event.set()
        if eng is not None and (sess is None or owns):
            eng.stop_event.set()


def _start_analysis_job(job, session=None):
    _cancel_other_analysis_jobs(job.job_id)
    if session is not None:
        with _job_runtime_lock:
            _job_sessions[job.job_id] = session
    try:
        t = threading.Thread(
            target=_run_analysis_job, args=(job, session), daemon=True
        )
        with _job_runtime_lock:
            job_threads[job.job_id] = t
        t.start()
    except Exception as e:
        # Rollback: lock order is job_registry_lock -> session.lock.
        with _job_runtime_lock:
            _job_sessions.pop(job.job_id, None)
            job_threads.pop(job.job_id, None)
        with job_registry_lock:
            job.status = 'error'
            job.error = f'worker start failed: {e}'
            job.finished_at = time.time()
        if session is not None:
            with session.lock:
                if _owns_session(session, job):
                    session.active_job_id = None
                    session.reservation_token = None
                    session.status = 'error'
                    session.last_access_at = time.time()
        raise


@app.route('/api/jobs', methods=['POST'])
def api_create_job():
    try:
        data = request.get_json(silent=True) or {}
        job_type = data.get('job_type')
        if not job_type:
            return jsonify({'error': 'job_type required'}), 400
        payload = data.get('payload')
        if payload is not None and not isinstance(payload, dict):
            return jsonify({'error': 'payload must be an object'}), 400
        provenance = data.get('provenance')
        if provenance is not None and not isinstance(provenance, dict):
            return jsonify({'error': 'provenance must be an object'}), 400
        if job_type not in _DISPATCHABLE_JOB_TYPES:
            return jsonify({'error':
                f'job_type not yet dispatchable: {job_type!r}'}), 400
        session = None
        session_id_in = data.get('session_id')
        if job_type == 'analysis':
            fen = (payload or {}).get('fen', 'startpos')
            try:
                session = resolve_session_for_request(fen, session_id_in)
            except SessionResolutionError as e:
                status = 404 if e.code == 'session_not_found' else 409
                return jsonify({'error': e.code, 'message': e.message}), status
            job, was_reattach = _create_session_job(
                job_type, payload, provenance, session
            )
            if was_reattach:
                return jsonify(job.to_json()), 200
        else:
            try:
                job = _create_job(job_type, payload, provenance)
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        _start_analysis_job(job, session=session)
        return jsonify(job.to_json()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs', methods=['GET'])
def api_list_jobs():
    try:
        limit = request.args.get('limit', 32, type=int)
        limit = max(1, min(64, limit))
        return jsonify({'jobs': [j.to_json() for j in _list_jobs(limit)]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def api_get_job(job_id):
    job = _get_job(job_id)
    if job is None:
        return jsonify({'error': 'job not found'}), 404
    return jsonify(job.to_json())


@app.route('/api/session/<session_id>', methods=['GET'])
def api_get_session(session_id):
    sess = get_session(session_id)
    if sess is None:
        sess = _load_checkpoint(session_id)
    if sess is None:
        return jsonify({'error': 'session not found'}), 404
    return jsonify(sess.to_json())


@app.route('/api/jobs/<job_id>/cancel', methods=['POST'])
def api_cancel_job(job_id):
    job = _cancel_job(job_id)
    if job is None:
        return jsonify({'error': 'job not found'}), 404
    return jsonify(job.to_json())

def _db_ro():
    conn = sqlite3.connect(f'file:{DB_PATH}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _canonical_identity_payload():
    """Read canonical players/aliases for analytics and provenance views."""
    conn = _db_ro()
    try:
        players = [
            dict(r)
            for r in conn.execute(
                "SELECT id, canonical_name, display_name FROM canonical_players ORDER BY id"
            )
        ]
        aliases = [
            dict(r)
            for r in conn.execute(
                "SELECT id, canonical_player_id, alias, source FROM player_aliases ORDER BY alias"
            )
        ]
        return {"players": players, "aliases": aliases}
    finally:
        conn.close()



def _validate_fen_syntax(fen):
    """Return True only when ChessBoard accepts the full six-field FEN."""
    try:
        board = ChessBoard()
        board.set_fen(fen)
        return True
    except Exception:
        return False


def _get_tree_scores(child_fens):
    if not child_fens: return {}
    conn = None
    try:
        conn = _db_ro()
        cur = conn.cursor()
        child_fens = list(set(f for f in child_fens if f))
        if not child_fens: return {}
        placeholders = ','.join('?' * len(child_fens))

        eng_model_id = CURRENT_MODEL_GENERATION.model_id
        eng_model_sha = CURRENT_MODEL_GENERATION.model_sha256

        cur.execute(f"""
            SELECT p.canonical_fen, pa.model_id, pa.model_sha256,
                   pa.best_score, pa.accepted_depth, pa.accepted_root_json, pa.updated_at
            FROM position_analysis pa
            JOIN positions p ON p.id = pa.position_id
            WHERE p.canonical_fen IN ({placeholders})
              AND pa.multipv = 1
              AND (
                  (pa.model_id = ? AND pa.model_sha256 = ? AND pa.eval_semantic_version = ? AND pa.search_semantic_version = ? AND pa.tt_semantic_version = ? AND pa.analysis_mode = 'unlimited' AND pa.history_context = 'unknown')
                  OR
                  (pa.model_id = 'stockfish' AND pa.analysis_mode = 'bounded' AND pa.eval_semantic_version = ? AND pa.search_semantic_version = ? AND pa.tt_semantic_version = ? AND pa.history_context = 'unknown')
              )
            ORDER BY pa.accepted_depth DESC, pa.updated_at DESC, pa.position_id ASC, pa.model_sha256 ASC
        """, child_fens + [eng_model_id, eng_model_sha, EVAL_SEMANTIC_VERSION, SEARCH_SEMANTIC_VERSION, CURRENT_TT_VERSION, SF_ADAPTER_VERSION, SF_ADAPTER_VERSION, SF_ADAPTER_VERSION])

        scores = {}
        for row in cur.fetchall():
            fen = row[0]
            model_id, model_sha, score, depth, root_json, updated_at = row[1], row[2], row[3], row[4], row[5], row[6]
            if fen not in scores: scores[fen] = {}

            if type(depth) is not int or isinstance(depth, bool) or depth <= 0:
                continue

            if model_id == 'stockfish':
                if 'sf_score_type' in scores[fen]:
                    continue
                score_type = None
                mate_moves = None
                mate_sign = None
                if root_json:
                    try:
                        j = json.loads(root_json)
                        score_type = j.get("score_type")
                        mate_moves = j.get("mate_moves")
                        mate_sign = j.get("mate_sign")
                    except Exception:
                        continue

                if score_type not in ("cp", "mate"):
                    continue
                if score_type == "cp":
                    if type(score) not in (int, float) or isinstance(score, bool) or not math.isfinite(score) or abs(score) > 29000:
                        continue
                    if not float(score).is_integer():
                        continue
                else:
                    if score is not None:
                        continue
                    if type(mate_moves) is not int or isinstance(mate_moves, bool) or mate_moves < 0:
                        continue
                    if type(mate_sign) is not int or isinstance(mate_sign, bool) or mate_sign not in (-1, 1):
                        continue

                scores[fen]['sf_score'] = score
                scores[fen]['sf_depth'] = depth
                scores[fen]['sf_score_type'] = score_type
                scores[fen]['sf_mate_moves'] = mate_moves
                scores[fen]['sf_mate_sign'] = mate_sign
                scores[fen]['sf_source'] = f"{model_sha[:8]} @ {updated_at}"

            elif model_sha == eng_model_sha:
                if 'engine_score_type' in scores[fen]:
                    continue
                score_type = None
                mate_moves = None
                mate_sign = None
                if root_json is not None:
                    try:
                        j = json.loads(root_json)
                        if not isinstance(j, dict):
                            continue
                    except Exception:
                        continue

                    if "score_type" in j:
                        score_type = j["score_type"]
                        if score_type not in ("cp", "mate"):
                            continue
                        mate_moves = j.get("mate_moves")
                        mate_sign = j.get("mate_sign")
                    else:
                        score_type = None
                else:
                    score_type = None

                if score_type is None:
                    if score is None or type(score) not in (int, float) or isinstance(score, bool) or not math.isfinite(score):
                        continue
                    if abs(score) > 29000:
                        if abs(score) > 30000:
                            continue
                        score_type = "mate"
                        plies = 30000 - abs(score)
                        mate_moves = (plies + 1) // 2
                        mate_sign = 1 if score > 0 else -1
                    else:
                        score_type = "cp"

                if score_type == "cp":
                    if type(score) not in (int, float) or isinstance(score, bool) or not math.isfinite(score) or abs(score) > 29000:
                        continue
                    if not float(score).is_integer():
                        continue
                elif score_type == "mate":
                    if type(score) not in (int, float) or isinstance(score, bool) or not math.isfinite(score) or not float(score).is_integer() or not (29000 < abs(score) <= 30000):
                        continue

                    plies = 30000 - int(abs(score))
                    expected_moves = (plies + 1) // 2
                    expected_sign = 1 if score > 0 else -1

                    if type(mate_moves) is not int or isinstance(mate_moves, bool) or mate_moves != expected_moves:
                        continue
                    if type(mate_sign) is not int or isinstance(mate_sign, bool) or mate_sign != expected_sign:
                        continue

                scores[fen]['engine_score'] = score
                scores[fen]['engine_depth'] = depth
                scores[fen]['engine_score_type'] = score_type
                scores[fen]['engine_mate_moves'] = mate_moves
                scores[fen]['engine_mate_sign'] = mate_sign
                scores[fen]['engine_source'] = f"{model_sha[:8]} @ {updated_at}"
        return scores
    except Exception as e:
        print(f"Error fetching tree scores: {e}")
        return {}
    finally:
        if conn: conn.close()

def _save_stockfish_score(fen, pv_map, multi_pv, sf_sha):
    if not fen or 1 not in pv_map: return
    if fen == 'startpos': fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    if not sf_sha or sf_sha == "unavailable": return

    data = pv_map[1]

    if data.get("exact") is not True:
        return

    cp_val = data.get("cp")
    mate_dist = data.get("mate")

    if cp_val is not None and mate_dist is not None: return
    if cp_val is not None:
        if type(cp_val) is not int or abs(cp_val) > 29000:
            return
    if mate_dist is not None:
        if type(mate_dist) is not int:
            return
    if cp_val is None and mate_dist is None:
        return

    depth = data.get("depth", 0)
    if type(depth) is not int or isinstance(depth, bool) or depth <= 0: return

    if mate_dist is not None:
        mate_moves = abs(mate_dist)
        mate_sign = 1 if mate_dist > 0 else -1
    else:
        mate_moves = None
        mate_sign = 1

    conn = None
    try:
        canonical = normalize_position_key(fen)
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("PRAGMA foreign_keys=ON;")
        cur = conn.cursor()

        cur.execute("SELECT id FROM positions WHERE fen = ?", (fen,))
        row = cur.fetchone()
        if row:
            pid = row[0]
            cur.execute("UPDATE positions SET canonical_fen = ? WHERE id = ? AND (canonical_fen IS NULL OR canonical_fen = '')", (canonical, pid))
        else:
            cur.execute("INSERT INTO positions (fen, canonical_fen) VALUES (?, ?)", (fen, canonical))
            pid = cur.lastrowid

        now = datetime.datetime.utcnow().isoformat()
        pv_str = data.get("uci_pv", "")
        best_move = pv_str.split()[0] if pv_str else None

        root_json = json.dumps({
            "requested_multipv": multi_pv,
            "score_type": "mate" if mate_dist is not None else "cp",
            "mate_moves": mate_moves,
            "mate_sign": mate_sign,
            "pv": pv_str
        })

        cur.execute("""
            INSERT INTO position_analysis (
                position_id, model_id, model_sha256, eval_semantic_version,
                search_semantic_version, tt_semantic_version, multipv, analysis_mode,
                history_context, accepted_depth, best_move, best_score, accepted_root_json,
                nodes, q_nodes, elapsed_seconds, created_at, updated_at
            ) VALUES (?, 'stockfish', ?, ?, ?, ?, 1, 'bounded', 'unknown', ?, ?, ?, ?, 0, 0, 0, ?, ?)
            ON CONFLICT (
                position_id, model_sha256, eval_semantic_version, search_semantic_version,
                tt_semantic_version, multipv, analysis_mode, history_context
            ) DO UPDATE SET
                accepted_depth = excluded.accepted_depth,
                best_move = excluded.best_move,
                best_score = excluded.best_score,
                accepted_root_json = excluded.accepted_root_json,
                updated_at = excluded.updated_at
            WHERE excluded.accepted_depth > position_analysis.accepted_depth
        """, (pid, sf_sha, SF_ADAPTER_VERSION, SF_ADAPTER_VERSION, SF_ADAPTER_VERSION, depth, best_move, cp_val, root_json, now, now))
        conn.commit()
    except Exception as e:
        print(f"Error saving SF score: {e}")
    finally:
        if conn: conn.close()

def _build_position_analysis(fen):
    """Read-only PositionAnalysis for one canonical position.

    Uses positions.id -> game_moves.position_id -> indexed aggregation.
    Historical and personal statistics share one game_id-deduplicated dataset.
    """
    canonical = normalize_position_key(fen)

    conn = _db_ro()
    try:
        # Resolve every physical positions.id for this canonical key.
        pos_ids = [
            r[0]
            for r in conn.execute(
                "SELECT id FROM positions WHERE canonical_fen = ?",
                (canonical,),
            )
        ]

        if not pos_ids:
            return None

        placeholders = ",".join("?" for _ in pos_ids)

        # Structural invariant:
        #   one canonical position + one game_id = one analytical observation.
        shared_sql = f"""
        SELECT
            gm.game_id,
            MAX(g.result) AS result,
            MAX(g.source_username) AS source_username,
            MAX(g.white) AS white,
            MAX(g.black) AS black
        FROM game_moves gm
        JOIN games g ON g.id = gm.game_id
        WHERE gm.position_id IN ({placeholders})
          AND gm.ply > 0
        GROUP BY gm.game_id
        """

        shared_rows = conn.execute(shared_sql, pos_ids).fetchall()

        # One deterministic example FEN for display.
        example_row = conn.execute(
            "SELECT fen FROM positions WHERE canonical_fen = ? ORDER BY fen LIMIT 1",
            (canonical,),
        ).fetchone()
        example_fen = example_row[0] if example_row else fen

        fields = canonical.split()
        if len(fields) < 2 or fields[1] not in ("w", "b"):
            raise ValueError("Malformed canonical position key")

        turn = fields[1]

        # Historical result aggregation.
        games = len(shared_rows)
        white_wins = 0
        draws = 0
        black_wins = 0

        for r in shared_rows:
            result = r["result"]
            if result == "1-0":
                white_wins += 1
            elif result == "0-1":
                black_wins += 1
            elif result == "1/2-1/2":
                draws += 1

        scored_games = white_wins + draws + black_wins

        def pct(w, d, total):
            return round(((w + 0.5 * d) / total) * 100, 1) if total else 0.0

        white_score = pct(white_wins, draws, scored_games)
        black_score = pct(black_wins, draws, scored_games)
        side_to_move_score = white_score if turn == "w" else black_score

        # Explicit canonical player resolution.
        player_row = conn.execute(
            """
            SELECT id, canonical_name, display_name
            FROM canonical_players
            WHERE canonical_name = ?
            LIMIT 1
            """,
            ("jothi",),
        ).fetchone()

        personal = None

        if player_row is not None:
            canonical_name = player_row["canonical_name"]
            display_name = player_row["display_name"]

            aliases = [
                r[0]
                for r in conn.execute(
                    "SELECT alias FROM player_aliases WHERE canonical_player_id = ?",
                    (player_row["id"],),
                )
            ]

            # Identity set includes canonical name + all aliases.
            identity_names = {
                canonical_name.strip().lower()
                if canonical_name else ""
            }
            identity_names.update(
                a.strip().lower()
                for a in aliases
                if a and a.strip()
            )

            personal_wins = 0
            personal_draws = 0
            personal_losses = 0
            personal_games = 0
            personal_white_games = 0
            personal_black_games = 0
            personal_side_to_move_games = 0
            personal_side_to_move_scored_games = 0
            personal_side_to_move_wins = 0
            personal_side_to_move_draws = 0
            identity_mismatch_games = 0

            for r in shared_rows:
                username = (r["source_username"] or "").strip().lower()
                if username not in identity_names:
                    continue

                white = (r["white"] or "").strip().lower()
                black = (r["black"] or "").strip().lower()

                if white in identity_names:
                    jothi_side = "white"
                elif black in identity_names:
                    jothi_side = "black"
                else:
                    # Explicitly detect and warn; do not silently include.
                    identity_mismatch_games += 1
                    continue

                personal_games += 1

                if jothi_side == "white":
                    personal_white_games += 1
                else:
                    personal_black_games += 1

                result = r["result"]

                if result == "1-0":
                    outcome = "win" if jothi_side == "white" else "loss"
                elif result == "0-1":
                    outcome = "win" if jothi_side == "black" else "loss"
                elif result == "1/2-1/2":
                    outcome = "draw"
                else:
                    outcome = None

                if outcome == "win":
                    personal_wins += 1
                elif outcome == "loss":
                    personal_losses += 1
                elif outcome == "draw":
                    personal_draws += 1

                # Side-to-move subset
                if jothi_side == ("white" if turn == "w" else "black"):
                    personal_side_to_move_games += 1
                    if outcome in ("win", "loss", "draw"):
                        personal_side_to_move_scored_games += 1
                        if outcome == "win":
                            personal_side_to_move_wins += 1
                        elif outcome == "draw":
                            personal_side_to_move_draws += 1

            if identity_mismatch_games:
                print(
                    f"WARNING: {identity_mismatch_games} identity-mismatch games "
                    f"skipped for canonical position {canonical}"
                )

            personal_scored_games = personal_wins + personal_draws + personal_losses
            personal_unscored_games = personal_games - personal_scored_games

            personal_score = pct(
                personal_wins,
                personal_draws,
                personal_scored_games,
            )

            personal_side_to_move_score = pct(
                personal_side_to_move_wins,
                personal_side_to_move_draws,
                personal_side_to_move_scored_games,
            )

            personal = {
                "canonical_player": canonical_name,
                "display_name": display_name,
                "score_basis": "personal_game_result",
                "games": personal_games,
                "scored_games": personal_scored_games,
                "unscored_games": personal_unscored_games,
                "wins": personal_wins,
                "draws": personal_draws,
                "losses": personal_losses,
                "score": personal_score,
                "white_games": personal_white_games,
                "black_games": personal_black_games,
                "side_to_move_games": personal_side_to_move_games,
                "side_to_move_scored_games": personal_side_to_move_scored_games,
                "side_to_move_score": personal_side_to_move_score,
                "opposite_side_games": personal_games - personal_side_to_move_games,
            }

        return {
            "position": {
                "canonical_fen": canonical,
                "example_fen": example_fen,
                "turn": turn,
            },
            "historical": {
                "score_basis": "game_result",
                "games": games,
                "scored_games": scored_games,
                "white_wins": white_wins,
                "draws": draws,
                "black_wins": black_wins,
                "white_score": white_score,
                "black_score": black_score,
                "side_to_move_score": side_to_move_score,
            },
            "personal": personal,
            "engine": None,
        }
    finally:
        conn.close()


@app.route('/api/position_analysis')
def api_position_analysis():
    try:
        fen = request.args.get('fen', '').strip()
        if not fen:
            return jsonify({'error': 'Missing fen'}), 400

        if not _validate_fen_syntax(fen):
            return jsonify({'error': 'Malformed FEN'}), 400

        result = _build_position_analysis(fen)
        if result is None:
            return jsonify({'error': 'Position not found'}), 404

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _reload_opening_cache():
    import opening
    with opening._tree_lock:
        opening._tree = None
        opening._id_to_fen = None
    with opening._examples_lock:
        opening._examples = None
    try:
        opening.get_moves_cached.cache_clear()
        opening.get_examples_cached.cache_clear()
    except Exception:
        pass
    opening.load_tree()
    opening.load_examples()

def _database_game_rows():
    conn = _db_ro()
    try:
        rows = conn.execute("""
            SELECT g.id, g.white, g.black, g.result, g.white_elo, g.black_elo, g.date,
                   g.eco, g.opening, g.termination, g.source, g.platform_game_id,
                   COUNT(gm.uci) AS moves_count,
                   (SELECT GROUP_CONCAT(san, ' ') FROM (
                        SELECT san FROM game_moves WHERE game_id = g.id AND uci IS NOT NULL
                        ORDER BY ply LIMIT 30
                    )) AS first_moves
            FROM games g
            LEFT JOIN game_moves gm ON gm.game_id = g.id AND gm.uci IS NOT NULL
            GROUP BY g.id
            ORDER BY g.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()




def _stats_score(w, d, g):
    if not g:
        return 0.0
    return round(((w + d * 0.5) / g) * 100, 1)

def _parse_stats_date(value):
    if not value:
        return None
    text = str(value).strip().replace('.', '-')
    try:
        return datetime.date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None

def _percentile_from_values(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)

def _stats_rows():
    conn = _db_ro()
    try:
        rows = conn.execute("""
            SELECT
                g.id,
                g.date,
                g.result,
                g.white_elo,
                g.black_elo,
                g.source,
                g.source_username,
                g.platform_game_id,
                g.eco,
                g.opening,
                g.termination,
                g.time_control,
                g.white,
                g.black,
                MIN(CASE WHEN gm.ply = 1 THEN gm.san END) AS first_move,
                COUNT(CASE WHEN gm.ply > 0 THEN 1 END) AS actual_plies
            FROM games g
            LEFT JOIN game_moves gm ON gm.game_id = g.id
            GROUP BY g.id
            ORDER BY g.id
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def _build_stats_dashboard():
    from collections import defaultdict

    rows = _stats_rows()
    total = len(rows)

    actual_counts = []
    year_counts = defaultdict(int)
    month_counts = defaultdict(int)
    season_month_counts = defaultdict(int)
    weekday_counts = defaultdict(int)
    result_counts = defaultdict(int)
    source_counts = defaultdict(int)
    source_platform_counts = defaultdict(int)
    eco_counts = defaultdict(int)
    player_counts = defaultdict(int)

    first_move_counts = defaultdict(lambda: {"games": 0, "wins": 0, "draws": 0, "losses": 0})
    games_with_first_move = 0

    missing_date = 0
    missing_eco = 0
    missing_opening = 0
    missing_termination = 0
    missing_time_control = 0
    missing_white_elo = 0
    missing_black_elo = 0
    missing_platform_id = 0
    source_username_null = 0
    unknown_result_count = 0

    white_elo_values = []
    black_elo_values = []

    rating_band_defs = [
        ('<1000', 0, 999),
        ('1000-1199', 1000, 1199),
        ('1200-1399', 1200, 1399),
        ('1400-1599', 1400, 1599),
        ('1600-1799', 1600, 1799),
        ('1800-1999', 1800, 1999),
        ('2000-2199', 2000, 2199),
        ('2200+', 2200, 10**9),
    ]
    white_bands = defaultdict(int)
    black_bands = defaultdict(int)

    advantage_bucket_defs = [
        ('White +300', 300, 10**9),
        ('White +200..299', 200, 299),
        ('White +100..199', 100, 199),
        ('White +50..99', 50, 99),
        ('Equal/Unknown', -49, 49),
        ('Black +50..99', -99, -50),
        ('Black +100..199', -199, -100),
        ('Black +200..299', -299, -200),
        ('Black +300', -10**9, -300),
    ]
    advantage_buckets = [
        {"label": label, "white_wins": 0, "draws": 0, "black_wins": 0}
        for label, _, _ in advantage_bucket_defs
    ]

    broad_advantage = {
        "white_higher": {"white_wins": 0, "draws": 0, "black_wins": 0},
        "black_higher": {"white_wins": 0, "draws": 0, "black_wins": 0},
        "equal_unknown": {"white_wins": 0, "draws": 0, "black_wins": 0},
    }

    length_bucket_order = ['0', '1-10', '11-20', '21-30', '31-40', '41-50', '51-60', '61-80', '81-100', '100+']
    length_buckets = {
        key: {"games": 0, "white_wins": 0, "draws": 0, "black_wins": 0}
        for key in length_bucket_order
    }

    for r in rows:
        result = (r.get('result') or '').strip()
        if result in ('1-0', '0-1', '1/2-1/2'):
            result_counts[result] += 1
        else:
            unknown_result_count += 1
            result_counts['unknown'] += 1

        actual = int(r.get('actual_plies') or 0)
        actual_counts.append(actual)

        d = _parse_stats_date(r.get('date'))
        if d:
            year_counts[d.year] += 1
            month_counts[f"{d.year:04d}-{d.month:02d}"] += 1
            season_month_counts[d.month] += 1
            weekday_counts[d.strftime('%A')] += 1
        else:
            missing_date += 1

        source = (r.get('source') or 'unknown').strip()
        source_counts[source] += 1

        platform_id = (r.get('platform_game_id') or '').strip()
        if platform_id:
            source_platform_counts[source] += 1
        else:
            missing_platform_id += 1

        if (r.get('source_username') or '').strip() == '':
            source_username_null += 1

        eco = (r.get('eco') or '').strip()
        if eco:
            eco_counts[eco] += 1
        else:
            missing_eco += 1

        if (r.get('opening') or '').strip() == '':
            missing_opening += 1

        if (r.get('termination') or '').strip() == '':
            missing_termination += 1

        if (r.get('time_control') or '').strip() == '':
            missing_time_control += 1

        white_elo = int(r.get('white_elo') or 0)
        black_elo = int(r.get('black_elo') or 0)

        if white_elo <= 0:
            missing_white_elo += 1
        else:
            white_elo_values.append(white_elo)
            for label, lo, hi in rating_band_defs:
                if lo <= white_elo <= hi:
                    white_bands[label] += 1
                    break

        if black_elo <= 0:
            missing_black_elo += 1
        else:
            black_elo_values.append(black_elo)
            for label, lo, hi in rating_band_defs:
                if lo <= black_elo <= hi:
                    black_bands[label] += 1
                    break

        first_move = (r.get('first_move') or '').strip()
        if first_move:
            games_with_first_move += 1
            fm = first_move_counts[first_move]
            fm['games'] += 1
            if result == '1-0':
                fm['wins'] += 1
            elif result == '1/2-1/2':
                fm['draws'] += 1
            elif result == '0-1':
                fm['losses'] += 1

        white_name = (r.get('white') or '').strip()
        black_name = (r.get('black') or '').strip()
        if white_name:
            player_counts[white_name] += 1
        if black_name:
            player_counts[black_name] += 1

        diff = None
        if white_elo > 0 and black_elo > 0:
            diff = white_elo - black_elo

        if diff is None or diff == 0:
            target = broad_advantage['equal_unknown']
        elif diff > 0:
            target = broad_advantage['white_higher']
        else:
            target = broad_advantage['black_higher']

        if result == '1-0':
            target['white_wins'] += 1
        elif result == '1/2-1/2':
            target['draws'] += 1
        elif result == '0-1':
            target['black_wins'] += 1

        if diff is not None:
            for bucket, (_, lo, hi) in zip(advantage_buckets, advantage_bucket_defs):
                if lo <= diff <= hi:
                    if result == '1-0':
                        bucket['white_wins'] += 1
                    elif result == '1/2-1/2':
                        bucket['draws'] += 1
                    elif result == '0-1':
                        bucket['black_wins'] += 1
                    break

        full_moves = int(math.ceil(actual / 2.0))
        if full_moves == 0:
            length_key = '0'
        elif full_moves <= 10:
            length_key = '1-10'
        elif full_moves <= 20:
            length_key = '11-20'
        elif full_moves <= 30:
            length_key = '21-30'
        elif full_moves <= 40:
            length_key = '31-40'
        elif full_moves <= 50:
            length_key = '41-50'
        elif full_moves <= 60:
            length_key = '51-60'
        elif full_moves <= 80:
            length_key = '61-80'
        elif full_moves <= 100:
            length_key = '81-100'
        else:
            length_key = '100+'

        length = length_buckets[length_key]
        length['games'] += 1
        if result == '1-0':
            length['white_wins'] += 1
        elif result == '1/2-1/2':
            length['draws'] += 1
        elif result == '0-1':
            length['black_wins'] += 1

    white_wins = result_counts.get('1-0', 0)
    black_wins = result_counts.get('0-1', 0)
    draws = result_counts.get('1/2-1/2', 0)
    games_with_actual_moves = sum(1 for c in actual_counts if c > 0)
    zero_move_games = sum(1 for c in actual_counts if c == 0)

    avg_actual_plies = sum(actual_counts) / max(total, 1)

    first_move_list = []
    for move, st in first_move_counts.items():
        total_move_games = st['games']
        if total_move_games <= 0:
            continue
        first_move_list.append({
            'move': move,
            'games': total_move_games,
            'white_wins': st['wins'],
            'draws': st['draws'],
            'black_wins': st['losses'],
            'white_score': _stats_score(st['wins'], st['draws'], total_move_games),
        })
    first_move_list.sort(key=lambda x: x['games'], reverse=True)

    eco_list = [
        {'eco': eco, 'games': count}
        for eco, count in sorted(eco_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
    ]

    players_list = [
        {'player': name, 'games': count}
        for name, count in sorted(player_counts.items(), key=lambda kv: kv[1], reverse=True)[:20]
    ]

    activity_years = [
        {'year': str(y), 'games': year_counts[y]}
        for y in sorted(year_counts)
    ]
    activity_months = [
        {'month': m, 'games': month_counts[m]}
        for m in sorted(month_counts)
    ]
    season_months = [
        {'month': m, 'games': season_month_counts.get(m, 0)}
        for m in range(1, 13)
    ]
    weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    activity_weekdays = [
        {'weekday': day, 'games': weekday_counts.get(day, 0)}
        for day in weekday_order
    ]

    by_source = []
    for source, count in sorted(source_counts.items(), key=lambda kv: kv[1], reverse=True):
        platform_count = source_platform_counts.get(source, 0)
        by_source.append({
            'source': source,
            'games': count,
            'with_platform_id': platform_count,
            'without_platform_id': count - platform_count,
        })

    dashboard = {
        'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'overview': {
            'total_games': total,
            'games_with_actual_moves': games_with_actual_moves,
            'zero_move_games': zero_move_games,
            'decisive_games': white_wins + black_wins,
            'draws': draws,
            'average_moves': round(avg_actual_plies / 2, 1),
            'median_moves': round(_percentile_from_values(actual_counts, 50) / 2, 1),
            'min_moves': round(min(actual_counts) / 2, 1),
            'max_moves': round(max(actual_counts) / 2, 1),
            'years': {'min': min(year_counts) if year_counts else None, 'max': max(year_counts) if year_counts else None},
            'unique_player_names': len(player_counts),
        },
        'results': {
            'overall': {
                'white_wins': white_wins,
                'black_wins': black_wins,
                'draws': draws,
                'unknown': unknown_result_count,
                'white_score': _stats_score(white_wins, draws, white_wins + black_wins + draws),
            },
        },
        'activity': {
            'by_year': activity_years,
            'by_month': activity_months,
            'seasonality_by_month': season_months,
            'by_weekday': activity_weekdays,
        },
        'game_length': {
            'percentiles': {
                'p25': round(_percentile_from_values(actual_counts, 25) / 2, 1),
                'p50': round(_percentile_from_values(actual_counts, 50) / 2, 1),
                'p75': round(_percentile_from_values(actual_counts, 75) / 2, 1),
                'p90': round(_percentile_from_values(actual_counts, 90) / 2, 1),
                'p95': round(_percentile_from_values(actual_counts, 95) / 2, 1),
            },
            'distribution': [
                {
                    'bucket': key,
                    'games': length_buckets[key]['games'],
                    'white_wins': length_buckets[key]['white_wins'],
                    'draws': length_buckets[key]['draws'],
                    'black_wins': length_buckets[key]['black_wins'],
                }
                for key in length_bucket_order
            ],
        },
        'first_moves': {
            'minimum_games': 20,
            'games_with_first_move': games_with_first_move,
            'items': first_move_list[:20],
        },
        'eco': {
            'top': eco_list,
        },
        'rating': {
            'white_average_elo': round(sum(white_elo_values) / len(white_elo_values), 1) if white_elo_values else None,
            'black_average_elo': round(sum(black_elo_values) / len(black_elo_values), 1) if black_elo_values else None,
            'white_median_elo': round(_percentile_from_values(white_elo_values, 50), 1) if white_elo_values else None,
            'black_median_elo': round(_percentile_from_values(black_elo_values, 50), 1) if black_elo_values else None,
            'bands': [
                {
                    'band': label,
                    'white_games': white_bands.get(label, 0),
                    'black_games': black_bands.get(label, 0),
                }
                for label, _, _ in rating_band_defs
            ],
            'advantage_buckets': advantage_buckets,
            'broad_advantage': {
                'white_higher': {
                    'white_wins': broad_advantage['white_higher']['white_wins'],
                    'draws': broad_advantage['white_higher']['draws'],
                    'black_wins': broad_advantage['white_higher']['black_wins'],
                    'white_score': _stats_score(
                        broad_advantage['white_higher']['white_wins'],
                        broad_advantage['white_higher']['draws'],
                        broad_advantage['white_higher']['white_wins'] + broad_advantage['white_higher']['draws'] + broad_advantage['white_higher']['black_wins'],
                    ),
                },
                'black_higher': {
                    'white_wins': broad_advantage['black_higher']['white_wins'],
                    'draws': broad_advantage['black_higher']['draws'],
                    'black_wins': broad_advantage['black_higher']['black_wins'],
                    'white_score': _stats_score(
                        broad_advantage['black_higher']['white_wins'],
                        broad_advantage['black_higher']['draws'],
                        broad_advantage['black_higher']['white_wins'] + broad_advantage['black_higher']['draws'] + broad_advantage['black_higher']['black_wins'],
                    ),
                },
                'equal_unknown': {
                    'white_wins': broad_advantage['equal_unknown']['white_wins'],
                    'draws': broad_advantage['equal_unknown']['draws'],
                    'black_wins': broad_advantage['equal_unknown']['black_wins'],
                },
            },
        },
        'players': {
            'unique_player_names': len(player_counts),
            'most_frequent_names': players_list,
        },
        'provenance': {
            'by_source': by_source,
            'source_username_null_count': source_username_null,
            'platform_id_coverage': {
                'with_platform_id': sum(source_platform_counts.values()),
                'without_platform_id': missing_platform_id,
            },
        },
        'data_quality': {
            'total_games': total,
            'zero_move_games': zero_move_games,
            'missing_date': missing_date,
            'missing_white_elo': missing_white_elo,
            'missing_black_elo': missing_black_elo,
            'missing_eco': missing_eco,
            'missing_opening': missing_opening,
            'missing_termination': missing_termination,
            'missing_time_control': missing_time_control,
            'missing_platform_id': missing_platform_id,
            'source_username_null_count': source_username_null,
            'unknown_result_count': unknown_result_count,
        },
    }
    dashboard['canonical_identity'] = _canonical_identity_payload()
    return dashboard


def _build_provenance_audit():
    """Read-only provenance/identity audit for frontend D1 controls."""
    conn = _db_ro()
    try:
        source_counts = [dict(r) for r in conn.execute("""
            SELECT
                source,
                source_username,
                source_class,
                COUNT(*) AS games
            FROM games
            GROUP BY source, source_username, source_class
            ORDER BY source, source_username, source_class
        """).fetchall()]

        source_username_null_count = conn.execute("""
            SELECT COUNT(*)
            FROM games
            WHERE source_username IS NULL
               OR TRIM(source_username) = ''
        """).fetchone()[0]

        lichess_without = conn.execute("""
            SELECT COUNT(*)
            FROM games
            WHERE source = 'lichess'
              AND LOWER(TRIM(white)) <> 'jothilingam'
              AND LOWER(TRIM(black)) <> 'jothilingam'
        """).fetchone()[0]

        chesscom_without = conn.execute("""
            SELECT COUNT(*)
            FROM games
            WHERE platform_game_id LIKE 'chess.com:%'
              AND LOWER(TRIM(white)) <> 'jothi_lingam'
              AND LOWER(TRIM(black)) <> 'jothi_lingam'
        """).fetchone()[0]

        # Aggregate by source for frontend display.
        source_totals = {}
        for row in source_counts:
            source = row["source"]
            if source not in source_totals:
                source_totals[source] = {
                    "source": source,
                    "games": 0,
                    "source_username_values": set(),
                }
            source_totals[source]["games"] += row["games"]
            if row["source_username"]:
                source_totals[source]["source_username_values"].add(row["source_username"])

        suggested_usernames = {
            "lichess": "jothilingam",
            "bulk_import": "jothi_lingam",
            "import_test": "jothi_lingam",
            "chesscom": "jothi_lingam",
        }

        summary = []
        for source in sorted(source_totals, key=lambda x: -source_totals[x]["games"]):
            item = source_totals[source]
            summary.append({
                "source": source,
                "games": item["games"],
                "source_username_values": sorted(item["source_username_values"]),
                "suggested_username": suggested_usernames.get(source),
            })

        canonical_identity = _canonical_identity_payload()
        players = canonical_identity.get("players", [])
        aliases = canonical_identity.get("aliases", [])

        player_by_id = {
            row["id"]: row.get("canonical_name", "unknown")
            for row in players
        }

        proposed_aliases = [
            {
                "alias": row["alias"],
                "canonical_name": player_by_id.get(row["canonical_player_id"], "unknown"),
                "source": row.get("source"),
            }
            for row in aliases
        ]

        return {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source_counts": source_counts,
            "source_summary": summary,
            "source_username_null_count": source_username_null_count,
            "identity_mismatch_checks": {
                "lichess_without_jothilingam": lichess_without,
                "chesscom_platform_without_jothi_lingam": chesscom_without,
            },
            "proposed_aliases": proposed_aliases,
            "canonical_identity": canonical_identity,
            "normalization_applied": source_username_null_count == 0,
        }
    finally:
        conn.close()



@app.route('/api/provenance/normalize-source-username', methods=['POST'])
def api_provenance_normalize_source_username():
    """Controlled D1.3 source_username normalization.

    Loopback-only for now. No manual SQL from Termux.
    """
    try:
        remote = request.remote_addr
        if remote not in ('127.0.0.1', '::1'):
            return jsonify({
                'status': 'error',
                'error': 'Forbidden: local-only operation',
            }), 403

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("BEGIN IMMEDIATE")

            version = conn.execute(
                "SELECT version FROM schema_version"
            ).fetchone()[0]

            if version != 5:
                raise RuntimeError(
                    f"Unexpected schema version {version}, expected 5"
                )

            active_jobs = conn.execute("""
                SELECT COUNT(*) AS n
                FROM sync_jobs
                WHERE status IN ('queued','running')
            """).fetchone()["n"]

            if active_jobs:
                raise RuntimeError(f"Active sync jobs present: {active_jobs}")

            canonical_count = conn.execute(
                "SELECT COUNT(*) FROM canonical_players"
            ).fetchone()[0]
            alias_count = conn.execute(
                "SELECT COUNT(*) FROM player_aliases"
            ).fetchone()[0]

            if canonical_count != 1 or alias_count != 2:
                raise RuntimeError(
                    "Canonical identity seed missing/mismatched"
                )

            expected_sources = {
                "lichess": 8474,
                "bulk_import": 6412,
                "import_test": 19,
                "chesscom": 11,
            }

            source_counts_before = {}
            for r in conn.execute("""
                SELECT source, COUNT(*) AS n
                FROM games
                GROUP BY source
            """):
                source_counts_before[r["source"]] = r["n"]

            if source_counts_before != expected_sources:
                raise RuntimeError(
                    f"Preflight source counts mismatch: {source_counts_before}"
                )

            null_before = conn.execute("""
                SELECT COUNT(*)
                FROM games
                WHERE source_username IS NULL
                   OR TRIM(source_username) = ''
            """).fetchone()[0]

            if null_before != 14916:
                raise RuntimeError(
                    f"Expected 14916 NULL source_username, found {null_before}"
                )

            cur = conn.execute("""
                UPDATE games
                SET source_username = CASE
                    WHEN source = 'lichess' THEN 'jothilingam'
                    WHEN source IN ('bulk_import','import_test','chesscom')
                        THEN 'jothi_lingam'
                    ELSE source_username
                END
                WHERE source_username IS NULL
                   OR TRIM(source_username) = ''
            """)

            if cur.rowcount != 14916:
                raise RuntimeError(
                    f"Update rowcount mismatch: expected 14916, got {cur.rowcount}"
                )

            null_after = conn.execute("""
                SELECT COUNT(*)
                FROM games
                WHERE source_username IS NULL
                   OR TRIM(source_username) = ''
            """).fetchone()[0]

            if null_after != 0:
                raise RuntimeError(
                    f"source_username NULL after update: {null_after}"
                )

            source_counts_after = {}
            for r in conn.execute("""
                SELECT source, COUNT(*) AS n
                FROM games
                GROUP BY source
            """):
                source_counts_after[r["source"]] = r["n"]

            if source_counts_after != expected_sources:
                raise RuntimeError(
                    f"Source counts changed after update: {source_counts_after}"
                )

            total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
            if total != 14916:
                raise RuntimeError(f"Total games changed: {total}")

            conn.commit()

            return jsonify({
                "status": "ok",
                "updated_count": cur.rowcount,
                "source_username_null_count_after": null_after,
            })

        except Exception as e:
            conn.rollback()
            raise

        finally:
            conn.close()

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
        }), 500



@app.route('/api/provenance/audit')
def api_provenance_audit():
    try:
        return jsonify(_build_provenance_audit())
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/api/stats/dashboard')
def api_stats_dashboard():
    try:
        return jsonify(_build_stats_dashboard())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


nn = DualNet()
if not nn.load(MODEL_PATH):
    print("WARNING: Neural network not loaded, using fallback evaluation")


def _compute_model_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


CURRENT_MODEL_GENERATION = ModelGeneration(
    model=nn,
    model_id=os.path.realpath(MODEL_PATH),
    model_sha256=_compute_model_sha256(MODEL_PATH),
)
print(
    f"Model generation: {CURRENT_MODEL_GENERATION.model_id} "
    f"sha256={CURRENT_MODEL_GENERATION.model_sha256[:12]}..."
)

engine = SearchEngine(nn=nn, max_depth=12)
engine_lock = threading.Lock()

test_batch_lock = threading.Lock()
test_batch = {
    'running': False, 'num_games': 0, 'games_completed': 0,
    'current_game_index': 0, 'current_fen': "", 'current_pgn': "",
    'all_pgns': [], 'wins': 0, 'losses': 0, 'draws': 0, 'errors': 0, 'all_pgns_count': 0,
    'engine_color': 'white', 'depth': 4, 'opponent': 'random',
    'stop_requested': False, 'moves': [], 'current_ply': 0,
    'human_game': False, 'human_side': 'white', 'human_move_pending': False
}
test_batch_thread = None

# ---------------------------------------------------------------------------
# Background sync worker registry + heartbeat lifecycle.
#
# The heartbeat thread only refreshes sync_jobs.heartbeat_at / updated_at.
# It must NEVER modify:
#   games, game_moves, import_batches, import_records,
#   sync_state, cursor, tree_dirty, chunk_index, or job counters.
# ---------------------------------------------------------------------------
SYNC_HEARTBEAT_INTERVAL = 15

sync_worker_registry = {}
sync_worker_lock = threading.Lock()

# Actual background worker threads, separate from heartbeat threads.
sync_job_threads = {}
sync_job_threads_lock = threading.Lock()


def _sync_worker_heartbeat_loop(job_id, worker_pid, stop_event):
    """Continuously refresh the owning worker's heartbeat until stopped."""
    from database_v2 import heartbeat_sync_job

    while not stop_event.is_set():
        try:
            heartbeat_sync_job(job_id, worker_pid)
        except Exception:
            # A failed heartbeat must never crash the worker loop.
            pass

        # Wait on stop_event so cancellation can end this loop promptly.
        stop_event.wait(SYNC_HEARTBEAT_INTERVAL)


def start_sync_worker_heartbeat(job_id, worker_pid):
    """Start a daemon heartbeat thread for one claimed job.

    Returns the stop_event if started, or None if already registered.
    """
    from database_v2 import heartbeat_sync_job  # noqa: F841

    job_id = int(job_id)
    worker_pid = int(worker_pid)

    with sync_worker_lock:
        if job_id in sync_worker_registry:
            return None

        stop_event = threading.Event()
        thread = threading.Thread(
            target=_sync_worker_heartbeat_loop,
            args=(job_id, worker_pid, stop_event),
            daemon=True,
        )

        sync_worker_registry[job_id] = (thread, stop_event)
        thread.start()
        return stop_event


def stop_sync_worker_heartbeat(job_id):
    """Stop and remove a job's heartbeat thread.

    Returns True if a heartbeat thread existed and was stopped.
    """
    job_id = int(job_id)

    with sync_worker_lock:
        entry = sync_worker_registry.pop(job_id, None)

    if entry is None:
        return False

    thread, stop_event = entry
    stop_event.set()
    thread.join(timeout=2.0)
    return True


def is_sync_worker_heartbeat_running(job_id):
    """Return True if a heartbeat thread is registered for job_id."""
    with sync_worker_lock:
        return int(job_id) in sync_worker_registry


sync_locks = {
    'lichess': threading.Lock(),
    'chesscom': threading.Lock(),
}

database_ingest_lock = threading.Lock()
tree_build_lock = threading.Lock()


def source_sync_locked(fn):
    """Serialize sync requests per source."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        data = request.get_json(silent=True) or {}
        source = str(data.get('source', '')).strip().lower()
        lock = sync_locks.get(source)
        if lock is not None:
            with lock:
                return fn(*args, **kwargs)
        return fn(*args, **kwargs)
    return wrapper


def _record_source_timestamp_ms(record, source):
    """Return the source game UTC timestamp in milliseconds, if available."""
    if source == "chesscom":
        from pgn_learner import _chesscom_game_timestamp_ms
        return _chesscom_game_timestamp_ms(record.get("raw_pgn", ""))

    headers = record.get("headers", {})
    date_value = headers.get("utcdate") or headers.get("date")
    if not date_value:
        return None

    time_value = headers.get("utctime") or "00:00:00"
    try:
        date_text = str(date_value).strip().replace(".", "-")
        time_text = str(time_value).strip()
        dt = datetime.datetime.strptime(
            date_text + "T" + time_text,
            "%Y-%m-%dT%H:%M:%S",
        )
        return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    except Exception:
        return None


def _sync_job_thread_wrapper(job_id):
    """Run the actual worker and contain unexpected thread exceptions."""
    current_thread = threading.current_thread()

    try:
        _run_sync_job_worker(job_id)
    except Exception as exc:
        # Do not allow an unexpected worker exception to escape the thread.
        print(f"sync job worker {job_id} unexpected error: {exc}", flush=True)
    finally:
        with sync_job_threads_lock:
            if sync_job_threads.get(int(job_id)) is current_thread:
                sync_job_threads.pop(int(job_id), None)


def start_sync_job_worker_thread(job_id):
    """Start one actual worker thread for a job.

    Returns True if a new thread was started, or False if an active
    worker thread is already registered for this job_id.
    """
    job_id = int(job_id)

    with sync_job_threads_lock:
        existing = sync_job_threads.get(job_id)

        if existing is not None and existing.is_alive():
            return False

        thread = threading.Thread(
            target=_sync_job_thread_wrapper,
            args=(job_id,),
            daemon=True,
        )

        sync_job_threads[job_id] = thread
        thread.start()
        return True


def is_sync_job_worker_thread_running(job_id):
    """Return True if an actual worker thread is currently active."""
    job_id = int(job_id)

    with sync_job_threads_lock:
        thread = sync_job_threads.get(job_id)
        return bool(thread is not None and thread.is_alive())


def _run_sync_job_worker(job_id):
    """Execute one claimed background sync job to completion/failure."""
    from database_v2 import (
        get_sync_job,
        update_sync_job,
        get_sync_state,
        finalize_sync_job_success,
        fail_sync_job_with_fatal_audit,
        terminate_sync_job_with_owner,
        insert_game_audited,
        heartbeat_sync_job,
        FATAL_SYNC_PARSER_STATUSES,
    )
    from pgn_utils_v2 import parse_pgn_content_detailed
    from pgn_learner import iter_lichess_pgn_chunks, iter_chesscom_pgn_chunks

    worker_pid = os.getpid()
    stop_event = None

    try:
        job = get_sync_job(job_id)
        if not job or job.get("status") != "running":
            return {"status": "not_running", "job_id": job_id}

        source = job["source"]
        username = job["source_username"]

        if source not in ("lichess", "chesscom"):
            raise ValueError(f"invalid worker source: {source}")

        state = get_sync_state(source, username) or {}
        last_cursor = int(state.get("last_successful_sync_at") or 0)
        initial_tree_dirty = int(state.get("tree_dirty") or 0)
        previous_batch_id = state.get("last_batch_id")

        overlap_ms = 24 * 60 * 60 * 1000
        fetch_cursor = max(0, last_cursor - overlap_ms)

        stop_event = start_sync_worker_heartbeat(job_id, worker_pid)

        update_sync_job(job_id, cursor_before=fetch_cursor, phase="downloading")

        chunk_index = int(job.get("chunk_index") or 0)
        newest_ms = None

        chunk_iter = (
            iter_lichess_pgn_chunks(username, fetch_cursor, chunk_size=100)
            if source == "lichess"
            else iter_chesscom_pgn_chunks(username, fetch_cursor, chunk_size=100)
        )

        for pgn_text, downloaded_count in chunk_iter:
            heartbeat_sync_job(job_id, worker_pid)

            records = parse_pgn_content_detailed(pgn_text)
            parsed_count = len(records)

            if parsed_count != downloaded_count:
                raise ValueError(
                    f"parsed_count {parsed_count} != downloaded_count {downloaded_count}"
                )

            fatal_records = [
                r for r in records
                if r.get("parser_status") in FATAL_SYNC_PARSER_STATUSES
            ]

            if fatal_records:
                with database_ingest_lock:
                    fail_sync_job_with_fatal_audit(
                        job_id=job_id,
                        worker_pid=worker_pid,
                        source=source,
                        source_username=username,
                        records=records,
                        fatal_records=fatal_records,
                        error="fatal parser record in sync chunk",
                    )
                return {"status": "failed", "job_id": job_id}

            for rec in records:
                ts = _record_source_timestamp_ms(rec, source)
                if ts is not None:
                    newest_ms = max(newest_ms or 0, ts)

            next_chunk = chunk_index + 1

            with database_ingest_lock:
                insert_game_audited(
                    records,
                    source=source,
                    source_file=f"sync_job_{job_id}_chunk_{next_chunk}.pgn",
                    source_username=username,
                    mark_tree_dirty=True,
                    job_id=job_id,
                    chunk_index=next_chunk,
                    previous_chunk_index=chunk_index,
                    chunk_downloaded_count=downloaded_count,
                    chunk_parsed_count=parsed_count,
                )

            chunk_index = next_chunk

            latest = get_sync_job(job_id)
            if int(latest.get("cancel_requested") or 0):
                with database_ingest_lock:
                    terminate_sync_job_with_owner(
                        job_id=job_id,
                        worker_pid=worker_pid,
                        source=source,
                        source_username=username,
                        terminal_status="canceled",
                        phase="canceled",
                    )
                return {"status": "canceled", "job_id": job_id}

        with database_ingest_lock:
            latest = get_sync_job(job_id)
            tree_new_count = int(latest.get("tree_new_count") or 0)

            needs_tree_rebuild = (initial_tree_dirty == 1) or (tree_new_count > 0)

            if needs_tree_rebuild:
                ok, err = _rebuild_opening_tree_locked()
                if not ok:
                    terminate_sync_job_with_owner(
                        job_id=job_id,
                        worker_pid=worker_pid,
                        source=source,
                        source_username=username,
                        terminal_status="failed",
                        phase="tree_build_failed",
                        error=err,
                    )
                    return {"status": "failed_tree", "job_id": job_id}

            cursor_after = newest_ms if newest_ms is not None else last_cursor

            final_batch_id = (
                latest.get("batch_id")
                if latest.get("batch_id") is not None
                else previous_batch_id
            )

            finalize_sync_job_success(
                job_id=job_id,
                worker_pid=worker_pid,
                source=source,
                source_username=username,
                cursor_after=cursor_after,
                last_batch_id=final_batch_id,
                tree_rebuilt=needs_tree_rebuild,
            )

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        try:
            latest_fail = get_sync_job(job_id)
            if latest_fail and latest_fail.get("status") == "running":
                terminate_sync_job_with_owner(
                    job_id=job_id,
                    worker_pid=worker_pid,
                    source=latest_fail["source"],
                    source_username=latest_fail["source_username"],
                    terminal_status="failed",
                    phase="failed",
                    error=str(e),
                )
        except Exception:
            pass

        return {"status": "failed", "job_id": job_id, "error": str(e)}

    finally:
        if stop_event is not None:
            stop_sync_worker_heartbeat(job_id)
def _rebuild_opening_tree_locked():
    """Rebuild opening tree and reload cache under the global tree lock."""
    with tree_build_lock:
        result = subprocess.run(
            ['python3', os.path.join(CHESS_DIR, 'build_tree.py')],
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode != 0:
            return False, result.stderr
        _reload_opening_cache()
        return True, None


# ---------- API endpoints ----------
@app.route('/api/move', methods=['POST'])
def api_move():
    global analysis_fen
    data = request.get_json()
    if not data: return jsonify({'error': 'Invalid JSON'}), 400
    fen, uci = data.get('fen'), data.get('uci')
    if not fen or not uci: return jsonify({'error': 'Missing fen or uci'}), 400
    board = ChessBoard()
    try: board.set_fen(fen)
    except ValueError as e: return jsonify({'error': f'Invalid FEN: {e}'}), 400
    move = str_to_move(uci)
    if not move or move not in board.generate_legal_moves():
        return jsonify({'error': 'Illegal move'}), 400
    san = move_to_san(move, board)
    board.make_move(move)
    analysis_fen = board.to_fen()
    with test_batch_lock:
        if test_batch.get('human_game') and test_batch.get('human_move_pending'):
            test_batch['human_move_pending'] = False
            test_batch['current_fen'] = board.to_fen()
            test_batch['moves'].append(san)
            test_batch['current_ply'] = len(test_batch['moves'])
    return jsonify({'fen': board.to_fen(), 'uci': uci, 'san': san})


@app.route('/api/human_move', methods=['POST'])
def api_human_move():
    return api_move()

@app.route('/api/legal_moves', methods=['POST'])
def api_legal_moves():
    data = request.get_json()
    if not data or not data.get('fen'): return jsonify({'error': 'Missing fen'}), 400
    board = ChessBoard(); board.set_fen(data['fen'])
    return jsonify({'moves': [move_to_str(m) for m in board.generate_legal_moves()]})

@app.route('/api/current_fen')
def api_current_fen():
    # Always returns the analysis board FEN – live games use /api/live_game_state
    return jsonify({"fen": analysis_fen, "current_fen": analysis_fen})

@app.route('/api/start_test_batch', methods=['POST'])
def start_test_batch():
    global test_batch_thread, test_batch
    with test_batch_lock:
        if test_batch['running']:
            return jsonify({'error': 'Batch already running'}), 400
        data = request.get_json()
        num_games = max(1, min(int(data.get('num_games', 10)), 100))
        depth = max(1, min(int(data.get('depth', 4)), 12))
        opponent = data.get('opponent', 'random')
        test_batch.update({
            'running': True, 'num_games': num_games, 'games_completed': 0,
            'current_game_index': -1, 'current_fen': "", 'current_pgn': "",
            'all_pgns': [], 'wins': 0, 'losses': 0, 'draws': 0, 'errors': 0,
            'depth': depth, 'opponent': opponent, 'stop_requested': False,
            'moves': [], 'current_ply': 0,
            'human_game': (opponent == 'human'),
            'human_move_pending': False
        })
        if opponent == 'human':
            test_batch['human_side'] = random.choice(['white', 'black'])
    test_batch_thread = threading.Thread(target=run_test_batch, args=(num_games, depth, opponent))
    test_batch_thread.daemon = True
    test_batch_thread.start()
    return jsonify({'status': 'started'})

@app.route('/api/test_batch_status')
def test_batch_status():
    with test_batch_lock:
        return jsonify({k: test_batch[k] for k in [
            'running','num_games','games_completed','current_game_index','current_fen','current_pgn',
            'wins','losses','draws','errors','engine_color','depth',
            'opponent','moves','current_ply','human_game','human_side','human_move_pending','all_pgns_count'
        ]})
@app.route('/api/test_batch_games')
def test_batch_games():
    with test_batch_lock:
        return jsonify({'pgn': '\n\n'.join(test_batch['all_pgns'])})

@app.route('/api/stop_test_batch')
def stop_test_batch():
    with test_batch_lock:
        if test_batch['running']:
            test_batch['stop_requested'] = True
            return jsonify({'status': 'stopping'})
    return jsonify({'status': 'not running'})

# ---- Opponent logic ----
class StockfishEngine:
    def __init__(self, path='stockfish'):
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True)
        self._send('uci'); self._read_until('uciok'); self._send('isready'); self._read_until('readyok')
    def _send(self, cmd): self.proc.stdin.write(cmd+'\n'); self.proc.stdin.flush()
    def _read_until(self, keyword):
        while True:
            line = self.proc.stdout.readline().strip()
            if keyword in line: break
    def get_move(self, fen, time_ms=1000):
        self._send(f'position fen {fen}'); self._send(f'go movetime {time_ms}')
        best = None
        while True:
            line = self.proc.stdout.readline().strip()
            if line.startswith('bestmove'):
                parts = line.split()
                if len(parts) >= 2 and parts[1] != '(none)': best = parts[1]
                break
        return str_to_move(best) if best else None
    def quit(self): self.proc.terminate()

def run_test_batch(num_games, depth, opponent):
    try:
        global test_batch
        if opponent == 'human':
            run_human_game(depth)
            return
        for game_num in range(1, num_games+1):
            with test_batch_lock:
                if test_batch['stop_requested']: test_batch['running'] = False; return
                test_batch['current_game_index'] = game_num
                test_batch['moves'] = []; test_batch['current_ply'] = 0
            engine_white = (game_num % 2 == 1)
            test_batch['engine_color'] = 'white' if engine_white else 'black'
            board = ChessBoard()
            test_engine = SearchEngine(nn=nn, max_depth=depth)
            sf = StockfishEngine() if opponent == 'stockfish' else None
            move_history = []; result = '*'; error = False; error_msg = ''
            try:
                while True:
                    if test_batch['stop_requested']: break
                    legal = board.generate_legal_moves()
                    if not legal: break
                    wtm = board.white_turn if hasattr(board,'white_turn') else (board.turn=='w')
                    engine_turn = (engine_white and wtm) or (not engine_white and not wtm)
                    move = None
                    if engine_turn:
                        try: move = test_engine.search(board.copy(), time_limit=5000, depth=depth)[0]
                        except: pass
                        if not move or move not in legal:
                            error = True; error_msg = f"Illegal/None move: {move_to_str(move) if move else 'None'}"; break
                        piece = board.board[move[0]][move[1]]
                        if (engine_white and piece.islower()) or (not engine_white and piece.isupper()):
                            error = True; error_msg = "Wrong colour piece moved"; break
                    else:
                        if opponent == 'random':
                            move = random.choice(legal)
                        elif opponent == 'self':
                            try: move = test_engine.search(board.copy(), time_limit=5000, depth=depth)[0]
                            except: pass
                            if not move or move not in legal: move = random.choice(legal) if legal else None
                        elif opponent == 'stockfish':
                            try:
                                uci = sf.get_move(board.to_fen(), 1000)
                                if uci and uci in legal: move = uci
                                else: move = random.choice(legal) if legal else None
                            except: move = random.choice(legal) if legal else None
                    if not move: break
                    fen_before = board.to_fen()
                    san = move_to_san(move, board) if move else ''
                    board.make_move(move)
                    move_history.append(san)
                    with test_batch_lock:
                        test_batch['current_fen'] = board.to_fen()
                        fen_queue.put(board.to_fen())
                        test_batch['moves'].append(san)
                        test_batch['current_ply'] = len(test_batch['moves'])
                        pgn = f'[Event "Engine vs {opponent}"]\n[Site "Chess AI"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n'
                        white_name = "Engine" if engine_white else opponent
                        black_name = "Engine" if not engine_white else opponent
                        pgn += f'[White "{white_name}"]\n'
                        pgn += f'[Black "{black_name}"]\n\n'
                        pgn += ' '.join(f'{i//2+1}. {s}' if i%2==0 else s for i,s in enumerate(move_history))
                        test_batch['current_pgn'] = pgn
                    if hasattr(board,'is_checkmate') and board.is_checkmate():
                        result = '1-0' if wtm else '0-1'
                        break
                    if hasattr(board,'is_draw') and board.is_draw(): result = '1/2-1/2'; break
                    time.sleep(0.05)
            except Exception as e: error = True; error_msg = str(e)
            finally:
                if sf: sf.quit()
            with test_batch_lock:
                pgn = f'[Event "Engine vs {opponent}"]\n[Site "Chess AI"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n'
                white_name = "Engine" if engine_white else opponent
                black_name = "Engine" if not engine_white else opponent
                pgn += f'[White "{white_name}"]\n'
                pgn += f'[Black "{black_name}"]\n'
                pgn += f'[Result "{result}"]\n\n'
                pgn += ' '.join(f'{i//2+1}. {s}' if i%2==0 else s for i,s in enumerate(move_history)) + ' ' + result
                if error: pgn += f'\n\n{{{error_msg}}}'; test_batch['errors'] += 1
                else:
                    if result == '1-0': test_batch['wins'] += 1
                    elif result == '0-1': test_batch['losses'] += 1
                    elif result == '1/2-1/2': test_batch['draws'] += 1
                test_batch['current_pgn'] = pgn
                test_batch['all_pgns'].append(pgn)
                test_batch['games_completed'] = game_num
            if test_batch['stop_requested']: test_batch['running'] = False; return
        test_batch['running'] = False
    except Exception as e:
        with test_batch_lock:
            test_batch['running'] = False
            test_batch['errors'] += 1
        print(f"Batch thread crashed: {e}")

def run_human_game(depth):
    try:
        result = "*"
        global test_batch
        board = ChessBoard()
        test_engine = SearchEngine(nn=nn, max_depth=depth)
        human_side = test_batch['human_side']
        engine_side = 'w' if human_side == 'b' else 'b'
        test_batch.update({'current_game_index':1,'num_games':1,'moves':[],'current_ply':0,
                           'engine_color':engine_side,'current_fen':board.to_fen(),
                           'current_pgn':'[Event "Engine vs Human"]\n[Site "Chess AI"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n[White "Human"][Black "Engine"]\n\n'})
        move_history = []
        while True:
            if test_batch['stop_requested']: break
            legal = board.generate_legal_moves()
            if not legal: break
            wtm = board.white_turn if hasattr(board,'white_turn') else (board.turn=='w')
            engine_turn = (engine_side=='w' and wtm) or (engine_side=='b' and not wtm)
            if engine_turn:
                try: move = test_engine.search(board.copy(), time_limit=5000, depth=depth)[0]
                except: move = random.choice(legal) if legal else None
                if move and move in legal:
                    san = move_to_san(move, board); board.make_move(move)
                    move_history.append(san)
                    with test_batch_lock:
                        test_batch['current_fen'] = board.to_fen()
                        test_batch['moves'].append(san)
                        test_batch['current_ply'] = len(test_batch['moves'])
                        pgn = '[Event "Engine vs Human"]\n[Site "Chess AI"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n[White "Human"][Black "Engine"]\n\n'
                        pgn += ' '.join(f'{i//2+1}. {s}' if i%2==0 else s for i,s in enumerate(move_history))
                        test_batch['current_pgn'] = pgn
                else: break
            else:
                with test_batch_lock: test_batch['human_move_pending'] = True; test_batch['current_fen'] = board.to_fen()
                while test_batch['human_move_pending'] and not test_batch['stop_requested']: time.sleep(0.05)
                if test_batch['stop_requested']: return
                board = ChessBoard(); board.set_fen(test_batch['current_fen'])
                move_history.append(test_batch['moves'][-1])
            if hasattr(board,'is_checkmate') and board.is_checkmate(): result = '1-0' if not wtm else '0-1'; break
            if hasattr(board,'is_draw') and board.is_draw(): result = '1/2-1/2'; break
        with test_batch_lock:
            pgn = '[Event "Engine vs Human"]\n[Site "Chess AI"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n[White "Human"][Black "Engine"]\n'
            pgn += f'[Result "{result}"]\n\n'
            pgn += ' '.join(f'{i//2+1}. {s}' if i%2==0 else s for i,s in enumerate(move_history)) + ' ' + result
            test_batch['current_pgn'] = pgn; test_batch['all_pgns'].append(pgn); test_batch['games_completed']=1
            test_batch['running'] = False
    except Exception as e:
        with test_batch_lock:
            test_batch['running'] = False
            test_batch['errors'] += 1
        print(f"Human game thread crashed: {e}")

# ---- All other existing endpoints (unchanged) ----
@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    try:
        data = request.get_json()
        fen = data.get('fen','startpos')
        moves_input = data.get('moves','').strip()
        fresh = bool(data.get('fresh', False))
        multipv_count = 3
        try: multipv_count = int(data.get('multipv',3))
        except: pass
        multipv_count = max(1, multipv_count)
        board = ChessBoard()
        if fen != 'startpos': board.set_fen(fen)
        move_history = []
        if moves_input:
            for token in moves_input.split():
                move = str_to_move(token)
                if not move or move not in board.generate_legal_moves():
                    return jsonify({'error':f'Invalid move: {token}'}),400
                board.make_move(move); move_history.append(token)
        start = time.time()
        reused_from_depth = 0
        with engine_lock:
            if not fresh:
                try:
                    _mg = CURRENT_MODEL_GENERATION
                    _snap, _sd = _lookup_reusable_frontier(board, _mg)
                    if _snap is not None and _sd > 0:
                        engine.restore_continuation_snapshot(_snap)
                        reused_from_depth = _sd
                except Exception:
                    reused_from_depth = 0
            else:
                try:
                    engine.tt.clear()
                except Exception:
                    pass
            if reused_from_depth > 0:
                result = engine.search(board, time_limit=2000,
                                       multipv=multipv_count,
                                       continue_from=reused_from_depth,
                                       unlimited=True)
            else:
                result = engine.search(board, time_limit=2000,
                                       multipv=multipv_count)
        move, score, depth, nodes = result[0], result[1], result[2], result[3]
        elapsed = max(time.time()-start,0.001)
        cp = score
        if abs(cp)>29000:
            mate = math.ceil((30000 - abs(cp)) / 2)
            score_text = f"M{mate}" if cp>0 else f"-M{mate}"
            win_prob = 100 if cp>0 else 0
        else:
            score_text = f"{cp/100:+.2f}"
            win_prob = 100/(1+math.exp(-cp/400))
        pv = engine.get_pv(); pv_str = [move_to_str(m) for m in pv]
        multipv = []
        if hasattr(engine,'sorted_root_scores'):
            total = len(engine.sorted_root_scores)
            if total>0:
                multipv_count = max(1,min(multipv_count,total))
                for m,s in engine.sorted_root_scores[:multipv_count]:
                    multipv.append({'move':move_to_str(m),'score':s})
        return jsonify({
            'fen':board.to_fen(),'score':score_text,'cp':cp,'win_prob':win_prob,
            'best_move':move_to_str(move) if move else None,'depth':engine.current_depth,
            'nodes':nodes,'nps':int(nodes/elapsed),'pv':pv_str,'multipv':multipv,
            'reused_from_depth':reused_from_depth,
            'move_history':move_history,'engine_name':'ChessAI','engine_version':'1.0'
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/jump', methods=['POST'])
def api_jump():
    try:
        data = request.get_json()
        moves = data.get('moves',[]); index = data.get('index',0)
        if index<0 or index>len(moves): return jsonify({'error':'Invalid index'}),400
        board = ChessBoard()
        for i in range(index):
            move = str_to_move(moves[i])
            if not move or move not in board.generate_legal_moves():
                return jsonify({'error':f'Illegal move at {i}'}),400
            board.make_move(move)
        return jsonify({'fen':board.to_fen()})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/pgn', methods=['POST'])
def api_pgn():
    try:
        data = request.get_json()
        moves = data.get('moves',[])
        board = ChessBoard()
        san_moves = []
        for uci in moves:
            move = str_to_move(uci)
            if not move or move not in board.generate_legal_moves():
                return jsonify({'error':f'Invalid move: {uci}'}),400
            san = move_to_san(move, board); san_moves.append(san); board.make_move(move)
        pgn = '[Event "Browser Analysis"]\n[Site "Termux"]\n[Date "'+time.strftime('%Y.%m.%d')+'"]\n[White "?"]\n[Black "?"]\n'
        pgn += ' '.join(f'{i//2+1}. {s}' if i%2==0 else s for i,s in enumerate(san_moves))
        return jsonify({'pgn':pgn})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/database_games')
def api_database_games():
    try:
        rows = _database_game_rows()
        return jsonify({'total': len(rows), 'games': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/game/<int:game_id>')
def api_database_game(game_id):
    try:
        conn = _db_ro()
        game = conn.execute("SELECT id, white, black, result, white_elo, black_elo, date, eco, opening, termination, raw_pgn, source, platform_game_id FROM games WHERE id=?", (game_id,)).fetchone()
        if not game:
            conn.close()
            return jsonify({'error':'Game not found'}),404
        moves = conn.execute("SELECT ply, uci, san, p.fen FROM game_moves gm JOIN positions p ON p.id=gm.position_id WHERE gm.game_id=? ORDER BY ply", (game_id,)).fetchall()
        conn.close()
        return jsonify({'game': dict(game), 'moves': [dict(r) for r in moves]})
    except Exception as e:
        return jsonify({'error': str(e)}),500

@app.route('/api/node_games')
def api_node_games():
    try:
        fen = request.args.get('fen', '')
        mode = str(request.args.get('mode', 'all') or 'all').strip().lower()
        valid_modes = {'all', 'my-games', 'opp-games', 'my-white', 'my-black'}
        if mode not in valid_modes:
            return jsonify({'error': f'Invalid mode: {mode}'}), 400
        if not fen:
            return jsonify({'error': 'Missing fen'}), 400

        canonical = normalize_position_key(fen)
        conn = _db_ro()

        pos = conn.execute(
            'SELECT id, fen, canonical_fen FROM positions '
            'WHERE fen=? OR canonical_fen=? '
            'ORDER BY CASE WHEN fen=? THEN 0 ELSE 1 END LIMIT 1',
            (fen, canonical, fen)
        ).fetchone()

        if not pos:
            return jsonify({
                'fen': fen, 'mode': mode,
                'canonical_fen': canonical,
                'count': 0, 'white_wins': 0, 'black_wins': 0, 'draws': 0,
                'games': [], 'white_games': [], 'black_games': [], 'draw_games': [],
                'sample_pgns': [],
                'my_white_count': 0, 'my_white_wins': 0, 'my_white_draws': 0, 'my_white_losses': 0,
                'my_black_count': 0, 'my_black_wins': 0, 'my_black_draws': 0, 'my_black_losses': 0,
                'mode_count': 0, 'mode_white_wins': 0, 'mode_black_wins': 0, 'mode_draws': 0,
                'mode_games': [], 'mode_white_games': [], 'mode_black_games': [],
                'mode_draw_games': [], 'mode_sample_pgns': [],
            })

        target_canonical = pos['canonical_fen'] or canonical
        rows = conn.execute(
            'SELECT DISTINCT g.id, g.white, g.black, g.result, g.white_elo, g.black_elo, g.date, g.eco '
            'FROM game_moves gm '
            'JOIN positions p ON p.id = gm.position_id '
            'JOIN games g ON g.id = gm.game_id '
            'WHERE p.canonical_fen = ? ORDER BY g.id',
            (target_canonical,)
        ).fetchall()

        alias_rows = conn.execute(
            "SELECT alias FROM player_aliases "
            "UNION SELECT canonical_name FROM canonical_players"
        ).fetchall()
        aliases = {(r[0] or '').strip().lower() for r in alias_rows if r and r[0]}

        def _is_me_white(r):
            return (r['white'] or '').strip().lower() in aliases

        def _is_me_black(r):
            return (r['black'] or '').strip().lower() in aliases

        my_white_rows = [r for r in rows if _is_me_white(r)]
        my_black_rows = [r for r in rows if _is_me_black(r)]

        parts = target_canonical.split()
        moving_side = parts[1] if len(parts) > 1 else 'w'

        if mode == 'all':
            mode_rows = list(rows)
        elif mode == 'my-white':
            mode_rows = my_white_rows
        elif mode == 'my-black':
            mode_rows = my_black_rows
        elif mode == 'my-games':
            mode_rows = my_white_rows if moving_side == 'w' else my_black_rows
        else:
            mode_rows = my_black_rows if moving_side == 'w' else my_white_rows

        count = len(rows)
        w = sum(1 for r in rows if r['result'] == '1-0')
        b = sum(1 for r in rows if r['result'] == '0-1')
        d = sum(1 for r in rows if r['result'] == '1/2-1/2')

        my_white_count = len(my_white_rows)
        my_white_wins = sum(1 for r in my_white_rows if r['result'] == '1-0')
        my_white_draws = sum(1 for r in my_white_rows if r['result'] == '1/2-1/2')
        my_white_losses = sum(1 for r in my_white_rows if r['result'] == '0-1')

        my_black_count = len(my_black_rows)
        my_black_wins = sum(1 for r in my_black_rows if r['result'] == '0-1')
        my_black_draws = sum(1 for r in my_black_rows if r['result'] == '1/2-1/2')
        my_black_losses = sum(1 for r in my_black_rows if r['result'] == '1-0')

        mode_count = len(mode_rows)
        mode_w = sum(1 for r in mode_rows if r['result'] == '1-0')
        mode_b = sum(1 for r in mode_rows if r['result'] == '0-1')
        mode_d = sum(1 for r in mode_rows if r['result'] == '1/2-1/2')

        def _row(r):
            return {
                'id': r['id'], 'white': r['white'], 'black': r['black'],
                'result': r['result'], 'white_elo': r['white_elo'],
                'black_elo': r['black_elo'], 'date': r['date'], 'eco': r['eco'],
            }

        white_games = [_row(r) for r in rows if r['result'] == '1-0'][:50]
        black_games = [_row(r) for r in rows if r['result'] == '0-1'][:50]
        draw_games = [_row(r) for r in rows if r['result'] == '1/2-1/2'][:50]

        mode_games = [_row(r) for r in mode_rows[:50]]
        mode_white_games = [_row(r) for r in mode_rows if r['result'] == '1-0'][:50]
        mode_black_games = [_row(r) for r in mode_rows if r['result'] == '0-1'][:50]
        mode_draw_games = [_row(r) for r in mode_rows if r['result'] == '1/2-1/2'][:50]

        full_sample_ids = [r['id'] for r in rows[:5]]
        samples = []
        if full_sample_ids:
            marks = ','.join('?' * len(full_sample_ids))
            samples = [r[0] for r in conn.execute(
                'SELECT raw_pgn FROM games WHERE id IN (' + marks + ') ORDER BY id',
                tuple(full_sample_ids)).fetchall()]

        mode_sample_ids = [r['id'] for r in mode_rows[:5]]
        mode_samples = []
        if mode_sample_ids:
            marks = ','.join('?' * len(mode_sample_ids))
            mode_samples = [r[0] for r in conn.execute(
                'SELECT raw_pgn FROM games WHERE id IN (' + marks + ') ORDER BY id',
                tuple(mode_sample_ids)).fetchall()]

        return jsonify({
            'fen': pos['fen'], 'mode': mode,
            'canonical_fen': target_canonical,
            'count': count, 'white_wins': w, 'black_wins': b, 'draws': d,
            'games': [dict(r) for r in rows[:50]],
            'white_games': white_games, 'black_games': black_games, 'draw_games': draw_games,
            'sample_pgns': samples,
            'my_white_count': my_white_count, 'my_white_wins': my_white_wins,
            'my_white_draws': my_white_draws, 'my_white_losses': my_white_losses,
            'my_black_count': my_black_count, 'my_black_wins': my_black_wins,
            'my_black_draws': my_black_draws, 'my_black_losses': my_black_losses,
            'mode_count': mode_count, 'mode_white_wins': mode_w,
            'mode_black_wins': mode_b, 'mode_draws': mode_d,
            'mode_games': mode_games,
            'mode_white_games': mode_white_games,
            'mode_black_games': mode_black_games,
            'mode_draw_games': mode_draw_games,
            'mode_sample_pgns': mode_samples,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/api/tree', methods=['POST'])
def api_tree():
    try:
        data = request.get_json()
        fen = data.get('fen','startpos')
        moves = get_moves(fen); eco = get_eco(fen)

        if moves:
            import chess
            board = chess.Board() if fen == 'startpos' else chess.Board(fen)
            child_fens = []
            for m in moves:
                pushed = False
                try:
                    move = chess.Move.from_uci(m['uci'])
                    board.push(move)
                    pushed = True
                    child_fens.append(normalize_position_key(board.fen()))
                except Exception:
                    child_fens.append(None)
                finally:
                    if pushed:
                        try: board.pop()
                        except Exception: pass

            scores_map = _get_tree_scores(child_fens)

            new_moves = []
            for i, m in enumerate(moves):
                m_dict = dict(m)
                cf = child_fens[i]
                if cf and cf in scores_map:
                    is_black = cf.split()[1] == 'b'
                    mult = -1 if is_black else 1

                    m_dict['engine_score'] = scores_map[cf].get('engine_score')
                    m_dict['engine_depth'] = scores_map[cf].get('engine_depth')
                    m_dict['engine_score_type'] = scores_map[cf].get('engine_score_type')
                    m_dict['engine_mate_moves'] = scores_map[cf].get('engine_mate_moves')
                    m_dict['engine_mate_sign'] = scores_map[cf].get('engine_mate_sign')
                    m_dict['engine_source'] = scores_map[cf].get('engine_source')

                    m_dict['sf_score'] = scores_map[cf].get('sf_score')
                    m_dict['sf_depth'] = scores_map[cf].get('sf_depth')
                    m_dict['sf_score_type'] = scores_map[cf].get('sf_score_type')
                    m_dict['sf_mate_moves'] = scores_map[cf].get('sf_mate_moves')
                    m_dict['sf_mate_sign'] = scores_map[cf].get('sf_mate_sign')
                    m_dict['sf_source'] = scores_map[cf].get('sf_source')

                    if m_dict['engine_score'] is not None: m_dict['engine_score'] *= mult
                    if m_dict['engine_mate_sign'] is not None: m_dict['engine_mate_sign'] *= mult
                    if m_dict['sf_score'] is not None: m_dict['sf_score'] *= mult
                    if m_dict['sf_mate_sign'] is not None: m_dict['sf_mate_sign'] *= mult
                new_moves.append(m_dict)
        else:
            new_moves = moves

        return jsonify({'fen':fen,'eco':eco.get('eco','A00'),'opening':eco.get('name','Unclassified'),'moves':new_moves})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/game_examples', methods=['POST'])
def api_game_examples():
    try:
        data = request.get_json()
        fen = data.get('fen',''); uci = data.get('uci','')
        if not fen or not uci: return jsonify({'error':'Missing fen or uci'}),400
        examples = get_examples(fen, uci)
        return jsonify({'examples':examples})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire', methods=['GET'])
def api_repertoire_get():
    try:
        fen = request.args.get('fen')
        if fen:
            entry = get_entry_by_fen(fen)
            return jsonify({'fen':fen,'entry':entry or {}})
        entries = get_all_entries()
        return jsonify({'entries':entries})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire', methods=['POST'])
def api_repertoire_set():
    try:
        data = request.get_json()
        fen = data.get('fen')
        if not fen: return jsonify({'error':'Missing fen'}),400
        entry = data.get('data',{})
        set_entry_by_fen(fen, entry)
        return jsonify({'status':'ok'})
    except ValueError as e:
        return jsonify({'error':str(e)}),400
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire/<fen>', methods=['DELETE'])
def api_repertoire_delete(fen):
    try:
        delete_entry_by_fen(fen)
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire/stats', methods=['GET'])
def api_repertoire_stats():
    try:
        entries = get_all_entries()
        total = len(entries)
        due = len(get_due_positions())
        success_total = sum(e[1].get('success_count',0) for e in entries)
        fail_total = sum(e[1].get('fail_count',0) for e in entries)
        accuracy = round(success_total/(success_total+fail_total)*100,1) if (success_total+fail_total)>0 else 0
        white_count = sum(1 for _,e in entries if e.get('color')=='white')
        black_count = sum(1 for _,e in entries if e.get('color')=='black')
        return jsonify({
            'total_positions':total,'due_positions':due,'total_success':success_total,
            'total_fail':fail_total,'accuracy':accuracy,'white_count':white_count,'black_count':black_count
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire/export', methods=['GET'])
def api_repertoire_export():
    try:
        return jsonify(export_repertoire())
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/repertoire/import', methods=['POST'])
def api_repertoire_import():
    try:
        data = request.get_json()
        if not data or not data.get('positions'): return jsonify({'error':'Invalid data'}),400
        if data.get('version') != 2: return jsonify({'error':'Unsupported version'}),400
        rep = load_repertoire()
        for fid, entry in data['positions'].items():
            if fid in rep['positions']: rep['positions'][fid].update(entry)
            else: rep['positions'][fid] = entry
        save_repertoire(rep)
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/train/next', methods=['GET'])
def api_train_next():
    try:
        due = get_due_positions()
        if not due: return jsonify({'fen':None,'entry':None})
        fid, data = due[0]
        from opening import get_fen_from_id
        fen = get_fen_from_id(int(fid))
        if not fen: return jsonify({'fen':None,'entry':None})
        eco = get_eco(fen)
        return jsonify({'fen':fen,'entry':data,'eco':eco})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/train/review', methods=['POST'])
def api_train_review():
    try:
        data = request.get_json()
        fen = data.get('fen'); user_input = data.get('move','').strip()
        if not fen or not user_input: return jsonify({'error':'Missing fen or move'}),400
        entry = get_entry_by_fen(fen)
        if not entry: return jsonify({'error':'No entry for this FEN'}),400
        expected_uci = entry.get('main_move','')
        if not expected_uci: return jsonify({'error':'No main move set'}),400
        board = ChessBoard(); board.set_fen(fen)
        expected_move = str_to_move(expected_uci)
        if not expected_move: return jsonify({'error':'Invalid main move'}),400
        user_norm = normalize_move(user_input)
        correct = False
        for m in board.generate_legal_moves():
            san = normalize_move(move_to_san(m, board))
            uci = normalize_move(move_to_str(m))
            if user_norm in (san, uci):
                if m == expected_move: correct = True
                break
        if correct: entry['success_count'] = entry.get('success_count',0)+1
        else: entry['fail_count'] = entry.get('fail_count',0)+1
        interval, easiness = calculate_interval(correct, entry.get('interval',1), entry.get('easiness',2.5))
        entry['interval'] = interval; entry['easiness'] = easiness; entry['last_reviewed'] = time.time()
        set_entry_by_fen(fen, entry)
        expected_san = move_to_san(expected_move, board)
        return jsonify({
            'correct':correct,'expected_uci':expected_uci,'expected_san':expected_san,
            'interval':interval,'easiness':round(easiness,2)
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/start_analysis', methods=['POST'])
def start_analysis():
    global _legacy_analysis_job_id
    try:
        with _legacy_analysis_lock:
            prev = _legacy_analysis_job_id
        if prev is not None:
            pj = _get_job(prev)
            if pj is not None and pj.status not in TERMINAL_JOB_STATUSES:
                return jsonify({'error': 'Analysis already running'}), 400
        data = request.get_json(silent=True) or {}
        fen = data.get('fen', 'startpos')
        job = _create_job('analysis', {'fen': fen})
        _start_analysis_job(job)
        with _legacy_analysis_lock:
            _legacy_analysis_job_id = job.job_id
        return jsonify({'status': 'started', 'job_id': job.job_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stop_analysis')
def stop_analysis():
    with _legacy_analysis_lock:
        jid = _legacy_analysis_job_id
    if jid is not None:
        _cancel_job(jid)
    return jsonify({'status': 'stopped'})


@app.route('/api/analysis_status')
def analysis_status():
    with _legacy_analysis_lock:
        jid = _legacy_analysis_job_id
    empty = {'depth': 0, 'score': '', 'best_move': None,
             'pv': [], 'nodes': 0, 'nps': 0}
    if jid is None:
        return jsonify(empty)
    job = _get_job(jid)
    if job is None:
        return jsonify(empty)
    result = job.result or {}
    progress = job.progress or {}
    return jsonify({
        'depth': progress.get('completed_depth', 0),
        'score': result.get('score', ''),
        'best_move': result.get('move'),
        'pv': result.get('pv', []),
        'nodes': progress.get('nodes', 0),
        'nps': progress.get('nps', 0),
        'job_id': jid,
        'status': job.status,
    })

@app.route('/api/reload_opening')
def api_reload_opening():
    try:
        reload_repertoire()
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/import_games', methods=['POST'])
def api_import_games():
    try:
        data = request.get_json() or {}
        source = str(data.get('source','')).strip().lower()
        username = str(data.get('username','')).strip()

        if not username:
            return jsonify({'error':'Username required'}),400

        if source not in ('lichess','chesscom'):
            return jsonify({'error':'Invalid source'}),400

        from pgn_learner import download_all_lichess_games, download_all_chesscom_games

        if source == 'lichess':
            pgn = download_all_lichess_games(username)
        else:
            pgn = download_all_chesscom_games(username)

        if not pgn.strip():
            return jsonify({'error':'No games downloaded'}),400

        pgn_path = os.path.join(CHESS_DIR, 'last_import.pgn')
        with open(pgn_path,'w',encoding='utf-8') as f:
            f.write(pgn)

        os.environ['CHESS_AI_TEST_DB'] = DB_PATH

        import database_v2
        database_v2.DB_PATH = DB_PATH

        from database_v2 import insert_game_audited
        from pgn_utils_v2 import parse_pgn_content_detailed

        records = parse_pgn_content_detailed(pgn)

        with database_ingest_lock:
            summary = insert_game_audited(
                records,
                source=source,
                source_file='last_import.pgn',
                source_username=username,
            )

            rebuilt = False
            if summary.get('new', 0) > 0:
                ok, err = _rebuild_opening_tree_locked()
                if not ok:
                    return jsonify({
                        'error':'Tree build failed',
                        'details':err,
                        'summary':summary,
                    }),500
                rebuilt = True

        return jsonify({
            'status':'ok',
            'message':(
                f'Import complete: {summary["new"]} new games, '
                f'{summary["duplicate_semantic"]} semantic duplicates, '
                f'{summary["duplicate_exact"]} exact duplicates, '
                f'{summary["duplicate_platform"]} platform duplicates, '
                f'{summary["zero_move"]} zero-move records.'
            ),
            'summary':summary,
            'tree_rebuilt':rebuilt,
            'database_games': len(_database_game_rows()),
        })
    except Exception as e:
        return jsonify({'error':str(e)}),500

@app.route('/api/sync', methods=['POST'])
@source_sync_locked
def api_sync():
    try:
        data = request.get_json() or {}
        source = str(data.get("source", "")).strip().lower()
        username = str(data.get("username", "")).strip()

        if source not in ("lichess", "chesscom"):
            return jsonify({
                "status": "error",
                "error": "Invalid source",
            }), 400

        if not username:
            return jsonify({
                "status": "error",
                "error": "Username required",
            }), 400

        # -----------------------------------------------------------------
        # Establish the correct database target BEFORE importing/using
        # database_v2. This is required for temporary-DB tests and for
        # the browser sync endpoint to target production chess_ai.db.
        # -----------------------------------------------------------------
        os.environ["CHESS_AI_TEST_DB"] = DB_PATH

        import database_v2
        database_v2.DB_PATH = DB_PATH

        from database_v2 import (
            get_sync_state,
            set_sync_state,
            set_sync_tree_dirty,
            record_parser_failure_batch,
            insert_game_audited,
        )

        from pgn_learner import (
            download_lichess_games_since,
            download_chesscom_games_since,
        )

        from pgn_utils_v2 import parse_pgn_content_detailed

        SYNC_OVERLAP_MS = 24 * 60 * 60 * 1000
        sync_start_ms = int(time.time() * 1000)

        state = get_sync_state(source, username) or {}
        last_cursor = int(state.get("last_successful_sync_at") or 0)
        previous_batch_id = state.get("last_batch_id")
        tree_dirty = int(state.get("tree_dirty") or 0)

        cursor = max(0, last_cursor - SYNC_OVERLAP_MS)

        tree_rebuilt_this_run = False

        # -----------------------------------------------------------------
        # Repair a previously failed tree rebuild before downloading.
        # This state/rebuild operation is itself serialized with all other
        # database ingestion, so it cannot race import/sync DB writes.
        # -----------------------------------------------------------------
        if tree_dirty:
            with database_ingest_lock:
                ok, err = _rebuild_opening_tree_locked()

                if not ok:
                    return jsonify({
                        "status": "tree_build_failed",
                        "error": err or "Opening tree rebuild failed",
                        "source": source,
                        "username": username,
                        "cursor": last_cursor,
                        "downloaded_count": 0,
                        "new_games": 0,
                        "tree_rebuilt": False,
                        "tree_dirty": True,
                        "last_batch_id": previous_batch_id,
                    }), 500

                tree_rebuilt_this_run = True

                set_sync_state(
                    source,
                    username,
                    last_cursor,
                    previous_batch_id,
                    tree_dirty=0,
                )

            tree_dirty = 0

        newest_ms = None
        downloaded_count = 0

        # -----------------------------------------------------------------
        # Incremental download
        # -----------------------------------------------------------------
        if source == "lichess":
            pgn, downloaded_count, download_error = download_lichess_games_since(username, cursor)
        else:
            pgn, downloaded_count, newest_ms, download_error = download_chesscom_games_since(username, cursor)

        if download_error:
            return jsonify({
                "status": "download_failed",
                "source": source,
                "username": username,
                "error": download_error,
                "cursor": last_cursor,
                "downloaded_count": 0,
                "new_games": 0,
                "tree_rebuilt": tree_rebuilt_this_run,
                "tree_dirty": tree_dirty,
                "last_batch_id": previous_batch_id,
            })

        # -----------------------------------------------------------------
        # No downloaded PGN
        # -----------------------------------------------------------------
        if not pgn.strip():
            next_cursor = max(0, sync_start_ms - SYNC_OVERLAP_MS)

            with database_ingest_lock:
                set_sync_state(
                    source,
                    username,
                    next_cursor,
                    previous_batch_id,
                    tree_dirty=0,
                )

            return jsonify({
                "status": "no_new_games",
                "source": source,
                "username": username,
                "cursor": next_cursor,
                "downloaded_count": 0,
                "new_games": 0,
                "tree_rebuilt": tree_rebuilt_this_run,
                "tree_dirty": 0,
                "last_batch_id": previous_batch_id,
            })

        # -----------------------------------------------------------------
        # Parse complete batch before any database write.
        # -----------------------------------------------------------------
        try:
            records = parse_pgn_content_detailed(pgn)
        except Exception as e:
            return jsonify({
                "status": "import_failed",
                "error": f"PGN parsing exception: {e}",
                "source": source,
                "username": username,
                "cursor": last_cursor,
                "downloaded_count": downloaded_count,
                "new_games": 0,
                "tree_rebuilt": tree_rebuilt_this_run,
                "tree_dirty": tree_dirty,
                "last_batch_id": previous_batch_id,
            }), 500

        NON_FATAL_PARSER_STATUSES = {
            "accepted",
            "zero_move",
            "unsupported_variant",
        }

        fatal_parser_failures = [
            rec
            for rec in records
            if rec.get("parser_status") not in NON_FATAL_PARSER_STATUSES
        ]

        # -----------------------------------------------------------------
        # Serialize ALL DB writes:
        #   parser-failure audit
        #   tree-dirty marking
        #   audited game insertion
        #   tree rebuild state update
        #   sync cursor update
        # -----------------------------------------------------------------
        with database_ingest_lock:
            if fatal_parser_failures:
                failure_summary = record_parser_failure_batch(
                    records,
                    source=source,
                    source_file="last_sync.pgn",
                    source_username=username,
                )

                return jsonify({
                    "status": "import_failed",
                    "error": "One or more downloaded games failed parsing",
                    "failure_count": len(fatal_parser_failures),
                    "first_failure": fatal_parser_failures[0].get("failure_reason"),
                    "source": source,
                    "username": username,
                    "cursor": last_cursor,
                    "downloaded_count": downloaded_count,
                    "new_games": 0,
                    "tree_rebuilt": tree_rebuilt_this_run,
                    "tree_dirty": tree_dirty,
                    "last_batch_id": failure_summary.get("batch_id"),
                    "summary": failure_summary,
                }), 500

            # Mark tree dirty BEFORE the audited DB transaction.
            set_sync_tree_dirty(
                source,
                username,
                batch_id=None,
                dirty=True,
            )
            tree_dirty = 1

            try:
                summary = insert_game_audited(
                    records,
                    source=source,
                    source_file="last_sync.pgn",
                    source_username=username,
                )
            except Exception as e:
                set_sync_tree_dirty(
                    source,
                    username,
                    batch_id=None,
                    dirty=False,
                )
                tree_dirty = 0

                return jsonify({
                    "status": "import_failed",
                    "error": str(e),
                    "source": source,
                    "username": username,
                    "cursor": last_cursor,
                    "downloaded_count": downloaded_count,
                    "new_games": 0,
                    "tree_rebuilt": tree_rebuilt_this_run,
                    "tree_dirty": 0,
                    "last_batch_id": previous_batch_id,
                }), 500

            batch_id = summary.get("batch_id")

            if summary.get("tree_new", 0) == 0:
                set_sync_tree_dirty(
                    source,
                    username,
                    batch_id=None,
                    dirty=False,
                )
                tree_dirty = 0

            if tree_dirty:
                ok, err = _rebuild_opening_tree_locked()
                if not ok:
                    return jsonify({
                        "status": "tree_build_failed",
                        "error": err or "Opening tree rebuild failed",
                        "summary": summary,
                        "source": source,
                        "username": username,
                        "cursor": last_cursor,
                        "downloaded_count": downloaded_count,
                        "tree_rebuilt": tree_rebuilt_this_run,
                        "tree_dirty": True,
                        "last_batch_id": previous_batch_id,
                    }), 500

                tree_rebuilt_this_run = True
                tree_dirty = 0

            watermark_ms = (
                newest_ms
                if source == "chesscom" and newest_ms is not None
                else sync_start_ms
            )

            next_cursor = max(0, watermark_ms - SYNC_OVERLAP_MS)

            set_sync_state(
                source,
                username,
                next_cursor,
                batch_id,
                tree_dirty=0,
            )

        return jsonify({
            "status": "success" if summary.get("new", 0) > 0 else "no_new_after_import",
            "source": source,
            "username": username,
            "cursor": next_cursor,
            "downloaded_count": downloaded_count,
            "summary": summary,
            "tree_rebuilt": tree_rebuilt_this_run,
            "tree_dirty": 0,
            "last_batch_id": batch_id,
            "database_games": len(_database_game_rows()),
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
        }), 500
@app.route('/api/sync_state', methods=['GET'])
def api_sync_state():
    try:
        source = request.args.get('source','').strip().lower()
        username = request.args.get('username','').strip()

        if source not in ('lichess','chesscom'):
            return jsonify({'status':'error','error':'Invalid source'}),400
        if not username:
            return jsonify({'status':'error','error':'Username required'}),400

        from database_v2 import get_sync_state

        state = get_sync_state(source, username)
        if state is None:
            state = {
                'source': source,
                'source_username': username,
                'last_successful_sync_at': None,
                'last_batch_id': None,
                'tree_dirty': 0,
                'updated_at': None,
            }

        india = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_ist = now_utc.astimezone(india)

        day_start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end_ist = day_start_ist + datetime.timedelta(days=1)

        utc_start = day_start_ist.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        utc_end = day_end_ist.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

        conn = _db_ro()
        try:
            today_imported = conn.execute(
                """
                SELECT COALESCE(SUM(new_games), 0)
                FROM import_batches
                WHERE source = ?
                  AND source_username = ?
                  AND started_at >= ?
                  AND started_at < ?
                """,
                (source, username, utc_start, utc_end),
            ).fetchone()[0]
        finally:
            conn.close()

        return jsonify({
            'status': 'ok',
            'source': source,
            'username': username,
            'state': state,
            'today_imported': today_imported,
        })
    except Exception as e:
        return jsonify({'status':'error','error':str(e)}),500

@app.route('/api/sync/start', methods=['POST'])
def api_sync_start():
    try:
        data = request.get_json() or {}
        source = str(data.get('source', '')).strip().lower()
        username = str(data.get('username', '')).strip()

        if source not in ('lichess', 'chesscom'):
            return jsonify({'status': 'error', 'error': 'Invalid source'}), 400
        if not username:
            return jsonify({'status': 'error', 'error': 'Username required'}), 400

        from database_v2 import (
            get_active_sync_job,
            create_sync_job,
            claim_sync_job,
            terminate_sync_job_with_owner,
        )

        active_id = get_active_sync_job(source, username)
        if active_id is not None:
            return jsonify({
                'status': 'already_running',
                'job_id': active_id,
            }), 409

        job_id = create_sync_job(source, username)
        if job_id is None:
            return jsonify({'status': 'already_running', 'job_id': None}), 409

        worker_pid = os.getpid()

        if not claim_sync_job(job_id, worker_pid):
            return jsonify({'status': 'error', 'error': 'Could not claim job'}), 500

        if not start_sync_job_worker_thread(job_id):
            # Clean up the claimed job because we couldn't start a worker thread.
            try:
                terminate_sync_job_with_owner(
                    job_id=job_id,
                    worker_pid=worker_pid,
                    source=source,
                    source_username=username,
                    terminal_status="failed",
                    phase="failed",
                    error="worker thread start failed",
                )
            except Exception:
                pass

            return jsonify({
                'status': 'error',
                'error': 'Could not start worker thread',
            }), 500

        return jsonify({
            'status': 'started',
            'job_id': job_id,
        })
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/sync/status', methods=['GET'])
def api_sync_status():
    try:
        job_id = request.args.get('job_id')
        if not job_id:
            return jsonify({'status': 'error', 'error': 'Missing job_id'}), 400

        from database_v2 import get_sync_job

        job = get_sync_job(job_id)
        if job is None:
            return jsonify({'status': 'error', 'error': 'Job not found'}), 404

        return jsonify({'status': 'ok', 'job': job})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/api/sync/cancel', methods=['POST'])
def api_sync_cancel():
    try:
        data = request.get_json() or {}
        job_id = data.get('job_id')

        if not job_id:
            return jsonify({'status': 'error', 'error': 'Missing job_id'}), 400

        from database_v2 import request_cancel_sync_job

        changed = request_cancel_sync_job(job_id)
        if not changed:
            return jsonify({'status': 'error', 'error': 'Job not running'}), 409

        return jsonify({'status': 'cancel_requested', 'job_id': int(job_id)})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


@app.route('/')
def index():
    return send_from_directory('.', 'frontend/index.html')

@app.route('/<path:path>')
def static_files(path):
    if os.path.exists(path): return send_from_directory('.', path)
    if os.path.exists(os.path.join('frontend', path)): return send_from_directory('frontend', path)
    return "Not found", 404

live_game_lock = threading.Lock()
class LiveGame:
    def __init__(self, white_type, black_type):
        self.white_type = white_type
        self.black_type = black_type
        self.board = ChessBoard()
        self.engine = SearchEngine(nn=nn, max_depth=12)
        self.status = "playing"
        self.move_count = 0
        self.last_move = None
        self.lock = threading.Lock()

    def run(self):
        """Main game loop – one ply at a time, 2 sec delay for non‑human moves."""
        while self.status == "playing":
            if self.board.is_checkmate() or self.board.is_stalemate() or self.board.is_insufficient_material():
                with self.lock:
                    self.status = "draw" if self.board.is_stalemate() or self.board.is_insufficient_material() else ("white_wins" if self.board.white_turn else "black_wins")
                break

            side = "white" if self.board.white_turn else "black"
            player_type = self.white_type if side == "white" else self.black_type

            if player_type == "human":
                # Wait for human move via /api/human_move
                time.sleep(0.2)
                continue

            if player_type == "engine":
                result = self.engine.search(self.board, 300)
                move = result[0]  # first element is the move tuple
            else:  # random
                legal = self.board.generate_legal_moves()
                move = random.choice(legal) if legal else None

            if move is None:
                with self.lock:
                    self.status = "draw"
                break

            self.board.make_move(move)
            self.move_count += 1
            with self.lock:
                self.last_move = move_to_str(move)
            time.sleep(2)   # watchable speed


live_game = None
live_game_thread = None

@app.route("/api/start_live_game", methods=["POST"])
def start_live_game():
    global live_game, live_game_thread
    data = request.get_json()
    white = data.get("white", "engine")
    black = data.get("black", "engine")
    with live_game_lock:
        if live_game and live_game.status == "playing":
            return jsonify({"error": "Game already running"}), 400
        live_game = LiveGame(white, black)
    live_game_thread = threading.Thread(target=live_game.run, daemon=True)
    live_game_thread.start()
    return jsonify({"status": "started"})

@app.route("/api/stop_live_game", methods=["POST"])
def stop_live_game():
    global live_game
    if live_game:
        with live_game.lock:
            live_game.status = "stopped"
    return jsonify({"status": "stopped"})

@app.route("/api/live_game_state")
def live_game_state():
    if not live_game:
        return jsonify({"active": False})
    with live_game.lock:
        return jsonify({
            "active": True,
            "fen": live_game.board.to_fen(),
            "last_move": live_game.last_move,
            "move_count": live_game.move_count,
            "status": live_game.status,
            "white_type": live_game.white_type,
            "black_type": live_game.black_type,
        })

import queue

# Queue for streaming live game FENs to SSE clients
fen_queue = queue.Queue()

@app.route("/api/stream_game")
def stream_game():
    def event_stream():
        while True:
            fen = fen_queue.get()   # blocks until new FEN is available
            yield f"data: {fen}\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


# BEGIN STOCKFISH ANALYSIS
import subprocess, threading, atexit, os, logging, time
from logging.handlers import RotatingFileHandler
from flask import abort

logger = logging.getLogger("stockfish_analysis")
logger.setLevel(logging.INFO)
if not logger.handlers:
    rh = RotatingFileHandler("stockfish_analysis.log", maxBytes=1_000_000, backupCount=2)
    rh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(rh)
    logger.propagate = False

sf_process = None
sf_lock = threading.Lock()
sf_current_options = {"Hash": 256, "Threads": 2, "MultiPV": 3}
sf_restart_count = 0
sf_generation = 0

_SF_PATH_CACHE = None
_SF_HASH_CACHE = None
_SF_STAT_CACHE = None
sf_binary_hash = "unavailable"
SF_ADAPTER_VERSION = 1

def _get_sf_identity(force_hash=False):
    global _SF_PATH_CACHE, _SF_HASH_CACHE, _SF_STAT_CACHE
    import shutil, hashlib
    sf_path = shutil.which("stockfish")
    if not sf_path:
        return None, "unavailable"

    try:
        st = os.stat(sf_path)
        current_stat = (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)
    except Exception:
        current_stat = None

    if not force_hash and current_stat and _SF_PATH_CACHE == sf_path and _SF_STAT_CACHE == current_stat and _SF_HASH_CACHE:
        return sf_path, _SF_HASH_CACHE

    try:
        with open(sf_path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        _SF_PATH_CACHE = sf_path
        _SF_STAT_CACHE = current_stat
        _SF_HASH_CACHE = h
        return sf_path, h
    except Exception:
        return sf_path, "unavailable"

def get_stockfish():
    global sf_process, sf_restart_count, sf_generation, sf_current_options, sf_binary_hash
    if sf_process is None or sf_process.poll() is not None:
        sf_restart_count += 1
        sf_generation += 1
        sf_path, sf_binary_hash = _get_sf_identity(force_hash=True)
        if not sf_path or sf_binary_hash == "unavailable":
            logger.error("Stockfish executable not found.")
            raise RuntimeError("Stockfish executable not found")

        logger.info(f"Starting Stockfish process (generation {sf_generation}, restart #{sf_restart_count})")
        sf_process = subprocess.Popen(
            [sf_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True
        )
        sf_process.stdin.write("uci\n")
        sf_process.stdin.flush()
        while True:
            line = sf_process.stdout.readline()
            if not line:
                logger.error("Stockfish closed unexpectedly during uci")
                raise RuntimeError("Stockfish closed unexpectedly during uci")
            if "uciok" in line:
                break
        sf_current_options = {}
        sf_process.stdin.write("setoption name Hash value 256\n")
        sf_process.stdin.write("setoption name Threads value 2\n")
        sf_process.stdin.write("setoption name MultiPV value 3\n")
        sf_process.stdin.write("isready\n")
        sf_process.stdin.flush()
        while True:
            line = sf_process.stdout.readline()
            if not line:
                logger.error("Stockfish closed unexpectedly during isready")
                raise RuntimeError("Stockfish closed unexpectedly during isready")
            if "readyok" in line:
                break
        sf_current_options["Hash"] = 256
        sf_current_options["Threads"] = 2
        sf_current_options["MultiPV"] = 3
    return sf_process, sf_generation

def apply_sf_option(sf, name, value):
    if sf_current_options.get(name) != value:
        logger.info(f"Setting {name} = {value}")
        sf.stdin.write(f"setoption name {name} value {value}\n")
        sf.stdin.write("isready\n")
        sf.stdin.flush()
        while True:
            line = sf.stdout.readline()
            if not line:
                logger.error("Stockfish closed unexpectedly during option change")
                raise RuntimeError("Stockfish closed unexpectedly during option change")
            if "readyok" in line:
                break
        sf_current_options[name] = value

def terminate_stockfish():
    global sf_process
    with sf_lock:
        if sf_process and sf_process.poll() is None:
            try:
                logger.info("Terminating Stockfish")
                sf_process.stdin.write("quit\n")
                sf_process.stdin.flush()
                sf_process.wait(timeout=2)
            except Exception as e:
                logger.warning(f"Error terminating Stockfish: {e}")
atexit.register(terminate_stockfish)

def analysis_watchdog(proc, max_wait, finished_event, gen):
    if not finished_event.wait(timeout=max_wait):
        should_kill = False
        with sf_lock:
            if gen == sf_generation and proc.poll() is None:
                should_kill = True
        if should_kill:
            logger.error(f"Watchdog triggered after {max_wait}s (generation {gen}) – killing Stockfish")
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

@app.route("/api/analyze_sf", methods=["POST"])
def analyze_sf():
    global sf_process

    data = request.get_json(silent=True) or {}
    fen = data.get("fen", "startpos")

    def _int_param(key, default, min_val, max_val):
        val = data.get(key, default)
        try:
            ival = int(val)
        except (TypeError, ValueError):
            abort(400, description=f"Invalid integer for {key}: {val}")
        return max(min_val, min(max_val, ival))

    multi_pv = _int_param("multi_pv", 3, 1, 8)
    movetime = _int_param("movetime", 1500, 100, 30000)
    threads  = _int_param("threads", 2, 1, os.cpu_count() or 4)
    hash_mb  = _int_param("hash_mb", 256, 16, 1024)

    logger.info(f"Analysis request: multi_pv={multi_pv}, movetime={movetime}, threads={threads}, hash={hash_mb}")

    start_time = time.time()
    finished_event = None

    local_sf_hash = "unavailable"
    try:
        with sf_lock:
            sf, gen = get_stockfish()
            local_sf_hash = sf_binary_hash
            apply_sf_option(sf, "Threads", threads)
            apply_sf_option(sf, "Hash", hash_mb)
            apply_sf_option(sf, "MultiPV", multi_pv)

            if fen == "startpos":
                sf.stdin.write("ucinewgame\n")
                sf.stdin.write("position startpos\n")
            else:
                if not fen or not isinstance(fen, str) or len(fen.split()) < 4:
                    logger.warning("Invalid FEN received")
                    return jsonify({"error": "Invalid FEN"}), 400
                sf.stdin.write("ucinewgame\n")
                sf.stdin.write(f"position fen {fen}\n")
            sf.stdin.write(f"go movetime {movetime}\n")
            sf.stdin.flush()

            finished_event = threading.Event()
            max_wait = max(movetime * 3 / 1000 + 10, 30)
            watchdog_thread = threading.Thread(
                target=analysis_watchdog, args=(sf, max_wait, finished_event, gen), daemon=True
            )
            watchdog_thread.start()

            pv_map = {}
            while True:
                line = sf.stdout.readline()
                if not line:
                    sf_process = None
                    raise RuntimeError("Stockfish closed unexpectedly during analysis")
                line = line.strip()
                if line.startswith("bestmove"):
                    break
                if line.startswith("info") and "multipv" in line:
                    parts = line.split()
                    try:
                        pv_idx = parts.index("multipv") + 1
                        score_idx = parts.index("score") + 1
                        pv_start = parts.index("pv") + 1
                        multipv = int(parts[pv_idx])
                        score_type = parts[score_idx]
                        score_val = int(parts[score_idx + 1])
                        if score_type == "mate":
                            sign = "+" if score_val > 0 else "-"
                            score_str = f"{sign}M{abs(score_val)}"
                        else:
                            score_str = f"{'+' if score_val >= 0 else ''}{score_val / 100:.2f}"
                        exact = True
                        cp_val = None
                        mate_dist = None
                        if "lowerbound" in line or "upperbound" in line:
                            exact = False
                        elif score_type == "mate":
                            mate_dist = score_val
                        elif score_type == "cp":
                            cp_val = score_val
                        else:
                            exact = False

                        if not exact:
                            score_str = score_str + "?"

                        depth_idx = parts.index("depth") + 1
                        depth_val = int(parts[depth_idx])
                        moves = " ".join(parts[pv_start:])
                        pv_map[multipv] = {"multipv": multipv, "score": score_str, "cp": cp_val, "mate": mate_dist, "uci_pv": moves, "depth": depth_val, "exact": exact}
                    except (ValueError, IndexError):
                        pass

            finished_event.set()

        elapsed = time.time() - start_time
        logger.info(f"Analysis completed in {elapsed:.2f}s")
        lines = [pv_map[i] for i in sorted(pv_map)]
        _save_stockfish_score(fen, pv_map, multi_pv, local_sf_hash)
        return jsonify({"lines": lines})

    except RuntimeError as e:
        if finished_event: finished_event.set()
        with sf_lock:
            sf_process = None
        logger.error(f"Analysis error: {e}")
        return jsonify({"error": str(e)}), 503
    except Exception:
        if finished_event: finished_event.set()
        raise
# END STOCKFISH ANALYSIS

if __name__ == '__main__':
    # Production startup migration + stale background-job recovery.
    try:
        from database_v2 import mark_stale_sync_jobs_interrupted
        recovered = mark_stale_sync_jobs_interrupted(stale_after_seconds=300)
        if recovered:
            print(f"Startup sync-job recovery: marked {recovered} stale job(s).", flush=True)
    except Exception as exc:
        print(f"Startup sync-job recovery skipped: {exc}", flush=True)

    app.run(host='0.0.0.0', port=5000, debug=False)
