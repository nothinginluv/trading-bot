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

### Phase 5: VN-Index Market Regime & Dynamic ATR Risk Management (`v0.5.0-regime-risk`)
- **Bộ Lọc Thị Trường Chung (VN-Index Gate)**:
  - Tự động thu thập dữ liệu nến ngày chỉ số `VNINDEX` qua endpoint `ohlcs/index` của Entrade API.
  - Đánh giá trạng thái thị trường: `BULLISH` (thị trường thuận lợi), `SIDEWAYS` (giằng co), `BEARISH` (downtrend / rủi ro).
  - Tự động **chặn mọi vị thế MUA mới** (cả Paper và Live) khi VN-Index rơi vào trạng thái `BEARISH` ($Close < EMA50$ hoặc $Close < EMA21$ kết hợp $RSI < 45$) để bảo toàn vốn trước các đợt sụt giảm thị trường.
- **Quản trị Rủi ro Động theo ATR (Volatility-adjusted SL/TP)**:
  - Biên độ cắt lỗ thích ứng theo độ biến động thực tế của từng mã ($1.5 \times ATR$), dao động từ $-3.5\%$ đến $-6.5\%$.
  - Biên độ chốt lời co giãn từ $+5.0\%$ đến $+12.0\%$ theo $1.5 \times ATR$ và $2.5 \times ATR$.
  - Trailing Stop động từ $2.0\%$ đến $3.5\%$ từ đỉnh.
- **Chốt Lời 2 Giai Đoạn (2-Step Partial Take Profit)**:
  - **Giai đoạn 1 (Target 1 - TP1)**: Khi vị thế đạt lãi mục tiêu 1 ($+5\%$ đến $+7\%$), tự động bán 50% khối lượng (tuân thủ quy tắc lô chẵn/lô lẻ HOSE) để hiện thực hóa lợi nhuận.
  - **Giai đoạn 2 (Target 2 / Breakeven)**: 50% còn lại được kích hoạt dừng lỗ Hoà Vốn (Breakeven - bán khi giá quay về giá vốn) và thả theo Trailing Stop để gồng hết con sóng lớn.
- **Lệnh Telegram mới**:
  - `/market` hoặc `/vnindex`: Xem chi tiết điểm số, chỉ báo và trạng thái bộ lọc giải ngân của VN-Index.
  - Cập nhật `/scan` và `/status`: Hiển thị banner trạng thái thị trường chung ngay trên đầu.

### Phase 6: Market News Crawler, Financial Sentiment Engine & Signal Combo (`v0.6.0-news`)
- **Thu thập Tin tức Tự động (Multi-source News Crawler)**:
  - Thu thập tin tức chứng khoán liên tục từ 2 trang báo tài chính hàng đầu Việt Nam: **CafeF** (`thi-truong-chung-khoan.chn`, `doanh-nghiep.chn`) và **Vietstock** (`chung-khoan.htm`, `doanh-nghiep.htm`).
  - Sử dụng Async HTTPX + bóc tách Regex tốc độ cao (<2s quét xong hàng chục bài viết mới nhất), không phụ thuộc vào trình duyệt nặng nề.
  - Chu kỳ quét định kỳ 10 phút/lần hoặc kích hoạt tức thì.
- **Bộ Phân tích Cảm tính Tài chính Tiếng Việt (Offline Sentiment Lexicon)**:
  - Phân tích từ khóa ngữ cảnh tài chính thuần Việt (tăng trưởng, lợi nhuận, phá đỉnh, thoái vốn, nợ xấu, lỗ ròng, điều tra, vi phạm...).
  - Hệ thống Alias thông minh nhận diện chuẩn 30 mã VN30 (ví dụ: FPT Telecom -> FPT, Vinamilk -> VNM, Techcombank -> TCB...).
  - Tốc độ xử lý siêu tốc (<5ms), hoạt động hoàn toàn offline không tốn chi phí và không phụ thuộc API bên thứ 3.
