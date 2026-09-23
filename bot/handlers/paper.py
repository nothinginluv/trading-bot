from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from strategy.paper_engine import PaperEngine
from storage.repository import PaperTradingRepository
from core.state import TradingState
from strategy.models import OrderStatus, SignalType
from strategy.signals import scan_signals

router = Router()

@router.message(Command("paper"))
@router.message(F.text == "💼 Tài khoản Giả lập")
async def cmd_paper(message: Message, paper_engine: PaperEngine, paper_repo: PaperTradingRepository, state_obj: TradingState):
    current_prices = {
        sym: s.price for sym, s in state_obj.vn30_summaries.items()
    }
    account = await paper_engine.get_account_summary(current_prices)
    positions = await paper_repo.get_positions()
    
    auto_status = "🟢 BẬT" if account.auto_trade_enabled else "🔴 TẮT"
    
    # Calculate unrealized pnl across positions
    total_unrealized_pnl = 0.0
    for pos in positions:
        mkt_price = current_prices.get(pos.symbol, pos.avg_buy_price)
        total_unrealized_pnl += (mkt_price - pos.avg_buy_price) * pos.total_quantity

    text = (
        "💼 **TÀI KHOẢN GIẢ LẬP (PAPER TRADING)**\n"
        "──────────────────────\n"
        f"• **Vốn ban đầu:** `{account.initial_balance:,.0f} đ`\n"
        f"• **Tiền mặt khả dụng:** `{account.cash_balance:,.0f} đ`\n"
        f"• **Giá trị cổ phiếu:** `{account.stock_value:,.0f} đ`\n"
        f"• **Tổng tài sản (NAV):** `{account.nav:,.0f} đ`\n"
        f"• **Lãi/Lỗ đã chốt:** `{account.total_realized_pnl:+,.0f} đ`\n"
        f"• **Lãi/Lỗ tạm tính:** `{total_unrealized_pnl:+,.0f} đ`\n"
        f"• **Chế độ Auto-Trade:** {auto_status}\n\n"
        "📈 **DANH MỤC NẮM GIỮ:**\n"
    )

    if not positions:
        text += "*(Chưa có cổ phiếu nào trong danh mục giả lập)*\n"
    else:
        for pos in positions:
            mkt_price = current_prices.get(pos.symbol, pos.avg_buy_price)
            pnl_vnd = (mkt_price - pos.avg_buy_price) * pos.total_quantity
            pnl_pct = ((mkt_price - pos.avg_buy_price) / pos.avg_buy_price) * 100 if pos.avg_buy_price > 0 else 0
            icon = "🟢" if pnl_vnd >= 0 else "🔴"
            lot_info = "Lô chẵn" if pos.total_quantity >= 100 else "Lô lẻ"
            text += (
                f"{icon} **{pos.symbol}** ({lot_info}):\n"
                f"  - Khối lượng: `{pos.total_quantity:,}` cp (Khả dụng T+2: `{pos.available_quantity:,}`)\n"
                f"  - Giá vốn: `{pos.avg_buy_price:,.0f} đ` | Giá TT: `{mkt_price:,.0f} đ`\n"
                f"  - Lãi/Lỗ: `{pnl_vnd:+,.0f} đ` (`{pnl_pct:+.2f}%`)\n"
            )

    text += (
        "\n📌 *Gợi ý lệnh:*\n"
        "• Mua giả lập: `/buy_paper <MÃ> <KL> [GIÁ]`\n"
        "• Bán giả lập: `/sell_paper <MÃ> <KL> [GIÁ]`\n"
        "• Bật/Tắt Auto: `/autotrade_paper on` hoặc `/autotrade_paper off`\n"
        "• Làm lại từ đầu: `/reset_paper`"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("signals"))
