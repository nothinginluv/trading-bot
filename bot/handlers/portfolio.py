import logging
import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from bot.keyboards import get_positions_inline_keyboard

logger = logging.getLogger(__name__)

router = Router()

def render_positions_board(state_obj) -> str:
    if not state_obj.positions:
        return "📊 **DANH MỤC VỊ THẾ**\n──────────────────────\nHiện tại tài khoản chưa mở vị thế cổ phiếu nào."

    header = (
        f"📊 **DANH MỤC VỊ THẾ ({len(state_obj.positions)}/4 mã)**\n"
        "```text\n"
        f"{'MÃ':<5} {'KL':>6} {'GIÁ VỐN':>8} {'THỊ GIÁ':>8} {'+/- (%)':>8}\n"
        f"{'─'*38}\n"
    )
    rows = []
    total_pnl = 0.0
    for p in state_obj.positions:
        row = f"{p.symbol:<5} {p.tradeQuantity:>6,} {p.costPrice:>8,.0f} {p.marketPrice:>8,.0f} {p.pnlPercent:>+7.2f}%"
        rows.append(row)
        total_pnl += p.unrealizedPnl

    pnl_sign = "+" if total_pnl >= 0 else ""
    footer = (
        f"\n{'─'*38}\n"
        f"TỔNG LÃI/LỖ TẠM TÍNH: {pnl_sign}{total_pnl:,.0f} đ\n"
        "```\n"
        "💡 *Bấm nút bên dưới để làm mới hoặc xem phân tích hiệu suất.*"
    )
    return header + "\n".join(rows) + footer

@router.message(Command("balance"))
@router.message(lambda msg: msg.text == "💰 Số dư")
async def cmd_balance(message: Message, state_obj, client, repo):
    # Fetch or use cache
    if not state_obj.is_cache_valid(ttl_seconds=15.0) and client and state_obj.account:
        sub_id = state_obj.get_sub_account_id()
        bal = await client.get_balances(sub_id)
        state_obj.set_balance(bal)
        await repo.save_balance_snapshot(
            sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash
        )

    if not state_obj.balance:
        await message.answer("⚠️ Chưa có dữ liệu số dư từ DNSE. Hãy bấm /sync để tải lại.")
        return

    s = state_obj.balance.stock
    acc = state_obj.account
    active_sub_id = state_obj.get_sub_account_id()
    text = (
        f"👤 **Tài khoản:** {acc.name if acc else 'N/A'} (`{acc.custodyCode if acc else 'N/A'}`)\n"
        f"🏦 **Tiểu khoản:** `{active_sub_id}`\n"
        "──────────────────────\n"
        f"💵 **Tiền khả dụng:** `{s.availableCash:,.0f} đ`\n"
        f"💰 **Tổng tiền mặt:** `{s.totalCash:,.0f} đ`\n"
        f"💳 **Nợ vay margin:** `{s.totalDebt:,.0f} đ`\n"
        f"🕒 **Cập nhật:** {time.strftime('%H:%M:%S', time.localtime(state_obj.last_sync_time))}"
    )
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("positions"))
@router.message(lambda msg: msg.text == "📊 Vị thế")
async def cmd_positions(message: Message, state_obj, client):
    if not state_obj.is_cache_valid(ttl_seconds=15.0) and client and state_obj.account:
        sub_id = state_obj.get_sub_account_id()
        pos = await client.get_positions(sub_id)
        state_obj.set_positions(pos)

    text = render_positions_board(state_obj)
    kb = get_positions_inline_keyboard() if state_obj.positions else None
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "pos_refresh")
async def cb_pos_refresh(query: CallbackQuery, state_obj, client):
    if client and state_obj.account:
        try:
            sub_id = state_obj.get_sub_account_id()
            pos = await client.get_positions(sub_id)
            state_obj.set_positions(pos)
        except Exception:
            pass
    text = render_positions_board(state_obj)
    kb = get_positions_inline_keyboard() if state_obj.positions else None
    try:
        if query.message:
            await query.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass
    await query.answer("✅ Đã làm mới danh mục vị thế!")

@router.callback_query(lambda c: c.data == "pos_pnl")
async def cb_pos_pnl(query: CallbackQuery, state_obj, repo):
    try:
        from bot.handlers.portfolio import cmd_performance
        if query.message:
            await cmd_performance(query.message, repo, state_obj)
    except Exception:
        pass
    await query.answer()

