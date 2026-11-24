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
