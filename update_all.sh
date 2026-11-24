#!/bin/bash
set -e
cd ~/chess_ai

echo "=== Creating all updated files ==="

# -------------------- board.py --------------------
cat > board.py << 'EOF'
#!/usr/bin/env python3
"""ChessBoard with Zobrist hashing, undo move, and legal move generation.
   Corrected version with full FIDE draw rules and strict FEN validation.
"""

import random

MATE = 30000

ZOBRIST_PIECES = {}
ZOBRIST_SIDE = random.getrandbits(64)
ZOBRIST_CASTLING = {k: random.getrandbits(64) for k in 'KQkq'}
ZOBRIST_EP = [random.getrandbits(64) for _ in range(8)]

def _init_zobrist():
    for p in 'PNBRQKpnbrqk':
        ZOBRIST_PIECES[p] = [random.getrandbits(64) for _ in range(64)]
_init_zobrist()

class UndoInfo:
    __slots__ = ('move', 'captured', 'castle_rook_move',
                 'ep_captured_piece', 'ep_captured_rank', 'ep_captured_file',
                 'old_castling', 'old_ep', 'old_halfmove', 'old_fullmove',
                 'old_white_turn', 'old_hash', 'new_hash', 'original_piece')
    def __init__(self):
        pass

class ChessBoard:
    __slots__ = ('board', 'white_turn', 'castling', 'en_passant',
                 'halfmove_clock', 'fullmove_number', 'hash', 'position_counts',
                 'track_repetition')
    def __init__(self, track_repetition=True):
        self.track_repetition = track_repetition
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

    # ----------------------------------------------------------------------
    # Zobrist hashing – EP included if a pawn that could capture exists
    # (lightweight; TODO: upgrade to true legal-EP for full FIDE accuracy)
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
        return b

    def piece_color(self, piece):
        if piece == '.': return None
        return 'w' if piece.isupper() else 'b'

    def is_white(self, piece): return piece != '.' and piece.isupper()
    def is_black(self, piece): return piece != '.' and piece.islower()

    # ---------- make_move ----------
    def make_move(self, move, update_history=True):
        fr, fc, tr, tc = move[:4]
        promo = move[4] if len(move) > 4 else None
        piece = self.board[fr][fc]
        captured = self.board[tr][tc]

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
        undo.castle_rook_move = None
        undo.ep_captured_piece = None
        undo.ep_captured_rank = -1
        undo.ep_captured_file = -1

        h = self.hash

        old_white_turn = self.white_turn
        old_ep_comp = self._ep_hash_component(self.en_passant, old_white_turn, self.board)
        h ^= old_ep_comp

        # 1. Remove piece from source
        h ^= ZOBRIST_PIECES[piece][fr*8 + fc]

        # 2. Remove captured piece
        if captured != '.':
            h ^= ZOBRIST_PIECES[captured][tr*8 + tc]

        # 3. Place moved/promoted piece
        if promo:
            promo_piece = promo.upper() if self.white_turn else promo.lower()
            h ^= ZOBRIST_PIECES[promo_piece][tr*8 + tc]
        else:
            h ^= ZOBRIST_PIECES[piece][tr*8 + tc]

        # 4. Castling rook
        if piece.upper() == 'K' and abs(tc - fc) == 2:
            if tc > fc:
                rook_fr, rook_fc = fr, 7
                rook_tr, rook_tc = fr, 5
            else:
                rook_fr, rook_fc = fr, 0
                rook_tr, rook_tc = fr, 3
            rook = self.board[rook_fr][rook_fc]
            h ^= ZOBRIST_PIECES[rook][rook_fr*8 + rook_fc]
            h ^= ZOBRIST_PIECES[rook][rook_tr*8 + rook_tc]
            undo.castle_rook_move = (rook_fr, rook_fc, rook_tr, rook_tc)

        # 5. En passant capture
        if (piece.upper() == 'P' and fc != tc and captured == '.' and undo.old_ep == (tr, tc)):
            ep_captured_rank = tr + (1 if self.white_turn else -1)
            ep_captured_file = tc
            ep_pawn = self.board[ep_captured_rank][ep_captured_file]
            if ep_pawn != '.':
                h ^= ZOBRIST_PIECES[ep_pawn][ep_captured_rank*8 + ep_captured_file]
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
        if promo:
            self.board[tr][tc] = promo_piece
        else:
            self.board[tr][tc] = piece

        if undo.castle_rook_move:
            rfr, rfc, rtr, rtc = undo.castle_rook_move
            self.board[rfr][rfc] = '.'
            self.board[rtr][rtc] = rook

        if undo.ep_captured_piece is not None:
            er, ec = undo.ep_captured_rank, undo.ep_captured_file
            self.board[er][ec] = '.'

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

        undo.new_hash = self.hash
        return undo

    # ---------- undo_move ----------
    def undo_move(self, undo, update_history=True):
        if update_history:
            key = undo.new_hash
            if key in self.position_counts:
                if self.position_counts[key] > 1:
                    self.position_counts[key] -= 1
                else:
                    del self.position_counts[key]

        move = undo.move
        fr, fc, tr, tc = move[:4]

        self.board[fr][fc] = undo.original_piece
        self.board[tr][tc] = undo.captured

        if undo.castle_rook_move:
            rfr, rfc, rtr, rtc = undo.castle_rook_move
            self.board[rfr][rfc] = self.board[rtr][rtc]
            self.board[rtr][rtc] = '.'

        if undo.ep_captured_piece is not None:
            er, ec = undo.ep_captured_rank, undo.ep_captured_file
            self.board[er][ec] = undo.ep_captured_piece

        self.castling = undo.old_castling
        self.en_passant = undo.old_ep
        self.halfmove_clock = undo.old_halfmove
        self.fullmove_number = undo.old_fullmove
        self.white_turn = undo.old_white_turn
        self.hash = undo.old_hash

    # ---------- Move generation ----------
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
                    if target != '.' and self.is_white(target) != self.white_turn:
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
                if target == '.' or self.is_white(target) != self.white_turn:
                    moves.append((r,c,nr,nc))

    def _sliding_moves(self, moves, r, c, directions):
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                target = self.board[nr][nc]
                if target == '.':
                    moves.append((r,c,nr,nc))
                else:
                    if self.is_white(target) != self.white_turn:
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
                    if target == '.' or self.is_white(target) != self.white_turn:
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
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = rank + dr, file + dc
            if 0 <= nr < 8 and 0 <= nc < 8:
                p = self.board[nr][nc]
                if p.upper() == 'N' and self.piece_color(p) == attacker_color:
                    return True
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
            nr, nc = rank + dr, file + dc
            while 0 <= nr < 8 and 0 <= nc < 8:
                p = self.board[nr][nc]
                if p != '.':
                    if self.piece_color(p) == attacker_color:
                        pt = p.upper()
                        if pt == 'Q' or (pt == 'R' and (dr==0 or dc==0)) or (pt == 'B' and dr!=0 and dc!=0):
                            return True
                    break
                nr += dr; nc += dc
        for dr in [-1,0,1]:
            for dc in [-1,0,1]:
                if dr==0 and dc==0: continue
                nr, nc = rank + dr, file + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    p = self.board[nr][nc]
                    if p.upper() == 'K' and self.piece_color(p) == attacker_color:
                        return True
        src_rank = rank + (1 if attacker_color == 'w' else -1)
        if 0 <= src_rank < 8:
            for dc in [-1,1]:
                nc = file + dc
                if 0 <= nc < 8:
                    p = self.board[src_rank][nc]
                    if p.upper() == 'P' and self.piece_color(p) == attacker_color:
                        return True
        return False

    def is_king_in_check(self, color):
        king_char = 'K' if color == 'w' else 'k'
        opponent = 'b' if color == 'w' else 'w'
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == king_char:
                    return self.is_square_attacked(r, c, opponent)
        raise ValueError(f"No {color} king found on the board")

    def generate_legal_moves(self):
        legal = []
        moving_side = 'w' if self.white_turn else 'b'
        for move in self.generate_pseudo_moves():
            undo = self.make_move(move, update_history=False)
            if not self.is_king_in_check(moving_side):
                legal.append(move)
            self.undo_move(undo, update_history=False)
        return legal

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

    def equals(self, other):
        return (self.board == other.board and
                self.white_turn == other.white_turn and
                self.castling == other.castling and
                self.en_passant == other.en_passant and
                self.halfmove_clock == other.halfmove_clock and
                self.fullmove_number == other.fullmove_number and
                self.hash == other.hash and
                self.position_counts == other.position_counts)
