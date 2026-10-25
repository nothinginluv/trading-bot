import pytest
from strategy.risk import calculate_position_size

def test_volatility_position_sizing_allocates_fewer_shares_to_high_atr():
    nav = 10_000_000.0
    cash = 10_000_000.0
    price = 50_000.0

    # High ATR (high volatility, e.g. 3,000đ = 6% price)
    high_atr = 3_000.0
    qty_high_atr = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=high_atr,
        risk_per_trade_pct=0.015,
        max_slot_nav_pct=0.35
    )

    # Low ATR (calm / consolidating stock, e.g. 1,000đ = 2% price)
    low_atr = 1_000.0
    qty_low_atr = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=low_atr,
        risk_per_trade_pct=0.015,
        max_slot_nav_pct=0.35
    )

    # The high volatility stock should be allocated FEWER shares
    assert qty_high_atr < qty_low_atr
    assert qty_high_atr > 0
    assert qty_low_atr > 0

def test_volatility_sizing_respects_hose_round_and_odd_lot():
    nav = 5_000_000.0
    cash = 5_000_000.0
    
    # 1. High price stock (FPT ~ 120,000đ) -> Fits in Odd Lot (< 100)
    qty_fpt = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=120_000.0,
        atr=2_500.0
    )
    assert 1 <= qty_fpt < 100  # Odd Lot supported

    # 2. Large NAV / lower price stock -> Fits in Round Lot (multiples of 100)
    qty_round = calculate_position_size(
        available_cash=50_000_000.0,
        nav=50_000_000.0,
        price=25_000.0,
        atr=600.0
    )
    assert qty_round >= 100
    assert qty_round % 100 == 0  # Round Lot

def test_volatility_sizing_never_exceeds_available_cash():
    nav = 10_000_000.0
    cash = 200_000.0  # Only 200k cash left
    price = 50_000.0
    
    qty = calculate_position_size(
        available_cash=cash,
        nav=nav,
        price=price,
        atr=1_000.0
    )
    # Total cost must be <= cash
    assert qty * price * 1.0015 <= cash

def test_institutional_volatility_targeting():
    from strategy.risk import calculate_volatility_target_size
    nav = 100_000_000.0
    price = 50_000.0

    # Stock A: Low annual volatility (ATR = 500đ -> daily vol 1%, annual vol ~ 15.8%)
    qty_low = calculate_volatility_target_size(
        nav=nav, price=price, atr=500.0, target_vol_annualized=0.15, max_slots=4
    )

    # Stock B: High annual volatility (ATR = 2,500đ -> daily vol 5%, annual vol ~ 79%)
    qty_high = calculate_volatility_target_size(
        nav=nav, price=price, atr=2500.0, target_vol_annualized=0.15, max_slots=4
    )

    assert qty_low > qty_high
    assert qty_high > 0

    # Verify integration with calculate_position_size
    qty_with_vol_target = calculate_position_size(
        available_cash=nav,
        nav=nav,
        price=price,
        atr=2500.0,
        target_vol_annualized=0.15
    )
    assert qty_with_vol_target <= qty_high

