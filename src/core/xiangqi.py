# =============================================================================
# === FILE: xiangqi.py (FINAL VERSION - CHECKED & VERIFIED) ===
# =============================================================================
import random

NUM_COLS = 9
NUM_ROWS = 10

# --- ZOBRIST HASHING ---
random.seed(2024)
_PIECE_TO_INT = {
    'b_K': 0, 'b_A': 1, 'b_E': 2, 'b_N': 3, 'b_R': 4, 'b_C': 5, 'b_P': 6,
    'r_K': 7, 'r_A': 8, 'r_E': 9, 'r_N': 10, 'r_R': 11, 'r_C': 12, 'r_P': 13
}
_ZOBRIST_TABLE = [[[random.getrandbits(64) for _ in range(14)] for _ in range(9)] for _ in range(10)]

# Bàn cờ mặc định
initial_board = [
    ['b_R', 'b_N', 'b_E', 'b_A', 'b_K', 'b_A', 'b_E', 'b_N', 'b_R'],
    ['.', '.', '.', '.', '.', '.', '.', '.', '.'],
    ['.', 'b_C', '.', '.', '.', '.', '.', 'b_C', '.'],
    ['b_P', '.', 'b_P', '.', 'b_P', '.', 'b_P', '.', 'b_P'],
    ['.', '.', '.', '.', '.', '.', '.', '.', '.'],
    ['.', '.', '.', '.', '.', '.', '.', '.', '.'],
    ['r_P', '.', 'r_P', '.', 'r_P', '.', 'r_P', '.', 'r_P'],
    ['.', 'r_C', '.', '.', '.', '.', '.', 'r_C', '.'],
    ['.', '.', '.', '.', '.', '.', '.', '.', '.'],
    ['r_R', 'r_N', 'r_E', 'r_A', 'r_K', 'r_A', 'r_E', 'r_N', 'r_R']
]

def get_board():
    return [row[:] for row in initial_board]

def get_zobrist_key(board):
    h = 0
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            p = board[r][c]
            if p != '.':
                idx = _PIECE_TO_INT.get(p)
                if idx is not None: h ^= _ZOBRIST_TABLE[r][c][idx]
    return h

def get_board_key(board):
    return str(get_zobrist_key(board))

def make_temp_move(board, move):
    """
    Trả về: (new_board, captured_piece)
    """
    new_board = [row[:] for row in board]
    (sc, sr), (dc, dr) = move
    piece = new_board[sr][sc]
    captured = new_board[dr][dc]
    new_board[dr][dc] = piece
    new_board[sr][sc] = '.'
    return new_board, captured

# --- HELPER FUNCTIONS ---
def get_king_pos(color, board):
    k = color + '_K'
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            if board[r][c] == k: return (c, r)
    return None

def count_pieces_between(s, d, board):
    (sc, sr), (dc, dr) = s, d
    cnt = 0
    if sc == dc: # Dọc
        for r in range(min(sr, dr) + 1, max(sr, dr)):
            if board[r][sc] != '.': cnt += 1
    elif sr == dr: # Ngang
        for c in range(min(sc, dc) + 1, max(sc, dc)):
            if board[sr][c] != '.': cnt += 1
    return cnt

# --- HÀM KIỂM TRA BỊ CHIẾU (LOGIC CHUẨN) ---
def is_king_in_check(color, board):
    """Kiểm tra phe 'color' có đang bị chiếu không"""
    my_king = get_king_pos(color, board)
    if not my_king: return True # Mất vua là thua
    
    opp_color = 'b' if color == 'r' else 'r'
    kx, ky = my_king

    # 1. Check Xe/Pháo (Dọc/Ngang)
    directions = [(0,1), (0,-1), (1,0), (-1,0)]
    for dx, dy in directions:
        cx, cy = kx + dx, ky + dy
        count = 0
        while 0 <= cx < NUM_COLS and 0 <= cy < NUM_ROWS:
            p = board[cy][cx]
            if p != '.':
                if p[0] == opp_color:
                    if p[2] == 'R' and count == 0: return True
                    if p[2] == 'C' and count == 1: return True
                if count == 1: break 
                count += 1
            cx += dx; cy += dy

    # 2. Check Mã (SỬ DỤNG CÔNG THỨC TRUNG ĐIỂM - CHÍNH XÁC 100%)
    n_offsets = [(1,2), (1,-2), (-1,2), (-1,-2), (2,1), (2,-1), (-2,1), (-2,-1)]
    for dx, dy in n_offsets:
        nx, ny = kx + dx, ky + dy  # Vị trí Mã địch tiềm năng
        if 0 <= nx < NUM_COLS and 0 <= ny < NUM_ROWS:
            p = board[ny][nx]
            if p != '.' and p[0] == opp_color and p[2] == 'N':
                # Tìm chân cản (blocking leg)
                # Công thức này đồng bộ hoàn toàn với logic di chuyển của Mã
                if abs(dx) == 2: # Mã địch nằm ngang so với Tướng
                    block_x = (kx + nx) // 2
                    block_y = ny 
                else: # Mã địch nằm dọc so với Tướng
                    block_x = nx 
                    block_y = (ky + ny) // 2

                # Kiểm tra điểm cản có trống không
                if 0 <= block_x < NUM_COLS and 0 <= block_y < NUM_ROWS:
                    if board[block_y][block_x] == '.':
                        return True

    # 3. Check Tốt
    p_offsets = []
    if opp_color == 'r': # Tốt đỏ đánh lên/ngang (Index giảm)
        p_offsets = [(0, 1)] # Tốt đỏ ở dưới (ky+1) đánh lên ky
        if ky <= 4: p_offsets.extend([(1,0), (-1,0)])
    else: # Tốt đen đánh xuống/ngang (Index tăng)
        p_offsets = [(0, -1)] # Tốt đen ở trên (ky-1) đánh xuống ky
        if ky >= 5: p_offsets.extend([(1,0), (-1,0)])
    
    for dx, dy in p_offsets:
        cx, cy = kx + dx, ky + dy
        if 0 <= cx < NUM_COLS and 0 <= cy < NUM_ROWS:
            p = board[cy][cx]
            if p != '.' and p[0] == opp_color and p[2] == 'P': return True
            
    # 4. Check Tướng (Lộ mặt tướng)
    other_king = get_king_pos(opp_color, board)
    if other_king and other_king[0] == kx:
         if count_pieces_between(my_king, other_king, board) == 0: return True

    return False