EOF

# -------------------- move_helpers.py --------------------
cat > move_helpers.py << 'EOF'
#!/usr/bin/env python3
"""Move helpers: UCI ↔ internal move conversion, SAN generation (PGN compliant), and Perft."""

# ---------- UCI conversion ----------
def move_to_str(move):
    if len(move) < 4:
        return str(move)
    fr, fc, tr, tc = move[0], move[1], move[2], move[3]
    s = chr(ord('a') + fc) + str(8 - fr) + chr(ord('a') + tc) + str(8 - tr)
    if len(move) > 4 and move[4] is not None:
        s += move[4].lower()
    return s

def str_to_move(s):
    if not s or len(s) < 4:
        return None
    try:
        fc = ord(s[0]) - ord('a')
        fr = 8 - int(s[1])
        tc = ord(s[2]) - ord('a')
        tr = 8 - int(s[3])
    except (ValueError, IndexError):
        return None
    if len(s) > 4:
        promo = s[4].upper()
        if promo not in ('Q', 'R', 'B', 'N'):
            return None
        return (fr, fc, tr, tc, promo)
    return (fr, fc, tr, tc)

# ---------- PGN‑compliant SAN generation ----------
def move_to_san(move, board):
    fr, fc, tr, tc = move[0], move[1], move[2], move[3]
    promo = move[4] if len(move) > 4 else None
    piece = board.board[fr][fc]
    piece_letter = piece.upper()

    moving_side = 'w' if board.white_turn else 'b'
    opponent = 'b' if moving_side == 'w' else 'w'

    if piece_letter == 'K' and abs(tc - fc) == 2:
        san = 'O-O' if tc > fc else 'O-O-O'
        undo = board.make_move(move, update_history=False)
        in_check = board.is_king_in_check(opponent)
        if in_check:
            if len(board.generate_legal_moves()) == 0:
                san += '#'
            else:
                san += '+'
        board.undo_move(undo, update_history=False)
        return san

    disambig = ""
    if piece_letter not in ('P', 'K'):
        all_legal = board.generate_legal_moves()
        same_target = [
            m for m in all_legal
            if m[2] == tr and m[3] == tc
            and board.board[m[0]][m[1]].upper() == piece_letter
            and m != move
        ]
        if same_target:
            same_file = any(m[1] == fc for m in same_target)
            same_rank = any(m[0] == fr for m in same_target)
            if not same_file:
                disambig = chr(ord('a') + fc)
            elif not same_rank:
                disambig = str(8 - fr)
            else:
                disambig = chr(ord('a') + fc) + str(8 - fr)

    capture = board.board[tr][tc] != '.' or (piece_letter == 'P' and board.en_passant == (tr, tc))
    dest = chr(ord('a') + tc) + str(8 - tr)

    if piece_letter == 'P':
        san = ''
        if capture:
            san = chr(ord('a') + fc) + 'x'
        san += dest
    else:
        san = piece_letter + disambig
        if capture:
            san += 'x'
        san += dest

    if promo:
        san += '=' + promo

    undo = board.make_move(move, update_history=False)
    in_check = board.is_king_in_check(opponent)
    if in_check:
        if len(board.generate_legal_moves()) == 0:
            san += '#'
        else:
            san += '+'
    board.undo_move(undo, update_history=False)

    return san

# ---------- Global move index mapping ----------
def _build_move_index():
    move_to_idx = {}
    idx_to_move = {}
    idx = 0
    for fr in range(8):
        for fc in range(8):
            for tr in range(8):
                for tc in range(8):
                    move = (fr, fc, tr, tc)
                    move_to_idx[move] = idx
                    idx_to_move[idx] = move
                    idx += 1
    for fr in range(8):
        for fc in range(8):
            for tr in range(8):
                for tc in range(8):
                    for promo in ('Q', 'R', 'B', 'N'):
                        move = (fr, fc, tr, tc, promo)
                        move_to_idx[move] = idx
                        idx_to_move[idx] = move
                        idx += 1
    return move_to_idx, idx_to_move, idx

MOVE_TO_INDEX, INDEX_TO_MOVE, NUM_MOVES = _build_move_index()

def move_to_index(move):
    if len(move) == 5 and move[4] is None:
        move = move[:4]
    return MOVE_TO_INDEX.get(move, -1)

def index_to_move(idx):
    return INDEX_TO_MOVE.get(idx, None)

# ---------- Perft ----------
def perft(board, depth):
    if depth == 0:
        return 1
    total = 0
    for move in board.generate_legal_moves():
        undo = board.make_move(move, update_history=False)
        total += perft(board, depth - 1)
        board.undo_move(undo, update_history=False)
    return total

def perft_divide(board, depth):
    if depth == 0:
        return 1
    total = 0
    for move in board.generate_legal_moves():
        undo = board.make_move(move, update_history=False)
        cnt = perft(board, depth - 1)
        print(f"{move_to_str(move)}: {cnt}")
        board.undo_move(undo, update_history=False)
        total += cnt
    return total
EOF

# -------------------- dataset_schema.py --------------------
cat > dataset_schema.py << 'EOF'
#!/usr/bin/env python3
"""Single source of truth for the training dataset format.
   Structural, semantic, and content validation.
   Callers must pass NUM_MOVES (from move_helpers) to avoid circular imports.
"""

import numbers
from board import ChessBoard

FORMAT_VERSION = 2
SUPPORTED_VERSIONS = {2}

FIELDS = (
    "positions",
    "policies",
    "values",
    "move_uci",
    "source",
    "white_elo",
    "black_elo",
    "opening",
    "date",
    "game_ids",
    "game_starts",
)

VALID_SOURCES = {0, 1, 2}

def _is_valid_uci(s):
    if not isinstance(s, str):
        return False
    if len(s) not in (4, 5):
        return False
    if not ('a' <= s[0] <= 'h' and '1' <= s[1] <= '8' and 'a' <= s[2] <= 'h' and '1' <= s[3] <= '8'):
        return False
    if len(s) == 5 and s[4] not in 'qrbnQRBN':
        return False
    return True