- **Chiến lược Phối hợp Kỹ thuật + Cảm tính (News Combo Logic)**:
  - **Mua (BUY Combo)**:
    - *Veto (Chặn mua)*: Nếu mã có tin tức tiêu cực rủi ro ($Sentiment \le -0.25$), bot tự động huỷ bỏ tín hiệu mua kỹ thuật để bảo vệ vốn.
    - *Boost (Tăng tự tin)*: Nếu mã có tin tức tích cực ($Sentiment \ge +0.25$), bot cộng thêm $+0.15$ điểm tin cậy (Confidence Boost).
  - **Bán (SELL Combo)**:
    - Khi tín hiệu kỹ thuật báo bán trùng với tin tức tiêu cực, bot nâng cao mức độ khẩn cấp (Amplify Urgency/Alert) trong thông báo gửi Admin.
- **Cơ chế Thoát hiểm Khẩn cấp khi gặp Khủng hoảng (Option 2B - Severe Crisis Exit)**:
  - Tự động nhận diện các sự kiện rủi ro pháp lý/tài chính đặc biệt nghiêm trọng ("khởi tố", "bắt tạm giam", "thanh tra", "đình chỉ giao dịch", "phá sản", "vỡ nợ"...).
  - Kích hoạt cơ chế `CRISIS_EXIT`: Lập tức bán sạch toàn bộ vị thế của mã đó (khi cổ phiếu đã khả dụng T+2) mà không chờ chạm ngưỡng Stop Loss kỹ thuật, đồng thời phát cảnh báo khẩn cấp màu đỏ về Telegram.
- **Lệnh Telegram mới**:
  - `/news` hoặc `/tin`: Xem bản tin thị trường tổng hợp mới nhất từ CafeF và Vietstock kèm điểm cảm tính.
  - `/news <MÃ>` (ví dụ: `/news FPT`): Xem các bài báo gần nhất và chỉ số tâm lý riêng cho mã cổ phiếu đó.
  - Nút bấm `📰 Tin tức` tích hợp trực tiếp trên Bàn phím nhanh (Reply Keyboard).

### Phase 7: Multi-Timeframe Engine, Advanced Portfolio Risk & Volatility Sizing (`v0.7.0-mtf-risk`)
- **Phân tích Đa Khung Thời Gian (Multi-Timeframe 1D + 15m)**:
  - Khung 1D: Xác định xu hướng lớn chủ đạo (Macro Trend) qua EMA21, EMA50, EMA200 và MACD.
  - Khung 15 phút (15m): Bắt nhịp kích hoạt vào lệnh chính xác (Precision Timing) qua bứt phá cản, nến đảo chiều rút chân và dòng tiền bùng nổ 15m.
  - Bộ lọc kiểm định 15m: Tự động phủ quyết tín hiệu mua nếu khung 15m xuất hiện lực xả mạnh bất thường; tự động tăng độ tin cậy (Confidence Boost) khi cả 1D và 15m đồng thuận.
- **Quản trị Rủi ro Danh mục & Cầu Dao Tự Động (Portfolio Risk & Circuit Breaker)**:
  - **Trần phơi nhiễm danh mục (Exposure Cap)**: Giới hạn tổng giá trị các vị thế mở tối đa **85% NAV** (luôn giữ đệm 15% tiền mặt an toàn), tự động co hẹp khối lượng vị thế khi chạm trần.
  - **Giới hạn số vị thế đồng thời (Slot Limit)**: Tối đa nắm giữ **4 mã cùng lúc** (tối ưu hóa danh mục, tránh phân tán vốn quá mỏng).
  - **Cam kết Tuyệt đối Không Margin (Cash-Only)**: Tiền mặt khả dụng là giới hạn tuyệt đối; lệnh thật trên DNSE luôn ưu tiên gói tài khoản thường (`type == "N"`), không phát sinh bất kỳ khoản vay margin nào.
  - **Cầu dao tự ngắt (Drawdown Circuit Breaker)**: Tự động kích hoạt Cầu Dao Khẩn Cấp (Emergency Kill Switch), chuyển hệ thống về `READ_ONLY` và phát cảnh báo đỏ khi:
    + Drawdown trong ngày sụt giảm $\le -3.0\%$ NAV.
    + Drawdown trong tuần sụt giảm $\le -7.0\%$ NAV.
    + Yêu cầu Admin gửi lệnh `/resume` thủ công để mở khóa sau khi thị trường ổn định.
