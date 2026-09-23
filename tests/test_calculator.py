import pytest
import numpy as np
from indicators.calculator import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_vol_sma,
    compute_technical_summary
)
from market.models import Candle, OHLCVSeries

def test_ema_calculation():
    prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0])
    ema5 = calculate_ema(prices, period=5)
    assert len(ema5) == len(prices)
    assert ema5[-1] < 19.0
    assert ema5[-1] > 15.0

def test_rsi_calculation():
    # Uptrend prices
    prices = np.linspace(10, 30, 30)
    rsi = calculate_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    assert rsi[-1] > 70  # Strong uptrend leads to high RSI

    # Downtrend prices
    down_prices = np.linspace(30, 10, 30)
    down_rsi = calculate_rsi(down_prices, period=14)
    assert down_rsi[-1] < 30

def test_macd_calculation():
    prices = np.linspace(10, 50, 50)
    macd, signal, hist = calculate_macd(prices, 12, 26, 9)
    assert len(macd) == len(prices)
    assert len(signal) == len(prices)
    assert len(hist) == len(prices)

def test_bollinger_bands_calculation():
    prices = np.array([20.0] * 30)
    upper, mid, lower = calculate_bollinger_bands(prices, period=20, std_dev=2.0)
    assert np.isclose(mid[-1], 20.0)
    assert np.isclose(upper[-1], 20.0)
    assert np.isclose(lower[-1], 20.0)

def test_compute_technical_summary():
    candles = [
        Candle(timestamp=i*86400, date_str=f"2026-01-{i+1:02d}", open=10+i*0.5, high=11+i*0.5, low=9.5+i*0.5, close=10.5+i*0.5, volume=1000000)
        for i in range(50)
    ]
    series = OHLCVSeries(symbol="FPT", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    assert summary is not None
    assert summary.symbol == "FPT"
    assert summary.rsi14 > 0
    assert summary.ema9 > 0
    assert summary.trend in ("UPTREND", "DOWNTREND", "SIDEWAYS")