@router.message(F.text == "🎯 Tín hiệu VN30")
async def cmd_signals(message: Message, state_obj: TradingState):
    if not state_obj.vn30_summaries:
        await message.answer("⚠️ Dữ liệu thị trường đang được đồng bộ. Vui lòng thử lại sau giây lát.", parse_mode="Markdown")
        return

    found_signals = []
    for sym, summary in state_obj.vn30_summaries.items():
        series = state_obj.vn30_candles.get(sym)
        if not series:
            continue
        sig = scan_signals(series, summary)
        if sig:
            found_signals.append((sig, summary))

    if not found_signals:
        await message.answer("ℹ️ Hiện tại chưa có mã nào trong rổ VN30 xuất hiện điểm mua đạt chuẩn (Breakout hoặc Pullback).", parse_mode="Markdown")
        return

    text = "🎯 **TÍN HIỆU CHIẾN LƯỢC VN30 HIỆN TẠI**\n──────────────────────\n"
    for sig, s in found_signals:
        strat_name = "Bứt phá (Breakout)" if sig.strategy.value == "BREAKOUT" else "Bắt đáy (Pullback)"
        text += (
            f"🚀 **{sig.symbol}** — *{strat_name}*\n"
            f"• Giá khuyến nghị: `{sig.price:,.0f} đ`\n"
            f"• RSI (14): `{s.rsi14:.1f}` | Vol / TB20: `{s.vol_ratio:.1f}x`\n"
            f"• Rationale: {sig.reason}\n\n"
        )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("buy_paper"))
async def cmd_buy_paper(message: Message, paper_engine: PaperEngine, state_obj: TradingState):
    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ Sai cú pháp! Vui lòng dùng:\n`/buy_paper <MÃ> <KHỐI_LƯỢNG> [GIÁ]`\n"
            "Ví dụ:\n• `/buy_paper FPT 15` (khớp giá hiện tại)\n• `/buy_paper HPG 100 26000`",
            parse_mode="Markdown"
        )
        return

    symbol = parts[1].upper()
    try:
        quantity = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Khối lượng phải là số nguyên dương!", parse_mode="Markdown")
        return

    price = None
    if len(parts) >= 4:
        try:
            price = float(parts[3])
        except ValueError:
            await message.answer("⚠️ Giá phải là số hợp lệ!", parse_mode="Markdown")
            return

    if price is None:
        summary = state_obj.get_summary(symbol)
        if not summary:
            await message.answer(f"⚠️ Không tìm thấy giá hiện tại cho mã `{symbol}`. Vui lòng nhập kèm giá.", parse_mode="Markdown")
            return
        price = summary.price

    order = await paper_engine.execute_buy(symbol, quantity, price)
    if order.status == OrderStatus.FILLED:
        lot_type = "Lô chẵn" if quantity >= 100 else "Lô lẻ"
        await message.answer(
            f"✅ **KHỚP LỆNH MUA GIẢ LẬP THÀNH CÔNG**\n"
            f"• Mã: `{symbol}` ({lot_type})\n"
            f"• Khối lượng: `{quantity:,}` cp\n"
            f"• Giá khớp: `{price:,.0f} đ`\n"
            f"• Phí giao dịch (0.15%): `{order.fee:,.0f} đ`\n"
            f"• Chu kỳ thanh toán: Ngày T+2 cổ phiếu mới về để bán.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"❌ **LỆNH MUA BỊ TỪ CHỐI**\n"
            f"Số dư tiền mặt khả dụng không đủ để mua `{quantity:,}` cp `{symbol}` với giá `{price:,.0f} đ` (+ phí 0.15%).",
            parse_mode="Markdown"
        )

