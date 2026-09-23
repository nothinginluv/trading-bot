import math
from typing import Optional, Tuple
from strategy.models import PaperPosition

def calculate_position_size(available_cash: float, nav: float, price: float) -> int:
    """
    Calculates the allowable share quantity given available cash and NAV.
    Supports both Round Lots (>= 100) and Odd Lots (1 to 99).
    Fee rate of 0.15% is accounted for.
    """
    if price <= 0 or available_cash <= 0:
        return 0
        
    fee_rate = 0.0015
    # Allocate up to NAV / 2 per position, bounded by available cash
    target_budget = min(available_cash, max(nav * 0.5, 0.0))
    if target_budget <= 0:
        target_budget = available_cash
    
    # Raw affordable shares including fee
    raw_shares = int(target_budget // (price * (1.0 + fee_rate)))
    
    if raw_shares <= 0:
        # Check if available cash can buy at least 1 share
        if available_cash >= price * (1.0 + fee_rate):
            return 1
        return 0
        
    if raw_shares >= 100:
        # Round down to nearest 100 (Round Lot)
        return (raw_shares // 100) * 100
    else:
        # Odd Lot (1 to 99)
        return raw_shares

def check_exit_conditions(
    position: PaperPosition,
    current_price: float,
    current_rsi: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Checks if a position triggers Stop Loss, Take Profit, or Trailing Stop.
    Returns (should_exit, reason).
    """
    if position.avg_buy_price <= 0 or current_price <= 0:
        return False, ""
        
    avg_price = position.avg_buy_price
    pnl_pct = (current_price - avg_price) / avg_price
    
    # 1. Hard Stop-Loss (-5.0%)
    if pnl_pct <= -0.05:
        return True, f"🚨 Cắt lỗ tự động (Stop Loss): Lỗ {pnl_pct*100:.2f}% (Giá {current_price:,.0f} so với giá vốn {avg_price:,.0f})."
        
    # 2. Take Profit (+8.0% baseline, or +7.0% if RSI > 75)
    tp_threshold = 0.07 if (current_rsi is not None and current_rsi > 75.0) else 0.08
    if pnl_pct >= tp_threshold:
        return True, f"🎯 Chốt lời tự động (Take Profit): Lãi {pnl_pct*100:.2f}% (Giá {current_price:,.0f} đạt mục tiêu TP {tp_threshold*100:.1f}%)."
        
    # 3. Dynamic Trailing Stop:
    # If position has ever achieved >= +5.0% gain
    peak_gain_pct = (position.highest_price - avg_price) / avg_price
    if peak_gain_pct >= 0.05 and position.highest_price > 0:
        # Trigger if price falls 2.0% from the peak
        trailing_stop_price = position.highest_price * 0.98
        if current_price <= trailing_stop_price:
            return True, (
                f"🛡️ Kích hoạt Trailing Stop: Giá giảm 2.0% từ đỉnh "
                f"({position.highest_price:,.0f} -> {current_price:,.0f}) để bảo toàn lợi nhuận (Lãi hiện tại: {pnl_pct*100:.2f}%)."
            )
            
    return False, ""
