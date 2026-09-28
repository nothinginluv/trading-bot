import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from core.state import TradingState
from core.risk_safeguards import RiskSafeguards
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary
from news.models import CorporateEvent, EventType

@pytest.mark.asyncio
async def test_autotrader_vetoes_buy_on_ex_date_and_picks_next(tmp_path):
    test_db = str(tmp_path / "test_ex_date_autotrader.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.0)
    await engine.initialize(initial_capital=5000000.0)

    state = TradingState()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Set FPT as having GDKHQ today (e.g. Cash Dividend 15%)
    ev_fpt_today = CorporateEvent(
        id="ev-fpt-today",
        symbol="FPT",
        ex_date=today_str,
        event_type=EventType.DIVIDEND_CASH,
        content="Trả cổ tức tiền mặt 15%"
    )
    state.set_corporate_events([ev_fpt_today])

    notifications = []
    async def capture_notify(text: str):
        notifications.append(text)

    safeguards = RiskSafeguards()
    live_trader = MagicMock()
    live_trader.safeguards = safeguards
    live_trader.auto_cancel_stale_orders = AsyncMock(return_value=[])

    trader = AutoTrader(engine=engine, state=state, notify_func=capture_notify, live_trader=live_trader)

    # Setup Breakout series for FPT (has ex-date today) and HPG (no ex-date)
    def make_breakout_series(sym, base):
        candles = []
        for i in range(50):
            c = base + i * 100.0
            candles.append(Candle(
                timestamp=1700000000 + i * 86400,
                date_str=f"2026-01-{(i%30)+1:02d}",
                open=c - 50, high=c + 50, low=c - 50, close=c,
                volume=1000000 if i < 49 else 2500000
            ))
        series = OHLCVSeries(symbol=sym, resolution="1D", candles=candles)
        summary = compute_technical_summary(series)
        state.update_candles(sym, series)
        state.update_summary(sym, summary)

    make_breakout_series("FPT", 120000.0)
    make_breakout_series("HPG", 25000.0)

    alerts = await trader.process_cycle()

    # FPT should be vetoed because today is GDKHQ
    assert any("TỪ CHỐI MUA DO NGÀY GDKHQ" in a and "FPT" in a for a in alerts)

    # Position FPT should NOT be opened
    pos_fpt = await repo.get_position("FPT")
    assert pos_fpt is None or pos_fpt.total_quantity == 0

    # AutoTrader should have picked HPG instead!
    pos_hpg = await repo.get_position("HPG")
    assert pos_hpg is not None
    assert pos_hpg.total_quantity > 0

@pytest.mark.asyncio
async def test_autotrader_advance_warning_for_held_position_ex_date_tomorrow(tmp_path):
    test_db = str(tmp_path / "test_adv_warn.db")
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo, slippage_pct=0.0)
    await engine.initialize(initial_capital=5000000.0)

    # Open position for MBB
    await repo.upsert_position("MBB", 100, 100, 20000.0, 20000.0)

    state = TradingState()
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Set MBB as having GDKHQ tomorrow
    ev_mbb_tomorrow = CorporateEvent(
        id="ev-mbb-tomorrow",
        symbol="MBB",
        ex_date=tomorrow_str,
        event_type=EventType.DIVIDEND_STOCK,
        content="Trả cổ tức cổ phiếu 15%"
    )
    state.set_corporate_events([ev_mbb_tomorrow])

    # Provide summary for MBB
    candles = [
        Candle(timestamp=1700000000, date_str="2026-01-01", open=20000, high=20500, low=19900, close=20000, volume=1000000)
    ] * 50
    series = OHLCVSeries(symbol="MBB", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    state.update_candles("MBB", series)
    state.update_summary("MBB", summary)

    notifications = []
    async def capture_notify(text: str):
        notifications.append(text)

    trader = AutoTrader(engine=engine, state=state, notify_func=capture_notify)
    alerts = await trader.process_cycle()

    # Advance warning alert should be triggered
    assert any("CẢNH BÁO SỰ KIỆN GDKHQ NGÀY MAI" in a and "MBB" in a for a in alerts)
    assert any("MBB" in n and "GDKHQ NGÀY MAI" in n for n in notifications)
