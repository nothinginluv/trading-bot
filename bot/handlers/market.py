from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from indicators.scanner import scan_vn30_market

router = Router()

def extract_symbol(text: str) -> str:
    parts = text.strip().split()
    if len(parts) > 1:
        return parts[1].upper()
    return ""

@router.message(Command("quote", "q"))
async def cmd_quote(message: Message, state_obj):
    sym = extract_symbol(message.text)
    if not sym:
        await message.answer("⚠️ Vui lòng nhập mã cổ phiếu. Ví dụ: `/quote FPT` hoặc `/q HPG`", parse_mode="Markdown")
        return
    s = state_obj.get_summary(sym)
    if not s:
        await message.answer(f"⚠️ Chưa có dữ liệu cho mã `{sym}` trong rổ VN30. Vui lòng thử lại sau.", parse_mode="Markdown")
        return

    icon = "🟢" if s.change > 0 else ("🔴" if s.change < 0 else "⚪")
    text = (
        f"{icon} **CỔ PHIẾU: {s.symbol} (Khung Ngày 1D)**\n"
        "──────────────────────\n"
        f"• **Thị giá:** `{s.price:,.1f} đ` ({s.change_pct:+.2f}%)\n"
        f"• **Biến động:** `{s.change:+.1f} đ`\n"
        f"• **Mở / Cao / Thấp:** `{s.open:,.1f}` / `{s.high:,.1f}` / `{s.low:,.1f}`\n"
        f"• **Khối lượng:** `{s.volume:,} CP`\n"
        f"• **Tỷ lệ Vol / TB20:** `{s.vol_ratio:.1f}x` (TB20: `{s.vol_sma20:,.0f}`)\n"
        f"• **Tín hiệu tổng quan:** `{s.composite_signal}`\n"
        f"• Tra cứu kỹ thuật: `/indicators {s.symbol}`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("indicators", "i"))
async def cmd_indicators(message: Message, state_obj):
    sym = extract_symbol(message.text)
    if not sym:
        await message.answer("⚠️ Vui lòng nhập mã cổ phiếu. Ví dụ: `/indicators FPT` hoặc `/i HPG`", parse_mode="Markdown")
        return
    s = state_obj.get_summary(sym)
    if not s:
        await message.answer(f"⚠️ Chưa có dữ liệu phân tích kỹ thuật cho mã `{sym}`.", parse_mode="Markdown")
        return

    trend_icon = "🟢" if s.trend == "UPTREND" else ("🔴" if s.trend == "DOWNTREND" else "🟡")
    text = (
        f"📊 **PHÂN TÍCH KỸ THUẬT: {s.symbol} (1D)**\n"
        "──────────────────────\n"
        f"• **Xu hướng chính:** {trend_icon} `{s.trend}`\n"
        f"• **Đường EMA:** 9: `{s.ema9:,.1f}` | 21: `{s.ema21:,.1f}` | 50: `{s.ema50:,.1f}`\n"
        f"• **RSI (14):** `{s.rsi14:.1f}` ({s.rsi_status})\n"
        f"• **MACD (12, 26, 9):** `{s.macd:+.2f}` | Signal: `{s.macd_signal:+.2f}` | Hist: `{s.macd_hist:+.2f}` ({s.macd_status})\n"
        f"• **Bollinger Bands:** `{s.bb_lower:,.1f}` - `{s.bb_middle:,.1f}` - `{s.bb_upper:,.1f}`\n"
        f"• **ATR (14):** `{s.atr14:.2f} đ`\n"
        f"• **Khối lượng:** `{s.volume:,} CP` (`{s.vol_ratio:.1f}x` TB20)\n"
        "──────────────────────\n"
        f"🎯 **ĐÁNH GIÁ CHUNG:** `{s.composite_signal}`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("scan"))
@router.message(lambda msg: msg.text == "🔍 Quét VN30")
async def cmd_scan(message: Message, state_obj):
    if not state_obj.vn30_summaries:
        await message.answer("⚠️ Dữ liệu VN30 đang được khởi tạo, vui lòng bấm lại sau 30 giây.")
        return

    res = scan_vn30_market(state_obj.vn30_summaries)
    lines = ["🔍 **KẾT QUẢ QUÉT TÍN HIỆU RỔ VN30 (1D)**\n──────────────────────"]

    # 1. Breakout
    lines.append("🚀 **BÙNG NỔ KHỐI LƯỢNG & GIÁ (Breakout):**")
    if res.breakout:
        for s in res.breakout[:5]:
            lines.append(f"• **{s.symbol}**: `{s.price:,.1f}` ({s.change_pct:+.2f}%) | Vol: `{s.vol_ratio:.1f}x` | RSI: `{s.rsi14:.1f}`")
    else:
        lines.append("• Hiện chưa có mã nào thỏa mãn điều kiện")

    # 2. Oversold
    lines.append("\n💎 **VÙNG QUÁ BÁN / TÍCH LŨY (Oversold):**")
    if res.oversold:
        for s in res.oversold[:5]:
            lines.append(f"• **{s.symbol}**: `{s.price:,.1f}` ({s.change_pct:+.2f}%) | RSI: `{s.rsi14:.1f}`")
    else:
        lines.append("• Hiện không có mã nào RSI < 35")

    # 3. Overbought
    lines.append("\n⚠️ **VÙNG QUÁ MUA (Cảnh báo điều chỉnh):**")
    if res.overbought:
        for s in res.overbought[:5]:
            lines.append(f"• **{s.symbol}**: `{s.price:,.1f}` ({s.change_pct:+.2f}%) | RSI: `{s.rsi14:.1f}`")
    else:
        lines.append("• Hiện không có mã nào RSI > 70")

    lines.append("\n💡 Gõ `/indicators <MÃ>` để xem chi tiết từng mã.")
    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(Command("vn30"))
@router.message(lambda msg: msg.text == "📈 Bảng giá VN30")
async def cmd_vn30(message: Message, state_obj):
    if not state_obj.vn30_summaries:
        await message.answer("⚠️ Đang đồng bộ bảng giá VN30, vui lòng thử lại sau giây lát.")
        return

    gainers, losers = state_obj.get_top_movers(limit=5)
    lines = ["📈 **BẢNG GIÁ VN30: TOP BIẾN ĐỘNG**\n──────────────────────"]
    
    lines.append("🟢 **Top 5 Tăng Mạnh Nhất:**")
    for s in gainers:
        lines.append(f"• **{s.symbol}**: `{s.price:,.1f}` (`{s.change_pct:+.2f}%`) | Vol: `{s.volume:,}`")

    lines.append("\n🔴 **Top 5 Giảm Mạnh Nhất:**")
    for s in losers:
        lines.append(f"• **{s.symbol}**: `{s.price:,.1f}` (`{s.change_pct:+.2f}%`) | Vol: `{s.volume:,}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")