# --- VALIDATION LOGIC ---
def is_valid_move(src, dst, board, color):
    sc, sr = src
    dc, dr = dst
    if not (0 <= dc < NUM_COLS and 0 <= dr < NUM_ROWS): return False
    
    p = board[sr][sc]
    target = board[dr][dc]
    
    if p == '.' or p[0] != color: return False
    if target != '.' and target[0] == color: return False 

    ptype = p[2]
    dx, dy = abs(sc - dc), abs(sr - dr)

    if ptype == 'K':
        if not (dx + dy == 1): return False
        if color == 'r': 
            if not (3 <= dc <= 5 and 7 <= dr <= 9): return False
        else: 
            if not (3 <= dc <= 5 and 0 <= dr <= 2): return False
    elif ptype == 'A':
        if not (dx == 1 and dy == 1): return False
        if color == 'r':
            if not (3 <= dc <= 5 and 7 <= dr <= 9): return False
        else:
            if not (3 <= dc <= 5 and 0 <= dr <= 2): return False
    elif ptype == 'E':
        if not (dx == 2 and dy == 2): return False
        if color == 'r' and dr < 5: return False 
        if color == 'b' and dr > 4: return False 
        if board[(sr + dr)//2][(sc + dc)//2] != '.': return False
    elif ptype == 'R':
        if not (sc == dc or sr == dr): return False
        if count_pieces_between(src, dst, board) > 0: return False
    elif ptype == 'C':
        if not (sc == dc or sr == dr): return False
        cnt = count_pieces_between(src, dst, board)
        if target == '.': 
            if cnt != 0: return False 
        else:
            if cnt != 1: return False 
    elif ptype == 'N':
        if not ((dx == 1 and dy == 2) or (dx == 2 and dy == 1)): return False
        if dx == 2: # Đi ngang -> Cản ở giữa hàng
            if board[sr][(sc + dc)//2] != '.': return False
        else: # Đi dọc -> Cản ở giữa cột
            if board[(sr + dr)//2][sc] != '.': return False
    elif ptype == 'P':
        if color == 'r':
            if dr > sr: return False  # Tốt Đỏ không đi lùi (index tăng)
            if sr >= 5: # Chưa qua sông
                if not (dx == 0 and dy == 1): return False
            else: # Đã qua sông
                if not ((dx == 1 and dy == 0) or (dx == 0 and dy == 1)): return False
        else:
            if dr < sr: return False # Tốt Đen không đi lùi (index giảm)
            if sr <= 4: # Chưa qua sông
                if not (dx == 0 and dy == 1): return False
            else: # Đã qua sông
                if not ((dx == 1 and dy == 0) or (dx == 0 and dy == 1)): return False

    # --- CHECK SAU KHI ĐI ---
    tmp_board, _ = make_temp_move(board, (src, dst))
    
    # Check lộ mặt tướng (Flying General) - Kiểm tra ngay lập tức
    r_k = get_king_pos('r', tmp_board)
    b_k = get_king_pos('b', tmp_board)
    if r_k and b_k and r_k[0] == b_k[0]: 
        if count_pieces_between(r_k, b_k, tmp_board) == 0:
            return False

    # Check xem đi xong mình có bị chiếu không
    if is_king_in_check(color, tmp_board): return False

    return True

def find_all_valid_moves(color, board):
    moves = []
    for r in range(NUM_ROWS):
        for c in range(NUM_COLS):
            if board[r][c] != '.' and board[r][c][0] == color:
                ptype = board[r][c][2]
                possible_dest = []
                
                if ptype in ['R', 'C']:
                    for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]:
                        tr, tc = r+dr, c+dc
                        while 0<=tr<NUM_ROWS and 0<=tc<NUM_COLS:
                            possible_dest.append((tc, tr))
                            if board[tr][tc] != '.': 
                                if ptype == 'R': break 
                            tr+=dr; tc+=dc
                elif ptype == 'N':
                    for dr, dc in [(1,2),(1,-2),(-1,2),(-1,-2),(2,1),(2,-1),(-2,1),(-2,-1)]:
                         possible_dest.append((c+dc, r+dr))
                elif ptype == 'E':
                    for dr, dc in [(2,2),(2,-2),(-2,2),(-2,-2)]: possible_dest.append((c+dc, r+dr))
                elif ptype == 'A':
                    for dr, dc in [(1,1),(1,-1),(-1,1),(-1,-1)]: possible_dest.append((c+dc, r+dr))
                elif ptype == 'K':
                    for dr, dc in [(0,1),(0,-1),(1,0),(-1,0)]: possible_dest.append((c+dc, r+dr))
                elif ptype == 'P':
                    offsets = [(0,-1)] if color=='r' else [(0,1)]
                    if (color=='r' and r<=4) or (color=='b' and r>=5): offsets.extend([(1,0),(-1,0)])
                    for dc, dr in offsets: possible_dest.append((c+dc, r+dr))

                for d in possible_dest:
                    if is_valid_move((c,r), d, board, color):
                        moves.append(((c,r), d))
    return moves