def validate_integrity(data, num_moves):
    ver = data.get("format_version")
    if ver not in SUPPORTED_VERSIONS:
        raise ValueError(f"Unsupported format_version {ver}. Supported: {SUPPORTED_VERSIONS}")

    for f in FIELDS:
        if f not in data:
            raise KeyError(f"Missing field '{f}'")
        if not isinstance(data[f], list):
            raise TypeError(f"Field '{f}' must be a list")

    n = len(data["positions"])
    for f in FIELDS:
        if len(data[f]) != n:
            raise ValueError(f"Length mismatch: positions has {n}, {f} has {len(data[f])}")

    if not all(isinstance(p, ChessBoard) for p in data["positions"]):
        raise TypeError("All positions must be ChessBoard instances")

    if not all(isinstance(idx, numbers.Integral) and 0 <= idx < num_moves for idx in data["policies"]):
        raise TypeError(f"Field 'policies' must contain integers in [0, {num_moves})")

    if not all(isinstance(v, numbers.Real) for v in data["values"]):
        raise TypeError("Field 'values' must contain real numbers")
    for v in data["values"]:
        if not (-1.0 <= float(v) <= 1.0):
            raise ValueError(f"Value {v} outside [-1, 1]")

    if not all(_is_valid_uci(u) for u in data["move_uci"]):
        raise ValueError("Field 'move_uci' contains malformed UCI strings")

    if not all(isinstance(s, numbers.Integral) and s in VALID_SOURCES for s in data["source"]):
        raise TypeError(f"Field 'source' must be one of {VALID_SOURCES}")

    for meta_field in ("white_elo", "black_elo", "opening", "date"):
        if not all(isinstance(x, str) for x in data[meta_field]):
            raise TypeError(f"Field '{meta_field}' must contain only strings")

    if not all(isinstance(b, bool) for b in data["game_starts"]):
        raise TypeError("Field 'game_starts' must contain only booleans")

    if not all(isinstance(g, numbers.Integral) for g in data["game_ids"]):
        raise TypeError("Field 'game_ids' must contain integers")

    seen_ids = {}
    for i, (gid, is_start) in enumerate(zip(data["game_ids"], data["game_starts"])):
        if gid not in seen_ids:
            if not is_start:
                raise RuntimeError(f"game_id {gid} first sample (index {i}) must have game_start=True")
            seen_ids[gid] = i
        else:
            if is_start:
                raise RuntimeError(f"game_id {gid} has multiple game_start=True (indices {seen_ids[gid]} and {i})")

    for prev, cur in zip(data["game_ids"], data["game_ids"][1:]):
        if cur < prev:
            raise RuntimeError(f"game_ids not monotonic: {prev} then {cur}")
EOF

# -------------------- prepare_pgn_with_policy.py --------------------
cat > prepare_pgn_with_policy.py << 'EOF'
#!/usr/bin/env python3
"""
Convert PGN to training data (versioned dict format).
Output dict:
{
  "format_version": 2,
  "positions": [...],
  "policies": [...],
  "values": [...],
  "source": [...],
  "white_elo": [...],
  "black_elo": [...],
  "opening": [...],
  "date": [...],
  "game_ids": [...],
  "game_starts": [...]
}
Append mode supported.
"""

import sys, os, pickle, chess, chess.pgn
from board import ChessBoard
from move_helpers import move_to_index
from dataset_schema import FORMAT_VERSION, FIELDS, validate_integrity

PROMO_MAP = {chess.QUEEN:'Q', chess.ROOK:'R', chess.BISHOP:'B', chess.KNIGHT:'N'}

def square_to_engine_rf(square):
    file = chess.square_file(square)
    rank = chess.square_rank(square)
    row = 7 - rank
    return row, file

def move_to_engine_move(move):
    fr, fc = square_to_engine_rf(move.from_square)
    tr, tc = square_to_engine_rf(move.to_square)
    promo = PROMO_MAP.get(move.promotion, None)
    return (fr, fc, tr, tc, promo)

def pgn_to_data(pgn_file_path, max_games=5000, source=0, append=True):
    outfile = "training_data.pkl"
    existing = None
    if append and os.path.exists(outfile):
        with open(outfile, "rb") as f:
            existing = pickle.load(f)
        if not isinstance(existing, dict) or existing.get("format_version") != FORMAT_VERSION:
            print("Old dataset format detected; starting fresh.")
            existing = None

    new_data = {f: [] for f in FIELDS}
    game_id = 0
    if existing:
        game_id = max(existing["game_ids"]) + 1 if existing["game_ids"] else 0

    with open(pgn_file_path, "r", encoding="utf-8", errors="ignore") as f:
        game_count = 0
        while game_count < max_games:
            game = chess.pgn.read_game(f)
            if game is None:
                break
            result = game.headers.get("Result", "*")
            white_result = 1.0 if result == "1-0" else (-1.0 if result == "0-1" else 0.0)

            white_elo = game.headers.get("WhiteElo", "")
            black_elo = game.headers.get("BlackElo", "")
            opening = game.headers.get("Opening", "")
            date = game.headers.get("Date", "")
            board = chess.Board()
            first_move = True
            for move in game.mainline_moves():
                cb = ChessBoard()
                cb.set_fen(board.fen())
                value = white_result if white_result == 0.0 else (white_result if cb.white_turn else -white_result)

                engine_move = move_to_engine_move(move)
                policy_idx = move_to_index(engine_move)
                move_uci = move.uci()
                if policy_idx >= 0:
                    new_data["positions"].append(cb)
                    new_data["policies"].append(policy_idx)
                    new_data["values"].append(value)
                    new_data["move_uci"].append(move_uci)
                    new_data["source"].append(source)
                    new_data["white_elo"].append(white_elo)
                    new_data["black_elo"].append(black_elo)
                    new_data["opening"].append(opening)
                    new_data["date"].append(date)
                    new_data["game_ids"].append(game_id)
                    new_data["game_starts"].append(first_move)
                    first_move = False
                board.push(move)
            game_id += 1
            game_count += 1

    if existing:
        for f in FIELDS:
            existing[f].extend(new_data[f])
        combined = existing
    else:
        combined = new_data

    combined["format_version"] = FORMAT_VERSION
    from move_helpers import NUM_MOVES
    validate_integrity(combined, NUM_MOVES)

    with open(outfile, "wb") as f:
        pickle.dump(combined, f)
    print(f"Dataset saved: {outfile} ({len(combined['positions'])} positions, version {FORMAT_VERSION}).")
    return combined

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prepare_pgn_with_policy.py <your_pgn_file.pgn> [source] [append]")
        print("source: 0=your games, 1=self-play, 2=Stockfish (default 0)")
        print("append: 1 to append, 0 to overwrite (default 1)")
        sys.exit(1)
    pgn_file = sys.argv[1]
    source = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    append = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    pgn_to_data(pgn_file, max_games=5000, source=source, append=bool(append))
EOF

# -------------------- pgn_utils.py --------------------
cat > pgn_utils.py << 'EOF'
#!/usr/bin/env python3
"""Shared PGN parser – used by data collector, trainer, etc.
   Value convention: side-to-move perspective.
"""

import re, hashlib
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
    from_file = from_rank = None
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

def parse_pgn_content(pgn_text):
    games = []
    current = []
    for line in pgn_text.split('\n'):
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
            game_id = hashlib.sha256(game_text.encode()).hexdigest()
            parsed.append({
                'moves': internal_moves,
                'result': result,
                'pgn': game_text,
                'game_id': game_id
            })
    return parsed

def extract_training_data(pgn_text, seen_set=None):
    games = parse_pgn_content(pgn_text)
    positions, results = [], []
    for game in games:
        if seen_set is not None:
            if game['game_id'] in seen_set:
                continue
            seen_set.add(game['game_id'])
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
EOF

# -------------------- pgn_learner.py --------------------
cat > pgn_learner.py << 'EOF'
#!/usr/bin/env python3
"""
PGN Learner – robust import from Lichess / Chess.com (unlimited) or local PGN.
APPENDS new positions to the existing pgn_data.pkl instead of overwriting.
Value convention: side-to-move perspective.
"""

import re, os, pickle, requests, sys
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
    params = {"max": 999999, "perfType": "blitz,rapid,classical", "moves": True, "pgnInJson": False}
    headers = {"Accept": "application/x-chess-pgn"}
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
EOF

# -------------------- generate_themed_data.py --------------------
cat > generate_themed_data.py << 'EOF'
#!/usr/bin/env python3
"""Generate multi‑source training data (version‑2 dict).
   Fields: positions, policies, values, move_uci, source, white_elo, black_elo,
            opening, date, game_ids, game_starts, format_version.
"""

import pickle, os, random, time, re
from board import ChessBoard
from nn import DualNet
from search import SearchEngine
from move_helpers import move_to_str, str_to_move, move_to_index, move_to_san
from dataset_schema import FORMAT_VERSION, FIELDS, validate_integrity

