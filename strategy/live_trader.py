import uuid
import time
import logging
from typing import Optional, Callable, Awaitable, Dict, Any, List
from datetime import datetime
from core.risk_safeguards import RiskSafeguards, TradingMode

logger = logging.getLogger(__name__)

class LiveTrader:
    """
    Live Order Dispatcher and Safety Orchestrator.
    Routes trading signals between Paper, Live Confirm, and Live Auto
    according to Risk Safeguards and active trading mode.
    """
    def __init__(
        self,
        client: Any,
        safeguards: RiskSafeguards,
        account_no: str,
        notify_func: Optional[Callable[[str], Awaitable[None]]] = None,
        trading_token: Optional[str] = None
    ):
        self.client = client
        self.safeguards = safeguards
        self.account_no = account_no
        self.notify_func = notify_func
        self.trading_token = trading_token
        self.pending_confirmations: Dict[str, dict] = {}
        self.tracked_live_orders: Dict[str, dict] = {}
        self.last_reconcile_time: float = 0.0
        self.last_reconcile_report: List[dict] = []

    def set_trading_token(self, token: str):
        self.trading_token = token

    async def route_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        reference_price: Optional[float] = None,
        strategy_name: str = "",
        reason: str = ""
    ) -> dict:
        symbol = symbol.upper()
        side = side.upper()

        # 1. Check if in PAPER mode
        if self.safeguards.mode == TradingMode.PAPER:
            return {
                "status": "PAPER_MODE",
                "message": "Hệ thống đang chạy chế độ Giả lập (Paper Trading). Không gửi lệnh thật."
            }

        # 2. Risk Safeguards Validation
        valid, msg = self.safeguards.validate_order(symbol, side, quantity, price, reference_price)
        if not valid:
            logger.warning(f"Order rejected by safeguards: {symbol} {side} - {msg}")
            if self.notify_func:
                await self.notify_func(f"🛑 [TỪ CHỐI LỆNH THẬT] {symbol} {side} {quantity:,} cp: {msg}")
            return {
                "status": "REJECTED",
                "reason": msg
            }

        # 3. LIVE_CONFIRM Mode
        if self.safeguards.mode == TradingMode.LIVE_CONFIRM:
            confirm_id = uuid.uuid4().hex[:8]
            data = {
                "confirm_id": confirm_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "strategy_name": strategy_name,
                "reason": reason,
                "created_at": datetime.now()
            }
            self.pending_confirmations[confirm_id] = data
            logger.info(f"Order pending manual confirmation: {confirm_id} - {symbol} {side}")
            return {
                "status": "PENDING_CONFIRMATION",
                "confirm_id": confirm_id,
                "data": data
            }

        # 4. LIVE_AUTO Mode
        if self.safeguards.mode == TradingMode.LIVE_AUTO:
            res = await self.client.place_order(
                account_no=self.account_no,
                symbol=symbol,
                side=side,
                order_type="LO",
                quantity=quantity,
                price=price,
                trading_token=self.trading_token
            )
            if res.success:
                self.safeguards.record_order_sent()
                if res.order_id:
                    self.track_live_order(res.order_id, symbol, side, quantity, price)
                lot_type = "Lô chẵn" if quantity >= 100 else "Lô lẻ"
                action_text = "MUA" if side == "NB" else "BÁN"
                alert = (
                    f"🔥 [ĐẶT LỆNH THẬT THÀNH CÔNG] {symbol}\n"
                    f"• Loại lệnh: {action_text} ({lot_type})\n"
                    f"• Khối lượng: `{quantity:,}` cp | Giá: `{price:,.0f} đ`\n"
                    f"• Mã lệnh DNSE: `{res.order_id}`\n"
                    f"• Lý do: {reason or strategy_name}"
                )
                if self.notify_func:
                    await self.notify_func(alert)
                return {
                    "status": "EXECUTED",
                    "order_id": res.order_id,
                    "message": res.message
                }
            else:
                alert = f"❌ [ĐẶT LỆNH THẬT THẤT BẠI] {symbol}: {res.message}"
                if self.notify_func:
                    await self.notify_func(alert)
                return {
                    "status": "FAILED",
                    "message": res.message
                }

        return {"status": "UNKNOWN_MODE"}

    async def confirm_pending_order(self, confirm_id: str) -> dict:
        data = self.pending_confirmations.pop(confirm_id, None)
        if not data:
            return {"status": "NOT_FOUND", "message": "Lệnh không tồn tại hoặc đã hết hạn"}

        # Validate safeguards again before execution
        valid, msg = self.safeguards.validate_order(
            data["symbol"], data["side"], data["quantity"], data["price"]
        )
        if not valid:
            return {"status": "REJECTED", "reason": msg}

        res = await self.client.place_order(
            account_no=self.account_no,
            symbol=data["symbol"],
            side=data["side"],
            order_type="LO",
            quantity=data["quantity"],
            price=data["price"],
            trading_token=self.trading_token
        )
        if res.success:
            self.safeguards.record_order_sent()
            if res.order_id:
                self.track_live_order(res.order_id, data["symbol"], data["side"], data["quantity"], data["price"])
            lot_type = "Lô chẵn" if data["quantity"] >= 100 else "Lô lẻ"
            action_text = "MUA" if data["side"] == "NB" else "BÁN"
            alert = (
                f"🔥 [XÁC NHẬN ĐẶT LỆNH THẬT] {data['symbol']}\n"
                f"• Loại lệnh: {action_text} ({lot_type})\n"
                f"• Khối lượng: `{data['quantity']:,}` cp | Giá: `{data['price']:,.0f} đ`\n"
                f"• Mã lệnh DNSE: `{res.order_id}`\n"
                f"• Trạng thái: Đã gửi lên sàn HOSE!"
            )
            if self.notify_func:
                await self.notify_func(alert)
            return {
                "status": "EXECUTED",
                "order_id": res.order_id,
                "message": res.message
            }
        else:
            return {
                "status": "FAILED",
                "message": res.message
            }

    def track_live_order(
        self,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        created_at: Optional[float] = None
    ):
        if not order_id:
            return
        self.tracked_live_orders[str(order_id)] = {
            "order_id": str(order_id),
            "symbol": symbol.upper(),
            "side": side.upper(),
            "quantity": quantity,
            "price": price,
            "created_at": created_at if created_at is not None else time.time()
        }
        logger.info(f"Tracking live LO order {order_id} for {symbol} ({side} {quantity} @ {price:,.0f} đ)")

    async def auto_cancel_stale_orders(self, stale_timeout_minutes: float = 15.0) -> List[str]:
        """
        Scans active LO orders. If an order has been pending/unfilled for > stale_timeout_minutes,
        automatically triggers cancel_order on DNSE to free up portfolio exposure and prevent
        getting filled late when the market trend has reversed.
        """
        now = time.time()
        timeout_seconds = stale_timeout_minutes * 60
        cancelled_order_ids: List[str] = []

        try:
            live_orders = await self.client.get_orders(self.account_no)
        except Exception as e:
            logger.error(f"Error fetching live orders for stale cancellation check: {e}")
            return []

        active_statuses = {"NEW", "PENDING_NEW", "WAITING", "PENDING", "QUEUED", "CONFIRMED"}

        def _parse_time(time_val: Any) -> Optional[float]:
            if not time_val:
                return None
            if isinstance(time_val, (int, float)):
                return time_val / 1000.0 if time_val > 1e11 else float(time_val)
            if isinstance(time_val, str):
                try:
                    num = float(time_val)
                    return num / 1000.0 if num > 1e11 else num
                except ValueError:
                    pass
                try:
                    dt = datetime.fromisoformat(time_val.replace("Z", "+00:00"))
                    return dt.timestamp()
                except Exception:
                    pass
            return None

        for ord in live_orders:
            # If not in active statuses (e.g. FILLED, CANCELLED, REJECTED), remove from tracking
            if ord.orderStatus.upper() not in active_statuses:
                if str(ord.id) in self.tracked_live_orders:
                    del self.tracked_live_orders[str(ord.id)]
                continue

            order_age: Optional[float] = None
            if str(ord.id) in self.tracked_live_orders:
                order_age = now - self.tracked_live_orders[str(ord.id)]["created_at"]
            elif ord.createdTime:
                t_val = _parse_time(ord.createdTime)
                if t_val:
                    order_age = now - t_val

            if order_age is not None and order_age >= timeout_seconds:
                minutes_open = order_age / 60
                logger.info(f"Order {ord.id} ({ord.symbol}) is stale ({minutes_open:.1f}m >= {stale_timeout_minutes:.0f}m). Auto-cancelling...")
                try:
                    cancel_res = await self.client.cancel_order(self.account_no, str(ord.id))
                    success = cancel_res.get("success", False) if isinstance(cancel_res, dict) else bool(cancel_res)
                    if success:
                        cancelled_order_ids.append(str(ord.id))
                        if str(ord.id) in self.tracked_live_orders:
                            del self.tracked_live_orders[str(ord.id)]

                        alert_msg = (
                            f"⏰ **[TỰ ĐỘNG HỦY LỆNH TREO (STALE ORDER)]**\n"
                            f"──────────────────────\n"
                            f"• Lệnh LO `{ord.symbol}` ({ord.side}) `{ord.quantity:,}` cp @ `{ord.price:,.0f} đ`\n"
                            f"• Thời gian treo: `{minutes_open:.1f}` phút (vượt ngưỡng {stale_timeout_minutes:.0f} phút)\n"
                            f"• Mã lệnh: `{ord.id}`\n"
                            f"• Mục đích: Giải phóng hạn mức phơi nhiễm danh mục, tránh khớp khi xu hướng đảo chiều."
                        )
                        if self.notify_func:
                            await self.notify_func(alert_msg)
                    else:
                        logger.warning(f"Failed to auto-cancel stale order {ord.id}: {cancel_res}")
                except Exception as e:
                    logger.error(f"Error auto-cancelling stale order {ord.id}: {e}")

        return cancelled_order_ids

    async def reconcile_positions(
        self,
        repo: Any,
        force: bool = False,
        has_active_events: bool = False
    ) -> List[str]:
        """
        Reconciles locally tracked positions against actual DNSE OpenAPI positions.
        Adaptive interval:
        - 30 minutes (1800s) on active corporate action days (Ex-Date ± 1 day).
        - 60 minutes (3600s) on normal trading days.
        - force=True bypasses the interval check (e.g. manual /reconcile command).

        Prioritizes DNSE data when discrepancies in quantity or cost basis occur,
        and alerts Admin via Telegram.
        """
        # If not forced, check mode and adaptive interval
        if not force:
            if self.safeguards.mode not in (TradingMode.LIVE_CONFIRM, TradingMode.LIVE_AUTO):
                return []
            interval = 1800.0 if has_active_events else 3600.0
            if time.time() - self.last_reconcile_time < interval:
                return []

        alerts: List[str] = []
        try:
            dnse_positions = await self.client.get_positions(self.account_no)
        except Exception as e:
            logger.error(f"Error fetching DNSE positions during reconciliation: {e}")
            return []

        self.last_reconcile_time = time.time()
        dnse_map = {p.symbol.upper(): p for p in dnse_positions}
        local_positions = await repo.get_positions()
        local_map = {p.symbol.upper(): p for p in local_positions if p.total_quantity > 0}

        all_symbols = sorted(set(list(dnse_map.keys()) + list(local_map.keys())))
        report: List[dict] = []
        is_live_mode = self.safeguards.mode in (TradingMode.LIVE_CONFIRM, TradingMode.LIVE_AUTO)

        for sym in all_symbols:
            local_pos = local_map.get(sym)
            p_dnse = dnse_map.get(sym)

            local_qty = local_pos.total_quantity if local_pos else 0
            local_avail = local_pos.available_quantity if local_pos else 0
            local_cost = local_pos.avg_buy_price if local_pos else 0.0
            local_highest = local_pos.highest_price if local_pos else 0.0
            local_tp1 = local_pos.tp1_taken if local_pos else False

            dnse_qty = (p_dnse.openQuantity if p_dnse.openQuantity > 0 else p_dnse.tradeQuantity) if p_dnse else 0
            dnse_avail = p_dnse.tradeQuantity if p_dnse else 0
            dnse_cost = p_dnse.costPrice if p_dnse else 0.0

            qty_diff = abs(local_qty - dnse_qty)
            price_diff_pct = (
                abs(local_cost - dnse_cost) / local_cost
                if local_cost > 0 and dnse_cost > 0
                else (1.0 if (local_cost > 0 or dnse_cost > 0) and (local_qty > 0 or dnse_qty > 0) else 0.0)
            )

            is_discrepancy = (qty_diff > 0 or price_diff_pct > 0.005)
            is_sync = False

            # Only synchronize positions currently tracked/held by the bot to prevent hijacking external manual holdings
            if is_discrepancy and is_live_mode and local_pos and local_pos.total_quantity > 0:
                logger.warning(
                    f"Reconciliation discrepancy for {sym}: local (qty={local_qty}, cost={local_cost}) "
                    f"vs DNSE (qty={dnse_qty}, cost={dnse_cost}). Synchronizing to DNSE..."
                )
                new_highest = max(local_highest, dnse_cost) if dnse_cost > 0 else local_highest
                await repo.upsert_position(
                    symbol=sym,
                    total_qty=dnse_qty,
                    available_qty=dnse_avail,
                    avg_price=dnse_cost,
                    highest_price=new_highest,
                    tp1_taken=local_tp1
                )
                is_sync = True
                alert = (
                    f"⚠️ **[ĐỐI CHIẾU VỊ THẾ SÀN DNSE (RECONCILIATION)]**\n"
                    f"──────────────────────\n"
                    f"Phát hiện chênh lệch vị thế `{sym}` giữa dữ liệu nội bộ và sàn DNSE:\n"
                    f"• Nội bộ: Khối lượng `{local_qty:,}` cp | Giá vốn `{local_cost:,.0f} đ`\n"
                    f"• Sàn DNSE: Khối lượng `{dnse_qty:,}` cp | Giá vốn `{dnse_cost:,.0f} đ`\n"
                    f"• Trạng thái: Đã tự động đồng bộ theo số liệu chính thức của DNSE để đảm bảo lệnh thật an toàn."
                )
                if local_pos:
                    local_pos.total_quantity = dnse_qty
                    local_pos.available_quantity = dnse_avail
                    local_pos.avg_buy_price = dnse_cost
                    local_pos.highest_price = new_highest

                alerts.append(alert)
                if self.notify_func:
                    await self.notify_func(alert)

            report.append({
                "symbol": sym,
                "local_qty": local_qty,
                "dnse_qty": dnse_qty,
                "local_cost": local_cost,
                "dnse_cost": dnse_cost,
                "discrepancy": is_discrepancy,
                "synchronized": is_sync
            })

        self.last_reconcile_report = report
        return alerts

    def cancel_pending_confirmation(self, confirm_id: str) -> bool:
        return self.pending_confirmations.pop(confirm_id, None) is not None

