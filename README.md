# AI Auto Trading Bot (Vietnam Stock Market - VN30)

Hệ thống Bot Giao Dịch Tự Động trên Thị Trường Chứng Khoán Việt Nam kết nối DNSE OpenAPI và Telegram Bot.

## Tính năng đã hoàn thành (Phase 1, 2, 3)

### Phase 1: MVP Read-Only & Telegram Bot (`v0.1.0-mvp`)
- Kết nối xác thực an toàn DNSE OpenAPI (HMAC-SHA256).
- Tra cứu số dư tài khoản (`/balance`), vị thế đang nắm giữ (`/portfolio`), tổng quan (`/status`).
- Bảo mật Whitelist: Chỉ duy nhất Admin Telegram Chat ID (`7385637982`) được phép thao tác.
- Chạy nền tự động trên Windows qua file `run_bot.bat`.

### Phase 2: Market Data Feed & Indicator Engine (`v0.2.0-indicators`)
- Cập nhật rổ VN30 chuẩn 30 mã cổ phiếu lớn nhất sàn HOSE.
- Thu thập nến ngày (1D) tốc độ cao từ Entrade / DNSE Chart API không cần xác thực.
- Tính toán chỉ báo kỹ thuật Vectorized (NumPy): EMA (9, 21, 50, 200), RSI (14), MACD (12, 26, 9), Bollinger Bands, ATR (14), Volume SMA (20).
- Lệnh Telegram: `/quote <MÃ>`, `/indicators <MÃ>`, `/scan`, `/vn30`.

### Phase 3: Trading Strategy Engine & Paper Trading Simulation (`v0.3.0-paper`)
- **Vốn giả lập**: 5.000.000 VNĐ lưu trữ an toàn trong SQLite nội bộ (100% không dùng tiền thật).
- **Lô chẵn & Lô lẻ**: Hỗ trợ đầy đủ mua bán lô chẵn (bội số 100) và lô lẻ (từ 1 đến 99 cổ phiếu), tối ưu hóa nguồn vốn cho cả các mã thị giá cao (như FPT, VCB, VJC).
- **Chiến lược kép (Dual Strategy)**:
  - **Strategy A (Trend Following Breakout)**: Điểm nổ khi Price > EMA21 > EMA50, MACD Bullish Cross, Vol >= 1.3x VolSMA20.
  - **Strategy B (Pullback / Buy on Dip)**: Bắt nhịp điều chỉnh về EMA21 / Lower BB trong xu hướng tăng lớn, RSI 30-45 có nến đảo chiều.
- **Biểu phí & Thuế sát thực tế**: Phí mua 0.15%, Phí bán 0.15% + Thuế 0.10% = 0.25%.
- **Chu kỳ thanh toán T+2**: Cổ phiếu mua ngày $T$ về tài khoản khả dụng để bán vào ngày $T+2$.
- **Quản trị rủi ro**: Cắt lỗ tự động (-5%), Chốt lời (+8% hoặc +7% khi RSI > 75), Trailing Stop tự động (giảm 2% từ đỉnh sau khi lãi >= +5%).
- **Lệnh Telegram Paper Trading**:
  - `/paper`: Xem Dashboard tài khoản giả lập, danh mục đang giữ và lãi/lỗ.
  - `/signals`: Quét danh sách cổ phiếu VN30 đang có tín hiệu Mua/Bán theo chiến lược.
  - `/buy_paper <MÃ> <KL> [GIÁ]`: Mua giả lập thủ công (hỗ trợ lô chẵn & lô lẻ).
  - `/sell_paper <MÃ> <KL> [GIÁ]`: Bán giả lập thủ công (kiểm tra cổ phiếu đã về T+2).
  - `/autotrade_paper [on|off]`: Bật/Tắt chế độ tự động đi lệnh ảo khi có tín hiệu.
  - `/reset_paper`: Đặt lại tài khoản giả lập về 5.000.000 VNĐ.