MODEL_PATH = 'chess_nn.pkl'
GAMES_PER_THEME = 10
DEPTH = 2
TIME_LIMIT = 100
STOCKFISH_PATH = '/data/data/com.termux/files/home/chess_ai/stockfish.sh'
USER_PGN_FILE = 'last_import.pgn'
NUM_SF_GAMES = 10

THEMES = [
    'checkmate', 'capture', 'pawnpush', 'king_safety', 'mobility',
    'opening', 'endgame', 'check', 'tactical', 'defense',
]

def load_engine():
    nn = DualNet()
    if not nn.load(MODEL_PATH):
        raise FileNotFoundError("Model not found")
    return SearchEngine(nn=nn, max_depth=DEPTH)

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

# ---------- Self‑play ----------
def play_self_play_game(engine):
    engine.tt.clear()
    if hasattr(engine, 'root_scores'): engine.root_scores.clear()
    if hasattr(engine, 'sorted_root_scores'): engine.sorted_root_scores.clear()
    if hasattr(engine, 'last_pv'): engine.last_pv = []

    board = ChessBoard()
    positions, moves_tup, moves_idx = [], [], []
    while True:
        legal = board.generate_legal_moves()
        if not legal:
            break
        move, _, _, _ = engine.search(board, time_limit=TIME_LIMIT, depth=DEPTH)
        if move is None or move not in legal:
            move = random.choice(legal)
        positions.append(board.copy())
        moves_tup.append(move)
        moves_idx.append(move_to_index(move))
        board.make_move(move)
        if board.is_checkmate() or board.is_draw():
            break
    if board.is_checkmate():
        white_result = -1.0 if board.white_turn else 1.0
    elif board.is_draw():
        white_result = 0.0
    else:
        white_result = 0.0
    values = []
    for pos in positions:
        if white_result == 0.0:
            values.append(0.0)
        else:
            values.append(white_result if pos.white_turn else -white_result)
    return positions, moves_tup, moves_idx, values

# Theme filters (unchanged)
def theme_checkmate(board, move, engine):
    try: _, score, _, _ = engine.search(board, time_limit=500, depth=2); return abs(score) > 29000
    except: return False
def theme_capture(board, move, engine):
    return board.board[move[2]][move[3]] != '.' or (len(move) > 4 and move[4] is not None)
def theme_pawnpush(board, move, engine):
    return board.board[move[0]][move[1]].upper() == 'P'
def theme_king_safety(board, move, engine):
    return board.is_king_in_check('w' if board.white_turn else 'b')
def theme_mobility(board, move, engine):
    return len(board.generate_legal_moves()) >= 30
def theme_opening(board, move, engine):
    return board.fullmove_number <= 10
def theme_endgame(board, move, engine):
    return sum(1 for row in board.board for p in row if p != '.') <= 12
def theme_check(board, move, engine):
    undo = board.make_move(move, update_history=False)
    opponent = 'b' if board.white_turn else 'w'
    g = board.is_king_in_check(opponent)
    board.undo_move(undo, update_history=False)
    return g
def theme_tactical(board, move, engine):
    return theme_capture(board, move, engine) or theme_check(board, move, engine)
def theme_defense(board, move, engine):
    return board.is_king_in_check('w' if board.white_turn else 'b')

THEME_FILTERS = {
    'checkmate': theme_checkmate, 'capture': theme_capture,
    'pawnpush': theme_pawnpush, 'king_safety': theme_king_safety,
    'mobility': theme_mobility, 'opening': theme_opening,
    'endgame': theme_endgame, 'check': theme_check,
    'tactical': theme_tactical, 'defense': theme_defense,
}

def generate_theme_data(theme, engine, num_games, start_game_id):
    out = {f: [] for f in FIELDS}
    filter_fn = THEME_FILTERS[theme]
    for g in range(num_games):
        print(f"  Theme {theme}: game {g+1}/{num_games}")
        positions, moves_tup, moves_idx, values = play_self_play_game(engine)
        first = True
        for pos, mtup, idx, val in zip(positions, moves_tup, moves_idx, values):
            if filter_fn(pos, mtup, engine):
                out["positions"].append(pos)
                out["policies"].append(idx)
                out["values"].append(val)
                out["move_uci"].append(move_to_str(mtup))
                out["source"].append(1)
                out["white_elo"].append("")
                out["black_elo"].append("")
                out["opening"].append(theme)
                out["date"].append("")
                out["game_ids"].append(start_game_id + g)
                out["game_starts"].append(first)
                first = False
    return out

def parse_pgn_to_training(pgn_text, start_game_id):
    out = {f: [] for f in FIELDS}
    games = pgn_text.strip().split('\n\n[Event')
    if len(games) <= 1:
        games = [g for g in pgn_text.split('\n\n') if g.startswith('[')]
    else:
        games = ['[Event' + g for g in games[1:]]
        games = [games[0]] + games[1:] if len(games) > 1 else games

    for gidx, game_str in enumerate(games):
        board = ChessBoard()
        result = '*'
        for line in game_str.split('\n'):
            if line.startswith('[Result '):
                result = line.split('"')[1]
                break
        white_result = 1.0 if result == '1-0' else (-1.0 if result == '0-1' else 0.0)

        last_tag = game_str.rfind(']')
        moves_text = game_str[last_tag+1:]
        moves_text = re.sub(r'\{[^}]*\}', '', moves_text, flags=re.DOTALL)
        moves_text = _remove_variations(moves_text)
        moves_text = re.sub(r'\d+\.', '', moves_text)
        moves_text = re.sub(r'[?!+#]', '', moves_text)
        tokens = moves_text.split()
        if tokens and tokens[-1] in ('1-0','0-1','1/2-1/2','*'):
            tokens = tokens[:-1]

        first = True
        for san in tokens:
            legal = board.generate_legal_moves()
            move_found = None
            for m in legal:
                try:
                    if move_to_san(m, board) == san:
                        move_found = m
                        break
                except:
                    pass
            if move_found:
                out["positions"].append(board.copy())
                out["policies"].append(move_to_index(move_found))
                val = white_result if white_result == 0.0 else (white_result if board.white_turn else -white_result)
                out["values"].append(val)
                out["move_uci"].append(move_to_str(move_found))
                out["source"].append(0)
                out["white_elo"].append("")
                out["black_elo"].append("")
                out["opening"].append("")
                out["date"].append("")
                out["game_ids"].append(start_game_id + gidx)
                out["game_starts"].append(first)
                first = False
                board.make_move(move_found)
            else:
                break
    return out

class StockfishEngine:
    def __init__(self, path='stockfish'):
        import subprocess
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

def generate_stockfish_games(engine, num_games, start_game_id):
    out = {f: [] for f in FIELDS}
    try:
        sf = StockfishEngine(STOCKFISH_PATH)
    except Exception as e:
        print(f"  Stockfish unavailable ({e}), skipping.")
        return out
    for g in range(num_games):
        print(f"  Stockfish game {g+1}/{num_games}")
        board = ChessBoard()
        engine_white = random.choice([True, False])
        engine_moves = []
        while True:
            legal = board.generate_legal_moves()
            if not legal: break
            if (engine_white and board.white_turn) or (not engine_white and not board.white_turn):
                move, _, _, _ = engine.search(board, time_limit=100, depth=2)
                if move is None or move not in legal:
                    move = random.choice(legal)
                engine_moves.append((board.copy(), move_to_index(move), move))
            else:
                try:
                    move = sf.get_move(board.to_fen(), 100)
                    if move is None or move not in legal:
                        move = random.choice(legal)
                except:
                    move = random.choice(legal)
            board.make_move(move)
            if board.is_checkmate() or board.is_draw():
                break
        if board.is_checkmate():
            white_result = -1.0 if board.white_turn else 1.0
        elif board.is_draw():
            white_result = 0.0
        else:
            white_result = 0.0
        first = True
        for pos, idx, move in engine_moves:
            out["positions"].append(pos)
            out["policies"].append(idx)
            val = white_result if white_result == 0.0 else (white_result if pos.white_turn else -white_result)
            out["values"].append(val)
            out["move_uci"].append(move_to_str(move))
            out["source"].append(2)
            out["white_elo"].append("")
            out["black_elo"].append("")
            out["opening"].append("")
            out["date"].append("")
            out["game_ids"].append(start_game_id + g)
            out["game_starts"].append(first)
            first = False
    sf.quit()
    return out

