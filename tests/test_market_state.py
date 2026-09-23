import pytest
from core.state import TradingState
from indicators.models import TechnicalSummary
from market.models import OHLCVSeries

def make_dummy_summary(symbol, change_pct=1.0):
    return TechnicalSummary(
        symbol=symbol, price=50.0, change=1.0, change_pct=change_pct, open=49.0, high=51.0, low=48.5,
        volume=2000000, vol_sma20=1300000, vol_ratio=1.5, ema9=49.0, ema21=48.0, ema50=46.0,
        rsi14=60.0, macd=0.5, macd_signal=0.3, macd_hist=0.2, bb_upper=55.0, bb_middle=50.0,
        bb_lower=45.0, atr14=1.0, trend="UPTREND", rsi_status="NEUTRAL", macd_status="BULLISH",
        composite_signal="MUA MẠNH"
    )

def test_market_state_caching_and_lookups():
    state = TradingState()
    assert state.vn30_summaries == {}
    
    summaries = {
        "FPT": make_dummy_summary("FPT", change_pct=2.5),
        "VNM": make_dummy_summary("VNM", change_pct=-1.5),
        "HPG": make_dummy_summary("HPG", change_pct=3.0)
    }
    state.set_market_data({}, summaries)
    
    assert state.get_summary("FPT") is not None
    assert state.get_summary("fpt") is not None  # Case-insensitive
    assert state.get_summary("XYZ") is None

    top_gainers, top_losers = state.get_top_movers(limit=2)
    assert top_gainers[0].symbol == "HPG"
    assert top_losers[0].symbol == "VNM"
