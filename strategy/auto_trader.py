import logging
import math
from datetime import datetime, timedelta
from typing import Optional, Callable, Awaitable, List
from strategy.paper_engine import PaperEngine
from strategy.models import OrderStatus, SignalType
from strategy.signals import scan_signals
from strategy.risk import calculate_position_size, check_exit_conditions, calculate_partial_exit_quantity
from news.event_adjuster import parse_event_adjustment
from core.state import TradingState
from core.risk_safeguards import TradingMode
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from strategy.live_trader import LiveTrader

logger = logging.getLogger(__name__)

class AutoTrader:
    """
    Background Autonomous Trading Service.
    - Settles T+2 tranches.
    - Monitors Stop Loss, Take Profit, Trailing Stop for open positions.
    - Scans VN30 for Buy signals and executes auto-trades when enabled.
    """
    def __init__(
        self,
        engine: PaperEngine,
        state: TradingState,
        notify_func: Optional[Callable[[str], Awaitable[None]]] = None,
        live_trader: Optional["LiveTrader"] = None
    ):
        self.engine = engine
        self.state = state
        self.notify_func = notify_func
        self.live_trader = live_trader

    async def process_cycle(self) -> List[str]:
        alerts: List[str] = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # 1. Settle mature T+2 tranches
        await self.engine.repo.settle_mature_tranches(today_str)

        # 1.1 Auto-cancel stale LO orders on DNSE
        if self.live_trader:
            try:
                stale_ids = await self.live_trader.auto_cancel_stale_orders(stale_timeout_minutes=15.0)
                if stale_ids:
                    alerts.append(f"⏰ Đã tự động hủy {len(stale_ids)} lệnh treo > 15 phút: {', '.join(stale_ids)}")
            except Exception as e:
                logger.error(f"Error checking stale orders in process_cycle: {e}")

        # 1.2 Reconcile live positions against DNSE if running in LIVE mode
        if self.live_trader:
            try:
                has_active_events = False
                now_dt = datetime.now()
                target_dates = [
                    (now_dt - timedelta(days=1)).strftime("%Y-%m-%d"),
                    now_dt.strftime("%Y-%m-%d"),
                    (now_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                ]
                current_positions = await self.engine.repo.get_positions()
                for p in current_positions:
                    if p.total_quantity > 0:
                        for dt_str in target_dates:
                            if self.state.is_ex_date(p.symbol, dt_str):
                                has_active_events = True
                                break
                    if has_active_events:
                        break

                rec_alerts = await self.live_trader.reconcile_positions(
                    self.engine.repo,
                    has_active_events=has_active_events
                )
                if rec_alerts:
                    alerts.extend(rec_alerts)
            except Exception as e:
                logger.error(f"Error during position reconciliation: {e}")

        # 2. Extract current prices from cache
        current_prices = {
            sym: summary.price
            for sym, summary in self.state.vn30_summaries.items()
        }
        await self.engine.update_highest_prices(current_prices)

        # 2.1 Circuit Breaker Check (Daily & Weekly Drawdown)
        account = await self.engine.get_account_summary(current_prices)
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")
        week_num = now_dt.isocalendar()[1]
        self.state.update_nav_tracker(account.nav, today_str, week_num)

        safeguards = self.live_trader.safeguards if self.live_trader else None
        if safeguards:
            tripped, cb_reason = safeguards.check_drawdown_circuit_breaker(
                account.nav, self.state.nav_day_start, self.state.nav_week_start
            )
            if tripped:
                cb_alert = (
                    f"🚨 [KÍCH HOẠT CIRCUIT BREAKER - NGẮT CẦU DAO TỰ ĐỘNG]\n"
                    f"{cb_reason}\n"
                    f"• NAV hiện tại: `{account.nav:,.0f} đ`\n"
                    f"• Hệ thống đã tự động chuyển READ_ONLY và bảo toàn vốn. Admin vui lòng gõ /resume khi sẵn sàng."
                )
                alerts.append(cb_alert)
                if self.notify_func:
                    await self.notify_func(cb_alert)
                return alerts

        # 3. Position Risk Management (SL, TP1 50%, Breakeven, TP2, Trailing Stop, Severe Crisis Exit 2B)
        positions = await self.engine.repo.get_positions()
        just_exited_symbols = set()
        for pos in positions:
            # 3.-2 Corporate Actions: Technical Adjustment on Ex-Date (ngày GDKHQ)
            ev_today = self.state.is_ex_date(pos.symbol, today_str)
            if ev_today and pos.total_quantity > 0:
                is_applied = await self.engine.repo.is_adjustment_applied(ev_today.id)
                if not is_applied:
                    adj = parse_event_adjustment(ev_today)
                    if adj:
                        old_qty = pos.total_quantity
                        old_avg = pos.avg_buy_price
                        old_highest = pos.highest_price
                        fractional_share = 0.0

                        if adj.multiplier > 1.0:
                            raw_new_qty = old_qty * adj.multiplier
                            new_total_qty = math.floor(raw_new_qty)
                            fractional_share = raw_new_qty - new_total_qty
                            if fractional_share > 0:
                                logger.info(f"Phần dư lẻ cổ phiếu {pos.symbol}: {fractional_share:.4f} cp (chi trả bằng tiền mặt theo quy định HOSE).")
                            new_avail_qty = pos.available_quantity
                            new_avg = self.engine.round_to_hose_tick(old_avg / adj.multiplier)
                            new_highest = self.engine.round_to_hose_tick(old_highest / adj.multiplier) if old_highest > 0 else 0.0
                            cash_delta = 0.0
                        elif adj.cash_per_share > 0:
                            new_total_qty = old_qty
                            new_avail_qty = pos.available_quantity
                            new_avg = self.engine.round_to_hose_tick(max(10.0, old_avg - adj.cash_per_share))
                            new_highest = self.engine.round_to_hose_tick(max(10.0, old_highest - adj.cash_per_share)) if old_highest > 0 else 0.0
                            cash_delta = adj.cash_per_share * old_qty
                        else:
                            new_total_qty, new_avail_qty, new_avg, new_highest, cash_delta = old_qty, pos.available_quantity, old_avg, old_highest, 0.0

                        await self.engine.repo.apply_position_adjustment(
                            symbol=pos.symbol,
                            new_total_qty=new_total_qty,
                            new_available_qty=new_avail_qty,
                            new_avg_price=new_avg,
                            new_highest_price=new_highest,
                            cash_delta=cash_delta
                        )
                        await self.engine.repo.record_position_adjustment(
                            event_id=ev_today.id,
                            symbol=pos.symbol,
                            adjustment_type=adj.adjustment_type,
                            ratio=adj.ratio,
                            cash_per_share=adj.cash_per_share,
                            old_quantity=old_qty,
                            new_quantity=new_total_qty,
                            old_avg_price=old_avg,
                            new_avg_price=new_avg,
                            old_highest_price=old_highest,
                            new_highest_price=new_highest,
                            applied_date=today_str
                        )

                        # Update in-memory pos object for subsequent checks in this cycle!
                        pos.total_quantity = new_total_qty
                        pos.available_quantity = new_avail_qty
                        pos.avg_buy_price = new_avg
                        pos.highest_price = new_highest

                        frac_line = f"• Phần dư lẻ: `{fractional_share:.2f}` cp (chi trả bằng tiền mặt theo quy định HOSE)\n" if fractional_share > 0 else ""
                        adj_alert = (
                            f"🔔 [ĐIỀU CHỈNH KỸ THUẬT NGÀY GDKHQ] {pos.symbol}:\n"
                            f"• Sự kiện: {ev_today.content}\n"
                            f"• Chi tiết: {adj.description}\n"
                            f"• Khối lượng: `{old_qty:,}` cp ➔ `{new_total_qty:,}` cp\n"
                            f"{frac_line}"
                            f"• Giá vốn: `{old_avg:,.0f}` đ ➔ `{new_avg:,.0f}` đ\n"
                            f"• Đỉnh Trailing: `{old_highest:,.0f}` đ ➔ `{new_highest:,.0f}` đ\n"
                            f"• Các ngưỡng SL/TP và Trailing Stop đã tự động co giãn theo tỷ lệ kỹ thuật."
                        )
                        alerts.append(adj_alert)
                        if self.notify_func:
                            await self.notify_func(adj_alert)

            cur_price = current_prices.get(pos.symbol, pos.avg_buy_price)
            if cur_price > pos.highest_price:
                pos.highest_price = cur_price
                await self.engine.repo.update_highest_price(pos.symbol, cur_price)

            summary = self.state.vn30_summaries.get(pos.symbol)
            rsi = summary.rsi14 if summary else None
            atr = summary.atr14 if summary else None

            # 3.-1 Corporate Events: Advance warning if GDKHQ tomorrow
            tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            ev_tomorrow = self.state.is_ex_date(pos.symbol, tomorrow_str)
            if ev_tomorrow and pos.total_quantity > 0:
                ev_alert = (
                    f"📢 [CẢNH BÁO SỰ KIỆN GDKHQ NGÀY MAI] {pos.symbol}:\n"
                    f"• Vị thế nắm giữ: `{pos.total_quantity:,}` cp\n"
                    f"• Sự kiện: {ev_tomorrow.content}\n"
                    f"• Chú ý: Giá tham chiếu ngày mai sẽ bị điều chỉnh kỹ thuật."
                )
                alerts.append(ev_alert)
                if self.notify_func:
                    await self.notify_func(ev_alert)

            # 3.0 Option 2B: Severe Crisis Emergency Exit (Arrest, Fraud, Trading Halt)
            is_crisis, crisis_title = self.state.is_symbol_in_crisis(pos.symbol)
            if is_crisis:
                if pos.available_quantity > 0:
                    order = await self.engine.execute_sell(pos.symbol, pos.available_quantity, cur_price)
                    if order.status == OrderStatus.FILLED:
                        just_exited_symbols.add(pos.symbol)
                        alert = (
                            f"🚨 [KHẨN CẤP: BÁN THOÁT HÀNG DO TIN CỰC XẤU (2B)] {pos.symbol}\n"
                            f"- Khối lượng: {order.quantity:,} cp\n"
                            f"- Giá khớp: {cur_price:,.0f} đ\n"
                            f"- Lý do: {crisis_title}"
                        )
                        alerts.append(alert)
                        if self.notify_func:
                            await self.notify_func(alert)

                    if self.live_trader and self.live_trader.safeguards.mode in (TradingMode.LIVE_CONFIRM, TradingMode.LIVE_AUTO):
                        await self.live_trader.route_order(
                            symbol=pos.symbol,
                            side="NS",
                            quantity=pos.available_quantity,
                            price=cur_price,
                            reference_price=cur_price,
                            strategy_name="CRISIS_EXIT",
                            reason=f"Tin cực xấu: {crisis_title}"
                        )
                    continue
                else:
                    alert = (
                        f"🚨 [CẢNH BÁO NGUY HIỂM] {pos.symbol} xuất hiện tin cực xấu ({crisis_title})\n"
                        f"nhưng cổ phiếu đang chờ T+2 về tài khoản!"
                    )
                    alerts.append(alert)
                    if self.notify_func:
                        await self.notify_func(alert)
                    continue
            
            decision = check_exit_conditions(pos, cur_price, rsi, atr=atr)
            if decision.should_exit:
                if pos.available_quantity > 0:
                    if decision.is_tp1:
                        sell_qty = calculate_partial_exit_quantity(pos.available_quantity, decision.sell_ratio)
                    else:
                        sell_qty = pos.available_quantity

                    if sell_qty > 0:
                        order = await self.engine.execute_sell(pos.symbol, sell_qty, cur_price)
                        if order.status == OrderStatus.FILLED:
                            if decision.is_tp1:
                                await self.engine.repo.set_position_tp1_taken(pos.symbol, True)
                                action_tag = "CHỐT LỜI 50% (TP1)"
                            else:
                                just_exited_symbols.add(pos.symbol)
                                action_tag = "BÁN TOÀN BỘ"

                            # Check if negative news accompanies technical exit -> amplify notice
                            sym_sentiment = self.state.get_symbol_sentiment(pos.symbol)
                            news_note = f" (Kèm tin tức xấu: {sym_sentiment:+.2f})" if sym_sentiment <= -0.25 else ""

                            alert = (
                                f"🔔 [AUTO-TRADE {action_tag} GIẢ LẬP] {pos.symbol}{news_note}\n"
                                f"- Khối lượng: {order.quantity:,} cp\n"
                                f"- Giá khớp: {cur_price:,.0f} đ\n"
                                f"- Lý do: {decision.reason}"
                            )
                            alerts.append(alert)
                            if self.notify_func:
                                await self.notify_func(alert)

                        if self.live_trader and self.live_trader.safeguards.mode in (TradingMode.LIVE_CONFIRM, TradingMode.LIVE_AUTO):
                            await self.live_trader.route_order(
                                symbol=pos.symbol,
                                side="NS",
                                quantity=sell_qty,
                                price=cur_price,
                                reference_price=cur_price,
                                strategy_name=decision.exit_type.value if decision.exit_type else "EXIT",
                                reason=decision.reason
                            )
                else:
                    alert = (
                        f"⚠️ [CẢNH BÁO VI PHẠM] {pos.symbol} thỏa mãn bán ({decision.reason})\n"
                        f"nhưng cổ phiếu đang chờ về tài khoản theo quy định T+2."
                    )
                    alerts.append(alert)
                    if self.notify_func:
                        await self.notify_func(alert)

        # 4. Auto-Trade Buy Entries (if auto_trade_enabled)
        account = await self.engine.get_account_summary(current_prices)
        if account.auto_trade_enabled:
            # Market Regime Filter: Gate buys if benchmark is BEARISH
            if self.state.market_regime == "BEARISH":
                return alerts
            # Maximum concurrent symbols in portfolio (default 4)
            max_slots = safeguards.max_concurrent_positions if safeguards else 4
            active_positions = [p for p in (await self.engine.repo.get_positions()) if p.total_quantity > 0]
            held_symbols = {p.symbol for p in active_positions} | just_exited_symbols
            
            if len(held_symbols) < max_slots:
                candidate_signals = []
                for sym, summary in self.state.vn30_summaries.items():
                    if sym in held_symbols:
                        continue
                    series = self.state.vn30_candles.get(sym)
                    if not series:
                        continue
                    series_15m = self.state.get_candles(sym, resolution="15")
                    summary_15m = self.state.get_summary(sym, resolution="15")
                    sig = scan_signals(series, summary, series_15m=series_15m, summary_15m=summary_15m)
                    if sig and sig.signal_type == SignalType.BUY:
                        # 4.0 Corporate Actions Filter: VETO buy if today is Ex-Date (GDKHQ)
                        today_str = datetime.now().strftime("%Y-%m-%d")
                        ex_event = self.state.is_ex_date(sym, today_str)
                        if ex_event:
                            veto_ex_msg = (
                                f"🛑 [TỪ CHỐI MUA DO NGÀY GDKHQ] {sym}: Đạt tín hiệu kỹ thuật "
                                f"nhưng hôm nay là Ngày Giao Dịch Không Hưởng Quyền ({ex_event.content}). "
                                f"Thị giá bị điều chỉnh kỹ thuật, tự động hủy mua để bảo vệ vốn."
                            )
                            alerts.append(veto_ex_msg)
                            if self.notify_func:
                                await self.notify_func(veto_ex_msg)
                            continue

                        # 4.0.1 Dilution check from upcoming events (ESOP, large additional listing)
                        sym_events = self.state.get_symbol_events(sym)
                        has_dilution = any(ev.event_type in ("ESOP", "ISSUE_ADDITIONAL", "LISTING") for ev in sym_events)
                        if has_dilution:
                            sig.confidence = max(0.1, sig.confidence - 0.15)
                            sig.reason += " | ⚠️ Cảnh báo pha loãng/niêm yết bổ sung (-0.15 điểm tin cậy)"

                        # 4.1 News Sentiment Filter (Combo Indicator + News)
                        sym_sentiment = self.state.get_symbol_sentiment(sym)
                        
                        # VETO: if bad news present (sentiment <= -0.25), abort buy!
                        if sym_sentiment <= -0.25:
                            veto_msg = (
                                f"🛑 [TỪ CHỐI MUA DO TIN XẤU] {sym}: Đạt tín hiệu kỹ thuật "
                                f"nhưng bị phủ quyết do tin tức tiêu cực (Điểm tin: {sym_sentiment:+.2f})."
                            )
                            alerts.append(veto_msg)
                            if self.notify_func:
                                await self.notify_func(veto_msg)
                            continue

                        # BOOST: if positive news present (sentiment >= +0.25), boost confidence!
                        if sym_sentiment >= 0.25:
                            sig.confidence = min(1.0, sig.confidence + 0.15)
                            sig.reason += f" | 📰 Tin tức tích cực bổ trợ (Điểm: {sym_sentiment:+.2f})"

                        candidate_signals.append(sig)
                
                if candidate_signals:
                    # Pick highest confidence signal satisfying sector concentration limit
                    candidate_signals.sort(key=lambda s: s.confidence, reverse=True)
                    top_signal = None

                    for cand in candidate_signals:
                        if safeguards:
                            valid_sec, sec_msg = safeguards.validate_sector_concentration(cand.symbol, list(held_symbols))
                            if not valid_sec:
                                sec_alert = f"🛑 [TỪ CHỐI MUA DO TẬP TRUNG NGÀNH] {cand.symbol}: {sec_msg}"
                                alerts.append(sec_alert)
                                if self.notify_func:
                                    await self.notify_func(sec_alert)
                                continue
                        top_signal = cand
                        break

                    if not top_signal:
                        return alerts
                    
                    # 2-Layer Position Sizing (ATR-Risk + 25% NAV Hard Cap & 85% Exposure Cap)
                    top_summary = self.state.vn30_summaries.get(top_signal.symbol)
                    top_atr = top_summary.atr14 if top_summary else None
                    risk_pct = safeguards.risk_per_trade_pct if safeguards else 0.015
                    max_pos_pct = safeguards.max_position_pct if safeguards else 0.25
                    exposure_cap = safeguards.max_portfolio_exposure_pct if safeguards else 0.85

                    current_exposure = sum(
                        p.total_quantity * current_prices.get(p.symbol, p.avg_buy_price)
                        for p in active_positions
                    )

                    qty = calculate_position_size(
                        available_cash=account.cash_balance,
                        nav=account.nav,
                        price=top_signal.price,
                        atr=top_atr,
                        risk_per_trade_pct=risk_pct,
                        stop_mult=1.5,
                        max_pos_pct=max_pos_pct,
                        current_open_exposure=current_exposure,
                        portfolio_exposure_cap=exposure_cap
                    )

                    # Boundary condition: reject if final_qty < 1
                    if qty < 1:
                        reject_msg = (
                            f"🛑 [TỪ CHỐI MUA] {top_signal.symbol}: Vốn còn lại hoặc hạn mức phơi nhiễm "
                            f"không đủ để mở vị thế tối thiểu (final_qty < 1)."
                        )
                        alerts.append(reject_msg)
                        if self.notify_func:
                            await self.notify_func(reject_msg)
                        return alerts

                    # Validate Portfolio Exposure Cap & Position Cap
                    if safeguards:
                        valid_pos, pos_msg = safeguards.validate_position_size(qty * top_signal.price, account.nav)
                        if not valid_pos:
                            pos_alert = f"🛑 [TỪ CHỐI MUA DO TRẦN VỊ THẾ] {top_signal.symbol}: {pos_msg}"
                            alerts.append(pos_alert)
                            if self.notify_func:
                                await self.notify_func(pos_alert)
                            return alerts

                        valid_exp, exp_msg = safeguards.validate_portfolio_exposure(
                            current_exposure, qty * top_signal.price, account.nav
                        )
                        if not valid_exp:
                            exp_alert = f"🛑 [TỪ CHỐI MUA DO TRẦN PHƠI NHIỄM] {top_signal.symbol}: {exp_msg}"
                            alerts.append(exp_alert)
                            if self.notify_func:
                                await self.notify_func(exp_alert)
                            return alerts

                    if qty >= 1:
                        order = await self.engine.execute_buy(top_signal.symbol, qty, top_signal.price)
                        lot_type = "Lô chẵn" if qty >= 100 else "Lô lẻ"
                        if order.status == OrderStatus.FILLED:
                            alert = (
                                f"🚀 [AUTO-TRADE MUA GIẢ LẬP] {top_signal.symbol}\n"
                                f"- Chiến lược: {top_signal.strategy.value}\n"
                                f"- Khối lượng: {qty:,} cp ({lot_type})\n"
                                f"- Giá khớp: {top_signal.price:,.0f} đ\n"
                                f"- Lý do: {top_signal.reason}"
                            )
                            alerts.append(alert)
                            if self.notify_func:
                                await self.notify_func(alert)

                        if self.live_trader and self.live_trader.safeguards.mode in (TradingMode.LIVE_CONFIRM, TradingMode.LIVE_AUTO):
                            live_res = await self.live_trader.route_order(
                                symbol=top_signal.symbol,
                                side="NB",
                                quantity=qty,
                                price=top_signal.price,
                                reference_price=top_signal.price,
                                strategy_name=top_signal.strategy.value,
                                reason=top_signal.reason
                            )
                            if live_res.get("status") == "PENDING_CONFIRMATION":
                                confirm_id = live_res["confirm_id"]
                                alert = (
                                    f"⚠️ [YÊU CẦU XÁC NHẬN LỆNH THẬT]\n"
                                    f"• Mã: {top_signal.symbol} | Mua: {qty:,} cp | Giá: {top_signal.price:,.0f} đ\n"
                                    f"• Mã xác nhận: `{confirm_id}`\n"
                                    f"• Hãy xác nhận trên bot để gửi lệnh lên sàn HOSE!"
                                )
                                alerts.append(alert)
                                if self.notify_func:
                                    await self.notify_func(alert)
                            elif live_res.get("status") == "EXECUTED":
                                alerts.append(f"🔥 [LỆNH THẬT ĐÃ ĐƯỢC GỬI SÀN] {top_signal.symbol} {qty:,} cp @ {top_signal.price:,.0f}")

        return alerts