def main():
    engine = load_engine()
    all_data = {f: [] for f in FIELDS}
    next_game_id = 0

    for theme in THEMES:
        print(f"\n=== Themed self‑play: {theme} ===")
        d = generate_theme_data(theme, engine, GAMES_PER_THEME, next_game_id)
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += GAMES_PER_THEME
        print(f"  Collected {len(d['positions'])} positions.")

    print("\n=== Importing user PGN games ===")
    pgn_content = ''
    if os.path.exists(USER_PGN_FILE):
        with open(USER_PGN_FILE) as f:
            pgn_content = f.read()
    if pgn_content:
        d = parse_pgn_to_training(pgn_content, next_game_id)
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += len(set(d["game_ids"]))
        print(f"  Added {len(d['positions'])} PGN positions.")
    else:
        print("  No PGN file found, skipping.")

    print("\n=== Playing vs Stockfish ===")
    d = generate_stockfish_games(engine, NUM_SF_GAMES, next_game_id)
    if d["positions"]:
        for f in FIELDS: all_data[f].extend(d[f])
        next_game_id += NUM_SF_GAMES
        print(f"  Added {len(d['positions'])} Stockfish positions.")

    all_data["format_version"] = FORMAT_VERSION
    from move_helpers import NUM_MOVES
    validate_integrity(all_data, NUM_MOVES)

    with open('training_data_merged.pkl', 'wb') as f:
        pickle.dump(all_data, f)
    print(f"Saved training_data_merged.pkl ({len(all_data['positions'])} positions, version {FORMAT_VERSION}).")

if __name__ == '__main__':
    main()
EOF

# -------------------- train.py --------------------
cat > train.py << 'EOF'
#!/usr/bin/env python3
"""Train the dual‑head network. Uses dataset_schema for validation."""
import sys, os, pickle, signal
import numpy as np
from nn import DualNet
from move_helpers import NUM_MOVES, move_to_index
from dataset_schema import FORMAT_VERSION, FIELDS

def load_dataset(path):
    with open(path, 'rb') as f:
        data = pickle.load(f)

    if isinstance(data, dict):
        if data.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"Expected format_version {FORMAT_VERSION}, got {data.get('format_version')}")
        for f in FIELDS:
            if f not in data:
                raise KeyError(f"Missing field '{f}'")
        positions = data["positions"]
        values = data["values"]
        policies = data["policies"]
    elif isinstance(data, (list, tuple)):
        if len(data) == 0:
            return [], [], []
        first = data[0]
        if isinstance(first, tuple) and len(first) >= 4:
            positions = [x[0] for x in data]
            policies  = [x[1] for x in data]
            values    = [x[3] for x in data]
        else:
            raise ValueError("Unsupported dataset format.")
    else:
        raise ValueError("Dataset must be a dict or list of tuples.")

    if not (len(positions) == len(values) == len(policies)):
        raise ValueError(f"Length mismatch: positions={len(positions)}, values={len(values)}, policies={len(policies)}")

    if not all(isinstance(v, (int, float, np.floating, np.integer)) for v in values):
        raise ValueError("All value targets must be numeric.")
    for v in values:
        if v < -1.0 or v > 1.0:
            raise ValueError(f"Value {v} outside [-1, 1].")

    valid = [(p, v, pol) for p, v, pol in zip(positions, values, policies)
             if isinstance(pol, (int, np.integer)) and 0 <= pol < NUM_MOVES]
    if len(valid) < len(positions):
        print(f"Filtered out {len(positions) - len(valid)} invalid policy indices.")
    positions, values, policies = zip(*valid) if valid else ([], [], [])
    return list(positions), list(values), list(policies)

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 train.py <dataset.pkl> [epochs] [lr] [batch_size] [output_model]")
        sys.exit(1)
    path = sys.argv[1]
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    lr = float(sys.argv[3]) if len(sys.argv) > 3 else 0.001
    batch_size = int(sys.argv[4]) if len(sys.argv) > 4 else 512
    output_model = sys.argv[5] if len(sys.argv) > 5 else 'chess_nn.pkl'

    print("Loading dataset...")
    positions, values, policies = load_dataset(path)
    if not positions:
        print("No valid positions. Exiting.")
        return

    one_hot = np.zeros((len(policies), NUM_MOVES), dtype=np.float32)
    for i, pol_idx in enumerate(policies):
        if 0 <= pol_idx < NUM_MOVES:
            one_hot[i, pol_idx] = 1.0

    net = DualNet()
    if os.path.exists(output_model):
        print(f"Resuming from {output_model}")
        net.load(output_model)
    else:
        print("Starting from scratch.")

    print(f"Training on {len(positions)} samples, epochs={epochs}, lr={lr}, batch={batch_size}...")

    def save_model():
        net.save(output_model)
        print(f"Model saved to {output_model}")

    def handler(sig, frame):
        print("\nStopping (model NOT saved).")
        sys.exit(1)
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    training_ok = False
    try:
        net.train(positions, values, one_hot, epochs=epochs, lr=lr, batch_size=batch_size)
        training_ok = True
    except Exception as e:
        print(f"Training error: {e}")
    else:
        save_model()

if __name__ == '__main__':
    main()
EOF

# -------------------- nn.py --------------------
cat > nn.py << 'EOF'
#!/usr/bin/env python3
"""Dual‑head neural network – value (tanh) and policy (softmax per move index)."""

import numpy as np
import pickle, os
from move_helpers import NUM_MOVES

