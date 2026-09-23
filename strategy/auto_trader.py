from datetime import datetime
from typing import Optional, Callable, Awaitable, List
from strategy.paper_engine import PaperEngine
from strategy.models import OrderStatus, SignalType
from strategy.signals import scan_signals
from strategy.risk import calculate_position_size, check_exit_conditions
from core.state import TradingState
from core.risk_safeguards import TradingMode
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from strategy.live_trader import LiveTrader

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

        # 2. Extract current prices from cache
        current_prices = {
            sym: summary.price
            for sym, summary in self.state.vn30_summaries.items()
        }
        await self.engine.update_highest_prices(current_prices)

        # 3. Position Risk Management (SL, TP, Trailing Stop)
        positions = await self.engine.repo.get_positions()
        just_exited_symbols = set()
        for pos in positions:
            cur_price = current_prices.get(pos.symbol, pos.avg_buy_price)
            summary = self.state.vn30_summaries.get(pos.symbol)
            rsi = summary.rsi14 if summary else None
            
            should_exit, reason = check_exit_conditions(pos, cur_price, rsi)
            if should_exit:
                if pos.available_quantity > 0:
                    order = await self.engine.execute_sell(pos.symbol, pos.available_quantity, cur_price)
                    if order.status == OrderStatus.FILLED:
                        just_exited_symbols.add(pos.symbol)
                        alert = (
                            f"🔔 [AUTO-TRADE BÁN GIẢ LẬP] {pos.symbol}\n"
                            f"- Khối lượng: {order.quantity:,} cp\n"
                            f"- Giá khớp: {cur_price:,.0f} đ\n"
                            f"- Lý do: {reason}"
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
                            strategy_name="EXIT",
                            reason=reason
                        )
                else:
                    alert = (
                        f"⚠️ [CẢNH BÁO VI PHẠM] {pos.symbol} thỏa mãn bán ({reason})\n"
                        f"nhưng cổ phiếu đang chờ về tài khoản theo quy định T+2."
                    )
                    alerts.append(alert)
                    if self.notify_func:
                        await self.notify_func(alert)

        # 4. Auto-Trade Buy Entries (if auto_trade_enabled)
        account = await self.engine.get_account_summary(current_prices)
        if account.auto_trade_enabled:
            # Maximum 3 concurrent symbols in portfolio
            active_positions = [p for p in (await self.engine.repo.get_positions()) if p.total_quantity > 0]
            held_symbols = {p.symbol for p in active_positions} | just_exited_symbols
            
            if len(held_symbols) < 3:
                candidate_signals = []
                for sym, summary in self.state.vn30_summaries.items():
                    if sym in held_symbols:
                        continue
                    series = self.state.vn30_candles.get(sym)
                    if not series:
                        continue
                    sig = scan_signals(series, summary)
                    if sig and sig.signal_type == SignalType.BUY:
                        candidate_signals.append(sig)
                
                if candidate_signals:
                    # Pick highest confidence signal
                    candidate_signals.sort(key=lambda s: s.confidence, reverse=True)
                    top_signal = candidate_signals[0]
                    
                    qty = calculate_position_size(account.cash_balance, account.nav, top_signal.price)
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
