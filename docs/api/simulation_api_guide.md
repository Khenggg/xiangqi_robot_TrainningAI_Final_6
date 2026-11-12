# 🎮 Simulation Match API

Hướng dẫn tích hợp cho bên thứ 3

**🌐 https://tuongkydaisu.com** | **📦 v1.0 — 10/03/2026** | **✅ Tested on Production**

## Mục lục
1. [Tổng quan](#1-tong-quan)
2. [Xác thực](#2-xac-thuc)
3. [Hệ tọa độ chuẩn & FEN](#3-he-toa-do-chuan--fen)
4. [Danh sách API](#4-danh-sach-api)
5. [Chi tiết từng API](#5-chi-tiet-tung-api)
6. [Flow mẫu hoàn chỉnh](#6-flow-mau-hoan-chinh)
7. [WebSocket — Xem trực tiếp](#7-websocket-xem-truc-tiep)
8. [Mã lỗi](#8-ma-loi)
9. [Giới hạn & Quy tắc](#9-gioi-han--quy-tac)

---

## 1. Tổng quan

API cho phép bên thứ 3 **điều khiển hoàn toàn** một trận đấu Cờ Tướng qua REST API:

```text
Bên thứ 3                            Server API                           WebSocket                Người xem
   │                                     │                                    │                        │
   │── POST /matches ───────────────────▶│                                    │                        │
   │◀── roomId = "2511" ─────────────────│                                    │                        │
   │                                     │                                    │                        │
Mỗi nước đi                              │                                    │                        │
┌──┴─────────────────────────────────────┴┐                                   │                        │
│  │                                     ││                                   │                        │
│  │── POST /matches/{roomId}/fen ───────▶│── Broadcast ─────────────────────▶│── Cập nhật bàn cờ ───▶│
│  │◀─ moveNumber, piece ─────────────────│   real-time                       │                        │
└──┬─────────────────────────────────────┬┘                                   │                        │
   │                                     │                                    │                        │
   │── POST /end ────────────────────────▶│── Broadcast kết quả ─────────────▶│───────────────────────▶│
```

**Người dùng web** vào "Xem Cờ Trực Tiếp" sẽ thấy trận đấu real-time. Không cần bên thứ 3 xử lý WebSocket.

---

## 2. Xác thực
Tất cả API yêu cầu header:
```
Authorization: Bearer <SIMULATION_TOKEN>
```

> ⚠️ **QUAN TRỌNG:** Token có hiệu lực **365 ngày**. Liên hệ admin để được cấp.

---

## 3. Hệ tọa độ chuẩn & FEN

> ⚠️ **QUAN TRỌNG:** Tất cả FEN string gửi lên API sử dụng **hệ tọa độ chuẩn quốc tế Xiangqi** (giống UCI / Pikafish engine).

### 3.1. Bàn cờ — Tọa độ chuẩn

```text
  a b c d e f g h i ← CỘT (a→i, trái→phải) 
  ┌───┬───┬───┬───┬───┬───┬───┬───┬───┐
9 │ r │ n │ b │ a │ k │ a │ b │ n │ r │ ← Rank 9 (ĐEN)
  ├───┼───┼───┼───╲───╱───┼───┼───┼───┤
8 │   │   │   │   │ ╳ │   │   │   │   │
  ├───┼───┼───┼───╱───╲───┼───┼───┼───┤
7 │   │ c │   │   │   │   │   │ c │   │ ← Pháo đen
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
6 │ p │   │ p │   │ p │   │ p │   │ p │ ← Tốt đen
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
5 │═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══│ ← SÔNG 
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
4 │═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══╪═══│ ← SÔNG 
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
3 │ P │   │ P │   │ P │   │ P │   │ P │ ← Tốt đỏ
  ├───┼───┼───┼───┼───┼───┼───┼───┼───┤
2 │   │ C │   │   │   │   │   │ C │   │ ← Pháo đỏ
  ├───┼───┼───┼───╲───╱───┼───┼───┼───┤
1 │   │   │   │   │ ╳ │   │   │   │   │
  ├───┼───┼───┼───╱───╲───┼───┼───┼───┤
0 │ R │ N │ B │ A │ K │ A │ B │ N │ R │ ← Rank 0 (ĐỎ)
  └───┴───┴───┴───┴───┴───┴───┴───┴───┘
  a i

▲ RANK 0 = ĐỎ (dưới) 
▼ RANK 9 = ĐEN (trên)
```

| Thứ | Giá trị | Mô tả |
| --- | --- | --- |
| **Cột** | `a` → `i` | Trái → Phải (9 cột, a=0 ... i=8) |
| **Hàng (Rank)** | `0` → `9` | Dưới (ĐỎ) → Trên (ĐEN) |
| **Phe Đỏ** | `RNBAKCP` | Chữ IN HOA |
| **Phe Đen** | `rnbakcp` | Chữ thường |

### 3.2. FEN String chuẩn (6 phần)

```text
rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1
                                                            │ │ │ │ │
                                                            │ │ │ │ └─ Fullmove number
                                                            │ │ │ └─── Halfmove clock
                                                            │ │ └───── Luôn "-"
                                                            │ └─────── Luôn "-"
                                                            └───────── w=Đỏ, b=Đen
```

> 💡 **LƯU Ý:** FEN viết tả bàn cờ **từ trên xuống** (rank 9 → rank 0). Phần đầu `rnbakabnr` = hàng trên cùng (ĐEN), phần cuối `RNBAKABNR` = hàng dưới cùng (ĐỎ).

### 3.3. Quân cờ

| Ký tự | Quân cờ | Bên |
| --- | --- | --- |
| `K` / `k` | Tướng (King) | Đỏ / Đen |
| `A` / `a` | Sĩ (Advisor) | Đỏ / Đen |
| `B` / `b` | Tượng (Bishop) | Đỏ / Đen |
| `N` / `n` | Mã (Knight) | Đỏ / Đen |
| `R` / `r` | Xe (Rook) | Đỏ / Đen |
| `C` / `c` | Pháo (Cannon) | Đỏ / Đen |
| `P` / `p` | Tốt (Pawn) | Đỏ / Đen |
| `1-9` | Số ô trống liên tiếp | — |

### 3.4. Cách tạo FEN sau mỗi nước đi
1. Lấy FEN hiện tại (từ response hoặc GET state)
2. Parse phần board (trước dấu cách đầu tiên)
3. Xóa quân ở vị trí cũ, đặt quân ở vị trí mới
4. Ghép lại: `{board} {w|b} - - {halfmove} {fullmove}`
5. Gửi FEN chuẩn lên server

**Ví dụ**: Pháo đỏ ở `h2` di chuyển sang `e2`:
```text
Trước: .../1C5C1/...     → Rank 2: . C . . . . . C .    (h2 = Pháo đỏ)
Sau:   .../1C2C4/...     → Rank 2: . C . . C . . . .    (e2 = Pháo đỏ)

FEN gửi lên:
rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1
                                                              ↑ 
                                                   Đổi w→b vì đến lượt Đen
```

---

## 4. Danh sách API

| # | Method | Endpoint | Mô tả |
| --- | --- | --- | --- |
| 1 | `POST` | `/api/simulation/matches` | Tạo trận đấu mới |
| 2 | `POST` | `/api/simulation/matches/{roomId}/fen` | Gửi nước đi (FEN chuẩn) |
| 3 | `POST` | `/api/simulation/matches/{roomId}/end` | Kết thúc trận đấu |
| 4 | `GET` | `/api/simulation/matches` | Liệt kê trận đang chạy |
| 5 | `GET` | `/api/simulation/matches/{roomId}` | Xem trạng thái trận |
| 6 | `GET` | `/api/simulation/matches/{roomId}/moves` | Lịch sử nước đi |

---

## 5. Chi tiết từng API

### 5.1. Tạo trận đấu
`POST` `/api/simulation/matches`

**Request Body:**
```json
{
  "redPlayerName": "Wang Tianyi",
  "blackPlayerName": "Zheng Weidong",
  "redPlayerAvatar": "https://example.com/red.jpg",
  "blackPlayerAvatar": "https://example.com/black.jpg"
}
```

| Field | Bắt buộc | Mô tả |
| --- | --- | --- |
| `redPlayerName` | ✅ | Tên kỳ thủ bên Đỏ |
| `blackPlayerName` | ✅ | Tên kỳ thủ bên Đen |
| `redPlayerAvatar` | ❌ | URL ảnh đại diện (tự tạo nếu не gửi) |
| `blackPlayerAvatar` | ❌ | URL ảnh đại diện (tự tạo nếu không gửi) |

**Response (200):**
```json
{
  "code": 200,
  "success": true,
  "message": "Simulation match created",
  "data": {
    "roomId": "2511",
    "status": "PLAYING",
    "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",
    "currentTurn": "RED",
    "redPlayerInfo": { "displayName": "Wang Tianyi", "avatar": "...", "elo": 0 },
    "blackPlayerInfo": { "displayName": "Zheng Weidong", "avatar": "...", "elo": 0 }
  }
}
```

> 💡 **LƯU Ý:** **Lưu lại `roomId`** — dùng cho tất cả API tiếp theo.

### 5.2. Gửi nước đi (Submit FEN)
`POST` `/api/simulation/matches/{roomId}/fen`

**Request Body:**
```json
{
  "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1"
}
```

> 💡 **LƯU Ý:** Gửi **FEN chuẩn đầy đủ** (6 phần) sau khi đi xong. Server tự so sánh FEN cũ/mới để phát hiện nước đi.

**Response (200):**
```json
{
  "code": 200,
  "success": true,
  "data": {
    "roomId": "2511",
    "fen": "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1",
    "moveNumber": 1,
    "currentTurn": "BLACK",
    "move": {
      "fromRow": 7, "fromCol": 7,
      "toRow": 7,   "toCol": 4,
      "piece": "C", "captured": null
    }
  }
}
```

> 🔄 **Chuyển đổi tọa độ response:** `move.fromRow/toRow` dùng **FEN-row order** (row 0 = trên cùng = ĐEN).
Để chuyển ra **tọa độ chuẩn**: `rank = 9 - row`, `column = 'a' + col`.
Ví dụ: `fromRow=7, fromCol=7` → `rank = 9-7 = 2`, `col = 'a'+7 = 'h'` → ô **h2**.

- Server **validate nước đi theo luật cờ tướng** → nước đi sai = lỗi `11004`
- Server **tự chuyển lượt** (RED → BLACK → RED...)
- Mỗi FEN gửi lên → **broadcast real-time** tới người xem

### 5.3. Kết thúc trận đấu
`POST` `/api/simulation/matches/{roomId}/end`
```json
{ "winner": "RED", "reason": "CHECKMATE" }
```

| Field | Bắt buộc | Giá trị |
| --- | --- | --- |
| `winner` | ✅ | `"RED"` / `"BLACK"` / `"DRAW"` |
| `reason` | ❌ | `"CHECKMATE"` / `"RESIGN"` / `"TIMEOUT"` / `"OTHER"` |

### 5.4. Liệt kê trận đang chạy
`GET` `/api/simulation/matches` — Trả về danh sách trận có `status = PLAYING`.

### 5.5. Xem trạng thái trận
`GET` `/api/simulation/matches/{roomId}` — Trả về toàn bộ MatchState.

### 5.6. Lịch sử nước đi + FEN
`GET` `/api/simulation/matches/{roomId}/moves`
```json
{
  "code": 200,
  "data": {
    "roomId": "2511",
    "currentFen": "r1bakabnr/9/1cn1c4/p1p1p1p1p/9/4P4/P1P3P1P/1C2C4/9/RNBAKABNR w - - 0 3",
    "currentTurn": "RED",
    "totalMoves": 4,
    "moves": [
      { "moveNumber": 1, "piece": "C", "fen": "...after move FEN..." },
      { "moveNumber": 2, "...": "..." }
    ]
  }
}
```

---

## 6. Flow mẫu hoàn chỉnh

✅ Flow này đã test thành công trên production `tuongkydaisu.com`

Thay `<TOKEN>` bằng token thực. Thay `<DOMAIN>` bằng `tuongkydaisu.com`.

**Bước 1 — Tạo trận đấu**
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"redPlayerName":"Wang Tianyi","blackPlayerName":"Zheng Weidong"}'
```
→ Lưu `roomId`. Ví dụ: `ROOM=2511`

**Bước 2 — Nước 1: Đỏ Pháo `h2→e2`**
Pháo đỏ bên phải (ô h2) di chuyển ngang sang giữa (ô e2).
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches/$ROOM/fen \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fen":"rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR b - - 0 1"}'
```
→ moveNumber=1, piece="C", currentTurn="BLACK"

**Bước 3 — Nước 2: Đen Mã `b9→c7`**
Mã đen bên trái (ô b9) nhảy xuống (ô c7).
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches/$ROOM/fen \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fen":"r1bakabnr/9/1cn4c1/p1p1p1p1p/9/9/P1P1P1P1P/1C2C4/9/RNBAKABNR w - - 0 2"}'
```
→ moveNumber=2, piece="n", currentTurn="RED"

**Bước 4 — Nước 3: Đỏ Tốt `e3→e4`**
Tốt giữa (ô e3) tiến lên 1 bước (ô e4).
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches/$ROOM/fen \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fen":"r1bakabnr/9/1cn4c1/p1p1p1p1p/9/4P4/P1P3P1P/1C2C4/9/RNBAKABNR b - - 0 2"}'
```
→ moveNumber=3, piece="P", currentTurn="BLACK"

**Bước 5 — Nước 4: Đen Pháo `h7→e7`**
Pháo đen bên phải (ô h7) di chuyển ngang sang giữa (ô e7).
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches/$ROOM/fen \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"fen":"r1bakabnr/9/1cn1c4/p1p1p1p1p/9/4P4/P1P3P1P/1C2C4/9/RNBAKABNR w - - 0 3"}'
```
→ moveNumber=4, piece="c", currentTurn="RED"

**Bước 6 — Kiểm tra lịch sử**
```bash
curl -s -X GET https://<DOMAIN>/api/simulation/matches/$ROOM/moves \
  -H "Authorization: Bearer <TOKEN>"
```
→ totalMoves=4, mỗi nước có FEN tương ứng

**Bước 7 — Kết thúc trận**
```bash
curl -s -X POST https://<DOMAIN>/api/simulation/matches/$ROOM/end \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"winner":"RED","reason":"CHECKMATE"}'
```
→ status="FINISHED", winner="RED"

---

## 7. WebSocket — Xem trực tiếp
```text
Topic: /topic/match/{roomId}
```
Mỗi khi bên thứ 3 gửi FEN mới → server broadcast `MatchState` → bàn cờ cập nhật real-time. **Không cần bên thứ 3 xử lý gì thêm.**

---

## 8. Mã lỗi

| HTTP | Code | Message | Nguyên nhân |
| --- | --- | --- | --- |
| 400 | `11001` | Match not found | roomId sai hoặc trận đã kết thúc |
| 400 | `11002` | Invalid FEN format | FEN không đúng chuẩn |
| 400 | `11003` | No move detected | FEN mới = FEN cũ, hoặc >1 quân thay đổi |
| 400 | `11004` | Illegal move | Vi phạm luật di chuyển quân |
| 401 | — | Unauthorized | Token hết hạn hoặc sai |
| 403 | — | Forbidden | Token không có role SIMULATION |

---

## 9. Giới hạn & Quy tắc

| Quy tắc | Giá trị |
| --- | --- |
| TTL trận đấu | **3 giờ** — tự kết thúc nếu quá hạn |
| Token validity | **365 ngày** |
| FEN format | Chuẩn 6 phần: `{board} {w|b} - - {half} {full}` |
| Lượt đi | Server tự chuyển RED ↔ BLACK |
| Validate | ✅ Luật di chuyển từng quân |
| Không validate | ❌ Chiếu vĩnh viễn, đuổi vĩnh viễn, luật 60 nước hòa |

---
**Liên hệ hỗ trợ**: Nếu cần token mới hoặc có lỗi → liên hệ admin.
© 2026 Tướng Kỳ Đại Sư — Simulation Match API v1.0
