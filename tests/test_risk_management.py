from strategy.models import PaperPosition
from strategy.risk import calculate_position_size, check_exit_conditions

def test_position_sizing_round_and_odd_lot():
    # 5,000,000 VND capital, target ~ 2,500,000 VND
    # Case 1: HPG at 26,000đ -> 2,500,000 / (26000 * 1.0015) ~ 96 shares -> Odd lot = 96
    qty_odd = calculate_position_size(available_cash=5000000.0, nav=5000000.0, price=26000.0)
    assert qty_odd == 96
    
    # Case 2: Available cash = 4,000,000đ, price = 15,000đ -> ~2,000,000 / (15000 * 1.0015) = 133 shares -> Round lot = 100
    qty_round = calculate_position_size(available_cash=4000000.0, nav=4000000.0, price=15000.0)
    assert qty_round == 100
    
    # Case 3: Available cash = 200,000đ, FPT price = 130,000đ -> 1 share
    qty_min = calculate_position_size(available_cash=200000.0, nav=5000000.0, price=130000.0)
    assert qty_min == 1
    
    # Case 4: Insufficient cash for even 1 share
    qty_zero = calculate_position_size(available_cash=50000.0, nav=5000000.0, price=130000.0)
    assert qty_zero == 0

def test_exit_conditions_stop_loss():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=26000.0
    )
    # -5% from 26,000 = 24,700
    should_exit, reason = check_exit_conditions(pos, current_price=24600.0)
    assert should_exit is True
    assert "Cắt lỗ" in reason

def test_exit_conditions_take_profit():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=26000.0
    )
    # +8% from 26,000 = 28,080
    should_exit, reason = check_exit_conditions(pos, current_price=28100.0)
    assert should_exit is True
    assert "Chốt lời" in reason

def test_exit_conditions_trailing_stop():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=28000.0  # +7.6% gain reached
    )
    # -2% from peak 28,000 = 27,440
    should_exit, reason = check_exit_conditions(pos, current_price=27400.0)
    assert should_exit is True
    assert "Trailing Stop" in reason

def test_no_exit_when_normal():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=26500.0
    )
    should_exit, reason = check_exit_conditions(pos, current_price=26200.0)
    assert should_exit is False
    assert reason == ""