PIECE_TO_IDX = {
    'P':0,'N':1,'B':2,'R':3,'Q':4,'K':5,
    'p':6,'n':7,'b':8,'r':9,'q':10,'k':11
}

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

    def features(self, board):
        f = np.zeros(self.INPUT_SIZE, dtype=np.float32)
        for r in range(8):
            for c in range(8):
                p = board.board[r][c]
                if p == '.': continue
                idx = PIECE_TO_IDX[p]
                fidx = (r*8+c)*12 + idx
                if fidx < 768: f[fidx] = 1.0
        f[768] = 1.0 if board.white_turn else -1.0
        f[769] = 1.0 if board.castling.get('K', False) else 0.0
        f[770] = 1.0 if board.castling.get('Q', False) else 0.0
        f[771] = 1.0 if board.castling.get('k', False) else 0.0
        f[772] = 1.0 if board.castling.get('q', False) else 0.0
        if board.en_passant is not None:
            ep_rank, ep_file = board.en_passant
            f[773 + ep_file] = 1.0
        key = board.hash
        count = board.position_counts.get(key, 0) if board.track_repetition else 0
        f[781] = 1.0 if count >= 3 else 0.0
        f[782] = board.halfmove_clock / 100.0
        return f

    def forward(self, x):
        if x.ndim == 1: x = x.reshape(1, -1)
        h1 = np.maximum(0, x @ self.w1.T + self.b1)
        h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
        value = np.tanh(h2 @ self.v_w.T + self.v_b).ravel()
        policy = h2 @ self.p_w.T + self.p_b
        return value, policy

    def evaluate(self, board):
        f = self.features(board)
        val, pol = self.forward(f)
        return float(val[0]), pol[0]

    def train(self, positions, targets_value, targets_policy, epochs=10, lr=0.001, batch_size=512):
        X = np.array([self.features(b) for b in positions], dtype=np.float32)
        y_val = np.array(targets_value, dtype=np.float32).reshape(-1,1)
        y_pol = np.array(targets_policy, dtype=np.float32)
        n = len(X)
        for ep in range(epochs):
            perm = np.random.permutation(n)
            X_shuf = X[perm]; y_val_shuf = y_val[perm]; y_pol_shuf = y_pol[perm]
            total_loss = 0.0
            for i in range(0, n, batch_size):
                batch_X = X_shuf[i:i+batch_size]
                batch_val = y_val_shuf[i:i+batch_size]
                batch_pol = y_pol_shuf[i:i+batch_size]
                h1 = np.maximum(0, batch_X @ self.w1.T + self.b1)
                h2 = np.maximum(0, h1 @ self.w2.T + self.b2)
                out_val = np.tanh(h2 @ self.v_w.T + self.v_b)
                out_pol = h2 @ self.p_w.T + self.p_b
                loss_val = np.mean((batch_val - out_val)**2)
                log_probs = out_pol - np.max(out_pol, axis=1, keepdims=True)
                log_probs = log_probs - np.log(np.sum(np.exp(log_probs), axis=1, keepdims=True))
                loss_pol = -np.mean(np.sum(batch_pol * log_probs, axis=1))
                loss = loss_val + loss_pol
                total_loss += loss * len(batch_X)
                dout_val = -2 * (batch_val - out_val) * (1 - out_val**2) / batch_val.shape[0]
                dv_w = dout_val.T @ h2; dv_b = dout_val.sum(axis=0)
                dh2_val = dout_val @ self.v_w
                softmax = np.exp(log_probs)
                dout_pol = softmax - batch_pol
                dp_w = dout_pol.T @ h2; dp_b = dout_pol.sum(axis=0)
                dh2_pol = dout_pol @ self.p_w
                dh2 = dh2_val + dh2_pol
                dh2[h2 <= 0] = 0
                dw2 = dh2.T @ h1; db2 = dh2.sum(axis=0)
                dh1 = dh2 @ self.w2
                dh1[h1 <= 0] = 0
                dw1 = dh1.T @ batch_X; db1 = dh1.sum(axis=0)
                self.v_w -= lr * dv_w; self.v_b -= lr * dv_b
                self.p_w -= lr * dp_w; self.p_b -= lr * dp_b
                self.w2 -= lr * dw2; self.b2 -= lr * db2
                self.w1 -= lr * dw1; self.b1 -= lr * db1
            avg_loss = total_loss / n
            if (ep+1)%5==0:
                print(f"  epoch {ep+1}/{epochs}  loss={avg_loss:.4f} (val={loss_val:.4f}, pol={loss_pol:.4f})")

    def save(self, path):
        data = {'w1':self.w1,'b1':self.b1,'w2':self.w2,'b2':self.b2,
                'v_w':self.v_w,'v_b':self.v_b,'p_w':self.p_w,'p_b':self.p_b}
        with open(path, 'wb') as f: pickle.dump(data, f)

    def load(self, path):
        if not os.path.exists(path):
            print(f"WARNING: Model file {path} not found.")
            return False
        try:
            with open(path, 'rb') as f: data = pickle.load(f)
        except: return False
        if 'w1' in data and data['w1'].shape[1] != self.INPUT_SIZE:
            print(f"ERROR: Model input size mismatch.")
            return False
        if 'v_w' not in data:
            print("Converting old single-head model...")
            for k in ['w1','b1','w2','b2']:
                if k in data: setattr(self, k, data[k].astype(np.float32))
            if 'w3' in data:
                old_w3 = data['w3']
                if not isinstance(old_w3, np.ndarray): old_w3 = np.array(old_w3, dtype=np.float32)
                if old_w3.ndim == 1: old_w3 = old_w3.reshape(1, -1)
                self.v_w = old_w3.astype(np.float32)
            if 'b3' in data:
                old_b3 = data['b3']
                if not isinstance(old_b3, np.ndarray): old_b3 = np.array(old_b3, dtype=np.float32)
                if old_b3.ndim == 0: old_b3 = old_b3.reshape(1)
                self.v_b = old_b3.astype(np.float32)
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
EOF

# -------------------- search.py --------------------
cat > search.py << 'EOF'
#!/usr/bin/env python3
"""Search engine – hybrid NN + classical heuristics (killer, history, TT move)."""

import math, time
from board import ChessBoard, MATE
from move_helpers import move_to_str, str_to_move, move_to_index

MAX_DEPTH = 20
MATE_SCORE = 30000
TT_MAX = 500000
NN_SCALE = 800

class SearchTimeout(Exception):
    pass