### Phase 4: Live Order Execution & Risk Safeguards (`v0.4.0-live`)
- **Kết nối Đặt lệnh Thật DNSE OpenAPI**:
  - Khởi tạo và ký HMAC-SHA256 chuẩn cho các endpoint đặt lệnh (`POST /accounts/{accountNo}/orders?marketType=STOCK&orderCategory=NORMAL`), tra cứu gói vay Margin/Deal (`GET /accounts/{accountNo}/loan-packages`), tra cứu sổ lệnh (`GET /accounts/{accountNo}/orders`), hủy lệnh (`DELETE /accounts/{accountNo}/orders/{orderId}`).
  - Xử lý xác thực tự động trực tiếp bằng `API Key` & `API Secret` mà không làm gián đoạn hệ thống.
- **3 Chế độ Giao dịch Linh hoạt (Trading Modes)**:
  - `PAPER` *(Mặc định khi khởi động)*: Chế độ an toàn tuyệt đối, chỉ chạy mô phỏng giả lập, bảo vệ 100% tiền thật.
  - `LIVE_CONFIRM`: Chế độ Bán tự động (Semi-Auto) — Khi phát hiện cơ hội giao dịch, bot gửi thông báo kèm nút bấm Inline Keyboard `[✅ Xác nhận ĐẶT LỆNH THẬT]` và `[❌ Hủy bỏ]`. Chỉ khi Admin bấm duyệt lệnh mới được đẩy lên sàn HOSE.
  - `LIVE_AUTO`: Chế độ Tự động hoàn toàn (Full Auto) — Bot tự động gửi lệnh thật lên sàn ngay khi các chỉ báo kỹ thuật hội tụ đủ điều kiện mua/bán.
- **Hệ thống Bảo vệ & Quản trị Rủi ro (Risk Safeguards)**:
  - **Hạn mức giá trị lệnh (Max Gross Value)**: Tối đa 5.000.000 VNĐ cho mỗi lệnh đặt.
  - **Giới hạn số lệnh ngày (Daily Rate Limiting)**: Tối đa 5 lệnh đặt/ngày để kiểm soát chi phí giao dịch và tránh over-trading.
  - **Kiểm soát biên độ trần/sàn HOSE ($\pm 7\%$)**: Từ chối đặt giá vượt quá biên độ cho phép so với giá tham chiếu.
- **Cầu Dao Khẩn Cấp (Emergency Kill Switch)**:
  - Kích hoạt qua lệnh `/kill_switch` hoặc nút bấm chuyên dụng trên bàn phím Telegram.
  - Tức thì hủy bỏ tất cả lệnh đang chờ khớp trên sàn HOSE và khóa chặt hệ thống về chế độ `READ_ONLY`.
  - Khôi phục hệ thống an toàn qua lệnh `/resume`.
- **Lệnh Telegram Live Trading**:
  - `/mode [paper|live_confirm|live_auto]`: Tra cứu và thay đổi chế độ giao dịch.
  - `/buy_live <MÃ> <KL> [GIÁ]`: Đặt lệnh mua thật thủ công lên sàn HOSE.
  - `/sell_live <MÃ> <KL> [GIÁ]`: Đặt lệnh bán thật thủ công lên sàn HOSE.
  - `/orders_live`: Tra cứu sổ lệnh thật trong ngày từ DNSE OpenAPI.
  - `/cancel_live <MÃ_LỆNH>`: Gửi yêu cầu hủy lệnh đang chờ trên sàn.
  - `/kill_switch`: Ngắt cầu dao khẩn cấp, hủy lệnh và khóa giao dịch.
  - `/resume`: Mở lại cầu dao và khôi phục hệ thống.

## Hướng dẫn Chạy Bot

```bash
# Kích hoạt môi trường ảo
.venv\Scripts\activate

# Chạy test toàn bộ hệ thống
pytest -v

# Khởi chạy bot
python main.py
# Hoặc nhấp đúp file run_bot.bat
```