@router.message(Command("sell_paper"))
async def cmd_sell_paper(message: Message, paper_engine: PaperEngine, state_obj: TradingState):
    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ Sai cú pháp! Vui lòng dùng:\n`/sell_paper <MÃ> <KHỐI_LƯỢNG> [GIÁ]`\n"
            "Ví dụ: `/sell_paper FPT 15` hoặc `/sell_paper HPG 100 27000`",
            parse_mode="Markdown"
        )
        return

    symbol = parts[1].upper()
    try:
        quantity = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Khối lượng phải là số nguyên dương!", parse_mode="Markdown")
        return

    price = None
    if len(parts) >= 4:
        try:
            price = float(parts[3])
        except ValueError:
            await message.answer("⚠️ Giá phải là số hợp lệ!", parse_mode="Markdown")
            return

    if price is None:
        summary = state_obj.get_summary(symbol)
        if not summary:
            await message.answer(f"⚠️ Không tìm thấy giá hiện tại cho mã `{symbol}`. Vui lòng nhập kèm giá.", parse_mode="Markdown")
            return
        price = summary.price

    order = await paper_engine.execute_sell(symbol, quantity, price)
    if order.status == OrderStatus.FILLED:
        await message.answer(
            f"✅ **KHỚP LỆNH BÁN GIẢ LẬP THÀNH CÔNG**\n"
            f"• Mã: `{symbol}`\n"
            f"• Khối lượng bán: `{quantity:,}` cp\n"
            f"• Giá khớp: `{price:,.0f} đ`\n"
            f"• Phí (0.15%): `{order.fee:,.0f} đ` | Thuế (0.10%): `{order.tax:,.0f} đ`\n"
            f"• Tiền đã cộng vào tài khoản giả lập!",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"❌ **LỆNH BÁN BỊ TỪ CHỐI**\n"
            f"Số lượng khả dụng của mã `{symbol}` không đủ `{quantity:,}` cp "
            f"(có thể do cổ phiếu vừa mua chưa qua chu kỳ thanh toán T+2).",
            parse_mode="Markdown"
        )

@router.message(Command("autotrade_paper"))
async def cmd_autotrade_paper(message: Message, paper_repo: PaperTradingRepository):
    parts = message.text.strip().split()
    account = await paper_repo.get_or_create_account()
    
    if len(parts) > 1:
        arg = parts[1].lower()
        if arg in ("on", "bat", "bật", "1", "true"):
            new_state = True
        elif arg in ("off", "tat", "tắt", "0", "false"):
            new_state = False
        else:
            await message.answer("⚠️ Vui lòng chỉ định `on` hoặc `off`. Ví dụ: `/autotrade_paper off`", parse_mode="Markdown")
            return
    else:
        # Toggle
        new_state = not account.auto_trade_enabled

    await paper_repo.set_auto_trade(new_state)
    status_str = "🟢 ĐÃ BẬT" if new_state else "🔴 ĐÃ TẮT"
    await message.answer(f"🤖 Chế độ Auto-Trade Giả lập: {status_str}", parse_mode="Markdown")

@router.message(Command("reset_paper"))
async def cmd_reset_paper(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Xác nhận Reset 5,000,000 VNĐ", callback_data="cb_reset_paper_confirm"),
        InlineKeyboardButton(text="❌ Hủy", callback_data="cb_reset_paper_cancel")
    ]])
    await message.answer(
        "⚠️ **CẢNH BÁO RESET TÀI KHOẢN GIẢ LẬP**\n"
        "Toàn bộ vị thế đang giữ và lịch sử lệnh giả lập sẽ bị xóa, "
        "số dư tiền mặt sẽ được đặt lại về **5.000.000 VNĐ**.\n"
        "Bạn có chắc chắn muốn thực hiện?",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@router.callback_query(F.data == "cb_reset_paper_confirm")
async def cb_reset_paper_confirm(callback: CallbackQuery, paper_repo: PaperTradingRepository):
    await paper_repo.reset_account(5000000.0)
    await callback.message.edit_text("✅ Tài khoản giả lập đã được Reset thành công về **5.000.000 VNĐ**!", parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "cb_reset_paper_cancel")
async def cb_reset_paper_cancel(callback: CallbackQuery):
    await callback.message.edit_text("Đã hủy thao tác Reset.", parse_mode="Markdown")
    await callback.answer()
