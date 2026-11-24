#!/usr/bin/env python3
"""Dual‑head neural network with incremental feature updates.
   After evaluate(), board._pending_delta is always None.
"""

import numpy as np
import pickle, os, stat, tempfile
from move_helpers import NUM_MOVES
from board import MoveDelta

_FEATURE_IDX = np.zeros((64, 12), dtype=np.int32)
for sq in range(64):
    for pt in range(12):
        _FEATURE_IDX[sq, pt] = sq * 12 + pt

PIECE_TO_IDX = {
    'P':0,'N':1,'B':2,'R':3,'Q':4,'K':5,
    'p':6,'n':7,'b':8,'r':9,'q':10,'k':11
}

DEBUG_INCREMENTAL = False

class FeatureCache:
    __slots__ = ('feature', 'hash', 'parent')
    def __init__(self, parent_network):
        self.parent = parent_network
        self.feature = np.zeros(parent_network.INPUT_SIZE, dtype=np.float32)
        self.hash = None

    def build_full(self, board):
        self.parent._compute_features_into(board, self.feature)
        self.hash = board.hash

    def apply_delta(self, delta):
        for sq, old_piece, new_piece in delta.piece_changes:
            if old_piece != '.':
                pt = PIECE_TO_IDX.get(old_piece)
                if pt is not None:
                    self.feature[_FEATURE_IDX[sq, pt]] = 0.0
            if new_piece != '.':
                pt = PIECE_TO_IDX.get(new_piece)
                if pt is not None:
                    self.feature[_FEATURE_IDX[sq, pt]] = 1.0
        self.feature[768] = 1.0 if delta.white_turn else -1.0
        self.feature[769] = 1.0 if delta.castling.get('K', False) else 0.0
        self.feature[770] = 1.0 if delta.castling.get('Q', False) else 0.0
        self.feature[771] = 1.0 if delta.castling.get('k', False) else 0.0
        self.feature[772] = 1.0 if delta.castling.get('q', False) else 0.0
        self.feature[773:781] = 0.0
        if delta.ep is not None:
            ep_rank, ep_file = delta.ep
            self.feature[773 + ep_file] = 1.0
        self.feature[781] = delta.repetition_flag
        self.feature[782] = delta.halfmove / 100.0
        self.hash = delta.new_hash


