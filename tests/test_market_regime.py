import pytest
from market.client import AsyncMarketClient
from core.state import TradingState
from indicators.calculator import evaluate_market_regime
from indicators.models import TechnicalSummary

def make_summary(price: float, ema21: float, ema50: float, rsi14: float) -> TechnicalSummary:
    return TechnicalSummary(
        symbol="VNINDEX", price=price, change=10.0, change_pct=0.8, open=price - 5,
        high=price + 5, low=price - 10, volume=500_000_000, vol_sma20=400_000_000,
        vol_ratio=1.25, ema9=ema21 + 5, ema21=ema21, ema50=ema50,
        rsi14=rsi14, macd=5.0, macd_signal=3.0, macd_hist=2.0,
        bb_upper=price + 50, bb_middle=price, bb_lower=price - 50,
        atr14=15.0, trend="UPTREND", rsi_status="NEUTRAL", macd_status="BULLISH",
        composite_signal="MUA MẠNH"
    )

def test_market_regime_classification():
    # 1. Bullish: Price >= EMA21 and RSI14 >= 48
    bull_summary = make_summary(price=1280.0, ema21=1260.0, ema50=1240.0, rsi14=55.0)
    assert evaluate_market_regime(bull_summary) == "BULLISH"

    # 2. Bearish: Price < EMA50
    bear_summary1 = make_summary(price=1200.0, ema21=1230.0, ema50=1250.0, rsi14=42.0)
    assert evaluate_market_regime(bear_summary1) == "BEARISH"

    # 3. Bearish: Price < EMA21 and RSI14 < 45
    bear_summary2 = make_summary(price=1245.0, ema21=1255.0, ema50=1240.0, rsi14=40.0)
    assert evaluate_market_regime(bear_summary2) == "BEARISH"

    # 4. Sideways: Price < EMA21 but RSI >= 45 and Price >= EMA50
    sideways_summary = make_summary(price=1250.0, ema21=1255.0, ema50=1240.0, rsi14=50.0)
    assert evaluate_market_regime(sideways_summary) == "SIDEWAYS"

def test_trading_state_market_regime():
    state = TradingState()
    assert state.market_regime == "BULLISH" # Default safe start
    assert state.vnindex_summary is None

    summary = make_summary(price=1200.0, ema21=1230.0, ema50=1250.0, rsi14=42.0)
    state.set_market_regime(summary)
    assert state.market_regime == "BEARISH"
    assert state.vnindex_summary is not None
    assert state.vnindex_summary.price == 1200.0

@pytest.mark.asyncio
async def test_market_client_index_routing():
    client = AsyncMarketClient()
    try:
        series = await client.get_candles("VNINDEX", count=30)
        assert series.symbol == "VNINDEX"
        assert len(series) > 0
        assert series.candles[-1].close > 0
    finally:
        await client.close()
