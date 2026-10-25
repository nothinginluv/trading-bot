import pytest
import numpy as np
from unittest.mock import AsyncMock
from indicators.calculator import calculate_price_correlation
from core.state import TradingState
from market.models import OHLCVSeries, Candle
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from storage.repository import PaperTradingRepository
from storage.db import init_db
from indicators.models import TechnicalSummary
from datetime import datetime

def test_calculate_price_correlation_basic():
    # 1. Short arrays
    assert calculate_price_correlation(np.array([10.0, 11.0]), np.array([20.0, 21.0])) == 0.0

    # 2. Perfect positive correlation
    p1 = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0])
    p2 = np.array([20.0, 22.0, 24.0, 26.0, 28.0, 30.0, 32.0, 34.0])
    corr = calculate_price_correlation(p1, p2)
    assert abs(corr - 1.0) < 1e-4

    # 3. Flat returns (zero variance)
    p_flat = np.array([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
    assert calculate_price_correlation(p1, p_flat) == 0.0

    # 4. Perfect negative correlation
    p_neg = np.array([50.0, 48.0, 46.0, 44.0, 42.0, 40.0, 38.0, 36.0])
    corr_neg = calculate_price_correlation(p1, p_neg)
    assert corr_neg < -0.95

@pytest.mark.asyncio
async def test_autotrader_correlation_gate(tmp_path):
    db_path = str(tmp_path / "test_corr.db")
    await init_db(db_path)
    paper_repo = PaperTradingRepository(db_path)
    engine = PaperEngine(paper_repo)
    await engine.initialize(10_000_000.0)

    # Currently holding VIC
    await paper_repo.upsert_position("VIC", 100, 100, 50000.0, 50000.0)

    state = TradingState()
    state.market_regime = "BULLISH"

    # Create 30 candles for VIC
    vic_candles = []
    base_time = datetime(2026, 9, 1, 9, 15)
    for i in range(35):
        price = 50000.0 + i * 500.0
        vic_candles.append(Candle(
            timestamp=base_time,
            open=price - 100,
            high=price + 200,
            low=price - 200,
            close=price,
            volume=500000
        ))
    state.vn30_candles["VIC"] = OHLCVSeries(symbol="VIC", candles=vic_candles)

    # Candidate VHM: Highly correlated with VIC (moves identically)
    vhm_candles = []
    for i in range(35):
        price = 40000.0 + i * 400.0
        vhm_candles.append(Candle(
            timestamp=base_time,
            open=price - 100,
            high=price + 200,
            low=price - 200,
            close=price,
            volume=600000
        ))
    state.vn30_candles["VHM"] = OHLCVSeries(symbol="VHM", candles=vhm_candles)
    state.vn30_summaries["VHM"] = TechnicalSummary(
        symbol="VHM", price=54000.0, ema21=50000.0, ema50=48000.0,
        macd_hist=100.0, macd=200.0, macd_signal=100.0, vol_sma20=300000,
        atr14=1200.0, rsi14=60.0
    )

    # Candidate FPT: Completely independent / low correlation
    fpt_candles = []
    fpt_prices = [100000.0, 102000.0, 99000.0, 101000.0, 98000.0, 103000.0, 101000.0] * 5
    for i, p in enumerate(fpt_prices[:35]):
        fpt_candles.append(Candle(
            timestamp=base_time,
            open=p - 100,
            high=p + 200,
            low=p - 200,
            close=p,
            volume=700000
        ))
    state.vn30_candles["FPT"] = OHLCVSeries(symbol="FPT", candles=fpt_candles)
    state.vn30_summaries["FPT"] = TechnicalSummary(
        symbol="FPT", price=101000.0, ema21=98000.0, ema50=95000.0,
        macd_hist=150.0, macd=300.0, macd_signal=150.0, vol_sma20=350000,
        atr14=2000.0, rsi14=58.0
    )

    notifications = []
    async def mock_notify(msg: str):
        notifications.append(msg)

    trader = AutoTrader(engine, state, notify_func=mock_notify)
    state.vn30_summaries["VIC"] = TechnicalSummary(symbol="VIC", price=67500.0)

    alerts = await trader.process_cycle()

    # Verify that VHM was rejected due to high correlation with held VIC
    corr_rejects = [a for a in alerts if "TỪ CHỐI MUA DO TƯƠNG QUAN CAO" in a and "VHM" in a]
    assert len(corr_rejects) == 1
    assert "VIC" in corr_rejects[0]

def test_calculate_series_correlation_date_alignment():
    from indicators.calculator import calculate_series_correlation
    from datetime import timedelta
    t0 = datetime(2026, 9, 1, 9, 15)
    # Series A has 10 days
    candles_a = [
        Candle(timestamp=t0 + timedelta(days=i), open=10.0+i, high=11.0+i, low=9.0+i, close=10.0+i, volume=100)
        for i in range(10)
    ]
    # Series B has some overlapping days (misses day 0)
    candles_b = [
        Candle(timestamp=t0 + timedelta(days=i), open=20.0+2*i, high=21.0+2*i, low=19.0+2*i, close=20.0+2*i, volume=100)
        for i in range(1, 10)
    ]
    s_a = OHLCVSeries(symbol="A", candles=candles_a)
    s_b = OHLCVSeries(symbol="B", candles=candles_b)

    corr = calculate_series_correlation(s_a, s_b, window=10)
    assert abs(corr - 1.0) < 1e-4
