import time
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from bot.keyboards import get_main_keyboard
from core.market_hours import MarketHours

router = Router()

@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, state_obj):
    text = (
        "🤖 **Chào mừng bạn đến với AI Auto Trading Bot!**\n"
        "*(Chế độ: READ_ONLY — An toàn vốn tuyệt đối)*\n\n"
        "**Các lệnh tra cứu tài khoản:**\n"
        "• `/balance` hoặc bấm 💰 Số dư\n"
        "• `/positions` hoặc bấm 📊 Vị thế\n"
        "• `/sync` hoặc bấm 🔄 Làm mới\n"
        "• `/reconcile` (hoặc `/doichieu`): Đối chiếu vị thế với sàn DNSE\n"
        "• `/status` hoặc bấm ℹ️ Trạng thái\n\n"
        "**Các lệnh thị trường & chỉ báo (VN30):**\n"
        "• `/quote <MÃ>` (hoặc `/q <MÃ>`): Xem giá & nến ngày\n"
        "• `/indicators <MÃ>` (hoặc `/i <MÃ>`): Phân tích kỹ thuật (EMA, RSI, MACD, BB)\n"
        "• `/market` (hoặc `/vnindex`): Xem trạng thái thị trường chung VN-Index & Bộ lọc giải ngân\n"
        "• `/scan` hoặc bấm 🔍 Quét VN30: Lọc cổ phiếu bùng nổ, quá bán, quá mua\n"
        "• `/vn30` hoặc bấm 📈 Bảng giá VN30: Top tăng/giảm mạnh nhất"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@router.message(Command("status"))
@router.message(lambda msg: msg.text == "ℹ️ Trạng thái")
async def cmd_status(message: Message, state_obj):
    session_display = MarketHours.get_session_display()
    conn_text = "🟢 Đang kết nối" if state_obj.is_connected else "🔴 Mất kết nối"
    latency = f"{state_obj.latency_ms:.1f}ms" if state_obj.latency_ms > 0 else "N/A"
    
    regime_emoji = "🟢" if state_obj.market_regime == "BULLISH" else ("🔴" if state_obj.market_regime == "BEARISH" else "🟡")
    vnindex_text = f"`{state_obj.vnindex_summary.price:,.1f}` ({state_obj.vnindex_summary.change_pct:+.2f}%)" if state_obj.vnindex_summary else "Đang đồng bộ"
    gate_text = "Cho phép mua" if state_obj.market_regime != "BEARISH" else "Chặn mua mới"

    text = (
        "ℹ️ **TRẠNG THÁI HỆ THỐNG**\n"
        "──────────────────────\n"
        f"• **Kết nối DNSE:** {conn_text} ({latency})\n"
        f"• **Thị trường (VN-INDEX):** {vnindex_text} | {regime_emoji} `{state_obj.market_regime}` ({gate_text})\n"
        f"• **Phiên HOSE:** {session_display}\n"
        f"• **Chế độ bot:** `{state_obj.mode}` (An toàn vốn)\n"
        f"• **Đồng bộ gần nhất:** {time.strftime('%H:%M:%S', time.localtime(state_obj.last_sync_time)) if state_obj.last_sync_time else 'Chưa đồng bộ'}\n"
    )
    await message.answer(text, parse_mode="Markdown")
