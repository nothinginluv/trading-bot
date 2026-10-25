import pytest
from unittest.mock import AsyncMock
from datetime import datetime
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from core.state import TradingState
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary

@pytest.mark.asyncio
async def test_auto_trader_cycle_no_signals(tmp_path):
    test_db = str(tmp_path / "test_auto_trader.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    
    state = TradingState()
    notifier = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=notifier)
    
    alerts = await trader.process_cycle()
    assert isinstance(alerts, list)
    assert len(alerts) == 0

@pytest.mark.asyncio
async def test_auto_trader_buy_trigger_and_exit(tmp_path):
    test_db = str(tmp_path / "test_auto_trader2.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    
    state = TradingState()
    notifier = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=notifier)
    
    # 1. Create a Breakout series for HPG
    candles = []
    base_price = 25000.0
    for i in range(50):
        c = base_price + i * 200.0
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{(i%30)+1:02d}",
            open=c - 100, high=c + 100, low=c - 100, close=c,
            volume=1000000 if i < 49 else 2500000
        ))
    series = OHLCVSeries(symbol="HPG", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    state.update_candles("HPG", series)
    state.update_summary("HPG", summary)
    
    # 2. Process cycle -> should trigger BUY
    alerts = await trader.process_cycle()
    assert len(alerts) > 0
    assert any("HPG" in a for a in alerts)
    
    pos = await repo.get_position("HPG")
    assert pos is not None
    assert pos.total_quantity > 0
    assert pos.available_quantity == 0
    
    # 3. Simulate settlement (T+2)
    await repo.settle_mature_tranches("2099-01-01")
    pos_settled = await repo.get_position("HPG")
    assert pos_settled.available_quantity == pos.total_quantity
    
    # 4. Trigger Stop-Loss: set price -6%
    sl_price = pos.avg_buy_price * 0.94
    summary.price = sl_price
    state.update_summary("HPG", summary)
    
    alerts_sl = await trader.process_cycle()
    assert any("Cắt lỗ" in a for a in alerts_sl)
    
    # Verify position sold
    pos_after_sl = await repo.get_position("HPG")
    assert pos_after_sl is None or pos_after_sl.total_quantity == 0


@pytest.mark.asyncio
async def test_auto_trader_with_live_trader(tmp_path):
    from dnse.mock_client import MockDNSEClient
    from core.risk_safeguards import RiskSafeguards, TradingMode
    from strategy.live_trader import LiveTrader

    test_db = str(tmp_path / "test_auto_trader_live.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)

    client = MockDNSEClient()
    safeguards = RiskSafeguards()
    safeguards.set_mode(TradingMode.LIVE_CONFIRM)
    live_trader = LiveTrader(client=client, safeguards=safeguards, account_no="0001880229")

    state = TradingState()
    notifier = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=notifier, live_trader=live_trader)

    # Add breakout series
    candles = []
    base_price = 25000.0
    for i in range(50):
        c = base_price + i * 200.0
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{(i%30)+1:02d}",
            open=c - 100, high=c + 100, low=c - 100, close=c,
            volume=1000000 if i < 49 else 2500000
        ))
    series = OHLCVSeries(symbol="HPG", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    state.update_candles("HPG", series)
    state.update_summary("HPG", summary)

    # Process cycle -> should generate pending confirmation for live order
    alerts = await trader.process_cycle()
    assert any("YÊU CẦU XÁC NHẬN" in a for a in alerts)
    assert len(live_trader.pending_confirmations) == 1

    # Verify paper engine was NOT used to falsely buy/record the position
    paper_pos = await repo.get_position("HPG")
    assert paper_pos is None or paper_pos.total_quantity == 0

    await client.close()


@pytest.mark.asyncio
async def test_auto_trader_lock_concurrency(tmp_path):
    import asyncio
    test_db = str(tmp_path / "test_auto_trader_lock.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)

    state = TradingState()
    notifier = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=notifier)

    # When lock is acquired by another background task, concurrent process_cycle skips
    async with trader._lock:
        res = await trader.process_cycle()
        assert res == []

    # When lock is free, process_cycle executes normally
    res_free = await trader.process_cycle()
    assert isinstance(res_free, list)

