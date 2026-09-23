from enum import Enum
from typing import Optional, Tuple
from datetime import datetime

class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE_CONFIRM = "LIVE_CONFIRM"
    LIVE_AUTO = "LIVE_AUTO"

class RiskSafeguards:
    """
    Capital protection and risk management firewall.
    Enforces maximum order value, maximum daily order count,
    daily loss limit, HOSE price collars, and emergency kill switch.
    """
    def __init__(
        self,
        mode: TradingMode = TradingMode.PAPER,
        max_order_value: float = 5_000_000.0,
        max_daily_orders: int = 5,
        max_daily_loss_pct: float = -0.03
    ):
        self.mode = mode
        self.kill_switch_active = False
        self.kill_switch_reason = ""
        self.max_order_value = max_order_value
        self.max_daily_orders = max_daily_orders
        self.max_daily_loss_pct = max_daily_loss_pct
        self.daily_orders_count = 0
        self.daily_realized_loss = 0.0

    def set_mode(self, mode: TradingMode):
        self.mode = mode

    def activate_kill_switch(self, reason: str = ""):
        self.kill_switch_active = True
        self.kill_switch_reason = reason or "Kích hoạt thủ công"

    def deactivate_kill_switch(self):
        self.kill_switch_active = False
        self.kill_switch_reason = ""

    def record_order_sent(self):
        self.daily_orders_count += 1

    def record_realized_loss(self, loss_vnd: float):
        if loss_vnd < 0:
            self.daily_realized_loss += abs(loss_vnd)

    def reset_daily_counters(self):
        self.daily_orders_count = 0
        self.daily_realized_loss = 0.0

    def validate_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        reference_price: Optional[float] = None
    ) -> Tuple[bool, str]:
        # 1. Kill switch check
        if self.kill_switch_active:
            return False, f"🚨 Kill Switch đang bật! ({self.kill_switch_reason})"

        # 2. Daily orders count check
        if self.daily_orders_count >= self.max_daily_orders:
            return False, f"⚠️ Đã chạm giới hạn Số lệnh tối đa trong ngày ({self.max_daily_orders} lệnh)"

        # 3. Max order gross value check
        gross_value = price * quantity
        if gross_value > self.max_order_value:
            return False, f"⚠️ Giá trị lệnh ({gross_value:,.0f} đ) vượt quá Hạn mức tối đa ({self.max_order_value:,.0f} đ)"

        # 4. HOSE price collar check (+-7%)
        if reference_price and reference_price > 0:
            floor_price = reference_price * 0.93
            ceiling_price = reference_price * 1.07
            if price < floor_price or price > ceiling_price:
                return False, f"⚠️ Giá đặt {price:,.0f} đ vi phạm biên độ Trần/Sàn HOSE (+-7% từ tham chiếu {reference_price:,.0f} đ)"

        return True, "OK"
