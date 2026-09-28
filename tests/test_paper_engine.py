import pytest
from datetime import datetime
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.models import OrderStatus, OrderSide

@pytest.mark.asyncio
async def test_paper_engine_buy_and_sell_lifecycle(tmp_path):
    test_db = str(tmp_path / "test_paper_engine.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.0)
    await engine.initialize(initial_capital=5000000.0)
    
    # 1. Execute BUY 10 shares of FPT at 130,000đ
    # Cost = 1,300,000 + 0.15% fee (1,950) = 1,301,950đ
    order_buy = await engine.execute_buy(symbol="FPT", quantity=10, price=130000.0)
    assert order_buy.status == OrderStatus.FILLED
    assert order_buy.fee == 1950.0
    
    acc = await engine.get_account_summary(current_prices={"FPT": 130000.0})
    assert acc.cash_balance == 5000000.0 - 1301950.0
    assert acc.stock_value == 1300000.0
    assert acc.nav == 5000000.0 - 1950.0
    
    # Check position T+2
    pos = await repo.get_position("FPT")
    assert pos.total_quantity == 10
    assert pos.available_quantity == 0  # Not yet settled
    
    # Try selling before T+2 -> should raise ValueError or return REJECTED
    order_early_sell = await engine.execute_sell(symbol="FPT", quantity=10, price=140000.0)
    assert order_early_sell.status == OrderStatus.REJECTED
    
    # Settle tranches for T+2
    await repo.settle_mature_tranches(current_date="2099-01-01")  # Future date ensures settlement
    
    # Now available_quantity = 10, execute SELL at 140,000đ (+7.69%)
    # Gross = 1,400,000. Fee = 0.15% (2,100). Tax = 0.1% (1,400). Net = 1,396,500đ
    # Realized PnL = 1,396,500 - 1,300,000 = +96,500đ
    order_sell = await engine.execute_sell(symbol="FPT", quantity=10, price=140000.0)
    assert order_sell.status == OrderStatus.FILLED
    assert order_sell.fee == 2100.0
    assert order_sell.tax == 1400.0
    
    acc_after = await engine.get_account_summary()
    assert acc_after.total_realized_pnl == 96500.0
    assert acc_after.cash_balance == (5000000.0 - 1301950.0 + 1396500.0)
    
    # Position total quantity should be 0
    pos_sold = await repo.get_position("FPT")
    assert pos_sold is None or pos_sold.total_quantity == 0