- **Phân Bổ Vốn 2 Lớp (2-Layer Position Sizing: ATR-Risk + 25% NAV Hard Cap)**:
  - **Lớp 1 (Rủi ro ATR)**: $Shares_{ATR} = \frac{NAV \times 1.5\%}{1.5 \times ATR}$.
  - **Lớp 2 (Trần cứng 25% NAV)**: $Shares_{Cap} = \frac{NAV \times 25\%}{Price}$.
  - **Khối lượng cuối cùng**: $Final = \min(Shares_{ATR}, Shares_{Cap})$.
  - Cổ phiếu biến động mạnh ($ATR$ cao) $\rightarrow$ Size nhỏ an toàn theo Lớp 1.
  - Cổ phiếu tích lũy ít biến động ($ATR$ thấp) $\rightarrow$ Bị chặn cứng ở 25% NAV theo Lớp 2 (không bị phình to vol).
  - Tuân thủ nghiêm ngặt quy định khớp lệnh Lô chẵn (bội số 100) và Lô lẻ (1-99) sàn HOSE. Nếu $Final < 1$, tự động từ chối mở vị thế.
- **Cập nhật Giao diện Telegram**:
  - Lệnh `/paper`: Hiển thị tỷ lệ phơi nhiễm danh mục (% NAV), quy mô slot (ví dụ `2/4 mã`), và drawdown ngày so với ngưỡng cầu dao tự ngắt.
  - Lệnh `/signals`: Đồng bộ quét tín hiệu đa khung thời gian 1D + 15m.

### Phase 8: SQLite WAL Mode, Stale LO Order Auto-Cancellation & Performance Analytics (`v0.8.0-wal-perf`)
- **Cơ chế SQLite Đa Luồng Không Khóa (WAL Mode Concurrency)**:
  - Tự động kích hoạt `PRAGMA journal_mode=WAL;`, `PRAGMA busy_timeout=10000;`, `PRAGMA synchronous=NORMAL;` trên mọi kết nối cơ sở dữ liệu.
  - Ngăn ngừa 100% lỗi `sqlite3.OperationalError: database is locked` khi bot chạy song song nến 15m, nến 1D, cào tin tức HTTPX và nhận lệnh từ Telegram.
- **Tự Động Hủy Lệnh Treo Quá Hạn (Auto-Cancel Stale LO Orders)**:
  - Khi đặt lệnh LO qua `/buy_live`, `/sell_live` hoặc Auto-Trader: nếu sau 15 phút lệnh chưa khớp do thị giá chạy xa, bot tự động kích hoạt `cancel_order` lên DNSE.
  - Mục đích: Giải phóng hạn mức phơi nhiễm danh mục, tránh bị khớp bất lợi vào cuối phiên khi xu hướng đảo chiều.
- **Báo Cáo Hiệu Suất Đầu Tư & Dashboard PnL (`/pnl`, `/performance`)**:
  - Lệnh Telegram `/pnl` và `/performance` (kèm nút bấm `📊 Hiệu suất PnL` trên bàn phím nhanh).
  - Thống kê toàn diện: Lãi/Lỗ đã chốt (Realized PnL), Lãi/Lỗ tạm tính (Unrealized PnL), Tỷ lệ thắng (Win Rate %), Tỷ số Lãi/Lỗ (Profit Factor), Lệnh thắng/thua/hòa, Kỷ lục lãi/lỗ cao nhất, Drawdown ngày/tuần so với ngưỡng Cầu dao ngắt tự động.
