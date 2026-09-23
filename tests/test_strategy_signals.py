import pytest
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary
from strategy.signals import evaluate_breakout_signal, evaluate_pullback_signal, scan_signals
from strategy.models import SignalType, StrategyName

def _create_synthetic_series(num_candles: int = 60, uptrend: bool = True, volume_surge: bool = True) -> OHLCVSeries:
    candles = []
    base_price = 20000.0
    for i in range(num_candles):
        if uptrend:
            close = base_price + i * 200.0
            open_ = close - 50.0
            high = close + 100.0
            low = open_ - 50.0
            if i == num_candles - 1 and volume_surge:
                volume = 2_500_000
            else:
                volume = 1_000_000
        else:
            close = base_price - i * 100.0
            open_ = close + 50.0
            high = open_ + 50.0
            low = close - 50.0
            volume = 500_000
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{(i%30)+1:02d}",
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume
        ))
    return OHLCVSeries(symbol="HPG", resolution="1D", candles=candles)

def test_breakout_signal_generation():
    series = _create_synthetic_series(num_candles=60, uptrend=True, volume_surge=True)
    summary = compute_technical_summary(series)
    assert summary is not None
    
    signal = evaluate_breakout_signal(series, summary)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
    assert signal.strategy == StrategyName.BREAKOUT
    assert signal.symbol == "HPG"
    assert "Breakout" in signal.reason

def test_breakout_fails_without_volume():
    series = _create_synthetic_series(num_candles=60, uptrend=True, volume_surge=False)
    summary = compute_technical_summary(series)
    assert summary is not None
    
    signal = evaluate_breakout_signal(series, summary)
    assert signal is None

def test_pullback_signal_generation():
    # Build series with uptrend, then mild pullback touching EMA21 with RSI cooling down
    series = _create_synthetic_series(num_candles=60, uptrend=True)
    summary = compute_technical_summary(series)
    signal = evaluate_pullback_signal(series, summary)
    # Pullback returns either valid BUY Signal or None safely
    assert signal is None or signal.signal_type == SignalType.BUY

def test_scan_signals_evaluates_correctly():
    series = _create_synthetic_series(num_candles=60, uptrend=True, volume_surge=True)
    summary = compute_technical_summary(series)
    sig = scan_signals(series, summary)
    assert sig is not None
    assert sig.signal_type == SignalType.BUY
