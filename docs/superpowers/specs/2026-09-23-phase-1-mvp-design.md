# Thiết Kế Chi Tiết: AI Auto Trading Bot — Phase 1: MVP Read-Only & Telegram Bot

- **Dự án**: AI Auto Trading Bot — Chứng khoán Việt Nam (DNSE + Telegram)
- **Giai đoạn**: Sub-project 1 (Giai đoạn 0 & 1 trong Lộ trình 6 giai đoạn)
- **Mục tiêu**: Thiết lập nền tảng hệ thống, kết nối Live DNSE OpenAPI ở chế độ chỉ đọc (Read-Only), điều khiển và tra cứu số dư/danh mục cổ phiếu qua Telegram Bot, lưu trữ lịch sử bằng SQLite cục bộ trên máy tính cá nhân (Windows).

---

## 1. Bối cảnh & Mục tiêu

### 1.1 Mục tiêu giai đoạn 1
- Xây dựng kiến trúc module hóa chuẩn mực, tạo nền móng vững chắc để tích hợp Risk Management Engine (Giai đoạn 3) và AI/ML Signal Engine (Giai đoạn 4) mà không cần tái cấu trúc core.
- Tích hợp trực tiếp và xác thực chữ ký số động HMAC-SHA256 theo chuẩn DNSE LightSpeed OpenAPI.
- Cung cấp giao diện Telegram Bot (`aiogram 3.x`) có phân quyền bảo mật tuyệt đối (Whitelist Middleware chỉ cho phép Admin Telegram ID).
- Quản lý trạng thái bộ nhớ đệm (In-memory TradingState) kết hợp lưu trữ SQLite không đồng bộ (`aiosqlite`) và điều phối tác vụ nền theo khung giờ giao dịch của sàn HOSE (`APScheduler`).
- **An toàn vốn tuyệt đối**: Chế độ vận hành ở Giai đoạn 1 là **READ_ONLY** — không có bất kỳ logic đặt lệnh thật nào được kích hoạt.

### 1.2 Dữ liệu tài khoản đã xác thực Live
Hệ thống đã kiểm thử kết nối thành công tới endpoint OpenAPI của DNSE:
- **Tên chủ tài khoản**: Nguyễn Doãn Minh Hiếu
- **Mã lưu ký (Custody Code)**: `064C551408`
- **Số tiểu khoản cơ sở (Account No)**: `0001880229`
- **Telegram Bot**: `@AI_agent_tradingbot` (ID: `8825550394`)
- **Telegram Admin ID**: `7385637982`

---

## 2. Kiến trúc Hệ Thống (Unified Async Event Loop)

Hệ thống hoạt động dưới một tiến trình Python async duy nhất (`asyncio`), tối ưu cho môi trường máy cá nhân Windows (tiêu tốn RAM < 100MB, CPU < 1%).

```
┌──────────────────────────────────────────────────────────────┐
│                    TELEGRAM BOT LAYER (aiogram 3.x)          │
│  - WhitelistMiddleware: chỉ nhận lệnh từ ID 7385637982        │
│  - Lệnh: /start, /help, /status, /balance, /positions, /sync  │
│  - Bàn phím nút bấm nhanh (Inline Keyboard)                  │
└───────────────────────────────┬──────────────────────────────┘
                                │ Query / User Event
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                    CORE STATE & SCHEDULER                    │
│  - TradingState: Bộ nhớ đệm tài sản, danh mục, kết nối (TTL) │
│  - APScheduler: Tự động sync 60s (trong phiên) / 30m (ngoài) │
│  - Market Hours Engine: Nhận diện phiên HOSE (ATO/ATC/Khớp)  │
└───────────────┬──────────────────────────────┬───────────────┘
                │                              │
         Fetch / Refresh                 Save / Audit Log
                ▼                              ▼
┌──────────────────────────────┐ ┌─────────────────────────────┐
│       DNSE OPENAPI CLIENT    │ │    SQLITE LOCAL STORAGE     │
│  - HTTP Signature Generator  │ │  (storage/bot.db)           │
│  - Rate Limiter (TokenBucket)│ │  - account_snapshots        │
│  - Base: openapi.dnse.com.vn │ │  - positions_snapshot       │
│  - Circuit Breaker fallback  │ │  - audit_logs               │
└───────────────┬──────────────┘ └─────────────────────────────┘
                │ HTTPS (HMAC-SHA256)
                ▼
        DNSE OpenAPI Server
```

---

## 3. Cấu trúc Thư mục Chi tiết

