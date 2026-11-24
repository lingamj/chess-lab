"""Material evaluation."""
_MATERIAL_VALS = {
    "P":100, "N":320, "B":330, "R":500, "Q":900, "K":0,
    "p":-100, "n":-320, "b":-330, "r":-500, "q":-900, "k":0
}

def eval_material(board):
    return sum(_MATERIAL_VALS.get(p, 0) for row in board.board for p in row)
