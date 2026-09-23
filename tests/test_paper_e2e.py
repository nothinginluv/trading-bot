import pytest
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from strategy.models import OrderStatus
from core.state import TradingState
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary

@pytest.mark.asyncio
async def test_full_paper_trading_pipeline(tmp_path):
    test_db = str(tmp_path / "test_paper_e2e.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(initial_capital=5000000.0)
    
    state = TradingState()
    notifications = []
    async def capture_notify(text: str):
        notifications.append(text)
        
    trader = AutoTrader(engine=engine, state=state, notify_func=capture_notify)
    
    # 1. Setup synthetic series with Breakout for TCB
    candles = []
    base_price = 22000.0
    for i in range(50):
        c = base_price + i * 150.0
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{(i%30)+1:02d}",
            open=c - 100, high=c + 100, low=c - 100, close=c,
            volume=1000000 if i < 49 else 2500000
        ))
    series = OHLCVSeries(symbol="TCB", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    state.update_candles("TCB", series)
    state.update_summary("TCB", summary)
    
    # 2. Run AutoTrader cycle -> should trigger BUY
    alerts = await trader.process_cycle()
    assert len(alerts) > 0
    assert any("TCB" in a for a in alerts)
    
    pos = await repo.get_position("TCB")
    assert pos is not None
    assert pos.total_quantity > 0
    assert pos.available_quantity == 0  # Pending T+2
    
    # Verify account cash deducted
    acc_after_buy = await engine.get_account_summary()
    assert acc_after_buy.cash_balance < 5000000.0
    assert acc_after_buy.stock_value > 0
    
    # 3. Verify early sell is blocked before T+2
    early_sell = await engine.execute_sell("TCB", pos.total_quantity, pos.avg_buy_price)
    assert early_sell.status == OrderStatus.REJECTED
    
    # 4. Simulate passage of T+2 days
    settled = await repo.settle_mature_tranches("2099-01-01")
    assert settled == pos.total_quantity
    pos_settled = await repo.get_position("TCB")
    assert pos_settled.available_quantity == pos.total_quantity
    
    # 5. Trigger Take Profit (+8.5% gain)
    tp_price = pos.avg_buy_price * 1.085
    summary.price = tp_price
    state.update_summary("TCB", summary)
    
    # Next cycle should trigger Take-Profit SELL
    alerts_exit = await trader.process_cycle()
    assert any("Chốt lời" in a for a in alerts_exit)
    
    acc_final = await engine.get_account_summary()
    assert acc_final.total_realized_pnl > 0  # Profitable trade
    assert acc_final.stock_value == 0.0
    assert acc_final.cash_balance > 5000000.0  # Profited beyond initial capital
    
    # 6. Test Reset Account
    await repo.reset_account(5000000.0)
    acc_reset = await engine.get_account_summary()
    assert acc_reset.cash_balance == 5000000.0
    assert acc_reset.total_realized_pnl == 0.0
    positions = await repo.get_positions()
    assert len(positions) == 0