```text
d:\TradingBot\
├── .env                      # Cấu hình bí mật (API keys, Bot token, Account ID) - KHÔNG commit
├── .env.example              # Mẫu cấu hình môi trường
├── .gitignore                # Loại trừ .env, API.txt, *.db, logs/, __pycache__/
├── requirements.txt          # Các thư viện phụ thuộc
├── run_bot.bat               # Script 1-click khởi chạy trên Windows
├── main.py                   # Điểm khởi chạy hệ thống (Entrypoint)
│
├── config/
│   ├── __init__.py
│   ├── settings.py           # Pydantic Settings nạp từ .env
│   └── constants.py          # Hằng số: URLs, danh sách VN30, khung giờ HOSE
│
├── core/
│   ├── __init__.py
│   ├── state.py              # In-memory TradingState (quản lý state & cache)
│   ├── market_hours.py       # Kiểm tra trạng thái phiên HOSE (ATO/ATC/Nghỉ trưa)
│   └── scheduler.py          # APScheduler cho background polling & tổng kết ngày
│
├── dnse/
│   ├── __init__.py
│   ├── signer.py             # Thuật toán sinh chữ ký số HTTP Signature (HMAC-SHA256)
│   ├── client.py             # Async DNSE Client (REST requests: accounts, balances, positions)
│   ├── mock_client.py        # Giả lập dữ liệu phục vụ test offline / ngoài giờ
│   └── models.py             # Pydantic models cho Account, Balance, Position
│
├── bot/
│   ├── __init__.py
│   ├── app.py                # Khởi tạo aiogram Bot & Dispatcher
│   ├── middlewares.py        # WhitelistMiddleware chặn ID lạ
│   ├── keyboards.py          # Bàn phím nút bấm nhanh (Inline/Reply Keyboard)
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── basic.py          # /start, /help, /status
│   │   └── portfolio.py      # /balance, /positions, /sync
│   └── notifier.py           # Gửi tin nhắn thông báo chủ động đến Telegram Admin
│
├── storage/
│   ├── __init__.py
│   ├── db.py                 # Quản lý kết nối SQLite async (aiosqlite) & tạo bảng
│   └── repository.py         # Truy vấn đọc/ghi snapshots & audit logs
│
└── tests/
    ├── __init__.py
    ├── test_signer.py        # Unit test thuật toán ký số HTTP Signature
    ├── test_whitelist.py     # Unit test chặn truy cập Telegram trái phép
    └── test_state.py         # Unit test cập nhật và lấy dữ liệu từ TradingState
```

---

## 4. Tích hợp DNSE OpenAPI & Ký số HTTP Signature

### 4.1 Thuật toán Ký số (DNSE HTTP Signature)
Mọi request gửi tới `https://openapi.dnse.com.vn` bắt buộc phải kèm 3 headers xác thực:
1. `X-API-Key`: Khóa API của tài khoản.
2. `Date`: Thời gian UTC theo định dạng RFC1123 (Ví dụ: `Wed, 23 Sep 2026 02:45:00 GMT`).
3. `X-Signature`: Chuỗi chữ ký số động.

**Quy trình sinh chữ ký**:
- **Nonce**: Sinh chuỗi UUID4 hex (32 ký tự không dấu gạch ngang).
- **Signing String**:
  ```text
  (request-target): {method.lower()} {path}
  date: {date_str}
  nonce: {nonce}
  ```
  *(Lưu ý: `{path}` là đường dẫn không bao gồm query string, ví dụ `/accounts/0001880229/positions`).*
- **HMAC-SHA256**: Ký chuỗi bằng `DNSE_API_SECRET`.
- **Base64 & URL Encoding**: Mã hóa Base64 raw bytes và chỉ thay thế 3 ký tự:
  - `+` → `%2B`
  - `/` → `%2F`
  - `=` → `%3D`
- **Đóng gói Header**:
  ```text
  X-Signature: Signature keyId="{API_KEY}",algorithm="hmac-sha256",headers="(request-target) date",signature="{ENCODED_SIGNATURE}",nonce="{NONCE}"
  ```

### 4.2 Các Endpoints Sử dụng
- `GET /accounts`: Lấy thông tin định danh và danh sách tiểu khoản (`0001880229`).
- `GET /accounts/{accountNo}/balances`: Lấy số dư tiền khả dụng, tiền tổng, nợ vay.
- `GET /accounts/{accountNo}/positions?marketType=STOCK`: Lấy danh mục vị thế cổ phiếu cơ sở đang nắm giữ.

### 4.3 Phòng vệ Rate Limit & Circuit Breaker
- Áp dụng **Token Bucket Limiter**: Tối đa 5 requests/giây.
- Bộ đệm **In-memory Cache**: TTL 15 giây đối với dữ liệu số dư/vị thế. Các lệnh gọi liên tiếp từ người dùng sẽ được trả kết quả từ cache.
- **Circuit Breaker**: Khi gặp lỗi 5xx hoặc timeout liên tiếp 3 lần, hệ thống tạm dừng gọi API 60 giây và gửi cảnh báo qua Telegram.

---

## 5. Thiết kế Giao diện Telegram Bot (`aiogram 3.x`)

### 5.1 Phân quyền Bảo mật (`WhitelistMiddleware`)
- Kiểm tra `event.from_user.id == settings.TELEGRAM_CHAT_ID (7385637982)`.
- Nếu không khớp: Ghi log cảnh báo vào bảng `audit_logs` và drop event (không trả lời bot để tránh tiết lộ sự tồn tại của hệ thống).

