#!/usr/bin/env python3
"""ChessBoard with Zobrist hashing, undo move, legal move generation,
   and incremental move‑delta generation for NN feature updates.
   King‑capture prevention included.  Perft‑verified (depth 1‑5 exact).
"""

import random
from evaluation.material import _MATERIAL_VALS

MATE = 30000

ZOBRIST_PIECES = {}
ZOBRIST_SIDE = random.getrandbits(64)
ZOBRIST_CASTLING = {k: random.getrandbits(64) for k in 'KQkq'}
ZOBRIST_EP = [random.getrandbits(64) for _ in range(8)]

def _init_zobrist():
    for p in 'PNBRQKpnbrqk':
        ZOBRIST_PIECES[p] = [random.getrandbits(64) for _ in range(64)]
_init_zobrist()

# Parallel integer piece codes for hot-path consumers.
# 0 = empty. Bits 0-2: piece type (1=P..6=K). Bit 3: color (1=black).
WP, WN, WB, WR, WQ, WK = 1, 2, 3, 4, 5, 6
BP, BN, BB, BR, BQ, BK = 9, 10, 11, 12, 13, 14
CHAR_TO_CODE = {
    '.': 0,
    'P': WP, 'N': WN, 'B': WB, 'R': WR, 'Q': WQ, 'K': WK,
    'p': BP, 'n': BN, 'b': BB, 'r': BR, 'q': BQ, 'k': BK,
}
CODE_TO_CHAR = {v: k for k, v in CHAR_TO_CODE.items()}

class MoveDelta:
    """Lightweight description of a move's effect on the board.
       Used by the neural network to update its feature vector incrementally.
    """
    __slots__ = ('piece_changes',   # list of (square_index, old_piece_char, new_piece_char)
                 'white_turn',      # new side to move (bool)
                 'castling',        # new castling dict
                 'ep',              # new en passant (tuple or None)
                 'halfmove',        # new halfmove clock
                 'repetition_flag', # new repetition flag (1.0 or 0.0)
                 'old_hash',        # board hash before the move
                 'new_hash')        # board hash after the move

class UndoInfo:
    __slots__ = ('move', 'captured', 'castle_rook_move',
                 'ep_captured_piece', 'ep_captured_rank', 'ep_captured_file',
                 'old_castling', 'old_ep', 'old_halfmove', 'old_fullmove',
                 'old_white_turn', 'old_hash', 'new_hash', 'original_piece',
                 'delta', 'old_king_w', 'old_king_b', 'old_material')

