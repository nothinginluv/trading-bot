import math
from typing import Optional, Tuple
from strategy.models import PaperPosition, ExitDecision, ExitType

def calculate_position_size(
    available_cash: float,
    nav: float,
    price: float,
    atr: Optional[float] = None,
    risk_per_trade_pct: float = 0.015,
    stop_mult: float = 1.5,
    max_pos_pct: float = 0.25,
    current_open_exposure: float = 0.0,
    portfolio_exposure_cap: float = 0.85,
    max_slot_nav_pct: Optional[float] = None
) -> int:
    """
    Position Sizing 2 Lớp (ATR-Risk + Hard Cap 25% NAV) & Chính sách Cash-Only Không Margin.

    1. Lớp 1 (Risk-based Sizing):
       qty_by_risk = (NAV * RISK_PCT) / (STOP_MULT * ATR)
       Với STOP_MULT = 1.5, giới hạn khoảng dừng lỗ trong [3.5%, 6.5%].
    
    2. Lớp 2 (Hard Cap % NAV):
       qty_by_cap = (NAV * MAX_POS_PCT) / price
       Với MAX_POS_PCT = 25% (4 slot x 25% = tối đa 100% NAV).
    
    3. Kết hợp min():
       final_qty = min(qty_by_risk, qty_by_cap) nếu có ATR, ngược lại lấy qty_by_cap.
    
    4. Ràng buộc Không Margin (Cash-Only):
       Khối lượng mua (tính cả phí 0.15%) tuyệt đối không vượt quá số tiền mặt khả dụng.
       cash_max_qty = int(available_cash // (price * (1 + fee_rate)))
       final_qty = min(final_qty, cash_max_qty)

    5. Ràng buộc Trần phơi nhiễm danh mục (Portfolio Exposure Cap = 85% NAV):
       remaining_exposure = max(0, NAV * portfolio_exposure_cap - current_open_exposure)
       exposure_max_qty = int(remaining_exposure // price)
       final_qty = min(final_qty, exposure_max_qty)
    
    6. Quy tắc làm tròn Lô sàn HOSE:
       - Lô chẵn (>= 100): Làm tròn xuống bội số 100 gần nhất.
       - Lô lẻ (1 - 99): Giữ nguyên số lẻ.
       - final_qty < 1: Trả về 0 (từ chối do vốn/hạn mức không đủ để mở vị thế tối thiểu).
    """
    if price <= 0 or available_cash <= 0 or nav <= 0:
        return 0

    fee_rate = 0.0015
    cap_pct = max_slot_nav_pct if max_slot_nav_pct is not None else max_pos_pct

    # Layer 2: Hard Cap % NAV per position
    pos_budget = max(nav * cap_pct, 0.0)
    qty_by_cap = int(pos_budget // price)

    # Layer 1: Risk-based sizing via ATR
    if atr and atr > 0:
        stop_distance = max(price * 0.035, min(price * 0.065, stop_mult * atr))
        risk_budget = max(nav * risk_per_trade_pct, 0.0)
        qty_by_risk = int(risk_budget // stop_distance) if stop_distance > 0 else qty_by_cap
        raw_qty = min(qty_by_risk, qty_by_cap)
    else:
        raw_qty = qty_by_cap

    # Cash constraint (No margin / Cash-only)
    cash_max_qty = int(available_cash // (price * (1.0 + fee_rate)))
    raw_qty = min(raw_qty, cash_max_qty)

    # Portfolio exposure cap constraint (e.g. 85% NAV)
    remaining_exposure = max(0.0, (nav * portfolio_exposure_cap) - current_open_exposure)
    exposure_max_qty = int(remaining_exposure // price)
    raw_qty = min(raw_qty, exposure_max_qty)

    if raw_qty <= 0:
        return 0

    # Round to HOSE lots
    if raw_qty >= 100:
        final_qty = (raw_qty // 100) * 100
    else:
        final_qty = raw_qty

    return max(0, final_qty)

def calculate_partial_exit_quantity(available_quantity: int, ratio: float = 0.5) -> int:
    """
    Calculates the quantity to sell for a partial exit (e.g. TP1 50%).
    Respects HOSE round lot (multiples of 100) and odd lot rules.
    If 1 share held, returns 0 (keep for full exit).
    """
    if available_quantity <= 1 or ratio <= 0:
        return 0

    if available_quantity >= 200:
        # Round lots: round down to nearest 100
        raw = int(available_quantity * ratio)
        rounded = (raw // 100) * 100
        if rounded <= 0:
            rounded = 100
        return min(rounded, available_quantity)
    elif available_quantity >= 100:
        raw = int(round(available_quantity * ratio))
        if raw >= 100:
            return (raw // 100) * 100
        return raw
    else:
        # Odd lot (1 to 99)
        return min(max(1, int(round(available_quantity * ratio))), available_quantity)

def check_exit_conditions(
    position: PaperPosition,
    current_price: float,
    current_rsi: Optional[float] = None,
    atr: Optional[float] = None
) -> ExitDecision:
    """
    Checks if a position triggers Dynamic Stop Loss, Take Profit 1 (50%),
    Breakeven (after TP1), Take Profit 2, or Dynamic Trailing Stop.
    Returns ExitDecision (which also unpacks as (should_exit, reason)).
    """
    if position.avg_buy_price <= 0 or current_price <= 0:
        return ExitDecision(should_exit=False, reason="")

    avg_price = position.avg_buy_price
    pnl_pct = (current_price - avg_price) / avg_price

    # 1. Volatility adjustments based on ATR
    if atr and atr > 0 and current_price > 0:
        atr_pct = atr / current_price
        sl_pct = max(0.035, min(0.065, 1.5 * atr_pct))
        tp1_pct = max(0.05, min(0.07, 1.5 * atr_pct))
        tp2_pct = max(0.08, min(0.12, 2.5 * atr_pct))
        if current_rsi is not None and current_rsi > 75.0:
            tp2_pct = min(tp2_pct, 0.075)
        trail_step_pct = max(0.02, min(0.035, 1.0 * atr_pct))
    else:
        # Standard default baseline
        sl_pct = 0.05
        tp1_pct = 0.05
        tp2_pct = 0.07 if (current_rsi is not None and current_rsi > 75.0) else 0.08
        trail_step_pct = 0.02

    # STAGE 1: Full Position Intact (tp1_taken == False)
    if not position.tp1_taken:
        # 1.1 Hard Stop Loss
        if pnl_pct <= -sl_pct:
            return ExitDecision(
                should_exit=True,
                exit_type=ExitType.STOP_LOSS,
                sell_ratio=1.0,
                reason=f"🚨 Cắt lỗ tự động (Stop Loss): Lỗ {pnl_pct*100:.2f}% (Giá {current_price:,.0f} so với giá vốn {avg_price:,.0f}, ngưỡng SL {sl_pct*100:.1f}%)."
            )

        # 1.2 Trailing Stop if profit reached >= 5% but price has pulled back from peak
        peak_gain_pct = (position.highest_price - avg_price) / avg_price
        if peak_gain_pct >= 0.05 and position.highest_price > 0:
            trailing_stop_price = position.highest_price * (1.0 - trail_step_pct)
            if current_price <= trailing_stop_price:
                return ExitDecision(
                    should_exit=True,
                    exit_type=ExitType.TRAILING_STOP,
                    sell_ratio=1.0,
                    reason=(
                        f"🛡️ Kích hoạt Trailing Stop: Giá giảm {trail_step_pct*100:.1f}% từ đỉnh "
                        f"({position.highest_price:,.0f} -> {current_price:,.0f}) để bảo toàn lợi nhuận (Lãi hiện tại: {pnl_pct*100:.2f}%)."
                    )
                )

        # 1.3 Take Profit 1 (50% partial exit)
        if pnl_pct >= tp1_pct:
            return ExitDecision(
                should_exit=True,
                exit_type=ExitType.TAKE_PROFIT_1,
                sell_ratio=0.5,
                is_tp1=True,
                reason=f"🎯 Chốt lời Giai đoạn 1 (TP1 - 50%): Lãi {pnl_pct*100:.2f}% (Giá {current_price:,.0f} đạt mục tiêu TP1 {tp1_pct*100:.1f}%)."
            )

    # STAGE 2: 50% Position Remaining (tp1_taken == True)
    else:
        # 2.1 Breakeven Stop: If price drops back to cost basis (with 0.2% buffer)
        if current_price <= avg_price * 1.002:
            return ExitDecision(
                should_exit=True,
                exit_type=ExitType.BREAKEVEN,
                sell_ratio=1.0,
                reason=f"🛡️ Dừng lỗ Hoà Vốn (Breakeven): Giá {current_price:,.0f} thoái lui về giá vốn {avg_price:,.0f} sau khi đã chốt lời TP1."
            )

        # 2.2 Take Profit 2 (Target 2 - 100% of remaining shares)
        if pnl_pct >= tp2_pct:
            return ExitDecision(
                should_exit=True,
                exit_type=ExitType.TAKE_PROFIT_2,
                sell_ratio=1.0,
                reason=f"🚀 Chốt lời Giai đoạn 2 (TP2 - Toàn bộ): Lãi {pnl_pct*100:.2f}% (Giá {current_price:,.0f} đạt mục tiêu TP2 {tp2_pct*100:.1f}%)."
            )

        # 2.3 Dynamic Trailing Stop for the remaining 50%
        peak_gain_pct = (position.highest_price - avg_price) / avg_price
        if peak_gain_pct >= 0.05 and position.highest_price > 0:
            trailing_stop_price = position.highest_price * (1.0 - trail_step_pct)
            if current_price <= trailing_stop_price:
                return ExitDecision(
                    should_exit=True,
                    exit_type=ExitType.TRAILING_STOP,
                    sell_ratio=1.0,
                    reason=(
                        f"🛡️ Kích hoạt Trailing Stop (Phần còn lại): Giá giảm {trail_step_pct*100:.1f}% từ đỉnh "
                        f"({position.highest_price:,.0f} -> {current_price:,.0f}) để bảo toàn lợi nhuận (Lãi hiện tại: {pnl_pct*100:.2f}%)."
                    )
                )

    return ExitDecision(should_exit=False, reason="")
