import pytest
from unittest.mock import AsyncMock
from core.state import TradingState
from strategy.auto_trader import AutoTrader
from strategy.models import Signal, SignalType, StrategyName, PaperPosition
from indicators.models import TechnicalSummary
from market.models import Candle, OHLCVSeries

def make_dummy_series(symbol: str, price: float) -> OHLCVSeries:
    candles = [
        Candle(timestamp=i*86400, date_str=f"2026-01-{i+1:02d}", open=price-1, high=price+1, low=price-2, close=price, volume=1_000_000)
        for i in range(40)
    ]
    return OHLCVSeries(symbol=symbol, resolution="1D", candles=candles)

def make_dummy_summary(symbol: str, price: float) -> TechnicalSummary:
    return TechnicalSummary(
        symbol=symbol, price=price, change=1.0, change_pct=2.0, open=price-1, high=price+1, low=price-2,
        volume=2_000_000, vol_sma20=1_000_000, vol_ratio=2.0, ema9=price-2, ema21=price-4, ema50=price-6,
        rsi14=60.0, macd=1.0, macd_signal=0.5, macd_hist=0.5, bb_upper=price+5, bb_middle=price, bb_lower=price-5,
        atr14=2.0, trend="UPTREND", rsi_status="NEUTRAL", macd_status="BULLISH", composite_signal="MUA MẠNH"
    )

@pytest.mark.asyncio
async def test_auto_trader_blocks_buys_when_regime_is_bearish(tmp_path):
    db_file = str(tmp_path / "test_regime_trader.db")
    from storage.db import init_db
    from storage.repository import PaperTradingRepository
    from strategy.paper_engine import PaperEngine

    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    await engine.initialize(5_000_000.0)

    state = TradingState()
    state.market_regime = "BEARISH"  # Gate active!
    
    # Add candidate signal
    state.vn30_summaries["FPT"] = make_dummy_summary("FPT", 100_000.0)
    state.vn30_candles["FPT"] = make_dummy_series("FPT", 100_000.0)

    mock_notify = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)

    alerts = await trader.process_cycle()
    
    # No buy orders should have been placed
    positions = await repo.get_positions()
    assert len(positions) == 0

@pytest.mark.asyncio
async def test_auto_trader_partial_tp1_execution(tmp_path):
    db_file = str(tmp_path / "test_partial_tp.db")
    from storage.db import init_db
    from storage.repository import PaperTradingRepository
    from strategy.paper_engine import PaperEngine

    await init_db(db_file)
    repo = PaperTradingRepository(db_file)
    engine = PaperEngine(repo)
    await engine.initialize(5_000_000.0)

    # Insert position with 200 shares bought at 50,000, 200 available
    await repo.upsert_position("HPG", 200, 200, 50_000.0, 50_000.0, tp1_taken=False)

    state = TradingState()
    state.market_regime = "BULLISH"
    # Price rises to 53,000 (+6% -> triggers TP1)
    state.vn30_summaries["HPG"] = make_dummy_summary("HPG", 53_000.0)

    mock_notify = AsyncMock()
    trader = AutoTrader(engine=engine, state=state, notify_func=mock_notify)

    alerts = await trader.process_cycle()

    pos = await repo.get_position("HPG")
    assert pos is not None
    assert pos.tp1_taken is True
    # 50% sold (100 shares sold, 100 remaining)
    assert pos.total_quantity == 100
    assert any("CHỐT LỜI 50%" in a for a in alerts)
