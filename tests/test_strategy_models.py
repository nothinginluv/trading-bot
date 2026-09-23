from datetime import datetime
from strategy.models import (
    SignalType, StrategyName, Signal,
    OrderSide, OrderStatus, OrderType,
    PaperOrder, SettlementTranche, PaperPosition, PaperAccount
)

def test_signal_model_creation():
    sig = Signal(
        symbol="HPG",
        signal_type=SignalType.BUY,
        strategy=StrategyName.BREAKOUT,
        price=26500.0,
        confidence=0.85,
        reason="Giá vượt EMA21 kèm khối lượng lớn"
    )
    assert sig.symbol == "HPG"
    assert sig.signal_type == SignalType.BUY
    assert sig.price == 26500.0

def test_paper_order_supports_odd_lot():
    order = PaperOrder(
        order_id="ORD-001",
        symbol="FPT",
        side=OrderSide.BUY,
        quantity=15,  # Odd lot
        price=130000.0,
        order_type=OrderType.MP,
        status=OrderStatus.FILLED,
        fee=2925.0
    )
    assert order.quantity == 15
    assert order.side == OrderSide.BUY

def test_paper_account_defaults():
    acc = PaperAccount(cash_balance=5000000.0)
    assert acc.initial_balance == 5000000.0
    assert acc.cash_balance == 5000000.0
    assert acc.auto_trade_enabled is True
    assert acc.nav == 5000000.0
