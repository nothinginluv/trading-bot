import math
from enum import Enum
from typing import Optional, Tuple, List
from datetime import datetime

def calculate_hose_collar(reference_price: float) -> Tuple[float, float]:
    """
    Calculates HOSE Floor and Ceiling prices with standard tick size rounding:
    - Tick sizes: < 10k: 10d, 10k-50k: 50d, >= 50k: 100d.
    - Ceiling: reference * 1.07 rounded down to tick size.
    - Floor: reference * 0.93 rounded up to tick size.
    """
    def _tick(p: float) -> float:
        if p < 10_000:
            return 10.0
        elif p < 50_000:
            return 50.0
        else:
            return 100.0

    raw_ceil = reference_price * 1.07
    tick_ceil = _tick(raw_ceil)
    ceiling_price = math.floor(round(raw_ceil, 2) / tick_ceil) * tick_ceil

    raw_floor = reference_price * 0.93
    tick_floor = _tick(raw_floor)
    floor_price = math.ceil(round(raw_floor, 2) / tick_floor) * tick_floor

    return floor_price, ceiling_price

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
        max_daily_loss_pct: float = -0.03,
        max_portfolio_exposure_pct: float = 0.85,
        max_position_pct: float = 0.25,
        max_weekly_drawdown_pct: float = -0.07,
        max_concurrent_positions: int = 4,
        max_positions_per_sector: int = 2,
        risk_per_trade_pct: float = 0.015
    ):
        self.mode = mode
        self.kill_switch_active = False
        self.kill_switch_reason = ""
        self.max_order_value = max_order_value
        self.max_daily_orders = max_daily_orders
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_portfolio_exposure_pct = max_portfolio_exposure_pct
        self.max_position_pct = max_position_pct
        self.max_weekly_drawdown_pct = max_weekly_drawdown_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.max_positions_per_sector = max_positions_per_sector
        self.risk_per_trade_pct = risk_per_trade_pct
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

    @property
    def is_read_only(self) -> bool:
        return self.kill_switch_active

    @property
    def read_only_reason(self) -> str:
        return self.kill_switch_reason

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

        # 4. HOSE price collar check (+-7% with tick size rounding)
        if reference_price and reference_price > 0:
            floor_price, ceiling_price = calculate_hose_collar(reference_price)
            if price < (floor_price - 1.0) or price > (ceiling_price + 1.0):
                return False, f"⚠️ Giá đặt {price:,.0f} đ vi phạm biên độ Trần/Sàn HOSE [Sàn: {floor_price:,.0f} đ, Trần: {ceiling_price:,.0f} đ] từ tham chiếu {reference_price:,.0f} đ"

        return True, "OK"

    def check_drawdown_circuit_breaker(
        self,
        current_nav: float,
        nav_day_start: Optional[float],
        nav_week_start: Optional[float]
    ) -> Tuple[bool, str]:
        """
        Monitors daily and weekly drawdown against circuit breaker thresholds.
        Trips emergency kill switch automatically if breach occurs.
        Returns (tripped: bool, message: str).
        """
        if current_nav <= 0:
            return False, "OK"

        # 1. Daily Drawdown
        if nav_day_start and nav_day_start > 0:
            dd_day = (current_nav - nav_day_start) / nav_day_start
            limit_day = -abs(self.max_daily_loss_pct)
            if dd_day <= limit_day:
                reason = (
                    f"🚨 CIRCUIT BREAKER: Drawdown ngày đạt {dd_day*100:.2f}% NAV "
                    f"(vượt ngưỡng an toàn {limit_day*100:.1f}%). Hệ thống tự ngắt bảo toàn vốn!"
                )
                self.activate_kill_switch(reason)
                return True, reason

        # 2. Weekly Drawdown
        if nav_week_start and nav_week_start > 0:
            dd_week = (current_nav - nav_week_start) / nav_week_start
            limit_week = -abs(self.max_weekly_drawdown_pct)
            if dd_week <= limit_week:
                reason = (
                    f"🚨 CIRCUIT BREAKER: Drawdown tuần đạt {dd_week*100:.2f}% NAV "
                    f"(vượt ngưỡng an toàn {limit_week*100:.1f}%). Hệ thống tự ngắt bảo toàn vốn!"
                )
                self.activate_kill_switch(reason)
                return True, reason

        return False, "OK"

    def validate_portfolio_exposure(
        self,
        current_exposure: float,
        new_order_value: float,
        nav: float
    ) -> Tuple[bool, str]:
        """
        Validates total portfolio exposure including the new order against NAV cap (e.g. 100%).
        """
        if nav <= 0:
            return True, "OK"
        projected_exposure = current_exposure + new_order_value
        exposure_ratio = projected_exposure / nav
        if exposure_ratio > (self.max_portfolio_exposure_pct + 0.005):
            return False, (
                f"⚠️ Tổng vị thế mở ({exposure_ratio*100:.1f}% NAV) vượt quá trần cho phép "
                f"({self.max_portfolio_exposure_pct*100:.0f}% NAV)"
            )
        return True, "OK"

    def validate_position_slots(self, current_positions_count: int) -> Tuple[bool, str]:
        """
        Validates open position count against slot limit (e.g. max 4 concurrent symbols).
        """
        if current_positions_count >= self.max_concurrent_positions:
            return False, f"⚠️ Đã đạt giới hạn tối đa {self.max_concurrent_positions} vị thế mở đồng thời trong danh mục"
        return True, "OK"

    def validate_position_size(self, order_value: float, nav: float) -> Tuple[bool, str]:
        """
        Validates individual order value against max position percentage (e.g. 25% NAV).
        """
        if nav <= 0:
            return True, "OK"
        pos_ratio = order_value / nav
        if pos_ratio > (self.max_position_pct + 0.005):
            return False, f"⚠️ Giá trị vị thế ({pos_ratio*100:.1f}% NAV) vượt quá trần cứng 1 mã ({self.max_position_pct*100:.0f}% NAV)"
        return True, "OK"

    def validate_sector_concentration(
        self,
        target_symbol: str,
        active_symbols: List[str]
    ) -> Tuple[bool, str]:
        """
        Validates sector concentration risk: max_positions_per_sector (default 2)
        concurrent positions in the same sector.
        """
        from config.constants import get_symbol_sector
        target_sector = get_symbol_sector(target_symbol)
        if target_sector == "KHÁC":
            return True, "OK"

        same_sector_symbols = [
            s.upper() for s in active_symbols
            if get_symbol_sector(s) == target_sector and s.upper() != target_symbol.upper()
        ]
        if len(same_sector_symbols) >= self.max_positions_per_sector:
            return False, (
                f"⚠️ Ngành {target_sector} đã có {len(same_sector_symbols)} mã đang mở ({', '.join(same_sector_symbols)}). "
                f"Vượt quá giới hạn tối đa {self.max_positions_per_sector} mã cùng ngành!"
            )
        return True, "OK"


