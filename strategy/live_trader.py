import uuid
import logging
from typing import Optional, Callable, Awaitable, Dict, Any
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

    def cancel_pending_confirmation(self, confirm_id: str) -> bool:
        return self.pending_confirmations.pop(confirm_id, None) is not None