@router.message(Command("sync"))
@router.message(lambda msg: msg.text == "🔄 Làm mới")
async def cmd_sync(message: Message, state_obj, client, repo):
    await message.answer("🔄 Đang đồng bộ dữ liệu mới nhất từ DNSE...")
    if not client or not state_obj.account:
        await message.answer("❌ Lỗi: Chưa kết nối được tài khoản DNSE.")
        return

    sub_id = state_obj.get_sub_account_id()
    start = time.time()
    bal = await client.get_balances(sub_id)
    pos = await client.get_positions(sub_id)
    latency = (time.time() - start) * 1000

    state_obj.latency_ms = latency
    state_obj.set_balance(bal)
    state_obj.set_positions(pos)
    await repo.save_balance_snapshot(
        sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash
    )
    await message.answer(f"✅ Đã làm mới xong ({latency:.0f}ms)! Bấm 💰 Số dư hoặc 📊 Vị thế để xem.")

@router.message(Command("pnl"))
@router.message(Command("performance"))
@router.message(lambda msg: msg.text == "📊 Hiệu suất PnL")
async def cmd_pnl(
    message: Message,
    state_obj,
    paper_engine=None,
    paper_repo=None,
    safeguards=None
):
    if not paper_repo or not paper_engine:
        await message.answer("⚠️ Dịch vụ phân tích hiệu suất chưa sẵn sàng.", parse_mode="Markdown")
        return

    current_prices = {
        sym: s.price for sym, s in state_obj.vn30_summaries.items()
    }
    account = await paper_engine.get_account_summary(current_prices)
    positions = await paper_repo.get_positions()
    stats = await paper_repo.get_performance_statistics()

    total_unrealized_pnl = 0.0
    for pos in positions:
        mkt_price = current_prices.get(pos.symbol, pos.avg_buy_price)
        total_unrealized_pnl += (mkt_price - pos.avg_buy_price) * pos.total_quantity

    total_combined_pnl = stats["total_realized_pnl"] + total_unrealized_pnl
    pnl_pct_nav = (total_combined_pnl / account.initial_balance * 100) if account.initial_balance > 0 else 0.0

    active_positions = [p for p in positions if p.total_quantity > 0]
    exposure_pct = (account.stock_value / account.nav * 100) if account.nav > 0 else 0.0

    dd_day_str = "0.00%"
    if state_obj.nav_day_start and state_obj.nav_day_start > 0:
        dd_day = ((account.nav - state_obj.nav_day_start) / state_obj.nav_day_start) * 100
        dd_day_str = f"{dd_day:+.2f}%"

    dd_week_str = "0.00%"
    if state_obj.nav_week_start and state_obj.nav_week_start > 0:
        dd_week = ((account.nav - state_obj.nav_week_start) / state_obj.nav_week_start) * 100
        dd_week_str = f"{dd_week:+.2f}%"

    circuit_breaker_status = "🟢 Bình thường"
    if safeguards and safeguards.is_read_only:
        circuit_breaker_status = f"🔴 NGẮT CẦU DAO ({safeguards.read_only_reason})"

    win_icon = "🟢" if stats["win_rate_pct"] >= 50 else ("🟡" if stats["win_rate_pct"] >= 35 else "🔴")
    pnl_icon = "🟢" if total_combined_pnl >= 0 else "🔴"

    text = (
        "📊 **BÁO CÁO HIỆU SUẤT ĐẦU TƯ (PERFORMANCE & PNL)**\n"
        "──────────────────────\n"
        f"💰 **Tổng tài sản (NAV):** `{account.nav:,.0f} đ`\n"
        f"💵 **Vốn ban đầu:** `{account.initial_balance:,.0f} đ`\n"
        f"🎯 **Phơi nhiễm danh mục:** `{exposure_pct:.1f}% NAV` (Trần: 85% NAV)\n"
        f"📂 **Quy mô danh mục:** `{len(active_positions)}/4 mã`\n"
        "──────────────────────\n"
        f"💵 **Lãi/Lỗ đã chốt (Realized):** `{stats['total_realized_pnl']:+,.0f} đ`\n"
        f"⏳ **Lãi/Lỗ tạm tính (Unrealized):** `{total_unrealized_pnl:+,.0f} đ`\n"
        f"{pnl_icon} **Tổng PnL toàn danh mục:** `{total_combined_pnl:+,.0f} đ` (`{pnl_pct_nav:+.2f}%`)\n"
        "──────────────────────\n"
        f"{win_icon} **Tỷ lệ thắng (Win Rate):** `{stats['win_rate_pct']:.1f}%` ({stats['winning_trades']}/{stats['total_trades']} lệnh chốt)\n"
        f"⚖️ **Thắng / Thua / Hòa:** `{stats['winning_trades']}` 🟢 | `{stats['losing_trades']}` 🔴 | `{stats['break_even_trades']}` ⚪\n"
        f"📈 **Hệ số Lợi nhuận (Profit Factor):** `{stats['profit_factor']:.2f}`\n"
        f"🎯 **Kỳ vọng / lệnh (Expectancy):** `{stats.get('expectancy_vnd', 0.0):+,.0f} đ`\n"
        f"⚖️ **Tỷ lệ Lãi/Lỗ TB (Payoff Ratio):** `{stats.get('win_loss_ratio', 0.0):.2f}`\n"
        f"🏆 **Lệnh lãi cao nhất:** `{stats['best_trade']:+,.0f} đ`\n"
        f"💥 **Lệnh lỗ nặng nhất:** `{stats['worst_trade']:+,.0f} đ`\n"
        "──────────────────────\n"
        "🏛️ **CHỈ SỐ RỦI RO ĐỊNH LƯỢNG (INSTITUTIONAL METRICS)**\n"
        f"• **Sharpe Ratio (Rf=5.0%):** `{stats.get('sharpe_ratio', 0.0):.2f}`\n"
        f"• **Sortino Ratio (Downside):** `{stats.get('sortino_ratio', 0.0):.2f}`\n"
        f"• **Calmar Ratio:** `{stats.get('calmar_ratio', 0.0):.2f}`\n"
        f"• **Max Drawdown Lịch sử:** `{stats.get('max_drawdown_pct', 0.0):.2f}%` (`-{stats.get('max_drawdown_vnd', 0.0):,.0f} đ`)\n"
        "──────────────────────\n"
        f"📉 **Drawdown Ngày:** `{dd_day_str}` (Cầu dao: `-3.0%`)\n"
        f"📉 **Drawdown Tuần:** `{dd_week_str}` (Cầu dao: `-7.0%`)\n"
        f"🛡️ **Trạng thái Cầu dao:** {circuit_breaker_status}\n\n"
        "👉 Gõ `/paper` xem chi tiết danh mục hoặc `/positions` xem danh mục thật."
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("reconcile"))
@router.message(Command("doichieu"))
async def cmd_reconcile(
    message: Message,
    state_obj=None,
    client=None,
    paper_repo=None,
    live_trader=None,
    safeguards=None
):
    if not live_trader or not client:
        await message.answer("⚠️ Dịch vụ LiveTrader hoặc kết nối DNSE chưa sẵn sàng.", parse_mode="Markdown")
        return

    repo = paper_repo
    if not repo:
        await message.answer("⚠️ Cơ sở dữ liệu danh mục chưa sẵn sàng.", parse_mode="Markdown")
        return

    await message.answer("🔍 Đang đối chiếu vị thế nội bộ với dữ liệu trực tiếp từ sàn DNSE...")
    try:
        await live_trader.reconcile_positions(repo, force=True)
    except Exception as e:
        logger.error(f"Error during manual reconcile: {e}")
        await message.answer(f"❌ Lỗi khi đối chiếu với DNSE: {e}")
        return

    report = live_trader.last_reconcile_report
    mode = safeguards.mode.value if safeguards else "UNKNOWN"
    current_time_str = time.strftime("%H:%M:%S %d/%m/%Y")

    if not report:
        await message.answer(
            f"🔍 **BÁO CÁO ĐỐI CHIẾU VỊ THẾ (RECONCILIATION)**\n"
            f"──────────────────────\n"
            f"⚙️ **Chế độ:** `{mode}`\n"
            f"🕒 **Thời điểm:** `{current_time_str}`\n\n"
            f"ℹ️ Không có vị thế mở nào ở cả danh mục nội bộ và tài khoản sàn DNSE.",
            parse_mode="Markdown"
        )
        return

    lines = [
        "🔍 **BÁO CÁO ĐỐI CHIẾU VỊ THẾ (RECONCILIATION)**",
        "──────────────────────",
        f"⚙️ **Chế độ:** `{mode}`",
        f"🕒 **Thời điểm:** `{current_time_str}`",
        f"📊 **Số mã kiểm tra:** `{len(report)}` mã\n"
    ]

    discrepancy_count = 0
    for item in report:
        sym = item["symbol"]
        loc_q = item["local_qty"]
        dnse_q = item["dnse_qty"]
        loc_c = item["local_cost"]
        dnse_c = item["dnse_cost"]
        disc = item["discrepancy"]
        sync = item["synchronized"]

        if disc:
            discrepancy_count += 1
            if sync:
                status_icon = "⚠️"
                status_text = "Phát hiện lệch → Đã đồng bộ theo DNSE"
            else:
                status_icon = "⚠️"
                status_text = "Phát hiện lệch (Chế độ PAPER - Không ghi đè)"
        else:
            status_icon = "🟢"
            status_text = "Khớp hoàn toàn 100%"

        lines.append(
            f"{status_icon} **{sym}**:\n"
            f"   • Nội bộ: `{loc_q:,}` cp | Giá vốn `{loc_c:,.0f} đ`\n"
            f"   • Sàn DNSE: `{dnse_q:,}` cp | Giá vốn `{dnse_c:,.0f} đ`\n"
            f"   • Trạng thái: _{status_text}_"
        )

    lines.append("──────────────────────")
    if discrepancy_count == 0:
        lines.append("✅ Tất cả vị thế đều khớp chuẩn xác với tài khoản chứng khoán DNSE.")
    else:
        lines.append(f"⚠️ Phát hiện {discrepancy_count} mã có sự sai lệch.")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("stress"))
