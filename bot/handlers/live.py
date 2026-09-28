import logging
from typing import Any, Optional
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from core.risk_safeguards import RiskSafeguards, TradingMode
from strategy.live_trader import LiveTrader
from core.state import TradingState

logger = logging.getLogger(__name__)

router = Router()

def get_mode_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="📝 Giả lập (PAPER)", callback_data="set_mode:paper"),
            InlineKeyboardButton(text="🛡️ Bán tự động (CONFIRM)", callback_data="set_mode:live_confirm"),
        ],
        [
            InlineKeyboardButton(text="🤖 Tự động hoàn toàn (AUTO)", callback_data="set_mode:live_auto")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_confirm_order_keyboard(confirm_id: str) -> InlineKeyboardMarkup:
    kb = [
        [
            InlineKeyboardButton(text="✅ Xác nhận ĐẶT LỆNH THẬT", callback_data=f"confirm_live:{confirm_id}"),
            InlineKeyboardButton(text="❌ Hủy bỏ", callback_data=f"cancel_live:{confirm_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(Command("mode"))
@router.message(F.text == "⚙️ Chế độ GD")
async def cmd_mode(message: Message, safeguards: RiskSafeguards):
    parts = message.text.strip().split() if message.text else []
    if len(parts) > 1:
        target_mode = parts[1].strip().lower()
        if target_mode in ("paper", "gia_lap"):
            safeguards.set_mode(TradingMode.PAPER)
            await message.answer("✅ **Đã chuyển chế độ sang: GIẢ LẬP (PAPER TRADING)**\nAn toàn tuyệt đối, không phát sinh lệnh thật.", parse_mode="Markdown")
            return
        elif target_mode in ("live_confirm", "confirm", "ban_tu_dong"):
            safeguards.set_mode(TradingMode.LIVE_CONFIRM)
            await message.answer("⚠️ **Đã chuyển chế độ sang: BÁN TỰ ĐỘNG (LIVE CONFIRM)**\nCác lệnh thật sẽ yêu cầu bấm xác nhận qua Telegram trước khi gửi sàn.", parse_mode="Markdown")
            return
        elif target_mode in ("live_auto", "auto", "tu_dong"):
            safeguards.set_mode(TradingMode.LIVE_AUTO)
            await message.answer("🔥 **Đã chuyển chế độ sang: TỰ ĐỘNG HOÀN TOÀN (LIVE AUTO)**\nBot sẽ tự động đẩy lệnh thật lên sàn HOSE ngay khi có tín hiệu!", parse_mode="Markdown")
            return
        else:
            await message.answer("⚠️ Cú pháp không hợp lệ. Chọn một trong các chế độ: `paper`, `live_confirm`, `live_auto`.", parse_mode="Markdown")
            return

    # Display current status and menu
    mode_text = {
        TradingMode.PAPER: "📝 Giả lập (Paper Trading)",
        TradingMode.LIVE_CONFIRM: "🛡️ Bán tự động (Live Confirm - Cần xác nhận)",
        TradingMode.LIVE_AUTO: "🔥 Tự động hoàn toàn (Live Auto)"
    }.get(safeguards.mode, "Không xác định")

    status_icon = "🟢" if not safeguards.kill_switch_active else "🛑 CẦU DAO ĐANG NGẮT"

    text = (
        "⚙️ **CẤU HÌNH CHẾ ĐỘ GIAO DỊCH (TRADING MODE)**\n"
        "──────────────────────\n"
        f"• **Chế độ hiện tại:** {mode_text}\n"
        f"• **Trạng thái an toàn:** {status_icon}\n"
        f"• **Lệnh thật hôm nay:** `{safeguards.daily_orders_count}/{safeguards.max_daily_orders}`\n"
        f"• **Hạn mức 1 lệnh:** `{safeguards.max_order_value:,.0f} đ`\n\n"
        "👇 *Chọn chế độ giao dịch bạn muốn thiết lập:*"
    )
    await message.answer(text, reply_markup=get_mode_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("set_mode:"))
async def cb_set_mode(query: CallbackQuery, safeguards: RiskSafeguards):
    mode_str = query.data.split(":")[1]
    if mode_str == "paper":
        safeguards.set_mode(TradingMode.PAPER)
        msg = "📝 Đã chuyển sang chế độ **GIẢ LẬP (PAPER)**."
    elif mode_str == "live_confirm":
        safeguards.set_mode(TradingMode.LIVE_CONFIRM)
        msg = "🛡️ Đã chuyển sang chế độ **BÁN TỰ ĐỘNG (LIVE CONFIRM)**."
    elif mode_str == "live_auto":
        safeguards.set_mode(TradingMode.LIVE_AUTO)
        msg = "🔥 Đã chuyển sang chế độ **TỰ ĐỘNG HOÀN TOÀN (LIVE AUTO)**."
    else:
        msg = "⚠️ Chế độ không hợp lệ."

    await query.answer()
    if query.message:
        await query.message.answer(msg, parse_mode="Markdown")


@router.message(Command("kill_switch"))
@router.message(F.text == "🛑 CẦU DAO KHẨN CẤP")
@router.message(F.text == "🛑 KILL SWITCH")
async def cmd_kill_switch(message: Message, safeguards: RiskSafeguards, client: Any, state_obj: TradingState):
    reason = "Kích hoạt thủ công qua lệnh Telegram /kill_switch"
    safeguards.activate_kill_switch(reason)

    account_no = state_obj.account.accounts[0].id if (state_obj.account and state_obj.account.accounts) else "0001880229"

    # Attempt to cancel all open orders
    cancelled_count = 0
    try:
        orders = await client.get_orders(account_no)
        for ord in orders:
            if ord.orderStatus in ("NEW", "PENDING_NEW", "PARTIALLY_FILLED", "WAITING", "PENDING"):
                await client.cancel_order(account_no, ord.id)
                cancelled_count += 1
    except Exception as e:
        logger.error(f"Error cancelling orders during kill switch: {e}")

    alert_msg = (
        "🛑 **[CẦU DAO KHẨN CẤP ĐÃ ĐƯỢC KÍCH HOẠT!]**\n"
        "──────────────────────\n"
        "• Toàn bộ quyền đặt lệnh thật và auto-trade đã bị **KHÓA CHẶT (READ-ONLY)**.\n"
        f"• Đã hủy `{cancelled_count}` lệnh mở trên sàn DNSE/HOSE.\n"
        f"• Lý do: {reason}\n\n"
        "👉 Để khôi phục hệ thống khi thị trường ổn định, hãy gõ lệnh: `/resume`"
    )
    await message.answer(alert_msg, parse_mode="Markdown")


@router.message(Command("resume"))
async def cmd_resume(message: Message, safeguards: RiskSafeguards):
    safeguards.deactivate_kill_switch()
    await message.answer(
        "🟢 **HỆ THỐNG ĐÃ KHÔI PHỤC HOẠT ĐỘNG BÌNH THƯỜNG**\n"
        "──────────────────────\n"
        f"• Cầu dao khẩn cấp đã được mở lại.\n"
        f"• Chế độ hiện tại: `{safeguards.mode.value}`.\n"
        "• Các quy tắc an toàn vốn và định mức 5M / 5 lệnh vẫn được kiểm soát nghiêm ngặt.",
        parse_mode="Markdown"
    )


@router.message(Command("buy_live"))
async def cmd_buy_live(message: Message, live_trader: LiveTrader, state_obj: TradingState):
    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ **Cú pháp đặt lệnh mua thật:**\n"
            "`/buy_live <MÃ_CP> <KHỐI_LƯỢNG> [GIÁ_ĐẶT]`\n\n"
            "Ví dụ:\n"
            "• `/buy_live HPG 100 26500`\n"
            "• `/buy_live SSI 100` (Tự lấy giá thị trường hiện tại)",
            parse_mode="Markdown"
        )
        return

    symbol = parts[1].upper()
    try:
        quantity = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Khối lượng cổ phiếu phải là số nguyên dương.", parse_mode="Markdown")
        return

    price = 0.0
    summary = state_obj.vn30_summaries.get(symbol)
    if len(parts) >= 4:
        try:
            price = float(parts[3])
        except ValueError:
            await message.answer("⚠️ Giá đặt không hợp lệ.", parse_mode="Markdown")
            return
    elif summary and summary.price > 0:
        price = summary.price
    else:
        await message.answer(f"⚠️ Chưa có giá thị trường cho mã {symbol}. Vui lòng nhập giá cụ thể: `/buy_live {symbol} {quantity} <GIÁ>`", parse_mode="Markdown")
        return

    ref_price = summary.price if summary else price

    # Sector concentration risk check
    if live_trader.safeguards:
        active_live_symbols = [
            p.symbol for p in state_obj.positions
            if (getattr(p, 'tradeQuantity', 0) > 0 or getattr(p, 'openQuantity', 0) > 0)
        ]
        valid_sec, sec_msg = live_trader.safeguards.validate_sector_concentration(symbol, active_live_symbols)
        if not valid_sec:
            await message.answer(
                f"🛑 **LỆNH BỊ TỪ CHỐI BỞI QUẢN TRỊ RỦI RO NGÀNH:**\n{sec_msg}",
                parse_mode="Markdown"
            )
            return

    res = await live_trader.route_order(
        symbol=symbol,
        side="NB",
        quantity=quantity,
        price=price,
        reference_price=ref_price,
        strategy_name="MANUAL_BUY",
        reason="Lệnh mua thật thủ công từ Admin qua Telegram"
    )

    status = res.get("status")
    if status == "PAPER_MODE":
        await message.answer(
            f"ℹ️ **Hệ thống đang ở chế độ Giả lập (PAPER)**\n"
            f"Không gửi lệnh thật lên sàn. Nếu muốn đặt lệnh thật, hãy chuyển chế độ bằng lệnh `/mode live_confirm` hoặc `/mode live_auto`.",
            parse_mode="Markdown"
        )
    elif status == "REJECTED":
        await message.answer(
            f"🛑 **LỆNH BỊ TỪ CHỐI BỞI HỆ THỐNG BẢO VỆ (RISK SAFEGUARDS):**\n"
            f"• Lý do: {res.get('reason')}",
            parse_mode="Markdown"
        )
    elif status == "PENDING_CONFIRMATION":
        confirm_id = res["confirm_id"]
        total_val = quantity * price
        await message.answer(
            f"⚠️ **YÊU CẦU XÁC NHẬN ĐẶT LỆNH MUA THẬT (LIVE CONFIRM)**\n"
            f"──────────────────────\n"
            f"• **Mã cổ phiếu:** `{symbol}`\n"
            f"• **Khối lượng:** `{quantity:,}` cp\n"
            f"• **Giá đặt:** `{price:,.0f} đ`\n"
            f"• **Tổng giá trị:** `{total_val:,.0f} đ`\n"
            f"• **Tài khoản:** `{live_trader.account_no}`\n\n"
            f"👉 Nhấn nút xác nhận bên dưới để gửi lệnh lên sàn HOSE:",
            reply_markup=get_confirm_order_keyboard(confirm_id),
            parse_mode="Markdown"
        )
    elif status == "EXECUTED":
        await message.answer(
            f"🔥 **ĐẶT LỆNH MUA THẬT THÀNH CÔNG!**\n"
            f"──────────────────────\n"
            f"• **Mã:** `{symbol}` | **KL:** `{quantity:,}` cp | **Giá:** `{price:,.0f} đ`\n"
            f"• **Mã lệnh DNSE:** `{res.get('order_id')}`\n"
            f"• Lệnh đã được tiếp nhận trên sàn HOSE.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"❌ Đặt lệnh thất bại: {res.get('message')}", parse_mode="Markdown")


@router.message(Command("sell_live"))
async def cmd_sell_live(message: Message, live_trader: LiveTrader, state_obj: TradingState):
    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ **Cú pháp đặt lệnh bán thật:**\n"
            "`/sell_live <MÃ_CP> <KHỐI_LƯỢNG> [GIÁ_ĐẶT]`\n\n"
            "Ví dụ:\n"
            "• `/sell_live HPG 100 27000`\n"
            "• `/sell_live SSI 100`",
            parse_mode="Markdown"
        )
        return

    symbol = parts[1].upper()
    try:
        quantity = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Khối lượng cổ phiếu phải là số nguyên dương.", parse_mode="Markdown")
        return

    price = 0.0
    summary = state_obj.vn30_summaries.get(symbol)
    if len(parts) >= 4:
        try:
            price = float(parts[3])
        except ValueError:
            await message.answer("⚠️ Giá đặt không hợp lệ.", parse_mode="Markdown")
            return
    elif summary and summary.price > 0:
        price = summary.price
    else:
        await message.answer(f"⚠️ Chưa có giá thị trường cho mã {symbol}. Vui lòng nhập giá: `/sell_live {symbol} {quantity} <GIÁ>`", parse_mode="Markdown")
        return

    ref_price = summary.price if summary else price
    res = await live_trader.route_order(
        symbol=symbol,
        side="NS",
        quantity=quantity,
        price=price,
        reference_price=ref_price,
        strategy_name="MANUAL_SELL",
        reason="Lệnh bán thật thủ công từ Admin qua Telegram"
    )

    status = res.get("status")
    if status == "PAPER_MODE":
        await message.answer("ℹ️ Hệ thống đang ở chế độ Giả lập (PAPER). Không gửi lệnh thật.", parse_mode="Markdown")
    elif status == "REJECTED":
        await message.answer(f"🛑 **LỆNH BỊ TỪ CHỐI:** {res.get('reason')}", parse_mode="Markdown")
    elif status == "PENDING_CONFIRMATION":
        confirm_id = res["confirm_id"]
        total_val = quantity * price
        await message.answer(
            f"⚠️ **YÊU CẦU XÁC NHẬN ĐẶT LỆNH BÁN THẬT (LIVE CONFIRM)**\n"
            f"──────────────────────\n"
            f"• **Mã cổ phiếu:** `{symbol}`\n"
            f"• **Khối lượng:** `{quantity:,}` cp\n"
            f"• **Giá bán:** `{price:,.0f} đ`\n"
            f"• **Tổng giá trị:** `{total_val:,.0f} đ`\n\n"
            f"👉 Nhấn nút xác nhận bên dưới:",
            reply_markup=get_confirm_order_keyboard(confirm_id),
            parse_mode="Markdown"
        )
    elif status == "EXECUTED":
        await message.answer(
            f"🔥 **ĐẶT LỆNH BÁN THẬT THÀNH CÔNG!**\n"
            f"• **Mã:** `{symbol}` | **KL:** `{quantity:,}` cp | **Giá:** `{price:,.0f} đ`\n"
            f"• **Mã lệnh DNSE:** `{res.get('order_id')}`",
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"❌ Đặt lệnh thất bại: {res.get('message')}", parse_mode="Markdown")


@router.callback_query(F.data.startswith("confirm_live:"))
async def cb_confirm_live(query: CallbackQuery, live_trader: LiveTrader):
    confirm_id = query.data.split(":")[1]
    res = await live_trader.confirm_pending_order(confirm_id)
    await query.answer()

    if res.get("status") == "EXECUTED":
        msg = f"🔥 **XÁC NHẬN THÀNH CÔNG!** Lệnh thật đã gửi lên sàn HOSE.\nMã lệnh DNSE: `{res.get('order_id')}`"
    elif res.get("status") == "REJECTED":
        msg = f"🛑 **Lệnh bị từ chối:** {res.get('reason')}"
    elif res.get("status") == "NOT_FOUND":
        msg = "⚠️ Lệnh không tồn tại hoặc đã hết hạn xác nhận."
    else:
        msg = f"❌ Đặt lệnh thất bại: {res.get('message')}"

    if query.message:
        await query.message.answer(msg, parse_mode="Markdown")


@router.callback_query(F.data.startswith("cancel_live:"))
async def cb_cancel_live(query: CallbackQuery, live_trader: LiveTrader):
    confirm_id = query.data.split(":")[1]
    live_trader.cancel_pending_confirmation(confirm_id)
    await query.answer("Đã hủy lệnh chờ xác nhận!")
    if query.message:
        await query.message.answer("❌ **Đã hủy bỏ lệnh chờ xác nhận.**", parse_mode="Markdown")


@router.message(Command("orders_live"))
@router.message(F.text == "📋 Sổ lệnh Thật")
async def cmd_orders_live(message: Message, client: Any, state_obj: TradingState):
    account_no = state_obj.account.accounts[0].id if (state_obj.account and state_obj.account.accounts) else "0001880229"
    try:
        orders = await client.get_orders(account_no)
    except Exception as e:
        await message.answer(f"❌ Không thể tải sổ lệnh thật từ DNSE: {e}", parse_mode="Markdown")
        return

    if not orders:
        await message.answer("📋 Hiện tại tài khoản chưa có lệnh nào trong ngày trên DNSE.", parse_mode="Markdown")
        return

    text = "📋 **SỔ LỆNH THẬT TRONG NGÀY (DNSE OPENAPI)**\n──────────────────────\n"
    for ord in orders[:15]:
        side_text = "MUA" if ord.side == "NB" else "BÁN"
        icon = "🟢" if ord.side == "NB" else "🔴"
        text += (
            f"{icon} **{ord.symbol}** — {side_text} `{ord.quantity:,}` cp @ `{ord.price:,.0f} đ`\n"
            f"• Khớp: `{ord.filledQuantity:,}/{ord.quantity:,}` | TT: `{ord.orderStatus}`\n"
            f"• Mã lệnh: `{ord.id}`\n\n"
        )

    text += "👉 Hủy lệnh mở: `/cancel_live <MÃ_LỆNH>`"
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("cancel_live"))
async def cmd_cancel_live(message: Message, client: Any, state_obj: TradingState, live_trader: Optional[LiveTrader] = None):
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("⚠️ Cú pháp: `/cancel_live <MÃ_LỆNH>`", parse_mode="Markdown")
        return

    order_id = parts[1].strip()
    account_no = state_obj.account.accounts[0].id if (state_obj.account and state_obj.account.accounts) else "0001880229"
    try:
        res = await client.cancel_order(account_no, order_id)
        is_ok = res.get("success", False) if isinstance(res, dict) else bool(res)
        if is_ok:
            if live_trader and hasattr(live_trader, "tracked_live_orders") and order_id in live_trader.tracked_live_orders:
                del live_trader.tracked_live_orders[order_id]
            await message.answer(f"✅ Đã gửi yêu cầu hủy lệnh `{order_id}` lên DNSE thành công.", parse_mode="Markdown")
        else:
            err_msg = res.get("message", "Thất bại") if isinstance(res, dict) else "Thất bại"
            await message.answer(f"❌ Hủy lệnh `{order_id}` thất bại trên DNSE: {err_msg}", parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Lỗi khi hủy lệnh: {e}", parse_mode="Markdown")