class ChessBoard:
    __slots__ = ('board', 'white_turn', 'castling', 'en_passant',
                 'halfmove_clock', 'fullmove_number', 'hash', 'position_counts',
                 'track_repetition', '_pending_delta', '_nn_cache', '_king_sq',
                 '_piece_code', 'material')

    def __init__(self, track_repetition=True):
        self.track_repetition = track_repetition
        self._pending_delta = None
        self._nn_cache = None
        self._king_sq = {'w': None, 'b': None}
        self.reset()

    def reset(self):
        self.board = [
            ['r','n','b','q','k','b','n','r'],
            ['p','p','p','p','p','p','p','p'],
            ['.','.','.','.','.','.','.','.'],
            ['.','.','.','.','.','.','.','.'],
            ['.','.','.','.','.','.','.','.'],
            ['.','.','.','.','.','.','.','.'],
            ['P','P','P','P','P','P','P','P'],
            ['R','N','B','Q','K','B','N','R']
        ]
        self.white_turn = True
        self.castling = {'K':True,'Q':True,'k':True,'q':True}
        self.en_passant = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.position_counts = {}
        self.hash = self._compute_hash()
        self._update_position_count()
        self._pending_delta = None
        if self._nn_cache is not None:
            self._nn_cache = None
        self._king_sq['w'] = (7, 4)
        self._king_sq['b'] = (0, 4)
        self._piece_code = [
            CHAR_TO_CODE[self.board[r][c]]
            for r in range(8) for c in range(8)
        ]
        self.material = sum(
            _MATERIAL_VALS.get(p, 0) for row in self.board for p in row
        )

    # ----------------------------------------------------------------------
    # Zobrist hashing – EP included if a pawn that could capture exists
    # ----------------------------------------------------------------------
    def _ep_hash_component(self, ep_square, white_turn, board=None):
        if ep_square is None:
            return 0
        if board is None:
            board = self.board
        ep_rank, ep_file = ep_square
        from_rank = ep_rank + 1 if white_turn else ep_rank - 1
        if not (0 <= from_rank < 8):
            return 0
        pawn_char = 'P' if white_turn else 'p'
        for dc in (-1, 1):
            from_file = ep_file + dc
            if 0 <= from_file < 8 and board[from_rank][from_file] == pawn_char:
                return ZOBRIST_EP[ep_file]
        return 0

    def _compute_hash(self):
        h = 0
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p != '.':
                    h ^= ZOBRIST_PIECES[p][r*8 + c]
        if self.white_turn:
            h ^= ZOBRIST_SIDE
        for k in 'KQkq':
            if self.castling.get(k, False):
                h ^= ZOBRIST_CASTLING[k]
        if self.en_passant is not None:
            h ^= self._ep_hash_component(self.en_passant, self.white_turn, self.board)
        return h

    def _position_key(self):
        return self.hash

    def _update_position_count(self):
        if self.track_repetition:
            key = self._position_key()
            self.position_counts[key] = self.position_counts.get(key, 0) + 1

    def _repetition_flag(self):
        if not self.track_repetition:
            return 0.0
        return 1.0 if self.position_counts.get(self.hash, 0) >= 3 else 0.0

    def copy(self, copy_history=True):
        b = ChessBoard.__new__(ChessBoard)
        b.board = [r[:] for r in self.board]
        b.white_turn = self.white_turn
        b.castling = self.castling.copy()
        b.en_passant = None if self.en_passant is None else tuple(self.en_passant)
        b.halfmove_clock = self.halfmove_clock
        b.fullmove_number = self.fullmove_number
        b.hash = self.hash
        b.track_repetition = self.track_repetition if copy_history else False
        b.position_counts = self.position_counts.copy() if copy_history else {}
        b._pending_delta = None
        b._nn_cache = None
        b._king_sq = dict(self._king_sq)
        b._piece_code = self._piece_code[:]
        b.material = self.material
        return b

    def piece_color(self, piece):
        if piece == '.': return None
        return 'w' if piece.isupper() else 'b'

    def is_white(self, piece): return piece != '.' and piece.isupper()
    def is_black(self, piece): return piece != '.' and piece.islower()

    # ---------- make_move (with move delta, corrected promotion) ----------
    def make_move(self, move, update_history=True):
        fr, fc, tr, tc = move[:4]
        promo = move[4] if len(move) > 4 else None
        piece = self.board[fr][fc]
        captured = self.board[tr][tc]

        # Determine the promoted piece character early
        if promo:
            promo_piece = promo.upper() if self.white_turn else promo.lower()
        else:
            promo_piece = piece

        undo = UndoInfo()
        undo.move = move
        undo.captured = captured
        undo.original_piece = piece
        undo.old_castling = self.castling.copy()
        undo.old_ep = self.en_passant
        undo.old_halfmove = self.halfmove_clock
        undo.old_fullmove = self.fullmove_number
        undo.old_white_turn = self.white_turn
        undo.old_hash = self.hash
        undo.old_material = self.material
        undo.old_king_w = self._king_sq['w']
        undo.old_king_b = self._king_sq['b']
        undo.castle_rook_move = None
        undo.ep_captured_piece = None
        undo.ep_captured_rank = -1
        undo.ep_captured_file = -1
        undo.delta = None

        # ---------- collect piece changes for the delta ----------
        changes = []
        sq_from = fr * 8 + fc
        sq_to   = tr * 8 + tc
        changes.append((sq_from, piece, '.'))
        changes.append((sq_to, captured if captured != '.' else '.', promo_piece))

        h = self.hash
        old_white_turn = self.white_turn
        old_ep_comp = self._ep_hash_component(self.en_passant, old_white_turn, self.board)
        h ^= old_ep_comp

        # 1. Remove piece from source
        h ^= ZOBRIST_PIECES[piece][sq_from]
        # 2. Remove captured piece
        if captured != '.':
            h ^= ZOBRIST_PIECES[captured][sq_to]
        # 3. Place moved/promoted piece
        h ^= ZOBRIST_PIECES[promo_piece][sq_to]

        # 4. Castling rook
        if piece.upper() == 'K' and abs(tc - fc) == 2:
            if tc > fc:
                rook_fr, rook_fc = fr, 7
                rook_tr, rook_tc = fr, 5
            else:
                rook_fr, rook_fc = fr, 0
                rook_tr, rook_tc = fr, 3
            rook = self.board[rook_fr][rook_fc]
            sq_rfrom = rook_fr * 8 + rook_fc
            sq_rto   = rook_tr * 8 + rook_tc
            changes.append((sq_rfrom, rook, '.'))
            changes.append((sq_rto, '.', rook))
            h ^= ZOBRIST_PIECES[rook][sq_rfrom]
            h ^= ZOBRIST_PIECES[rook][sq_rto]
            undo.castle_rook_move = (rook_fr, rook_fc, rook_tr, rook_tc)

        # 5. En passant capture
        if (piece.upper() == 'P' and fc != tc and captured == '.' and undo.old_ep == (tr, tc)):
            ep_captured_rank = tr + (1 if self.white_turn else -1)
            ep_captured_file = tc
            ep_pawn = self.board[ep_captured_rank][ep_captured_file]
            if ep_pawn != '.':
                sq_ep = ep_captured_rank * 8 + ep_captured_file
                changes.append((sq_ep, ep_pawn, '.'))
                h ^= ZOBRIST_PIECES[ep_pawn][sq_ep]
                undo.ep_captured_piece = ep_pawn
                undo.ep_captured_rank = ep_captured_rank
                undo.ep_captured_file = ep_captured_file

        # 6. Update castling rights
        if piece == 'K':
            self.castling['K'] = self.castling['Q'] = False
        elif piece == 'k':
            self.castling['k'] = self.castling['q'] = False
        if piece == 'R' and fr == 7:
            if fc == 7: self.castling['K'] = False
            if fc == 0: self.castling['Q'] = False
        elif piece == 'r' and fr == 0:
            if fc == 7: self.castling['k'] = False
            if fc == 0: self.castling['q'] = False
        if captured == 'R' and tr == 7:
            if tc == 7: self.castling['K'] = False
            if tc == 0: self.castling['Q'] = False
        elif captured == 'r' and tr == 0:
            if tc == 7: self.castling['k'] = False
            if tc == 0: self.castling['q'] = False
        for k in 'KQkq':
            if undo.old_castling[k] != self.castling[k]:
                if undo.old_castling[k]: h ^= ZOBRIST_CASTLING[k]
                if self.castling[k]: h ^= ZOBRIST_CASTLING[k]

        # 7. Update en passant square
        self.en_passant = None
        if piece.upper() == 'P' and abs(tr - fr) == 2:
            self.en_passant = ((fr + tr) // 2, fc)

        # 8. Toggle side in hash
        h ^= ZOBRIST_SIDE

        # 9. Apply board changes
        self.board[fr][fc] = '.'
        self.board[tr][tc] = promo_piece
        self._piece_code[fr * 8 + fc] = 0
        self._piece_code[tr * 8 + tc] = CHAR_TO_CODE[promo_piece]

        if piece == 'K':
            self._king_sq['w'] = (tr, tc)
        elif piece == 'k':
            self._king_sq['b'] = (tr, tc)

        if undo.castle_rook_move:
            rfr, rfc, rtr, rtc = undo.castle_rook_move
            self.board[rfr][rfc] = '.'
            self.board[rtr][rtc] = rook
            self._piece_code[rfr * 8 + rfc] = 0
            self._piece_code[rtr * 8 + rtc] = CHAR_TO_CODE[rook]

        if undo.ep_captured_piece is not None:
            er, ec = undo.ep_captured_rank, undo.ep_captured_file
            self.board[er][ec] = '.'
            self._piece_code[er * 8 + ec] = 0

        # 10. Add new EP hash contribution
        new_ep_comp = self._ep_hash_component(self.en_passant, not old_white_turn, self.board)
        h ^= new_ep_comp

        self.hash = h

        if piece.upper() == 'P' or captured != '.':
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1
        if not old_white_turn:
            self.fullmove_number += 1
        self.white_turn = not old_white_turn

        if update_history:
            self._update_position_count()

        # ---------- build MoveDelta ----------
        delta = MoveDelta()
        delta.piece_changes = changes
        delta.white_turn = self.white_turn
        delta.castling = self.castling.copy()
        delta.ep = self.en_passant
        delta.halfmove = self.halfmove_clock
        delta.repetition_flag = self._repetition_flag()
        delta.old_hash = undo.old_hash
        delta.new_hash = self.hash

        undo.delta = delta
        self._pending_delta = delta

        undo.new_hash = self.hash

        # Incremental material update. Must exactly match
        # eval_material(board) after every make_move.
        for _sq, _old_p, _new_p in changes:
            self.material -= _MATERIAL_VALS.get(_old_p, 0)
            self.material += _MATERIAL_VALS.get(_new_p, 0)

        return undo

    # ---------- undo_move (with reverse delta) ----------
    def undo_move(self, undo, update_history=True):
        if update_history and self.track_repetition:
            key = undo.new_hash
            if key in self.position_counts:
                if self.position_counts[key] > 1:
                    self.position_counts[key] -= 1
                else:
                    del self.position_counts[key]

        move = undo.move
        fr, fc, tr, tc = move[:4]

        # Restore board
        self.board[fr][fc] = undo.original_piece
        self.board[tr][tc] = undo.captured
        self._piece_code[fr * 8 + fc] = CHAR_TO_CODE[undo.original_piece]
        self._piece_code[tr * 8 + tc] = CHAR_TO_CODE[undo.captured]

        if undo.castle_rook_move:
            rfr, rfc, rtr, rtc = undo.castle_rook_move
            self.board[rfr][rfc] = self.board[rtr][rtc]
            self.board[rtr][rtc] = '.'
            self._piece_code[rfr * 8 + rfc] = self._piece_code[rtr * 8 + rtc]
            self._piece_code[rtr * 8 + rtc] = 0

        if undo.ep_captured_piece is not None:
            er, ec = undo.ep_captured_rank, undo.ep_captured_file
            self.board[er][ec] = undo.ep_captured_piece
            self._piece_code[er * 8 + ec] = CHAR_TO_CODE[undo.ep_captured_piece]

        self.castling = undo.old_castling
        self.en_passant = undo.old_ep
        self.halfmove_clock = undo.old_halfmove
        self.fullmove_number = undo.old_fullmove
        self.white_turn = undo.old_white_turn
        self.hash = undo.old_hash
        self._king_sq['w'] = undo.old_king_w
        self._king_sq['b'] = undo.old_king_b
        self.material = undo.old_material


        # Build reverse delta that restores the NN cache to the previous state
        rev_delta = MoveDelta()
        if undo.delta is not None:
            rev_changes = [(sq, new, old) for (sq, old, new) in undo.delta.piece_changes]
        else:
            rev_changes = []
        rev_delta.piece_changes = rev_changes
        rev_delta.white_turn = self.white_turn
        rev_delta.castling = self.castling.copy()
        rev_delta.ep = self.en_passant
        rev_delta.halfmove = self.halfmove_clock
        rev_delta.repetition_flag = self._repetition_flag()
        rev_delta.old_hash = undo.new_hash
        rev_delta.new_hash = self.hash

        self._pending_delta = rev_delta

    # ---------- Move generation (king‑capture prevented) ----------
    def generate_pseudo_moves(self):
        moves = []
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p == '.': continue
                if self.white_turn != self.is_white(p): continue
                pt = p.upper()
                if pt == 'P':   self._pawn_moves(moves, r, c)
                elif pt == 'N': self._knight_moves(moves, r, c)
                elif pt == 'B': self._sliding_moves(moves, r, c, [(1,1),(1,-1),(-1,1),(-1,-1)])
                elif pt == 'R': self._sliding_moves(moves, r, c, [(1,0),(-1,0),(0,1),(0,-1)])
                elif pt == 'Q': self._sliding_moves(moves, r, c, [(1,0),(-1,0),(0,1),(0,-1),
                                                                     (1,1),(1,-1),(-1,1),(-1,-1)])
                elif pt == 'K': self._king_moves(moves, r, c)
        return moves

    def _pawn_moves(self, moves, r, c):
        direction = -1 if self.white_turn else +1
        start_rank = 6 if self.white_turn else 1
        promo_rank = 0 if self.white_turn else 7
        nr = r + direction
        if 0 <= nr < 8:
            if self.board[nr][c] == '.':
                if nr == promo_rank:
                    for p in ['Q','R','B','N']:
                        moves.append((r,c,nr,c,p))
                else:
                    moves.append((r,c,nr,c))
                if r == start_rank and self.board[r + 2*direction][c] == '.':
                    moves.append((r,c,r + 2*direction,c))
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < 8:
                    target = self.board[nr][nc]
                    if target != '.' and self.is_white(target) != self.white_turn and target.upper() != 'K':
                        if nr == promo_rank:
                            for p in ['Q','R','B','N']:
                                moves.append((r,c,nr,nc,p))
                        else:
                            moves.append((r,c,nr,nc))
                    if (nr, nc) == self.en_passant:
                        moves.append((r,c,nr,nc))

    def _knight_moves(self, moves, r, c):
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                target = self.board[nr][nc]
                if target == '.' or (self.is_white(target) != self.white_turn and target.upper() != 'K'):
                    moves.append((r,c,nr,nc))

    def _sliding_moves(self, moves, r, c, directions):
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                target = self.board[nr][nc]
                if target == '.':
                    moves.append((r,c,nr,nc))
                else:
                    if self.is_white(target) != self.white_turn and target.upper() != 'K':
                        moves.append((r,c,nr,nc))
                    break
                nr += dr; nc += dc

    def _king_moves(self, moves, r, c):
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr == 0 and dc == 0: continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    target = self.board[nr][nc]
                    if target == '.' or (self.is_white(target) != self.white_turn and target.upper() != 'K'):
                        moves.append((r,c,nr,nc))
        # Castling
        if self.white_turn:
            if (self.castling['K'] and self.board[7][7] == 'R' and
                self.board[7][5] == '.' and self.board[7][6] == '.' and
                not self.is_square_attacked(7,4,'b') and not self.is_square_attacked(7,5,'b') and
                not self.is_square_attacked(7,6,'b')):
                moves.append((7,4,7,6))
            if (self.castling['Q'] and self.board[7][0] == 'R' and
                self.board[7][1] == '.' and self.board[7][2] == '.' and self.board[7][3] == '.' and
                not self.is_square_attacked(7,4,'b') and not self.is_square_attacked(7,3,'b') and
                not self.is_square_attacked(7,2,'b')):
                moves.append((7,4,7,2))
        else:
            if (self.castling['k'] and self.board[0][7] == 'r' and
                self.board[0][5] == '.' and self.board[0][6] == '.' and
                not self.is_square_attacked(0,4,'w') and not self.is_square_attacked(0,5,'w') and
                not self.is_square_attacked(0,6,'w')):
                moves.append((0,4,0,6))
            if (self.castling['q'] and self.board[0][0] == 'r' and
                self.board[0][1] == '.' and self.board[0][2] == '.' and self.board[0][3] == '.' and
                not self.is_square_attacked(0,4,'w') and not self.is_square_attacked(0,3,'w') and
                not self.is_square_attacked(0,2,'w')):
                moves.append((0,4,0,2))

    def is_square_attacked(self, rank, file, attacker_color):
        if attacker_color == 'w':
            N_, K_, P_, Q_, R_, B_ = WN, WK, WP, WQ, WR, WB
        else:
            N_, K_, P_, Q_, R_, B_ = BN, BK, BP, BQ, BR, BB
        pc = self._piece_code
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = rank + dr, file + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                if pc[nr * 8 + nc] == N_:
                    return True
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            nr, nc = rank + dr, file + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                p = pc[nr * 8 + nc]
                if p != 0:
                    if p == Q_ or (p == R_ and (dr==0 or dc==0)) or (p == B_ and dr!=0 and dc!=0):
                        return True
                    break
                nr += dr; nc += dc
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr==0 and dc==0: continue
                nr, nc = rank + dr, file + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    if pc[nr * 8 + nc] == K_:
                        return True
        src_rank = rank + (1 if attacker_color == 'w' else -1)
        if 0 <= src_rank < 8:
            base = src_rank * 8
            for dc in [-1,1]:
                nc = file + dc
                if 0 <= nc < 8:
                    if pc[base + nc] == P_:
                        return True
        return False

    def is_king_in_check(self, color):
        opponent = 'b' if color == 'w' else 'w'
        sq = self._king_sq.get(color)
        if sq is not None:
            return self.is_square_attacked(sq[0], sq[1], opponent)
        king_char = 'K' if color == 'w' else 'k'
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == king_char:
                    return self.is_square_attacked(r, c, opponent)
        return False  # defensive fallback

    def _compute_pins(self, color):
        king_sq = self._king_sq.get(color)
        if king_sq is None:
            return None
        kr, kc = king_sq
        own = 'KQRBNP' if color == 'w' else 'kqrbnp'
        pins = {}
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1),
                       (1,1),(1,-1),(-1,1),(-1,-1)):
            diag = (dr != 0 and dc != 0)
            blocker = None
            r, c = kr + dr, kc + dc
            while 0 <= r < 8 and 0 <= c < 8:
                p = self.board[r][c]
                if p != '.':
                    if blocker is None:
                        if p in own:
                            blocker = (r, c)
                        else:
                            break
                    else:
                        pu = p.upper()
                        if pu in ('Q', 'R', 'B'):
                            if color == 'w' and p.islower():
                                if diag and pu in ('Q', 'B'):
                                    pins[blocker] = (r, c)
                                elif (not diag) and pu in ('Q', 'R'):
                                    pins[blocker] = (r, c)
                            elif color == 'b' and p.isupper():
                                if diag and pu in ('Q', 'B'):
                                    pins[blocker] = (r, c)
                                elif (not diag) and pu in ('Q', 'R'):
                                    pins[blocker] = (r, c)
                        break
                r += dr; c += dc
        return pins

    def generate_legal_moves(self):
        saved_pending = self._pending_delta
        legal = []
        moving_side = 'w' if self.white_turn else 'b'
        try:
            in_check = self.is_king_in_check(moving_side)
            pins = {} if in_check else (self._compute_pins(moving_side) or {})
            king_char = 'K' if moving_side == 'w' else 'k'

            for move in self.generate_pseudo_moves():
                fr, fc, tr, tc = move[:4]
                piece = self.board[fr][fc]
                is_king = (piece == king_char)
                is_castle = is_king and abs(tc - fc) == 2
                is_ep = (piece.upper() == 'P' and fc != tc
                         and self.board[tr][tc] == '.'
                         and self.en_passant == (tr, tc))

                if in_check or is_king or is_castle or is_ep:
                    undo = self.make_move(move, update_history=False)
                    try:
                        if not self.is_king_in_check(moving_side):
                            legal.append(move)
                    finally:
                        self.undo_move(undo, update_history=False)
                    continue

                pinner = pins.get((fr, fc))
                if pinner is None:
                    legal.append(move)
                    continue

                pr, pc = pinner
                dpr, dpc = pr - fr, pc - fc
                dtr, dtc = tr - fr, tc - fc
                if dtr * dpc != dtc * dpr:
                    continue
                legal.append(move)
        finally:
            self._pending_delta = saved_pending
        return legal

    def generate_legal_captures(self):
        saved_pending = self._pending_delta
        caps = []
        moving_side = 'w' if self.white_turn else 'b'
        try:
            in_check = self.is_king_in_check(moving_side)
            if in_check:
                for move in self.generate_legal_moves():
                    if self.board[move[2]][move[3]] != '.':
                        caps.append(move)
                return caps
            pins = self._compute_pins(moving_side) or {}
            king_char = 'K' if moving_side == 'w' else 'k'
            for move in self.generate_pseudo_moves():
                fr, fc, tr, tc = move[:4]
                if self.board[tr][tc] == '.':
                    continue
                piece = self.board[fr][fc]
                if piece == king_char:
                    undo = self.make_move(move, update_history=False)
                    try:
                        if not self.is_king_in_check(moving_side):
                            caps.append(move)
                    finally:
                        self.undo_move(undo, update_history=False)
                    continue
                pinner = pins.get((fr, fc))
                if pinner is None:
                    caps.append(move)
                    continue
                pr, pc = pinner
                dpr, dpc = pr - fr, pc - fc
                dtr, dtc = tr - fr, tc - fc
                if dtr * dpc != dtc * dpr:
                    continue
                caps.append(move)
        finally:
            self._pending_delta = saved_pending
        return caps

    def has_any_legal_move(self):
        saved_pending = self._pending_delta
        moving_side = 'w' if self.white_turn else 'b'
        try:
            in_check = self.is_king_in_check(moving_side)
            pins = {} if in_check else (self._compute_pins(moving_side) or {})
            king_char = 'K' if moving_side == 'w' else 'k'
            for move in self.generate_pseudo_moves():
                fr, fc, tr, tc = move[:4]
                piece = self.board[fr][fc]
                is_king = (piece == king_char)
                is_castle = is_king and abs(tc - fc) == 2
                is_ep = (piece.upper() == 'P' and fc != tc
                         and self.board[tr][tc] == '.'
                         and self.en_passant == (tr, tc))
                if in_check or is_king or is_castle or is_ep:
                    undo = self.make_move(move, update_history=False)
                    try:
                        if not self.is_king_in_check(moving_side):
                            return True
                    finally:
                        self.undo_move(undo, update_history=False)
                    continue
                pinner = pins.get((fr, fc))
                if pinner is None:
                    return True
                pr, pc = pinner
                dpr, dpc = pr - fr, pc - fc
                dtr, dtc = tr - fr, tc - fc
                if dtr * dpc == dtc * dpr:
                    return True
            return False
        finally:
            self._pending_delta = saved_pending

    def is_checkmate(self):
        moving_side = 'w' if self.white_turn else 'b'
        return self.is_king_in_check(moving_side) and len(self.generate_legal_moves()) == 0

    def is_stalemate(self):
        moving_side = 'w' if self.white_turn else 'b'
        return not self.is_king_in_check(moving_side) and len(self.generate_legal_moves()) == 0

    def is_insufficient_material(self):
        pieces = [p for row in self.board for p in row if p != '.']
        non_kings = [p for p in pieces if p.upper() != 'K']
        if not non_kings: return True
        if len(non_kings) == 1 and non_kings[0].upper() in ('B','N'): return True
        if len(non_kings) == 2 and all(p.upper() == 'B' for p in non_kings):
            squares = []
            for r in range(8):
                for c in range(8):
                    p = self.board[r][c]
                    if p.upper() == 'B':
                        squares.append((r + c) % 2)
            if squares and all(sq == squares[0] for sq in squares):
                return True
        return False

    def is_draw(self):
        if self.is_checkmate():
            return False
        if self.halfmove_clock >= 100:
            return True
        if self.track_repetition:
            key = self._position_key()
            count = self.position_counts.get(key, 0)
            if count >= 3:
                return True
        if self.is_insufficient_material():
            return True
        if self.is_stalemate():
            return True
        return False

    def to_fen(self):
        fen = []
        for r in range(8):
            empty = 0
            row = ''
            for c in range(8):
                p = self.board[r][c]
                if p == '.':
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p
            if empty:
                row += str(empty)
            fen.append(row)
        fen_str = '/'.join(fen) + ' ' + ('w' if self.white_turn else 'b') + ' '
        castling = ''
        for k in 'KQkq':
            if self.castling.get(k, False):
                castling += k
        fen_str += castling if castling else '-'
        if self.en_passant is not None:
            ep = chr(self.en_passant[1] + ord('a')) + str(8 - self.en_passant[0])
            fen_str += ' ' + ep
        else:
            fen_str += ' -'
        fen_str += f' {self.halfmove_clock} {self.fullmove_number}'
        return fen_str

    def set_fen(self, fen):
        parts = fen.strip().split()
        if len(parts) != 6:
            raise ValueError("FEN must contain exactly 6 fields")
        rows = parts[0].split('/')
        if len(rows) != 8:
            raise ValueError("FEN must contain 8 rows")
        board = [['.' for _ in range(8)] for _ in range(8)]
        for r_idx, row in enumerate(rows):
            c_idx = 0
            for ch in row:
                if ch.isdigit():
                    c_idx += int(ch)
                elif ch in 'pnbrqkPNBRQK':
                    board[r_idx][c_idx] = ch
                    c_idx += 1
                else:
                    raise ValueError(f"Invalid FEN char: {ch}")
                if c_idx > 8:
                    raise ValueError(f"Too many squares in row '{row}'")
            if c_idx != 8:
                raise ValueError(f"Invalid row: {row}")
        self.board = board

        if parts[1] not in ('w','b'):
            raise ValueError("Side to move must be w or b")
        self.white_turn = (parts[1] == 'w')

        rights = parts[2]
        if rights != '-':
            for ch in rights:
                if ch not in 'KQkq' or rights.count(ch) > 1:
                    raise ValueError(f"Invalid castling rights: {rights}")
            self.castling = {k: k in rights for k in 'KQkq'}
        else:
            self.castling = {'K':False,'Q':False,'k':False,'q':False}

        if self.castling.get('K') and (self.board[7][4] != 'K' or self.board[7][7] != 'R'):
            raise ValueError("Kingside castling right K requires king on e1 and rook on h1")
        if self.castling.get('Q') and (self.board[7][4] != 'K' or self.board[7][0] != 'R'):
            raise ValueError("Queenside castling right Q requires king on e1 and rook on a1")
        if self.castling.get('k') and (self.board[0][4] != 'k' or self.board[0][7] != 'r'):
            raise ValueError("Kingside castling right k requires king on e8 and rook on h8")
        if self.castling.get('q') and (self.board[0][4] != 'k' or self.board[0][0] != 'r'):
            raise ValueError("Queenside castling right q requires king on e8 and rook on a8")

        if parts[3] == '-':
            self.en_passant = None
        else:
            if len(parts[3]) != 2:
                raise ValueError("Invalid en passant square")
            ep_file = ord(parts[3][0]) - ord('a')
            ep_rank = 8 - int(parts[3][1])
            if not (0 <= ep_file < 8 and 0 <= ep_rank < 8):
                raise ValueError("En passant square out of range")
            if self.board[ep_rank][ep_file] != '.':
                raise ValueError("En passant square is not empty")
            self.en_passant = (ep_rank, ep_file)

        try:
            self.halfmove_clock = int(parts[4])
            self.fullmove_number = int(parts[5])
        except ValueError:
            raise ValueError("Invalid halfmove or fullmove number")

        pieces = [p for row in self.board for p in row]
        if pieces.count('K') != 1 or pieces.count('k') != 1:
            raise ValueError("Exactly one king of each color required")
        if pieces.count('P') > 8 or pieces.count('p') > 8:
            raise ValueError("Too many pawns per side")
        for c in range(8):
            if self.board[0][c] in ('P','p') or self.board[7][c] in ('P','p'):
                raise ValueError("Pawns on first or eighth rank")
        wr = wc = br = bc = None
        for r in range(8):
            for c in range(8):
                p = self.board[r][c]
                if p == 'K':
                    wr, wc = r, c
                elif p == 'k':
                    br, bc = r, c
        if abs(wr - br) <= 1 and abs(wc - bc) <= 1:
            raise ValueError("Kings are adjacent")

        self.position_counts = {}
        self.hash = self._compute_hash()
        self._update_position_count()
        self._pending_delta = None
        self._nn_cache = None
        self._king_sq['w'] = (wr, wc)
        self._king_sq['b'] = (br, bc)
        self._piece_code = [
            CHAR_TO_CODE[self.board[r][c]]
            for r in range(8) for c in range(8)
        ]
        self.material = sum(
            _MATERIAL_VALS.get(p, 0) for row in self.board for p in row
        )

    def equals(self, other):
        return (self.board == other.board and
                self.white_turn == other.white_turn and
                self.castling == other.castling and
                self.en_passant == other.en_passant and
                self.halfmove_clock == other.halfmove_clock and
                self.fullmove_number == other.fullmove_number and
                self.hash == other.hash and
                self.position_counts == other.position_counts)
