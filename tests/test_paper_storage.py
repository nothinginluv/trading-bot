import pytest
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.models import OrderSide, OrderStatus, OrderType, PaperOrder

@pytest.mark.asyncio
async def test_paper_repository_lifecycle(tmp_path):
    test_db = str(tmp_path / "test_bot.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    
    # 1. Initialize account
    account = await repo.get_or_create_account(initial_capital=5000000.0)
    assert account.initial_balance == 5000000.0
    assert account.cash_balance == 5000000.0
    assert account.auto_trade_enabled is True
    
    # 2. Add position and tranche
    await repo.add_settlement_tranche("FPT", quantity=15, buy_date="2026-09-20", settle_date="2026-09-22")
    await repo.upsert_position("FPT", total_qty=15, available_qty=0, avg_price=130000.0, highest_price=130000.0)
    
    pos = await repo.get_position("FPT")
    assert pos is not None
    assert pos.symbol == "FPT"
    assert pos.total_quantity == 15
    assert pos.available_quantity == 0
    
    # 3. Settle tranches on day >= 2026-09-22
    settled_qty = await repo.settle_mature_tranches(current_date="2026-09-23")
    assert settled_qty == 15
    
    pos_after = await repo.get_position("FPT")
    assert pos_after.available_quantity == 15
    
    # 4. Record order & trade
    order = PaperOrder(
        order_id="TEST-ORD-1",
        symbol="FPT",
        side=OrderSide.BUY,
        quantity=15,
        price=130000.0,
        fee=2925.0
    )
    await repo.record_order(order)
    await repo.record_trade(order.order_id, "FPT", OrderSide.BUY, 15, 130000.0, 2925.0, 0.0, 0.0)
    
    # 5. Reset account
    await repo.reset_account(reset_balance=5000000.0)
    acc_reset = await repo.get_or_create_account()
    assert acc_reset.cash_balance == 5000000.0
    positions = await repo.get_positions()
    assert len(positions) == 0
