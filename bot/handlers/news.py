from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from core.state import TradingState

router = Router()

def extract_symbol_arg(text: str) -> str:
    parts = text.strip().split()
    if len(parts) > 1:
        return parts[1].upper()
    return ""

@router.message(Command("news", "tin"))
@router.message(lambda msg: msg.text in ("📰 Tin tức", "📰 Tin tức thị trường"))
async def cmd_news(message: Message, state_obj: TradingState):
    sym = extract_symbol_arg(message.text) if message.text else ""
    articles = state_obj.latest_news

    # 1. Lookup specific ticker
    if sym and sym not in ("THỊ", "TỨC"):
        matched = [
            a for a in articles 
            if sym in [s.upper() for s in getattr(a, "related_symbols", [])]
            or sym in a.title.upper()
        ]
        sentiment = state_obj.get_symbol_sentiment(sym)
        is_crisis, crisis_title = state_obj.is_symbol_in_crisis(sym)

        status_emoji = "🟢" if sentiment >= 0.25 else ("🔴" if sentiment <= -0.25 else "🟡")
        label_text = "TÍCH CỰC" if sentiment >= 0.25 else ("TIÊU CỰC" if sentiment <= -0.25 else "TRUNG LẬP")

        lines = [
            f"📰 **TIN TỨC DOANH NGHIỆP: {sym}**",
            "──────────────────────",
            f"• **Điểm sắc thái:** {status_emoji} `{sentiment:+.2f}` ({label_text})"
        ]

        if is_crisis:
            lines.append(f"🚨 **CẢNH BÁO NGUY HIỂM:** Phát hiện tin cực xấu: `{crisis_title}`!")
        elif sentiment <= -0.25:
            lines.append("⚠️ **LƯU Ý:** Tin tức tiêu cực đang chi phối, bot sẽ phủ quyết (từ chối) mở điểm mua mới.")
        elif sentiment >= 0.25:
            lines.append("🚀 **XU HƯỚNG:** Tin tức tích cực hỗ trợ đà tăng giá (Catalyst).")

        lines.append("──────────────────────")
        lines.append(f"📋 **Các bài báo liên quan ({len(matched)} bài):**")

        if matched:
            for i, a in enumerate(matched[:5], 1):
                icon = "🟢" if a.sentiment_score >= 0.25 else ("🔴" if a.sentiment_score <= -0.25 else "⚪")
                lines.append(f"{i}. {icon} [{a.source}] [{a.title}]({a.link}) (`{a.sentiment_score:+.2f}`)")
        else:
            lines.append(f"• Chưa ghi nhận bài báo riêng cho mã `{sym}` trong 48h qua.")

        lines.append("\n💡 Gõ `/news` để xem điểm tin toàn thị trường.")
        await message.answer("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)
        return

    # 2. General Market News
    if not articles:
        await message.answer(
            "⚠️ Dữ liệu tin tức đang được đồng bộ từ CafeF & Vietstock. Vui lòng bấm lại sau ít phút.",
            parse_mode="Markdown"
        )
        return

    lines = [
        "📰 **TIN TỨC THỊ TRƯỜNG & TÂM LÝ ĐẦU TƯ (CafeF & Vietstock)**",
        "──────────────────────"
    ]

    # Show any active crisis
    if state_obj.severe_crisis_symbols:
        lines.append("🚨 **CẢNH BÁO TIN CỰC XẤU TRONG PHIÊN:**")
        for cs, c_title in state_obj.severe_crisis_symbols.items():
            lines.append(f"• `{cs}`: {c_title}")
        lines.append("──────────────────────")

    lines.append("🔥 **Top Tin Tức Mới Nhất:**")
    for i, a in enumerate(articles[:8], 1):
        icon = "🟢" if a.sentiment_score >= 0.25 else ("🔴" if a.sentiment_score <= -0.25 else "⚪")
        symbols_tag = f" `[{','.join(a.related_symbols)}]`" if a.related_symbols else ""
        lines.append(f"{i}. {icon} [{a.source}] [{a.title}]({a.link}){symbols_tag}")

    lines.append("──────────────────────")
    lines.append("💡 *Gõ `/news <MÃ>` (VD: `/news HPG` hoặc `/news FPT`) để lọc tin riêng từng cổ phiếu.*")

    await message.answer("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)

@router.message(Command("events", "sukien"))
@router.message(lambda msg: msg.text in ("📅 Sự kiện DN", "📅 Lịch sự kiện"))
async def cmd_events(message: Message, state_obj: TradingState, repo=None):
    sym = extract_symbol_arg(message.text) if message.text else ""
    events = state_obj.corporate_events

    # If state_obj has no events cached, query repo
    if not events and repo and hasattr(repo, "get_upcoming_events"):
        try:
            events = await repo.get_upcoming_events(limit=30)
        except Exception:
            events = []

    if sym and sym not in ("SỰ", "KIỆN"):
        matched = [e for e in events if e.symbol.upper() == sym]
        if not matched and repo and hasattr(repo, "get_upcoming_events"):
            try:
                matched = await repo.get_upcoming_events(symbol=sym, limit=10)
            except Exception:
                matched = []

        if not matched:
            await message.answer(f"ℹ️ Chưa ghi nhận sự kiện chốt quyền / công bố thông tin sắp tới cho mã `{sym}`.", parse_mode="Markdown")
            return

        lines = [
            f"📅 **LỊCH SỰ KIỆN DOANH NGHIỆP: {sym}**\n──────────────────────"
        ]
        for e in matched[:8]:
            ex_date_str = f"`{e.ex_date}`" if e.ex_date else "Chưa xác định"
            rec_date_str = f"`{e.record_date}`" if e.record_date else "N/A"
            type_str = e.event_type.value if hasattr(e.event_type, "value") else str(e.event_type)
            lines.append(
                f"• **Ngày GDKHQ:** {ex_date_str} (ĐKCC: {rec_date_str})\n"
                f"  📌 *Phân loại:* `{type_str}`\n"
                f"  📝 *Chi tiết:* {e.content}"
            )
        lines.append("💡 *Lưu ý: Bot tự động hủy lệnh MUA vào ngày GDKHQ để tránh điều chỉnh giá kỹ thuật.*")
        await message.answer("\n\n".join(lines), parse_mode="Markdown")
        return

    # All upcoming events
    if not events:
        await message.answer("ℹ️ Hiện tại chưa có lịch sự kiện / GDKHQ sắp diễn ra trong rổ theo dõi.", parse_mode="Markdown")
        return

    lines = [
        "📅 **LỊCH SỰ KIỆN & CHỐT QUYỀN DOANH NGHIỆP (VN30 & THỊ TRƯỜNG)**\n──────────────────────"
    ]
    for e in events[:10]:
        ex_date_str = f"`{e.ex_date}`" if e.ex_date else "Chưa xác định"
        lines.append(
            f"📌 **{e.symbol}** — GDKHQ: {ex_date_str}\n"
            f"• *{e.content}*"
        )

    lines.append("──────────────────────\n💡 *Gõ `/events <MÃ>` (VD: `/events FPT` hoặc `/events MBB`) để xem chi tiết.*")
    await message.answer("\n\n".join(lines), parse_mode="Markdown")

