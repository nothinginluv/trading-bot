import pytest
from indicators.models import TechnicalSummary
from indicators.scanner import scan_vn30_market

def make_dummy_summary(symbol, price=50.0, trend="UPTREND", vol_ratio=1.5, rsi=60.0, macd_hist=0.2, bb_low=45.0, bb_up=55.0):
    return TechnicalSummary(
        symbol=symbol, price=price, change=1.0, change_pct=2.0, open=49.0, high=51.0, low=48.5,
        volume=2000000, vol_sma20=1300000, vol_ratio=vol_ratio, ema9=49.0, ema21=48.0, ema50=46.0,
        rsi14=rsi, macd=0.5, macd_signal=0.3, macd_hist=macd_hist, bb_upper=bb_up, bb_middle=50.0,
        bb_lower=bb_low, atr14=1.0, trend=trend, rsi_status="NEUTRAL", macd_status="BULLISH",
        composite_signal="MUA MẠNH"
    )

def test_scan_vn30_market():
    summaries = {
        "FPT": make_dummy_summary("FPT", price=66.0, vol_ratio=1.6, macd_hist=0.5), # Breakout
        "VNM": make_dummy_summary("VNM", price=44.0, rsi=30.0, bb_low=45.0),        # Oversold
        "SSI": make_dummy_summary("SSI", price=56.0, rsi=76.0, bb_up=55.0),         # Overbought
        "HPG": make_dummy_summary("HPG", price=25.0, trend="UPTREND")               # Strong trend
    }
    results = scan_vn30_market(summaries)
    assert "FPT" in [s.symbol for s in results.breakout]
    assert "VNM" in [s.symbol for s in results.oversold]
    assert "SSI" in [s.symbol for s in results.overbought]
