import pytest
from strategy.paper_engine import PaperEngine
from strategy.models import OrderSide, OrderStatus
from storage.db import init_db
from storage.repository import PaperTradingRepository

def test_hose_tick_rounding():
    repo = None
    engine = PaperEngine(repo, slippage_pct=0.001)

    # < 10,000 VND -> tick 10đ
    assert engine.round_to_hose_tick(8504.0) == 8500.0
    assert engine.round_to_hose_tick(8506.0) == 8510.0

    # 10,000 - 49,950 VND -> tick 50đ
    assert engine.round_to_hose_tick(24024.0) == 24000.0
    assert engine.round_to_hose_tick(24035.0) == 24050.0

    # >= 50,000 VND -> tick 100đ
    assert engine.round_to_hose_tick(120040.0) == 120000.0
    assert engine.round_to_hose_tick(120060.0) == 120100.0

def test_slippage_calculation():
    engine = PaperEngine(None, slippage_pct=0.001) # 0.1%

    # FPT at 120,000 VND
    # Buy: 120,000 * 1.001 = 120,120 -> tick 100đ -> 120,100đ
    buy_price = engine.apply_slippage(120000.0, OrderSide.BUY)
    assert buy_price == 120100.0

    # Sell: 120,000 * 0.999 = 119,880 -> tick 100đ -> 119,900đ
    sell_price = engine.apply_slippage(120000.0, OrderSide.SELL)
    assert sell_price == 119900.0

    # Zero slippage engine
    zero_engine = PaperEngine(None, slippage_pct=0.0)
    assert zero_engine.apply_slippage(120000.0, OrderSide.BUY) == 120000.0
    assert zero_engine.apply_slippage(120000.0, OrderSide.SELL) == 120000.0

@pytest.mark.asyncio
async def test_paper_engine_slippage_lifecycle(tmp_path):
    test_db = str(tmp_path / "test_slippage.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.001)  # 0.1% slippage
    await engine.initialize(initial_capital=5000000.0)

    # 1. Buy 10 FPT at 120,000đ
    # Slippage +0.1% -> 120,100đ
    order_buy = await engine.execute_buy("FPT", 10, 120000.0)
    assert order_buy.status == OrderStatus.FILLED
    assert order_buy.price == 120100.0
    # Cost = 10 * 120,100 = 1,201,000đ; Fee = 1,201,000 * 0.0015 = 1,801.5đ
    assert order_buy.fee == 1801.5

    pos = await repo.get_position("FPT")
    assert pos.avg_buy_price == 120100.0
    assert pos.total_quantity == 10

    # Settle T+2
    await repo.settle_mature_tranches(current_date="2099-01-01")

    # 2. Sell 10 FPT at 130,000đ
    # Slippage -0.1% -> 129,900đ
    order_sell = await engine.execute_sell("FPT", 10, 130000.0)
    assert order_sell.status == OrderStatus.FILLED
    assert order_sell.price == 129900.0
    # Gross proceeds = 10 * 129,900 = 1,299,000đ
    # Fee = 1,299,000 * 0.0015 = 1,948.5đ
    # Tax = 1,299,000 * 0.0010 = 1,299.0đ
    # Net proceeds = 1,299,000 - 1,948.5 - 1,299.0 = 1,295,752.5đ
    # Realized PnL = 1,295,752.5 - (10 * 120,100) = 94,752.5đ
    assert order_sell.fee == 1948.5
    assert order_sell.tax == 1299.0
    assert order_sell.price == 129900.0

    acc = await engine.get_account_summary()
    assert acc.total_realized_pnl == 94752.5
