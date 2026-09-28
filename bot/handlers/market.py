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

def format_stock_price(price: float) -> str:
    if price <= 0:
        return f"{price:,.1f}"
    if price < 1000:
        return f"{price:,.1f} ({price * 1000:,.0f} đ)"
    return f"{price:,.0f} đ"

def format_stock_change(change: float) -> str:
    if abs(change) < 500:
        return f"{change:+.1f} ({change * 1000:+,.0f} đ)"
    return f"{change:+,.0f} đ"

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
    price_str = format_stock_price(s.price)
    change_str = format_stock_change(s.change)
    ohlc_str = f"`{s.open:,.1f}` / `{s.high:,.1f}` / `{s.low:,.1f}`"
    if s.price < 1000:
        ohlc_str += f" ({s.open*1000:,.0f} / {s.high*1000:,.0f} / {s.low*1000:,.0f} đ)"

    text = (
        f"{icon} **CỔ PHIẾU: {s.symbol} (Khung Ngày 1D)**\n"
        "──────────────────────\n"
        f"• **Thị giá:** `{price_str}` ({s.change_pct:+.2f}%)\n"
        f"• **Biến động:** `{change_str}`\n"
        f"• **Mở / Cao / Thấp:** {ohlc_str}\n"
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
    atr_str = f"`{s.atr14:.2f}` ({s.atr14*1000:,.0f} đ)" if s.atr14 < 1000 else f"`{s.atr14:.2f} đ`"
    text = (
        f"📊 **PHÂN TÍCH KỸ THUẬT: {s.symbol} (1D)**\n"
        "──────────────────────\n"
        f"• **Xu hướng chính:** {trend_icon} `{s.trend}`\n"
        f"• **Đường EMA:** 9: `{s.ema9:,.1f}` | 21: `{s.ema21:,.1f}` | 50: `{s.ema50:,.1f}`\n"
        f"• **RSI (14):** `{s.rsi14:.1f}` ({s.rsi_status})\n"
        f"• **MACD (12, 26, 9):** `{s.macd:+.2f}` | Signal: `{s.macd_signal:+.2f}` | Hist: `{s.macd_hist:+.2f}` ({s.macd_status})\n"
        f"• **Bollinger Bands:** `{s.bb_lower:,.1f}` - `{s.bb_middle:,.1f}` - `{s.bb_upper:,.1f}`\n"
        f"• **ATR (14):** {atr_str}\n"
        f"• **Khối lượng:** `{s.volume:,} CP` (`{s.vol_ratio:.1f}x` TB20)\n"
        "──────────────────────\n"
        f"🎯 **ĐÁNH GIÁ CHUNG:** `{s.composite_signal}`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("market", "vnindex"))
@router.message(lambda msg: msg.text in ("🏛️ VN-Index", "🏛️ Thị trường VN-Index"))
async def cmd_market(message: Message, state_obj):
    s = state_obj.vnindex_summary
    if not s:
        await message.answer("⚠️ Dữ liệu VN-Index đang được cập nhật, vui lòng thử lại sau giây lát.", parse_mode="Markdown")
        return

    regime = state_obj.market_regime
    regime_emoji = "🟢" if regime == "BULLISH" else ("🔴" if regime == "BEARISH" else "🟡")
    gate_status = "✅ CHO PHÉP MỞ VỊ THẾ MUA MỚI" if regime != "BEARISH" else "🛑 ĐANG CHẶN MUA MỚI (BẢO TOÀN VỐN)"

    text = (
        f"🏛️ **THỊ TRƯỜNG CHUNG: VN-INDEX (1D)**\n"
        "──────────────────────\n"
        f"• **Điểm số:** `{s.price:,.2f} điểm` ({s.change_pct:+.2f}% | `{s.change:+.2f}` điểm)\n"
        f"• **Trạng thái:** {regime_emoji} **{regime}**\n"
        f"• **Bộ lọc giải ngân:** {gate_status}\n"
        "──────────────────────\n"
        f"• **Đường EMA:** 21: `{s.ema21:,.1f}` | 50: `{s.ema50:,.1f}`\n"
        f"• **RSI (14):** `{s.rsi14:.1f}` ({s.rsi_status})\n"
        f"• **MACD:** `{s.macd:+.2f}` | Hist: `{s.macd_hist:+.2f}` ({s.macd_status})\n"
        f"• **Bollinger Bands:** `{s.bb_lower:,.1f}` - `{s.bb_middle:,.1f}` - `{s.bb_upper:,.1f}`\n"
        f"• **Khối lượng:** `{s.volume:,}` CP (`{s.vol_ratio:.1f}x` TB20)\n"
        "──────────────────────\n"
        f"💡 *Ghi chú: Khi VN-Index ở trạng thái BEARISH (Dưới EMA21, RSI < 45 hoặc thủng EMA50), bot sẽ tự động ngừng giải ngân mới để bảo toàn vốn.*"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("scan"))
@router.message(lambda msg: msg.text == "🔍 Quét VN30")
async def cmd_scan(message: Message, state_obj):
    if not state_obj.vn30_summaries:
        await message.answer("⚠️ Dữ liệu VN30 đang được khởi tạo, vui lòng bấm lại sau 30 giây.")
        return

    regime = state_obj.market_regime
    regime_emoji = "🟢" if regime == "BULLISH" else ("🔴" if regime == "BEARISH" else "🟡")
    gate_text = "MUA ĐƯỢC PHÉP" if regime != "BEARISH" else "TẠM CHẶN MUA (BẢO VỆ VỐN)"
    vnindex_text = f"`{state_obj.vnindex_summary.price:,.1f}`" if state_obj.vnindex_summary else "N/A"

    res = scan_vn30_market(state_obj.vn30_summaries)
    lines = [
        f"🔍 **KẾT QUẢ QUÉT TÍN HIỆU RỔ VN30 (1D)**",
        f"• **VN-Index:** {vnindex_text} | {regime_emoji} `{regime}` ({gate_text})",
        "──────────────────────"
    ]

    # 1. Breakout
    lines.append("🚀 **BÙNG NỔ KHỐI LƯỢNG & GIÁ (Breakout):**")
    if res.breakout:
        for s in res.breakout[:5]:
            p_str = format_stock_price(s.price)
            lines.append(f"• **{s.symbol}**: `{p_str}` ({s.change_pct:+.2f}%) | Vol: `{s.vol_ratio:.1f}x` | RSI: `{s.rsi14:.1f}`")
    else:
        lines.append("• Hiện chưa có mã nào thỏa mãn điều kiện")

    # 2. Oversold
    lines.append("\n💎 **VÙNG QUÁ BÁN / TÍCH LŨY (Oversold):**")
    if res.oversold:
        for s in res.oversold[:5]:
            p_str = format_stock_price(s.price)
            lines.append(f"• **{s.symbol}**: `{p_str}` ({s.change_pct:+.2f}%) | RSI: `{s.rsi14:.1f}`")
    else:
        lines.append("• Hiện không có mã nào RSI < 35")

    # 3. Overbought
    lines.append("\n⚠️ **VÙNG QUÁ MUA (Cảnh báo điều chỉnh):**")
    if res.overbought:
        for s in res.overbought[:5]:
            p_str = format_stock_price(s.price)
            lines.append(f"• **{s.symbol}**: `{p_str}` ({s.change_pct:+.2f}%) | RSI: `{s.rsi14:.1f}`")
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
        p_str = format_stock_price(s.price)
        lines.append(f"• **{s.symbol}**: `{p_str}` (`{s.change_pct:+.2f}%`) | Vol: `{s.volume:,}`")

    lines.append("\n🔴 **Top 5 Giảm Mạnh Nhất:**")
    for s in losers:
        p_str = format_stock_price(s.price)
        lines.append(f"• **{s.symbol}**: `{p_str}` (`{s.change_pct:+.2f}%`) | Vol: `{s.volume:,}`")

    await message.answer("\n".join(lines), parse_mode="Markdown")

@router.message(Command("sectors", "nganh"))
async def cmd_sectors(
    message: Message,
    state_obj=None,
    paper_repo=None,
    safeguards=None
):
    from config.constants import VN30_SECTOR_MAP
    sectors_dict = {}
    for sym, sec in VN30_SECTOR_MAP.items():
        sectors_dict.setdefault(sec, []).append(sym)

    active_symbols = set()
    if paper_repo:
        try:
            positions = await paper_repo.get_positions()
            active_symbols = {p.symbol for p in positions if p.total_quantity > 0}
        except Exception:
            pass
    elif state_obj and hasattr(state_obj, "positions") and state_obj.positions:
        active_symbols = {
            p.symbol for p in state_obj.positions
            if (getattr(p, 'tradeQuantity', 0) > 0 or getattr(p, 'openQuantity', 0) > 0)
        }

    max_sec = safeguards.max_positions_per_sector if safeguards else 2

    lines = [
        "🏢 **BẢNG PHÂN LOẠI NGÀNH VN30 (ICB CẤP 2) & QUẢN TRỊ RỦI RO**\n"
        f"• **Hạn mức cùng ngành:** Tối đa `{max_sec} mã/ngành` trong tổng 4 slot.\n"
        "──────────────────────"
    ]

    for sec, syms in sorted(sectors_dict.items()):
        held_in_sec = [s for s in syms if s in active_symbols]
        count = len(held_in_sec)
        status_tag = ""
        if count >= max_sec:
            status_tag = f" 🛑 **[ĐẦY {count}/{max_sec}]**"
        elif count > 0:
            status_tag = f" 🟡 **[{count}/{max_sec}]**"

        syms_str = ", ".join(f"`{s}` (Đang giữ)" if s in active_symbols else f"`{s}`" for s in sorted(syms))
        lines.append(f"📌 **{sec}** ({len(syms)} mã){status_tag}:\n{syms_str}")

    await message.answer("\n\n".join(lines), parse_mode="Markdown")
