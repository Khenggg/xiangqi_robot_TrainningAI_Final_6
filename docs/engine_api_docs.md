# ⚙️ Engine API — Phân Tích Nước Đi

Tài liệu tích hợp cho bên sử dụng engine Pikafish

**🌐 https://tuongkydaisu.com** | **📦 POST /api/engine/bestmove** | **🆓 Public API — Không cần token**

## Mục lục
1. [Gọi API](#1-goi-api)
2. [Bàn Cờ — Hệ Tọa Độ](#2-ban-co-he-toa-do)
3. [Chuỗi FEN — Giải Thích Chi Tiết](#3-chuoi-fen-giai-thich-chi-tiet)
4. [bestMove — Format UCI](#4-bestmove-format-uci)
5. [Ví Dụ Code (Python / JavaScript)](#5-vi-du-code-python--javascript)
6. [Lưu Ý](#6-luu-y)

---

## 1. Gọi API

### Request

`POST` `/api/engine/bestmove`

```bash
curl -X POST https://tuongkydaisu.com/api/engine/bestmove \
  -H "Content-Type: application/json" \
  -d '{"fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"}'
```

### Response

```json
{
  "success": true,
  "data": {
    "bestMove": "h2e2",
    "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    "nodes": 100000
  }
}
```

| Field | Mô tả |
| --- | --- |
| `bestMove` | Nước đi tốt nhất, format UCI (ví dụ `h2e2`) |
| `fen` | FEN gốc bạn gửi lên |
| `nodes` | Số node engine đã tính (100,000) |

---

## 2. Bàn Cờ Tướng — Hệ Tọa Độ

### Bàn cờ 9 cột × 10 hàng

```text
     a   b   c   d   e   f   g   h   i      ← CỘT (column)
   ┌───┬───┬───┬───┬───┬───┬───┬───┬───┐
 9 │ r │ n │ b │ a │ k │ a │ b │ n │ r │    ← Hàng 9 (ĐEN xa nhất)
   ├───┼───┼───┼───╲───╱───┼───┼───┼───┤
 8 │   │   │   │   │ ╳ │   │   │   │   │
   ├───┼───┼───┼───╱───╲───┼───┼───┼───┤
 7 │   │ c │   │   │   │   │   │ c │   │    ← Pháo đen
   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
 6 │ p │   │ p │   │ p │   │ p │   │ p │    ← Tốt đen
   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
 5 │═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══│    ← SÔNG
   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
 4 │═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══│    ← SÔNG
   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
 3 │ P │   │ P │   │ P │   │ P │   │ P │    ← Tốt đỏ
   ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
 2 │   │ C │   │   │   │   │   │ C │   │    ← Pháo đỏ
   ├───┼───┼───┼───╲───╱───┼───┼───┼───┤
 1 │   │   │   │   │ ╳ │   │   │   │   │
   ├───┼───┼───┼───╱───╲───┼───┼───┼───┤
 0 │ R │ N │ B │ A │ K │ A │ B │ N │ R │    ← Hàng 0 (ĐỎ gần nhất)
   └───┴───┴───┴───┴───┴───┴───┴───┴───┘
     a                               i
     ↑                               ↑
   Cột a                          Cột i
```

### Quy ước

| Thứ | Giá trị | Mô tả |
| --- | --- | --- |
| **Cột** | `a` → `i` | Trái → Phải (9 cột) |
| **Hàng** | `0` → `9` | Dưới (ĐỎ) → Trên (ĐEN) (10 hàng) |
| **Phe Đỏ** | `RNBAKCP` | Chữ IN HOA |
| **Phe Đen** | `rnbakcp` | Chữ thường |

### Tên quân cờ

| Ký hiệu | Tên | ĐỎ | ĐEN |
| --- | --- | --- | --- |
| K/k | **Tướng** (King) | `K` | `k` |
| A/a | **Sĩ** (Advisor) | `A` | `a` |
| B/b | **Tượng** (Bishop) | `B` | `b` |
| N/n | **Mã** (Knight) | `N` | `n` |
| R/r | **Xe** (Rook) | `R` | `r` |
| C/c | **Pháo** (Cannon) | `C` | `c` |
| P/p | **Tốt** (Pawn) | `P` | `p` |

---

## 3. Chuỗi FEN — Giải Thích Chi Tiết

### Format chuẩn

```text
rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1
│                                                              │ │ │ │ │
│                                                              │ │ │ │ └─ Số lượt đầy đủ (fullmove)
│                                                              │ │ │ └─── Đếm nửa nước (halfmove)
│                                                              │ │ └───── Không dùng (luôn "-")
│                                                              │ └─────── Không dùng (luôn "-")
│                                                              └───────── Lượt đi: w=Đỏ, b=Đen
└──────────────────────────────────────────────────────────────────────── Vị trí quân cờ
```

### Phần 1: Vị trí quân cờ

FEN mô tả bàn cờ **từ trên xuống dưới** (hàng 9 → hàng 0), mỗi hàng cách nhau bằng `/`.

```text
rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR
│         │ │       │         │ │ │         │       │ │
│         │ │       │         │ │ │         │       │ └ Hàng 0: R N B A K A B N R (ĐỎ)
│         │ │       │         │ │ │         │       └── Hàng 1: 9 ô trống
│         │ │       │         │ │ │         └────────── Hàng 2: _C_____C_ (Pháo ĐỎ)
│         │ │       │         │ │ └──────────────────── Hàng 3: P_P_P_P_P (Tốt ĐỎ)
│         │ │       │         │ └────────────────────── Hàng 4: 9 ô trống (SÔNG)
│         │ │       │         └──────────────────────── Hàng 5: 9 ô trống (SÔNG)
│         │ │       └────────────────────────────────── Hàng 6: p_p_p_p_p (Tốt ĐEN)
│         │ └────────────────────────────────────────── Hàng 7: _c_____c_ (Pháo ĐEN)
│         └──────────────────────────────────────────── Hàng 8: 9 ô trống
└────────────────────────────────────────────────────── Hàng 9: r n b a k a b n r (ĐEN)
```

**Quy tắc đọc:**
- Chữ cái = quân cờ tại ô đó
- Số = số ô trống liên tiếp (VD: `1c5c1` = 1 trống + pháo + 5 trống + pháo + 1 trống)

### Phần 2: Lượt đi
- `w` = **White** = phe Đỏ đi
- `b` = **Black** = phe Đen đi

### Phần 3-6: Các trường bổ sung
| Vị trí | Ý nghĩa | Giá trị |
| --- | --- | --- |
| 3 | Castling | Luôn `-` (Cờ Tướng không có) |
| 4 | En passant | Luôn `-` (Cờ Tướng không có) |
| 5 | Halfmove clock | Số nước đi không ăn quân (luật 60 nước hòa) |
| 6 | Fullmove number | Bắt đầu từ 1, tăng sau mỗi nước Đen |

---

## 4. bestMove — Format UCI

### Cấu trúc: `[cột_gốc][hàng_gốc][cột_đích][hàng_đích]`

```text
h2e2
││││
││└┘── Đích:  cột e, hàng 2
└┘──── Gốc:   cột h, hàng 2
```

→ Di chuyển quân ở **h2** sang **e2** (Pháo đỏ di ngang)

### Ví dụ thực tế
| bestMove | Nghĩa | Quân |
| --- | --- | --- |
| `h2e2` | h2 → e2 | Pháo đỏ di ngang |
| `h9g7` | h9 → g7 | Mã đen nhảy |
| `b0c2` | b0 → c2 | Mã đỏ nhảy |
| `e0e1` | e0 → e1 | Tướng đỏ tiến 1 |
| `a9a0` | a9 → a0 | Xe đen ăn Xe đỏ |

### Minh họa trên bàn cờ
```text
bestMove = "h2e2" (Pháo đỏ h2 → e2)

     a   b   c   d   e   f   g   h   i
   ┌───┬───┬───┬───┬───┬───┬───┬───┬───┐
 2 │   │ C │   │   │[C]│   │   │(C)│   │
   └───┴───┴───┴───┴───┴───┴───┴───┴───┘
                      ↑               ↑
                    ĐẾN            TỪ ĐÂY
                   (e2)            (h2)
```

---

## 5. Ví Dụ Sử Dụng Đầy Đủ

### Python
```python
import requests

url = "https://tuongkydaisu.com/api/engine/bestmove"

# Thế cờ ban đầu, Đỏ đi trước
fen = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"

response = requests.post(url, json={"fen": fen})
data = response.json()

if data["success"]:
    best = data["data"]["bestMove"]  # ví dụ: "h2e2"

    from_col = best[0]     # 'h'
    from_row = int(best[1])  # 2
    to_col   = best[2]     # 'e'
    to_row   = int(best[3])  # 2

    print(f"Di chuyển quân từ {from_col}{from_row} → {to_col}{to_row}")
```

### JavaScript
```javascript
const res = await fetch("https://tuongkydaisu.com/api/engine/bestmove", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    fen: "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1"
  })
});

const { data } = await res.json();
console.log("Nước đi tốt nhất:", data.bestMove);
// → "h2e2"
```

---

## 6. Lưu Ý

- Engine sử dụng **100,000 nodes** (~depth 8-10), trả kết quả trong **1-3 giây**
- FEN phải đúng chuẩn Xiangqi: `{board} {w|b} - - {halfmove} {fullmove}`
- `bestMove` luôn trả 4 ký tự: `[a-i][0-9][a-i][0-9]`
- API hoàn toàn **miễn phí**, không cần đăng ký hay token

> ⚠️ **QUAN TRỌNG:** FEN phải đúng chuẩn 6 phần: `vị_trí lượt_đi - - halfmove fullmove`
> Ví dụ: `rnbakabnr/9/.../RNBAKABNR w - - 0 1`

---
© 2026 Tướng Kỳ Đại Sư — Engine API Documentation