- **Kiểm thử tự động**: Đạt **100/100 tests passed** (100% pass rate).

### Phase 9: Paper Trading Slippage Simulation & Sector Concentration Risk Management (`v0.9.0-slippage-sector`)
- **Mô Phỏng Trượt Giá Sát Thực Tế (Realistic HOSE Slippage Simulation)**:
  - Khắc phục tình trạng P&L Paper Trading quá lạc quan: Thêm tham số `slippage_pct = 0.1%` (10 bps).
  - Lệnh MUA: Giá khớp thực tế trượt tăng $+0.1\%$ và làm tròn theo bước giá HOSE (10đ / 50đ / 100đ).
  - Lệnh BÁN: Giá khớp thực tế trượt giảm $-0.1\%$ và làm tròn theo bước giá HOSE.
  - Phản ánh chính xác vào giá vốn vị thế (VWAP), phí thuế và Realized PnL, đưa kết quả kiểm thử Paper Trading sát với môi trường thực chiến LIVE.
- **Quản Trị Rủi Ro Tập Trung Ngành (Sector Concentration Risk Management)**:
  - Phân loại 30 mã VN30 vào các nhóm ngành chuẩn: Ngân hàng, Bất động sản, Thép & Vật liệu, Bán lẻ, Công nghệ, Thực phẩm & Đồ uống, Năng lượng & Tiện ích, Chứng khoán, Bảo hiểm, Hàng không, Hóa chất & Cao su...
  - Quy tắc bảo vệ vốn: **Tối đa 2 mã cùng ngành** được phép nắm giữ đồng thời trong danh mục 4 slot (`max_positions_per_sector = 2`).
  - Loại bỏ hoàn toàn nguy cơ 4 slot đều là cổ phiếu Ngân hàng (vốn chiếm 13/30 mã VN30).
  - Cơ chế Auto-Trader thông minh: Tự động phát hiện ngành bão hòa, gửi cảnh báo và tự động chọn lọc tín hiệu tiềm năng tiếp theo thuộc nhóm ngành khác (FPT, HPG, MWG...).
  - Kiểm soát chặt chẽ cả trên lệnh đặt tay `/buy_paper` và `/buy_live`.
- **Kiểm thử tự động**: Đạt **113/113 tests passed** (100% pass rate).

### Phase 10: Explicit Sector Taxonomy & Automated Corporate Actions Engine (`v0.10.0-sectors-events`)
- **Bảng Phân Loại 12 Nhóm Ngành Chuẩn ICB Tường Minh**:
  - Tách bạch rõ ràng các mã biên giới: `GAS, PLX, BSR` thuộc `DẦU KHÍ & XĂNG DẦU`, `POW` thuộc `ĐIỆN & TIỆN ÍCH`, và `GVR` thuộc `CAO SU & VẬT LIỆU` (tách riêng mủ cao su & khu công nghiệp khỏi BĐS dân dụng).
  - Khắc phục triệt để nguy cơ phân loại nhầm hoặc triệt tiêu slot chéo giữa Điện phòng thủ và Dầu khí biến động theo giá dầu thế giới.
  - Lệnh Telegram `/sectors` (hoặc `/nganh`): Hiển thị bảng phân loại 12 nhóm ngành, số mã đang nắm giữ và cảnh báo slot ngành (ví dụ `🛑 [ĐẦY 2/2]`).