class DualNet:
    INPUT_SIZE = 783

    def __init__(self, hidden1=512, hidden2=256):
        self.w1 = np.random.normal(0, np.sqrt(2.0/self.INPUT_SIZE), (hidden1, self.INPUT_SIZE)).astype(np.float32)
        self.b1 = np.zeros(hidden1, dtype=np.float32)
        self.w2 = np.random.normal(0, np.sqrt(2.0/hidden1), (hidden2, hidden1)).astype(np.float32)
        self.b2 = np.zeros(hidden2, dtype=np.float32)
        self.v_w = np.random.normal(0, np.sqrt(2.0/hidden2), (1, hidden2)).astype(np.float32)
        self.v_b = np.zeros(1, dtype=np.float32)
        self.p_w = np.random.normal(0, np.sqrt(2.0/hidden2), (NUM_MOVES, hidden2)).astype(np.float32)
        self.p_b = np.zeros(NUM_MOVES, dtype=np.float32)

    def _prepare_features(self, board):
        cache = board._nn_cache
        delta = board._pending_delta

        if cache is None:
            cache = FeatureCache(self)
            board._nn_cache = cache
            cache.build_full(board)
        elif delta is not None:
            # Verify the delta's starting state matches the cache's
            # current state before applying it. A search-level nn_cache
            # hit can leave a delta unconsumed while the cache stays at
            # an earlier position; applying it would silently corrupt
            # the feature vector. Fall back to a full rebuild when the
            # delta's old_hash is missing or does not match.
            delta_old = getattr(delta, 'old_hash', None)
            if delta_old is not None and delta_old == cache.hash:
                cache.apply_delta(delta)
                if DEBUG_INCREMENTAL:
                    fresh = np.zeros_like(cache.feature)
                    self._compute_features_into(board, fresh)
                    if not np.allclose(cache.feature, fresh, atol=1e-7):
                        raise AssertionError("Incremental feature mismatch")
                if cache.hash != board.hash:
                    cache.build_full(board)
            else:
                cache.build_full(board)
        else:
            cache.build_full(board)

        board._pending_delta = None   # invariant guaranteed
        return cache.feature

    def evaluate(self, board):
        x = self._prepare_features(board)
        val, pol = self.forward(x)
        return float(val[0]), pol[0]

    def evaluate_value_only(self, board):
        x = self._prepare_features(board)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        if x.shape[0] == 1:
            h1 = np.maximum(0, self.w1 @ x.T + self.b1.reshape(-1, 1)).ravel()
            h2 = np.maximum(0, self.w2 @ h1.reshape(-1, 1) + self.b2.reshape(-1, 1)).ravel()
            v = np.tanh(self.v_w @ h2.reshape(-1, 1) + self.v_b.reshape(-1, 1)).ravel()
            return float(v[0])
        else:
            h1 = np.maximum(0, x @ self.w1.T + self.b1)
            h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
            v = np.tanh(h2 @ self.v_w.T + self.v_b).ravel()
            return float(v[0])

    def _compute_features_into(self, board, out):
        out.fill(0.0)
        for sq in range(64):
            r, c = divmod(sq, 8)
            ch = board.board[r][c]
            if ch == '.': continue
            pt = PIECE_TO_IDX[ch]
            out[_FEATURE_IDX[sq, pt]] = 1.0
        out[768] = 1.0 if board.white_turn else -1.0
        out[769] = 1.0 if board.castling.get('K', False) else 0.0
        out[770] = 1.0 if board.castling.get('Q', False) else 0.0
        out[771] = 1.0 if board.castling.get('k', False) else 0.0
        out[772] = 1.0 if board.castling.get('q', False) else 0.0
        if board.en_passant is not None:
            ep_rank, ep_file = board.en_passant
            out[773 + ep_file] = 1.0
        key = board.hash
        count = board.position_counts.get(key, 0) if board.track_repetition else 0
        out[781] = 1.0 if count >= 3 else 0.0
        out[782] = board.halfmove_clock / 100.0

    def features(self, board):
        f = np.zeros(self.INPUT_SIZE, dtype=np.float32)
        self._compute_features_into(board, f)
        return f

    def forward(self, x):
        if x.ndim == 1: x = x.reshape(1, -1)
        if x.shape[0] == 1:
            h1 = np.maximum(0, self.w1 @ x.T + self.b1.reshape(-1, 1)).ravel()
            h2 = np.maximum(0, self.w2 @ h1.reshape(-1, 1) + self.b2.reshape(-1, 1)).ravel()
            value = np.tanh(self.v_w @ h2.reshape(-1, 1) + self.v_b.reshape(-1, 1)).ravel()
            policy = (self.p_w @ h2.reshape(-1, 1) + self.p_b.reshape(-1, 1)).T
            return value, policy
        else:
            h1 = np.maximum(0, x @ self.w1.T + self.b1)
            h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
            value = np.tanh(h2 @ self.v_w.T + self.v_b).ravel()
            policy = h2 @ self.p_w.T + self.p_b
            return value, policy

    def train(self, positions, targets_value, targets_policy, epochs=10, lr=0.001, batch_size=512, value_loss_weight=1.0):
        X = np.array([self.features(b) for b in positions], dtype=np.float32)
        y_val = np.array(targets_value, dtype=np.float32).reshape(-1,1)
        y_pol = np.array(targets_policy, dtype=np.float32)
        # B-030: convert integer policy indices to one-hot targets
        if y_pol.ndim == 1:
            onehot = np.zeros((len(y_pol), NUM_MOVES), dtype=np.float32)
            onehot[np.arange(len(y_pol)), y_pol.astype(np.int32)] = 1.0
            y_pol = onehot
        n = len(X)
        for ep in range(epochs):
            perm = np.random.permutation(n)
            X_shuf = X[perm]; y_val_shuf = y_val[perm]; y_pol_shuf = y_pol[perm]
            total_loss = 0.0
            for i in range(0, n, batch_size):
                batch_X = X_shuf[i:i+batch_size]; batch_val = y_val_shuf[i:i+batch_size]; batch_pol = y_pol_shuf[i:i+batch_size]
                h1 = np.maximum(0, batch_X @ self.w1.T + self.b1)
                h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
                out_val = np.tanh(h2 @ self.v_w.T + self.v_b)
                out_pol = h2 @ self.p_w.T + self.p_b
                loss_val = np.mean((batch_val - out_val)**2)
                log_probs = out_pol - np.max(out_pol, axis=1, keepdims=True)
                log_probs = log_probs - np.log(np.sum(np.exp(log_probs), axis=1, keepdims=True))
                loss_pol = -np.mean(np.sum(batch_pol * log_probs, axis=1))
                loss = loss_val * value_loss_weight + loss_pol
                total_loss += loss * len(batch_X)
                dout_val = -2 * value_loss_weight * (batch_val - out_val) * (1 - out_val**2) / batch_val.shape[0]
                dv_w = dout_val.T @ h2; dv_b = dout_val.sum(axis=0); dh2_val = dout_val @ self.v_w
                softmax = np.exp(log_probs); dout_pol = softmax - batch_pol
                dp_w = dout_pol.T @ h2; dp_b = dout_pol.sum(axis=0); dh2_pol = dout_pol @ self.p_w
                dh2 = dh2_val + dh2_pol; dh2[h2 <= 0] = 0
                dw2 = dh2.T @ h1; db2 = dh2.sum(axis=0); dh1 = dh2 @ self.w2; dh1[h1 <= 0] = 0
                dw1 = dh1.T @ batch_X; db1 = dh1.sum(axis=0)
                self.v_w -= lr * dv_w; self.v_b -= lr * dv_b; self.p_w -= lr * dp_w; self.p_b -= lr * dp_b
                self.w2 -= lr * dw2; self.b2 -= lr * db2; self.w1 -= lr * dw1; self.b1 -= lr * db1
            avg_loss = total_loss / n
            if (ep+1)%5==0: print(f"  epoch {ep+1}/{epochs}  loss={avg_loss:.4f} (val={loss_val:.4f}, pol={loss_pol:.4f})")

    def save(self, path):
        data = {'w1':self.w1,'b1':self.b1,'w2':self.w2,'b2':self.b2,'v_w':self.v_w,'v_b':self.v_b,'p_w':self.p_w,'p_b':self.p_b}
        # P5.15I follow-up: atomic model save.
        # Use a unique temporary file beside the destination so
        # os.replace remains on the same filesystem. A failed
        # serialization leaves the previous destination untouched.
        target = os.path.realpath(os.fspath(path))
        directory = os.path.dirname(target) or os.curdir
        existing_mode = None
        try:
            existing_mode = stat.S_IMODE(os.stat(target).st_mode)
        except FileNotFoundError:
            pass
        fd, tmp_path = tempfile.mkstemp(
            prefix=f'.{os.path.basename(target)}.',
            suffix='.tmp', dir=directory
        )
        try:
            with os.fdopen(fd, 'wb') as f:
                pickle.dump(data, f)
                f.flush()
                if existing_mode is not None:
                    os.fchmod(f.fileno(), existing_mode)
                os.fsync(f.fileno())
            os.replace(tmp_path, target)
            tmp_path = None
            # Best-effort directory sync for rename durability.
            try:
                dir_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except FileNotFoundError:
                    pass

    def load(self, path):
        if not os.path.exists(path): print(f"WARNING: Model file {path} not found."); return False
        try:
            with open(path, 'rb') as f: data = pickle.load(f)
        except: return False
        if 'w1' in data and data['w1'].shape[1] != self.INPUT_SIZE: print(f"ERROR: Model input size mismatch."); return False
        if 'v_w' not in data:
            print("Converting old single-head model...")
            for k in ['w1','b1','w2','b2']:
                if k in data: setattr(self, k, data[k].astype(np.float32))
            if 'w3' in data:
                old_w3 = data['w3']
                if not isinstance(old_w3, np.ndarray): old_w3 = np.array(old_w3, dtype=np.float32)
                if old_w3.ndim == 1: old_w3 = old_w3.reshape(1, -1); self.v_w = old_w3.astype(np.float32)
            if 'b3' in data:
                old_b3 = data['b3']
                if not isinstance(old_b3, np.ndarray): old_b3 = np.array(old_b3, dtype=np.float32)
                if old_b3.ndim == 0: old_b3 = old_b3.reshape(1); self.v_b = old_b3.astype(np.float32)
            return True
        for k in ['w1','w2','v_w','p_w']:
            if k not in data: return False
            self.__dict__[k] = data[k].astype(np.float32)
        for k in ['b1','b2','v_b','p_b']:
            if k not in data: return False
            self.__dict__[k] = data[k].astype(np.float32)
        if self.v_w.ndim == 1: self.v_w = self.v_w.reshape(1, -1)
        if self.v_b.ndim == 0: self.v_b = self.v_b.reshape(1)
        if self.p_w.shape[0] != NUM_MOVES:
            print(f"WARNING: Policy size mismatch, reinitializing policy head.")
            self.p_w = np.random.normal(0, np.sqrt(2.0/self.w2.shape[0]), (NUM_MOVES, self.w2.shape[0])).astype(np.float32)
            self.p_b = np.zeros(NUM_MOVES, dtype=np.float32)
        return True
