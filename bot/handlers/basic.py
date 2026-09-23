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
        "Các lệnh khả dụng:\n"
        "• `/balance` hoặc bấm 💰 Số dư\n"
        "• `/positions` hoặc bấm 📊 Vị thế\n"
        "• `/sync` hoặc bấm 🔄 Làm mới\n"
        "• `/status` hoặc bấm ℹ️ Trạng thái"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@router.message(Command("status"))
@router.message(lambda msg: msg.text == "ℹ️ Trạng thái")
async def cmd_status(message: Message, state_obj):
    session = MarketHours.get_session()
    conn_text = "🟢 Online" if state_obj.is_connected else "🔴 Mất kết nối"
    latency = f"{state_obj.latency_ms:.1f}ms" if state_obj.latency_ms > 0 else "N/A"
    
    text = (
        "ℹ️ **TRẠNG THÁI HỆ THỐNG**\n"
        "──────────────────────\n"
        f"• **Kết nối DNSE:** {conn_text} ({latency})\n"
        f"• **Phiên HOSE:** `{session}`\n"
        f"• **Chế độ bot:** `{state_obj.mode}`\n"
        f"• **Đồng bộ gần nhất:** {time.strftime('%H:%M:%S', time.localtime(state_obj.last_sync_time)) if state_obj.last_sync_time else 'Chưa đồng bộ'}\n"
    )
    await message.answer(text, parse_mode="Markdown")