### 5.2 Danh sách Lệnh & Giao diện
1. `/start` & `/help`: Lời chào, hướng dẫn sử dụng và gắn kèm bàn phím nút bấm nhanh:
   - `[ 💰 Số dư ]` (tương đương `/balance`)
   - `[ 📊 Vị thế ]` (tương đương `/positions`)
   - `[ 🔄 Làm mới ]` (tương đương `/sync`)
   - `[ ℹ️ Trạng thái ]` (tương đương `/status`)
2. `/status`: Kiểm tra nhịp tim hệ thống:
   - Uptime của bot trên máy tính.
   - Trạng thái kết nối DNSE OpenAPI (Online / Offline, latency ms).
   - Phiên giao dịch hiện tại của sàn HOSE (Trước giờ / ATO / Khớp liên tục / Nghỉ trưa / ATC / Đóng cửa).
   - Chế độ hoạt động: `READ_ONLY` (An toàn vốn).
3. `/balance`: Hiển thị số dư tiền mặt:
   - Chủ tài khoản, số lưu ký, số tiểu khoản.
   - Tiền mặt khả dụng, tổng tiền mặt, nợ vay margin, tiền chờ về.
4. `/positions`: Hiển thị danh mục cổ phiếu:
   - Từng mã: Khối lượng nắm giữ, giá vốn bình quân, thị giá, Lãi/Lỗ tạm tính (VND & %).
   - Nếu chưa có cổ phiếu: "Hiện tại tài khoản chưa mở vị thế cổ phiếu nào".
5. `/sync`: Xóa cache bộ nhớ và gửi request ép làm mới dữ liệu từ DNSE.

### 5.3 Cảnh báo Chủ động (Proactive Alerts)
- Gửi tin nhắn chào mừng kèm thông tin máy và trạng thái kết nối khi bot vừa khởi động.
- Gửi cảnh báo ngay lập tức nếu phát hiện sự cố kết nối DNSE API hoặc mất kết nối mạng.
- Gửi báo cáo tóm tắt tài sản cuối phiên vào lúc 15:05 mỗi ngày giao dịch (T2 - T6).

---

## 6. Lưu trữ Dữ liệu SQLite (`storage/bot.db`)

Sử dụng thư viện `aiosqlite` thực thi bất đồng bộ.

### 6.1 Schema Bảng

```sql
-- Lưu snapshot số dư tài sản theo thời gian
CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_no TEXT NOT NULL,
    total_cash REAL NOT NULL,
    available_cash REAL NOT NULL,
    total_debt REAL DEFAULT 0,
    withdrawable_cash REAL NOT NULL
);

-- Lưu snapshot danh mục cổ phiếu
CREATE TABLE IF NOT EXISTS positions_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_no TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    cost_price REAL NOT NULL,
    market_price REAL NOT NULL,
    unrealized_pnl REAL NOT NULL
);

-- Nhật ký kiểm toán và cảnh báo hệ thống
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL, -- INFO, WARNING, ERROR, CRITICAL
    source TEXT NOT NULL, -- TELEGRAM, DNSE_API, SCHEDULER
    message TEXT NOT NULL
);

-- Cấu hình hệ thống lưu trữ động
CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 7. Vận hành trên Máy tính Cá nhân Windows

### 7.1 Script Khởi chạy 1-Click (`run_bot.bat`)
- Tự động tạo và kích hoạt virtual environment Python (`.venv`) nếu chưa có.
- Tự động cài đặt hoặc cập nhật thư viện từ `requirements.txt`.
- Khởi chạy bot `python main.py`.
- Tự động ghi log ra màn hình console và file `logs/tradingbot.log`.

### 7.2 Quản lý Log xoay vòng (Rotating Log)
- Sử dụng `logging.handlers.RotatingFileHandler`: Kích thước tối đa 10MB mỗi file, lưu giữ tối đa 5 file gần nhất (`tradingbot.log.1`, `tradingbot.log.2`,...).
- Che giấu toàn bộ API Secret và Bot Token, tuyệt đối không xuất plain text ra log.

---

## 8. Kế hoạch Kiểm thử (Verification Plan)

### 8.1 Automated Unit Tests (pytest)
- `test_signer.py`: Kiểm tra tính toàn vẹn của chuỗi signing-string, tính toán HMAC-SHA256, URL encoding cho header `X-Signature`.
- `test_whitelist.py`: Giả lập request từ Telegram ID hợp lệ (`7385637982`) và ID lạ (`999999999`) để đảm bảo middleware chặn 100% request lạ.
- `test_state.py`: Kiểm tra luồng ghi nhận và làm mới dữ liệu trong `TradingState`.

### 8.2 Live Integration Verification
- Khởi chạy bot thật bằng lệnh PowerShell hoặc `run_bot.bat`.
- Gửi lệnh `/start`, `/status`, `/balance`, `/positions` từ ứng dụng Telegram trên điện thoại tới `@AI_agent_tradingbot`.
- Kiểm tra tính chính xác của dữ liệu phản hồi so với thông tin tài khoản thật từ DNSE (Chủ tài khoản: *Nguyễn Doãn Minh Hiếu*, Tiền khả dụng: *27,856 VNĐ*).
- Kiểm tra dữ liệu được lưu đúng vào bảng `account_snapshots` và `audit_logs` trong file SQLite `storage/bot.db`.
