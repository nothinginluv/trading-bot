import pytest
from strategy.models import PaperPosition, ExitType, ExitDecision
from strategy.risk import (
    calculate_partial_exit_quantity,
    check_exit_conditions
)

def test_calculate_partial_exit_quantity():
    # Odd lot tests
    assert calculate_partial_exit_quantity(1) == 0  # 1 share cannot be split, keep for TP2
    assert calculate_partial_exit_quantity(10) == 5
    assert calculate_partial_exit_quantity(55) == 28 # round(27.5) = 28
    assert calculate_partial_exit_quantity(99) == 50

    # Round lot tests (multiples of 100)
    assert calculate_partial_exit_quantity(200) == 100
    assert calculate_partial_exit_quantity(300) == 100 or calculate_partial_exit_quantity(300) == 200
    assert calculate_partial_exit_quantity(500) in (200, 300)
    assert calculate_partial_exit_quantity(1000) == 500

def test_dynamic_stop_loss_trigger():
    # Position with avg buy price 50,000, atr = 1,000 (atr_pct = 2%, sl_pct = 3.0% -> clamped to 3.5%)
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=200,
        available_quantity=200,
        avg_buy_price=50_000.0,
        highest_price=50_000.0,
        tp1_taken=False
    )
    # Price down 4% (48,000) -> should trigger Stop Loss
    decision = check_exit_conditions(pos, current_price=48_000.0, atr=1000.0)
    assert decision.should_exit is True
    assert decision.exit_type == ExitType.STOP_LOSS
    assert decision.sell_ratio == 1.0
    assert "Cắt lỗ" in decision.reason

def test_take_profit_1_partial_exit():
    pos = PaperPosition(
        symbol="FPT",
        total_quantity=200,
        available_quantity=200,
        avg_buy_price=100_000.0,
        highest_price=106_000.0,
        tp1_taken=False
    )
    # Price up 6% (106,000) -> triggers TP1 (50% partial exit)
    decision = check_exit_conditions(pos, current_price=106_000.0, atr=2500.0)
    assert decision.should_exit is True
    assert decision.exit_type == ExitType.TAKE_PROFIT_1
    assert decision.sell_ratio == 0.5
    assert decision.is_tp1 is True
    assert "Chốt lời Giai đoạn 1" in decision.reason

def test_breakeven_stop_after_tp1():
    # Once TP1 is taken, if price falls back to cost price, trigger BREAKEVEN exit
    pos = PaperPosition(
        symbol="FPT",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=100_000.0,
        highest_price=106_000.0,
        tp1_taken=True
    )
    # Price falls back to 100,000 (cost price)
    decision = check_exit_conditions(pos, current_price=100_000.0, atr=2500.0)
    assert decision.should_exit is True
    assert decision.exit_type == ExitType.BREAKEVEN
    assert decision.sell_ratio == 1.0
    assert "giá vốn" in decision.reason

def test_trailing_stop_after_tp1():
    pos = PaperPosition(
        symbol="SSI",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=30_000.0,
        highest_price=33_000.0, # +10% peak
        tp1_taken=True
    )
    # Price drops from 33,000 peak down to 32,100 (-2.7% from peak)
    decision = check_exit_conditions(pos, current_price=32_100.0, atr=700.0)
    assert decision.should_exit is True
    assert decision.exit_type in (ExitType.TRAILING_STOP, ExitType.TAKE_PROFIT_2)
    assert decision.sell_ratio == 1.0

def test_take_profit_2_full_exit():
    pos = PaperPosition(
        symbol="VNM",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=70_000.0,
        highest_price=77_500.0, # +10.7%
        tp1_taken=True
    )
    # Price reaches +10.7% (77,500) -> triggers TP2 full exit
    decision = check_exit_conditions(pos, current_price=77_500.0, atr=1500.0)
    assert decision.should_exit is True
    assert decision.exit_type in (ExitType.TAKE_PROFIT_2, ExitType.TRAILING_STOP)
    assert decision.sell_ratio == 1.0
