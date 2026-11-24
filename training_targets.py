"""Training target generators for the neural value head.
   All functions are used only at training time – never inside the search."""

import math

VALUE_TARGET_MODE = "blended"  # set to "game_result" to use only outcome

# ---------- Pre‑built PST tables ----------
def _build_pst_tables():
    w = {}
    w['P'] = [0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10,
              5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5,
              5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0]
    w['N'] = [-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40, -30,0,10,15,15,10,0,-30,
              -30,5,15,20,20,15,5,-30, -30,0,15,20,20,15,0,-30, -30,5,10,15,15,10,5,-30,
              -40,-20,0,5,5,0,-20,-40, -50,-40,-30,-30,-30,-30,-40,-50]
    w['B'] = [-20,-10,-10,-10,-10,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,10,10,5,0,-10,
              -10,5,5,10,10,5,5,-10, -10,0,10,10,10,10,0,-10, -10,10,10,10,10,10,10,-10,
              -10,5,0,0,0,0,5,-10, -20,-10,-10,-10,-10,-10,-10,-20]
    w['R'] = [0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5,
              -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5,
              -5,0,0,0,0,0,0,-5, 0,0,0,5,5,0,0,0]
    w['Q'] = [-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,5,5,5,0,-10,
              -5,0,5,5,5,5,0,-5, 0,0,5,5,5,5,0,-5, -10,5,5,5,5,5,0,-10,
              -10,0,5,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20]
    w['K'] = [-30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30,
              -30,-40,-40,-50,-50,-40,-40,-30, -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10,
              20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20]
    b = {}
    for piece in w:
        b[piece] = [-w[piece][63-i] for i in range(64)]
    tables = {}
    for piece in w:
        tables[piece.upper()] = w[piece]
        tables[piece.lower()] = b[piece]
    return tables

PST_TABLES = _build_pst_tables()

# ---------- Static evaluation features ----------

def material_score(board):
    vals = {'P':100,'N':320,'B':330,'R':500,'Q':900,'K':0,
            'p':-100,'n':-320,'b':-330,'r':-500,'q':-900,'k':0}
    return sum(vals.get(p,0) for row in board.board for p in row)

def pst_score(board):
    score = 0
    for r in range(8):
        for c in range(8):
            p = board.board[r][c]
            if p == '.': continue
            sq = r*8 + c
            if p in PST_TABLES:
                score += PST_TABLES[p][sq]
    return score

def bishop_pair_score(board):
    wb = sum(1 for row in board.board for p in row if p == 'B')
    bb = sum(1 for row in board.board for p in row if p == 'b')
    return (50 if wb >= 2 else 0) - (50 if bb >= 2 else 0)

def passed_pawn_score(board):
    score = 0
    # White pawns move toward row 0; black pawns toward row 7.
    # rank_bonus_white[rank] – higher bonus when closer to promotion (row 0)
    rank_bonus_white = [0, 180, 100, 60, 35, 20, 10, 0]   # index = row
    rank_bonus_black = [0, 10, 20, 35, 60, 100, 180, 0]   # index = row (promotion at row 7)

    # White passed pawns
    for c in range(8):
        for r in range(6, 0, -1):   # white pawns cannot be on row 0 (promoted) or row 7
            if board.board[r][c] == 'P':
                passed = True
                # check rows ahead (smaller r) for black pawns
                for rr in range(r-1, -1, -1):
                    for cc in (c-1, c, c+1):
                        if 0 <= cc <= 7 and board.board[rr][cc] == 'p':
                            passed = False
                            break
                    if not passed:
                        break
                if passed:
                    score += rank_bonus_white[r]
    # Black passed pawns
    for c in range(8):
        for r in range(1, 7):   # black pawns cannot be on row 0 or 7
            if board.board[r][c] == 'p':
                passed = True
                # check rows ahead (larger r) for white pawns
                for rr in range(r+1, 8):
                    for cc in (c-1, c, c+1):
                        if 0 <= cc <= 7 and board.board[rr][cc] == 'P':
                            passed = False
                            break
                    if not passed:
                        break
                if passed:
                    score -= rank_bonus_black[r]
    return score

def king_safety_score(board):
    score = 0
    wk = bk = None
    for r in range(8):
        for c in range(8):
            if board.board[r][c] == 'K': wk = (r, c)
            elif board.board[r][c] == 'k': bk = (r, c)

    def shield(king_r, king_c, pawn_char, direction):
        s = 0
        # direction = -1 for white (shield toward row 0), +1 for black (toward row 7)
        for dr in (1, 2):
            rr = king_r + direction * dr
            if 0 <= rr < 8:
                for dc in (-1, 0, 1):
                    cc = king_c + dc
                    if 0 <= cc < 8 and board.board[rr][cc] == pawn_char:
                        s += 10
        return s

    if wk:
        score += shield(wk[0], wk[1], 'P', -1)   # white shield upward
    if bk:
        score -= shield(bk[0], bk[1], 'p', 1)    # black shield downward

    return score

def static_eval(board):
    return (material_score(board) + pst_score(board) + bishop_pair_score(board) +
            passed_pawn_score(board) + king_safety_score(board))

# ---------- Game phase ----------

def phase(board):
    weights = {'Q':4, 'R':2, 'B':1, 'N':1, 'P':0, 'q':4, 'r':2, 'b':1, 'n':1, 'p':0}
    total = sum(weights.get(p,0) for row in board.board for p in row)
    max_total = 4*2 + 2*4 + 1*4 + 1*4   # 24
    return max(0.0, min(1.0, 1.0 - total / max_total))

# ---------- Blended value target ----------

def blended_value(white_result, board):
    if VALUE_TARGET_MODE == "game_result":
        if white_result == 0.0:
            return 0.0
        return white_result if board.white_turn else -white_result

    if white_result == 0.0:
        return 0.0

    ph = phase(board)
    static_weight = 0.6 - 0.4 * ph
    result_weight = 1.0 - static_weight
    static_part = math.tanh(static_eval(board) / 400.0)
    blended = result_weight * white_result + static_weight * static_part
    return blended if board.white_turn else -blended