class SearchEngine:
    def __init__(self, nn=None, max_depth=MAX_DEPTH, tt_max=TT_MAX):
        self.nn = nn
        self.max_depth = max_depth
        self.tt = {}
        self.tt_max = tt_max
        self.nodes = 0
        self.start_time = 0
        self.time_limit = 0
        self.alpha_beta_calls = 0
        self.current_depth = 0
        self.last_pv = []
        self.root_scores = {}
        self.sorted_root_scores = []
        self.killers = [[None, None] for _ in range(MAX_DEPTH + 20)]
        self.history = {}
        self.stop_event = None

    def search(self, board, time_limit=3000, depth=None):
        self.start_time = time.time()
        self.time_limit = time_limit / 1000.0
        if depth is None:
            depth = self.max_depth
        self.nodes = 0
        self.current_depth = 0
        self.root_scores = {}
        self.sorted_root_scores = []
        self.last_pv = []
        self._clear_heuristics()

        best_move = None
        best_score = -MATE_SCORE

        try:
            for d in range(1, depth + 1):
                self.current_depth = d
                self.alpha_beta_calls = 0
                if d > 1 and abs(best_score) < MATE_SCORE - 100:
                    alpha = best_score - 50
                    beta  = best_score + 50
                else:
                    alpha = -MATE_SCORE
                    beta  =  MATE_SCORE
                score = self._pvs(board, alpha, beta, d, 0)
                if score >= beta:
                    score = self._pvs(board, -MATE_SCORE, MATE_SCORE, d, 0)
                if score <= alpha:
                    score = self._pvs(board, -MATE_SCORE, MATE_SCORE, d, 0)

                if self.root_scores:
                    best_move = max(self.root_scores, key=self.root_scores.get)
                else:
                    entry = self.tt.get(board.hash)
                    if entry and entry.get('move'):
                        best_move = entry['move']
                best_score = score

                if self._time_up():
                    break
        except SearchTimeout:
            pass

        if best_move is not None:
            if len(best_move) == 5 and best_move[4] is None:
                best_move = best_move[:4]
            legal = board.generate_legal_moves()
            if best_move not in legal:
                best_move = legal[0] if legal else None

        if best_move is None:
            legal = board.generate_legal_moves()
            if legal:
                best_move = legal[0]

        self.sorted_root_scores = sorted(self.root_scores.items(), key=lambda x: -x[1])
        self.last_pv = self._extract_pv(board)
        return best_move, best_score, self.current_depth, self.nodes

    def _time_up(self):
        if self.stop_event is not None and self.stop_event.is_set():
            return True
        return (time.time() - self.start_time) > self.time_limit

    def _clear_heuristics(self):
        self.killers = [[None, None] for _ in range(MAX_DEPTH + 20)]
        self.history = {}

    def _pvs(self, board, alpha, beta, depth, ply):
        if self._time_up():
            raise SearchTimeout

        self.alpha_beta_calls += 1
        self.nodes += 1

        alpha_orig = alpha
        beta_orig = beta

        if board.is_draw():
            return 0
        if board.is_checkmate():
            return -MATE_SCORE + ply

        if depth == 0:
            return self._quiescence(board, alpha, beta, ply)

        tt_entry = self.tt.get(board.hash)
        if tt_entry and tt_entry['depth'] >= depth:
            score = tt_entry['score']
            if abs(score) > MATE_SCORE - 100:
                score += ply if score > 0 else -ply
            if tt_entry['flag'] == 'exact':
                return score
            elif tt_entry['flag'] == 'lower':
                alpha = max(alpha, score)
            elif tt_entry['flag'] == 'upper':
                beta = min(beta, score)
            if alpha >= beta:
                return score

        moves = board.generate_legal_moves()
        if not moves:
            return 0

        self._order_moves(board, moves, ply, tt_entry)

        best_move = moves[0]
        best_score = -MATE_SCORE
        for i, move in enumerate(moves):
            if self._time_up():
                raise SearchTimeout

            is_capture = board.board[move[2]][move[3]] != '.' or (len(move) > 4 and move[4] is not None)
            is_promotion = len(move) > 4 and move[4] is not None

            undo = board.make_move(move)
            try:
                if i >= 4 and depth >= 3 and not is_capture and not is_promotion:
                    reduction = 1 + (i - 3) // 6
                    score = -self._pvs(board, -alpha - 1, -alpha, depth - 1 - reduction, ply + 1)
                    if score > alpha:
                        score = -self._pvs(board, -beta, -alpha, depth - 1, ply + 1)
                else:
                    if i == 0:
                        score = -self._pvs(board, -beta, -alpha, depth - 1, ply + 1)
                    else:
                        score = -self._pvs(board, -alpha - 1, -alpha, depth - 1, ply + 1)
                        if score > alpha:
                            score = -self._pvs(board, -beta, -alpha, depth - 1, ply + 1)
            finally:
                board.undo_move(undo)

            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score
            if alpha >= beta:
                if not is_capture and not is_promotion:
                    self._store_killer(ply, move)
                    self._update_history(move, depth)
                break

        flag = 'exact'
        if best_score <= alpha_orig:
            flag = 'upper'
        elif best_score >= beta_orig:
            flag = 'lower'
        stored_score = best_score
        if abs(best_score) > MATE_SCORE - 100:
            stored_score = best_score - ply
        self._store_tt(board.hash, stored_score, depth, flag, best_move)

        if ply == 0:
            self.root_scores[best_move] = best_score

        return best_score

    def _order_moves(self, board, moves, ply, tt_entry):
        if not moves:
            return

        policy = None
        if self.nn:
            _, policy = self.nn.evaluate(board)

        def score(move):
            if tt_entry and tt_entry.get('move') == move:
                return 10_000_000
            target = board.board[move[2]][move[3]]
            if target != '.':
                attacker = board.board[move[0]][move[1]]
                gain = self._piece_value(target) - self._piece_value(attacker)
                if gain > 0:
                    return 1_000_000 + gain
            if move == self.killers[ply][0]:
                return 500_000
            if move == self.killers[ply][1]:
                return 400_000
            hist = self.history.get(tuple(move), 0)
            if hist:
                return 200_000 + min(hist, 50_000)
            if policy is not None:
                idx = move_to_index(move)
                if 0 <= idx < len(policy):
                    return int(policy[idx] * 100_000)
            return 0

        moves.sort(key=score, reverse=True)

    @staticmethod
    def _piece_value(piece_char):
        if piece_char == '.': return 0
        return {'P':1,'N':2,'B':3,'R':4,'Q':5,'K':6}.get(piece_char.upper(), 0)

    def _store_killer(self, ply, move):
        killers = self.killers[ply]
        if killers[0] != move:
            killers[1] = killers[0]
            killers[0] = move

    def _update_history(self, move, depth):
        key = tuple(move)
        self.history[key] = self.history.get(key, 0) + depth * depth

    def _quiescence(self, board, alpha, beta, ply):
        if self._time_up():
            raise SearchTimeout
        if ply > 12:
            return self._evaluate(board)

        in_check = board.is_king_in_check('w' if board.white_turn else 'b')
        if not in_check:
            stand_pat = self._evaluate(board)
            if stand_pat >= beta:
                return beta
            if stand_pat > alpha:
                alpha = stand_pat
        else:
            stand_pat = -MATE_SCORE

        moves = board.generate_legal_moves()
        if not moves:
            if in_check:
                return -MATE_SCORE + ply
            return 0

        q_moves = []
        for move in moves:
            if in_check or board.board[move[2]][move[3]] != '.' or len(move) > 4 or self._move_gives_check(board, move):
                q_moves.append(move)

        if self.nn:
            _, policy = self.nn.evaluate(board)
            q_moves.sort(key=lambda mv: policy[move_to_index(mv)] if 0 <= move_to_index(mv) < len(policy) else 0, reverse=True)
        else:
            def mvv_lva(move):
                target = board.board[move[2]][move[3]]
                if target == '.': return 0
                return {'P':1,'N':2,'B':3,'R':4,'Q':5,'K':6}.get(target.upper(), 0)
            q_moves.sort(key=mvv_lva, reverse=True)

        for move in q_moves:
            undo = board.make_move(move)
            try:
                score = -self._quiescence(board, -beta, -alpha, ply + 1)
            finally:
                board.undo_move(undo)
            if score >= beta:
                return beta
            if score > alpha:
                alpha = score
        return alpha

    def _move_gives_check(self, board, move):
        undo = board.make_move(move, update_history=False)
        side_to_move = 'w' if board.white_turn else 'b'
        result = board.is_king_in_check(side_to_move)
        board.undo_move(undo, update_history=False)
        return result

    def _evaluate(self, board):
        if self.nn:
            val, _ = self.nn.evaluate(board)
            return int(val * NN_SCALE)
        return 0

    def _store_tt(self, hash_key, score, depth, flag, move):
        old = self.tt.get(hash_key)
        if old is None or depth >= old['depth']:
            self.tt[hash_key] = {'score': score, 'depth': depth, 'flag': flag, 'move': move}
        if len(self.tt) > self.tt_max:
            try:
                self.tt.popitem()
            except KeyError:
                pass

    def _extract_pv(self, board):
        pv = []
        visited = set()
        b = board.copy()
        for _ in range(20):
            entry = self.tt.get(b.hash)
            if not entry or not entry.get('move'):
                break
            move = entry['move']
            legal = b.generate_legal_moves()
            if move not in legal:
                break
            pv.append(move)
            b.make_move(move)
            if b.hash in visited:
                break
            visited.add(b.hash)
        return pv

    def get_pv(self):
        return self.last_pv
EOF

# -------------------- parallel_search.py --------------------
cat > parallel_search.py << 'EOF'
#!/usr/bin/env python3
"""Parallel search using Lazy SMP – shares TT, stop event, and heuristics."""

import threading, time
from search import SearchEngine

class ParallelSearch:
    def __init__(self, nn_evaluator=None, max_depth=10, tt_max=100000, num_threads=2):
        self.nn = nn_evaluator
        self.max_depth = max_depth
        self.tt_max = tt_max
        self.num_threads = num_threads
        self.shared_tt = {}
        self.best_move = None
        self.best_score = None
        self.actual_depth = 0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.start_time = 0
        self.nodes = 0
        self.nodes_lock = threading.Lock()

    def _worker(self, board, time_ms, thread_id):
        searcher = SearchEngine(nn=self.nn,
                                max_depth=self.max_depth,
                                tt_max=self.tt_max)
        searcher.tt = self.shared_tt
        searcher.stop_event = self.stop_event

        local_board = board.copy()
        move, score, depth, nodes = searcher.search(local_board, time_limit=time_ms, depth=self.max_depth)

        if move is not None:
            with self.lock:
                if self.best_move is None or score > self.best_score:
                    self.best_move = move
                    self.best_score = score
                    self.actual_depth = depth

        with self.nodes_lock:
            self.nodes += nodes

    def search(self, board, time_ms=2000):
        self.best_move = None
        self.best_score = None
        self.actual_depth = 0
        self.nodes = 0
        self.shared_tt.clear()
        self.stop_event.clear()
        self.start_time = time.time()

        threads = []
        for i in range(self.num_threads):
            t = threading.Thread(target=self._worker, args=(board, time_ms, i))
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        return self.best_move, self.best_score, self.actual_depth
EOF

