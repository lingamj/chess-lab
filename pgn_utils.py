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
