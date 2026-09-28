import pytest
import time
from market.models import Candle, OHLCVSeries
from market.mock_client import MockMarketClient
from indicators.calculator import compute_technical_summary
from strategy.signals import evaluate_breakout_signal, evaluate_pullback_signal, scan_signals
from core.state import TradingState

@pytest.mark.asyncio
async def test_mock_market_client_supports_15m_and_1d():
    client = MockMarketClient()
    s_1d = await client.get_candles("FPT", count=50, resolution="1D")
    assert s_1d.resolution == "1D"
    assert len(s_1d.candles) == 50
    assert " " not in s_1d.candles[0].date_str  # YYYY-MM-DD

    s_15m = await client.get_candles("FPT", count=50, resolution="15")
    assert s_15m.resolution == "15"
    assert len(s_15m.candles) == 50
    assert " " in s_15m.candles[0].date_str  # YYYY-MM-DD HH:MM

@pytest.mark.asyncio
async def test_trading_state_multi_timeframe_storage():
    state = TradingState()
    client = MockMarketClient()

    c_1d = await client.get_candles("HPG", count=40, resolution="1D")
    sum_1d = compute_technical_summary(c_1d)
    state.set_market_data({"HPG": c_1d}, {"HPG": sum_1d}, resolution="1D")

    c_15m = await client.get_candles("HPG", count=40, resolution="15")
    sum_15m = compute_technical_summary(c_15m)
    state.set_market_data({"HPG": c_15m}, {"HPG": sum_15m}, resolution="15")

    assert state.get_candles("HPG", resolution="1D").resolution == "1D"
    assert state.get_candles("HPG", resolution="15").resolution == "15"
    assert state.get_summary("HPG", resolution="1D") is not None
    assert state.get_summary("HPG", resolution="15") is not None

def test_mtf_breakout_signal_boosts_confidence_with_15m_confirmation():
    # Construct 1D series with bullish breakout
    now = int(time.time())
    candles_1d = []
    base_price = 100.0
    for i in range(40):
        t = now - (40 - i) * 86400
        p = base_price + i * 0.5
        v = 1_000_000 if i < 39 else 3_000_000  # volume spike on last candle
        candles_1d.append(Candle(
            timestamp=t,
            date_str="2026-09-01",
            open=p - 0.2,
            high=p + 1.0,
            low=p - 0.5,
            close=p,
            volume=v
        ))
    series_1d = OHLCVSeries(symbol="FPT", resolution="1D", candles=candles_1d)
    sum_1d = compute_technical_summary(series_1d)

    # 1D without 15m
    sig_1d_only = evaluate_breakout_signal(series_1d, sum_1d)
    assert sig_1d_only is not None

    # Construct 15m series with bullish confirmation
    candles_15m = []
    for i in range(20):
        t15 = now - (20 - i) * 900
        p15 = 115.0 + i * 0.2
        candles_15m.append(Candle(
            timestamp=t15,
            date_str="2026-09-23 14:00",
            open=p15 - 0.1,
            high=p15 + 0.3,
            low=p15 - 0.2,
            close=p15,
            volume=50_000
        ))
    series_15m = OHLCVSeries(symbol="FPT", resolution="15", candles=candles_15m)
    sum_15m = compute_technical_summary(series_15m)

    sig_mtf = evaluate_breakout_signal(series_1d, sum_1d, series_15m=series_15m, summary_15m=sum_15m)
    assert sig_mtf is not None
    assert sig_mtf.confidence >= sig_1d_only.confidence
    assert "15m" in sig_mtf.reason

def test_mtf_breakout_signal_vetoes_when_15m_has_heavy_dumping():
    now = int(time.time())
    candles_1d = []
    base_price = 100.0
    for i in range(40):
        t = now - (40 - i) * 86400
        p = base_price + i * 0.5
        v = 1_000_000 if i < 39 else 3_000_000
        candles_1d.append(Candle(
            timestamp=t,
            date_str="2026-09-01",
            open=p - 0.2,
            high=p + 1.0,
            low=p - 0.5,
            close=p,
            volume=v
        ))
    series_1d = OHLCVSeries(symbol="FPT", resolution="1D", candles=candles_1d)
    sum_1d = compute_technical_summary(series_1d)

    # 15m series with heavy dump on last bar
    candles_15m = []
    for i in range(20):
        t15 = now - (20 - i) * 900
        if i == 19:
            # Massive sell dump
            candles_15m.append(Candle(
                timestamp=t15,
                date_str="2026-09-23 14:15",
                open=120.0,
                high=120.5,
                low=110.0,
                close=111.0,  # strong red bar
                volume=200_000  # 4x volume
            ))
        else:
            candles_15m.append(Candle(
                timestamp=t15,
                date_str="2026-09-23 14:00",
                open=119.0,
                high=120.0,
                low=118.5,
                close=119.5,
                volume=50_000
            ))
    series_15m = OHLCVSeries(symbol="FPT", resolution="15", candles=candles_15m)
    sum_15m = compute_technical_summary(series_15m)

    sig = evaluate_breakout_signal(series_1d, sum_1d, series_15m=series_15m, summary_15m=sum_15m)
    assert sig is None  # Vetoed due to 15m heavy sell dump