# -------------------- tablebase.py --------------------
cat > tablebase.py << 'EOF'
#!/usr/bin/env python3
"""Syzygy tablebase probing via python‑chess – WDL-based, robust."""

import os, chess, chess.syzygy

class Tablebase:
    def __init__(self, path=None):
        self.path = path or os.path.expanduser('~/chess_ai/syzygy')
        self.tablebase = None
        if os.path.isdir(self.path):
            try:
                self.tablebase = chess.syzygy.open_tablebase(self.path)
            except:
                pass

    def probe(self, board):
        if not self.tablebase:
            return None, None
        fen = board.to_fen()
        try:
            chess_board = chess.Board(fen)
            n = chess_board.occupied.bit_count()
            if n > self.tablebase.max_pieces:
                return None, None

            best_move = None
            best_wdl = None
            best_dtz = None

            for move in board.generate_legal_moves():
                child = board.copy()
                child.make_move(move)
                child_fen = child.to_fen()
                child_board = chess.Board(child_fen)

                wdl = self.tablebase.probe_wdl(child_board)
                if wdl is None:
                    continue
                if wdl > 0:
                    score = -1
                elif wdl < 0:
                    score = 1
                else:
                    score = 0

                dtz = None
                try:
                    dtz = self.tablebase.probe_dtz(child_board)
                except:
                    pass

                if best_move is None:
                    best_move = move
                    best_wdl = score
                    best_dtz = dtz
                else:
                    if score > best_wdl:
                        best_move = move
                        best_wdl = score
                        best_dtz = dtz
                    elif score == best_wdl and dtz is not None:
                        if (best_dtz is None or abs(dtz) < abs(best_dtz)):
                            best_move = move
                            best_dtz = dtz

            if best_move is not None:
                return best_wdl, best_move
            return None, None
        except:
            return None, None
EOF

# -------------------- uci_engine.py --------------------
cat > uci_engine.py << 'EOF'
#!/usr/bin/env python3
"""UCI Engine – uses DualNet value head."""

import sys, os, time, threading, argparse

parser = argparse.ArgumentParser()
parser.add_argument('--max-depth', type=int, default=20)
parser.add_argument('--hash-size', type=int, default=500000)
parser.add_argument('--threads', type=int, default=2)
args, unknown = parser.parse_known_args()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)
MODEL_PATH = os.path.join(SCRIPT_DIR, 'chess_nn.pkl')

from board import ChessBoard
from nn import DualNet
from search import SearchEngine
from parallel_search import ParallelSearch
from move_helpers import move_to_str, str_to_move

class UCIBoard:
    def __init__(self, fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"):
        self.board = ChessBoard()
        self.set_fen(fen)

    def set_fen(self, fen):
        self.board.set_fen(fen)

    def make_move_uci(self, uci):
        move = str_to_move(uci)
        for m in self.board.generate_legal_moves():
            if m == move:
                self.board.make_move(m)
                return True
        return False

class UCIEngine:
    def __init__(self, max_depth=10, tt_max=100000, num_threads=1):
        self.nn = DualNet()
        if self.nn.load(MODEL_PATH):
            sys.stderr.write(f"UCI: loaded {MODEL_PATH}\n")
        else:
            sys.stderr.write(f"UCI: WARNING – could not load {MODEL_PATH}, using untrained network\n")

        if num_threads > 1:
            self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                           max_depth=max_depth,
                                           tt_max=tt_max,
                                           num_threads=num_threads)
        else:
            self.searcher = SearchEngine(nn=self.nn,
                                         max_depth=max_depth,
                                         tt_max=tt_max)
        self.board = UCIBoard()
        self.search_thread = None

    def send(self, msg):
        print(msg, flush=True)

    def handle(self, cmd):
        cmd = cmd.strip()
        if cmd == 'uci':
            self.send('id name ChessAI_Neural')
            self.send('id author PhoneTrained')
            self.send('uciok')
        elif cmd == 'isready':
            self.send('readyok')
        elif cmd == 'ucinewgame':
            self.board = UCIBoard()
            self.nn.load(MODEL_PATH)
            self.searcher.tt.clear()
            if args.threads > 1:
                self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                               max_depth=self.searcher.max_depth,
                                               tt_max=self.searcher.tt_max,
                                               num_threads=args.threads)
            else:
                self.searcher = SearchEngine(nn=self.nn,
                                             max_depth=self.searcher.max_depth,
                                             tt_max=self.searcher.tt_max)
        elif cmd.startswith('position'):
            if 'startpos' in cmd:
                self.board = UCIBoard()
                moves_part = cmd.split('moves')
                if len(moves_part) > 1:
                    for m in moves_part[1].strip().split():
                        if not self.board.make_move_uci(m):
                            self.send('info string Illegal move ignored')
                            break
            elif 'fen' in cmd:
                fen = cmd[cmd.find('fen')+4:].split(' moves')[0] if ' moves' in cmd else cmd[cmd.find('fen')+4:]
                self.board = UCIBoard(fen)
                if 'moves' in cmd:
                    for m in cmd.split('moves')[-1].split():
                        if not self.board.make_move_uci(m):
                            self.send('info string Illegal move ignored')
                            break
        elif cmd.startswith('go'):
            mt = 3000
            parts = cmd.split()
            for i, p in enumerate(parts):
                if p == 'movetime' and i+1 < len(parts):
                    mt = int(parts[i+1])
                elif p == 'wtime' and self.board.board.white_turn and i+1 < len(parts):
                    mt = min(mt, int(parts[i+1]) // 20)
                elif p == 'btime' and not self.board.board.white_turn and i+1 < len(parts):
                    mt = min(mt, int(parts[i+1]) // 20)

            if self.search_thread and self.search_thread.is_alive():
                self.searcher.stop_event.set()
                self.search_thread.join(timeout=1)

            self.nn.load(MODEL_PATH)
            if args.threads > 1:
                self.searcher = ParallelSearch(nn_evaluator=self.nn,
                                               max_depth=self.searcher.max_depth,
                                               tt_max=self.searcher.tt_max,
                                               num_threads=args.threads)
            else:
                self.searcher = SearchEngine(nn=self.nn,
                                             max_depth=self.searcher.max_depth,
                                             tt_max=self.searcher.tt_max)

            def search_and_report():
                move, score, depth, _ = self.searcher.search(self.board.board, mt)
                elapsed = int((time.time() - self.searcher.start_time)*1000) if self.searcher.start_time else 0
                nps = int(self.searcher.nodes / (elapsed / 1000)) if elapsed > 0 else 0
                self.send(f'info depth {depth} score cp {int(score)} nodes {self.searcher.nodes} nps {nps} time {elapsed}')
                if move:
                    self.send(f'bestmove {move_to_str(move)}')

            self.searcher.start_time = time.time()
            self.search_thread = threading.Thread(target=search_and_report)
            self.search_thread.start()
        elif cmd == 'stop':
            self.searcher.stop_event.set()
            if self.search_thread and self.search_thread.is_alive():
                self.search_thread.join(timeout=1)
        elif cmd == 'quit':
            self.searcher.stop_event.set()
            if self.search_thread and self.search_thread.is_alive():
                self.search_thread.join(timeout=1)
            self.send('info string shutting down')
            sys.exit(0)

def main():
    engine = UCIEngine(max_depth=args.max_depth, tt_max=args.hash_size, num_threads=args.threads)
    while True:
        try:
            cmd = sys.stdin.readline()
            if not cmd:
                break
            engine.handle(cmd)
        except Exception as e:
            print(f"info string error: {e}", flush=True)

if __name__ == '__main__':
    main()
EOF

echo "All files created. Running tests..."

# Run verification tests
python test_hash.py
python test_move_index.py
python audit_move_table.py

echo "All tests passed!"
