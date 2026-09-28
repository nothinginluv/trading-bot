import pytest
from strategy.risk import calculate_position_size
from core.risk_safeguards import RiskSafeguards

def test_low_atr_capped_by_25_pct_nav():
    """
    For a stock with very low volatility (ATR), risk-based sizing would allow
    over 40% of NAV. The 25% NAV Hard Cap must kick in and limit the position.
    """
    nav = 100_000_000.0
    cash = 100_000_000.0
    price = 10_000.0
    # Very low ATR -> stop distance is floored at 3.5% = 350đ
    # Risk budget = 100,000,000 * 1.5% = 1,500,000đ
    # qty_by_risk = 1,500,000 // 350 = 4,285 shares (42.8% NAV without cap!)
    low_atr = 100.0

    qty = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=low_atr,
        risk_per_trade_pct=0.015,
        max_pos_pct=0.25,
        portfolio_exposure_cap=0.85
    )

    # 25% NAV cap = 25,000,000đ // 10,000đ = 2,500 shares (Round lot = 2,500)
    assert qty == 2_500
    assert qty * price <= nav * 0.2501

def test_high_atr_sized_down_by_risk():
    """
    For a highly volatile stock, risk-based sizing allocates fewer shares than the
    25% NAV cap, ensuring absolute risk remains strictly within 1.5% NAV.
    """
    nav = 100_000_000.0
    cash = 100_000_000.0
    price = 50_000.0
    # High ATR: 3,000đ (6% of price)
    # 25% cap would allow 500 shares (25,000,000đ)
    high_atr = 3_000.0

    qty = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=high_atr,
        risk_per_trade_pct=0.015,
        max_pos_pct=0.25
    )

    # Risk budget: 1,500,000 // 3,250 (6.5% cap) ~ 461 -> 400 shares (Round lot)
    assert qty == 400
    assert qty * price < nav * 0.25

def test_exposure_cap_budget_adjustment():
    """
    When existing positions already consume most of the 85% NAV exposure cap,
    the 4th slot automatically shrinks to fit the remaining exposure budget.
    """
    nav = 10_000_000.0
    cash = 10_000_000.0
    price = 50_000.0
    # 3 positions currently open totaling 7,500,000đ (75% NAV)
    current_exposure = 7_500_000.0
    # Exposure cap = 85% NAV = 8,500,000đ. Remaining budget = 1,000,000đ (20 shares)

    qty = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=1_000.0,
        current_open_exposure=current_exposure,
        portfolio_exposure_cap=0.85
    )

    # 1,000,000 // 50,000 = 20 shares (odd lot)
    assert qty == 20
    assert (current_exposure + qty * price) <= nav * 0.8501

def test_insufficient_capital_or_exposure_rejects_zero():
    """
    When available cash or remaining exposure budget is less than 1 share,
    calculate_position_size returns 0 so caller can reject the signal.
    """
    nav = 10_000_000.0
    price = 50_000.0

    # Case 1: Cash is only 20,000đ (< 50,000đ)
    qty_no_cash = calculate_position_size(
        available_cash=20_000.0,
        nav=nav,
        price=price
    )
    assert qty_no_cash == 0

    # Case 2: Portfolio exposure is already at 85% NAV cap (8,500,000đ)
    qty_no_budget = calculate_position_size(
        available_cash=5_000_000.0,
        nav=nav,
        price=price,
        current_open_exposure=8_500_000.0,
        portfolio_exposure_cap=0.85
    )
    assert qty_no_budget == 0

def test_strict_non_margin_cash_boundary():
    """
    Strict cash-only constraint: Order cost must never exceed available cash,
    even if 25% NAV is much larger.
    """
    nav = 50_000_000.0
    cash = 500_000.0  # Only 500k cash left (e.g. rest in stock)
    price = 25_000.0

    qty = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        max_pos_pct=0.25
    )

    fee_rate = 0.0015
    assert qty > 0
    # Total purchase value with fees must be <= available_cash
    assert qty * price * (1.0 + fee_rate) <= cash

def test_safeguards_validate_position_size():
    safeguards = RiskSafeguards(max_position_pct=0.25)
    nav = 10_000_000.0

    # 2,400,000 (24% NAV <= 25%) -> OK
    valid, msg = safeguards.validate_position_size(2_400_000.0, nav)
    assert valid
    assert msg == "OK"

    # 3,000,000 (30% NAV > 25%) -> Rejected!
    valid, msg = safeguards.validate_position_size(3_000_000.0, nav)
    assert not valid
    assert "vượt quá trần cứng 1 mã" in msg
