"""Static evaluation – combines handcrafted terms. Used as supplement while NN value head improves."""
EVAL_SEMANTIC_VERSION = 1  # bump on any change to static eval semantics
from evaluation.material import eval_material
from evaluation.pst import eval_pst

def eval_development(board):
    """Reward piece development (knights/bishops moved from home squares)."""
    w_dev = 0
    if board.board[7][1] != 'N': w_dev += 1
    if board.board[7][6] != 'N': w_dev += 1
    if board.board[7][2] != 'B': w_dev += 1
    if board.board[7][5] != 'B': w_dev += 1
    b_dev = 0
    if board.board[0][1] != 'n': b_dev += 1
    if board.board[0][6] != 'n': b_dev += 1
    if board.board[0][2] != 'b': b_dev += 1
    if board.board[0][5] != 'b': b_dev += 1
    return (w_dev - b_dev) * 15

def eval_king_safety(board):
    """Reward castling and pawn shield; penalise exposed king."""
    score = 0
    # _king_sq is maintained by ChessBoard.reset, set_fen,
    # make_move, undo_move, and copy. No scan required.
    wk = board._king_sq.get('w')
    bk = board._king_sq.get('b')
    if wk:
        if wk == (7, 6) or wk == (7, 2):   # castled
            score += 40
        elif wk != (7, 4):                  # king moved but not castled
            score -= 30
    if bk:
        if bk == (0, 6) or bk == (0, 2):
            score -= 40
        elif bk != (0, 4):
            score += 30

    # Pawn shield in front of king
    def shield(r, c, side):
        cnt = 0
        for dr in (1, 2):
            rr = r - dr if side == 'w' else r + dr
            if 0 <= rr < 8:
                for dc in (-1, 0, 1):
                    cc = c + dc
                    if 0 <= cc < 8:
                        if side == 'w' and board.board[rr][cc] == 'P':
                            cnt += 1
                        elif side == 'b' and board.board[rr][cc] == 'p':
                            cnt += 1
        return cnt * 12
    if wk: score += shield(wk[0], wk[1], 'w')
    if bk: score -= shield(bk[0], bk[1], 'b')
    return score

def eval_center(board):
    """Reward control of the central squares (e4/d4 for White, e5/d5 for Black)."""
    score = 0
    if board.board[4][4] == 'P': score += 15   # e4
    if board.board[4][3] == 'P': score += 15   # d4
    if board.board[3][4] == 'p': score -= 15   # e5
    if board.board[3][3] == 'p': score -= 15   # d5
    return score

def combined_eval(board):
    score = 0
    score += board.material
    score += eval_pst(board)
    score += eval_development(board)
    score += eval_king_safety(board)
    score += eval_center(board)
    return int(score)