@router.message(Command("montecarlo"))
async def cmd_stress_test(
    message: Message,
    state_obj,
    paper_engine=None,
    paper_repo=None
):
    if not paper_repo or not paper_engine:
        await message.answer("⚠️ Dịch vụ kiểm định căng thẳng chưa sẵn sàng.", parse_mode="Markdown")
        return

    current_prices = {sym: s.price for sym, s in state_obj.vn30_summaries.items()}
    account = await paper_engine.get_account_summary(current_prices)

    returns_pct = await paper_repo.get_closed_trade_returns_pct()

    from strategy.stress_test import run_monte_carlo_simulation
    mc_res = run_monte_carlo_simulation(
        trade_returns_pct=returns_pct,
        initial_capital=account.nav if account.nav > 0 else 10_000_000.0,
        num_simulations=1000,
        horizon_trades=100,
        ruin_threshold_pct=15.0
    )

    ret_median = ((mc_res.median_final_capital - mc_res.initial_capital) / mc_res.initial_capital) * 100
    ret_p95 = ((mc_res.p95_final_capital - mc_res.initial_capital) / mc_res.initial_capital) * 100
    ret_p5 = ((mc_res.p5_final_capital - mc_res.initial_capital) / mc_res.initial_capital) * 100

    rec_msg = (
        "Danh mục kiểm soát rủi ro đuôi ở mức an toàn cao, không có nguy cơ vỡ nợ hệ thống."
        if mc_res.risk_of_ruin_pct < 5.0
        else "Cần giảm đòn bẩy hoặc quy mô vị thế do rủi ro đuôi vượt ngưỡng an toàn!"
    )

    text = (
        f"🎲 **BÁO CÁO MÔ PHỎNG MONTE CARLO & STRESS-TEST ({mc_res.num_simulations:,} KỊCH BẢN)**\n"
        "──────────────────────\n"
        f"💰 **Vốn khởi điểm:** `{mc_res.initial_capital:,.0f} đ`\n"
        f"🎯 **Tầm nhìn mô phỏng:** `{mc_res.horizon_trades}` lệnh kế tiếp\n"
        "──────────────────────\n"
        f"📈 **Kịch bản Lạc quan (95th %):** `{mc_res.p95_final_capital:,.0f} đ` (`{ret_p95:+.1f}%`)\n"
        f"⚖️ **Kịch bản Kỳ vọng (Median):** `{mc_res.median_final_capital:,.0f} đ` (`{ret_median:+.1f}%`)\n"
        f"📉 **Kịch bản Bất lợi (5th %):** `{mc_res.p5_final_capital:,.0f} đ` (`{ret_p5:+.1f}%`)\n"
        "──────────────────────\n"
        "🛡️ **ĐO LƯỜNG RỦI RO ĐUÔI (TAIL RISK & STRESS):**\n"
        f"• **VaR 95% (Value at Risk):** `{mc_res.var_95_pct:.1f}% NAV`\n"
        f"• **VaR 99% (Extreme Stress):** `{mc_res.var_99_pct:.1f}% NAV`\n"
        f"• **CVaR 95% (Expected Shortfall):** `{mc_res.cvar_95_pct:.1f}% NAV`\n"
        f"• **Max Drawdown Kỳ vọng:** `{mc_res.max_drawdown_p50:.1f}%`\n"
        f"• **Max Drawdown Khủng hoảng (95th %):** `{mc_res.max_drawdown_p95:.1f}%`\n"
        f"• **Xác suất Vi phạm ngưỡng 15% (Risk of Ruin):** `{mc_res.risk_of_ruin_pct:.1f}%`\n"
        "──────────────────────\n"
        f"💡 *Khuyến nghị:* {rec_msg}"
    )
    await message.answer(text, parse_mode="Markdown")