- **Phân Hệ Thu Thập & Xử Lý Sự Kiện Doanh Nghiệp Tự Động (Automated Corporate Actions Engine)**:
  - Cào dữ liệu sự kiện doanh nghiệp, quyền lợi và công bố thông tin chính thức từ nguồn CafeF: Ngày Giao Dịch Không Hưởng Quyền (GDKHQ), Ngày ĐKCC, Cổ tức tiền mặt, Cổ tức cổ phiếu, Phát hành thêm, ESOP, Bổ nhiệm/Miễn nhiệm.
  - Cơ chế tự động can thiệp toàn diện (Full Automation):
    - **Tự Động Điều Chỉnh Kỹ Thuật Vị Thế Đang Nắm Giữ (Technical Position Adjustment on Ex-Date)**: Khi vị thế đang mở gặp sự kiện cổ tức cổ phiếu, chia tách (tỷ lệ 10%, 100:15, 2:1...) hoặc cổ tức tiền mặt vào ngày GDKHQ, bot tự động tính toán lại khối lượng nắm giữ mới theo chuẩn VSD/HOSE ($Qty_{new} = \lfloor Qty_{old} \times \alpha \rfloor$ dùng `floor` cắt cụt phần lẻ, không tạo vol ảo), hạ giá vốn bình quân ($Avg_{new} = Avg_{old} / \alpha$), và điều chỉnh đỉnh trailing ($Highest_{new} = Highest_{old} / \alpha$). Nhờ đó, các mức Stop Loss và Take Profit tự động co giãn khớp chuẩn với giá tham chiếu mới, ngăn ngừa 100% nguy cơ bị **kích hoạt Cắt Lỗ Oan Uổng (False Stop Loss)**. Đảm bảo tính Idempotent qua bảng `position_adjustments`.
    - **Đối Chiếu Vị Thế Sàn DNSE Tần Suất Thích Ứng (Adaptive Live Position Reconciliation)**:
      - *Tần suất Thích ứng*: Tự động chạy mỗi 30 phút trong những ngày có sự kiện quyền (Ex-Date ± 1 ngày) và mỗi 60 phút trong ngày bình thường.
      - *Lệnh Telegram thủ công*: Cung cấp lệnh `/reconcile` (hoặc `/doichieu`) để Admin yêu cầu đối chiếu dữ liệu tức thì bất kỳ lúc nào, hiển thị bảng so khớp trực quan, minh bạch.
      - *Cơ chế Đồng bộ An toàn*: So khớp trực tiếp khối lượng và giá vốn nội bộ với dữ liệu chính thức từ DNSE OpenAPI (`reconcile_positions()`). Nếu phát hiện lệch, ưu tiên đồng bộ theo số liệu sàn DNSE. Bảo vệ tuyệt đối các cổ phiếu đầu tư riêng của Admin ngoài danh mục bot.
    - **Cảnh Báo Sớm GDKHQ (T-1 Warning)**: Quét và nhắc nhở Admin trước 1 ngày đối với các cổ phiếu đang nắm giữ trong danh mục để chủ động kế hoạch chốt lời hoặc nhận quyền.
    - **Phạt Điểm Tin Cậy Pha Loãng (Dilution Penalty)**: Trừ `-0.15` điểm tin cậy đối với mã có thông tin phát hành thêm hoặc niêm yết bổ sung lượng lớn sắp diễn ra.
  - Lệnh Telegram `/events` hoặc `/sukien`: Tra cứu lịch sự kiện doanh nghiệp tổng hợp hoặc theo từng mã cổ phiếu (ví dụ: `/events FPT`).
- **Nâng Cấp Bộ Phân Tích Cảm Tính Tiếng Việt (Vietnamese Negation Handling)**:
  - Bổ sung cơ chế nhận diện tiền tố phủ định câu (`"không"`, `"chưa"`, `"chẳng"`, `"bác bỏ"`, `"tránh được"`...) trong phạm vi mệnh đề 1-5 từ.
  - Triệt tiêu điểm số tiêu cực ảo đối với các tiêu đề phủ định tích cực (`"không thua lỗ"`, `"chưa lỗ"`, `"không giảm"`, `"không bị phạt"`), ngăn chặn 100% tình trạng **VETO Mua Oan Uổng**.
  - Triệt tiêu cờ khủng hoảng khẩn cấp khi gặp các tin đính chính/bác bỏ (`"bác bỏ tin đồn bị khởi tố"`).
- **Kiểm thử tự động**: Đạt **133/133 tests passed** (100% pass rate).

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

