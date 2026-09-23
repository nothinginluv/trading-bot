import pytest
import numpy as np
from market.models import Candle, OHLCVSeries, SymbolQuote

def test_candle_creation():
    c = Candle(
        timestamp=1727053200,
        date_str="2026-09-23",
        open=65.5,
        high=67.0,
        low=65.0,
        close=66.6,
        volume=4500000
    )
    assert c.close == 66.6
    assert c.volume == 4500000

def test_ohlcv_series_numpy_conversion():
    candles = [
        Candle(timestamp=100, date_str="2026-09-21", open=10.0, high=11.0, low=9.5, close=10.5, volume=1000),
        Candle(timestamp=200, date_str="2026-09-22", open=10.5, high=12.0, low=10.0, close=11.5, volume=1200),
        Candle(timestamp=300, date_str="2026-09-23", open=11.5, high=12.5, low=11.0, close=12.0, volume=1500),
    ]
    series = OHLCVSeries(symbol="FPT", resolution="1D", candles=candles)
    assert len(series) == 3
    assert np.array_equal(series.closes_np, np.array([10.5, 11.5, 12.0]))
    assert np.array_equal(series.highs_np, np.array([11.0, 12.0, 12.5]))
    assert np.array_equal(series.lows_np, np.array([9.5, 10.0, 11.0]))
    assert np.array_equal(series.volumes_np, np.array([1000, 1200, 1500]))
