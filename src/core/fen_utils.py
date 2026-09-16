# ==================================
# === FILE: VIP/fen_utils.py ===
# === FEN Conversion Utilities cho Cờ Tướng ===
# ==================================

# Mapping: tên quân nội bộ → ký tự FEN
_PIECE_TO_FEN = {
    'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
    'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
    'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
    'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
}

# Reverse mapping: ký tự FEN → tên quân nội bộ
_FEN_TO_PIECE = {v: k for k, v in _PIECE_TO_FEN.items()}

# FEN vị trí ban đầu chuẩn
INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"


def board_array_to_fen(board, color='r', move_number=1):
    """Convert board 10x9 + màu đi → FEN string.

    Args:
        board:       10x9 list-of-lists (format nội bộ)
        color:       'r' = Đỏ đi, 'b' = Đen đi
        move_number: số lượt (full move counter)

    Returns:
        FEN string, ví dụ:
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
    """
    rows = []
    for r in range(10):
        row_str = ''
        empty = 0
        for c in range(9):
            p = board[r][c]
            if p == '.':
                empty += 1
            else:
                if empty:
                    row_str += str(empty)
                    empty = 0
                fen_char = _PIECE_TO_FEN.get(p)
                if fen_char is None:
                    raise ValueError(f"Unknown piece: '{p}' at board[{r}][{c}]")
                row_str += fen_char
        if empty:
            row_str += str(empty)
        rows.append(row_str)

    fen_color = 'w' if color == 'r' else 'b'
    return f"{'/'.join(rows)} {fen_color} - - 0 {move_number}"


def fen_to_board_array(fen):
    """Convert FEN string → board 10x9 + màu đi.

    Returns:
        (board, color) — board là 10x9 list, color là 'r' hoặc 'b'
    """
    parts = fen.split(' ')
    ranks = parts[0].split('/')
    color = 'r' if parts[1] == 'w' else 'b'

    board = []
    for rank_str in ranks:
        row = []
        for ch in rank_str:
            if ch.isdigit():
                row.extend(['.'] * int(ch))
            else:
                piece = _FEN_TO_PIECE.get(ch)
                if piece is None:
                    raise ValueError(f"Unknown FEN character: '{ch}'")
                row.append(piece)
        if len(row) != 9:
            raise ValueError(f"Invalid rank length: {len(row)} (expected 9)")
        board.append(row)

    if len(board) != 10:
        raise ValueError(f"Invalid number of ranks: {len(board)} (expected 10)")

    return board, color
