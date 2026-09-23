from typing import Optional
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary
from strategy.models import Signal, SignalType, StrategyName

def evaluate_breakout_signal(series: OHLCVSeries, summary: TechnicalSummary) -> Optional[Signal]:
    """
    Evaluates Strategy A: Trend Following Momentum Breakout.
    - Close > EMA21 > EMA50
    - MACD Line > Signal Line & Histogram > 0
    - Volume >= 1.3x VolSMA20
    - Bullish candle: Close > Open and Close > Close[t-1]
    """
    candles = series.candles
    if len(candles) < 30:
        return None
        
    last_candle = candles[-1]
    prev_candle = candles[-2]
    
    # 1. Trend Filter: Close > EMA21 > EMA50
    if not (summary.ema21 and summary.ema50):
        return None
    if not (last_candle.close > summary.ema21 > summary.ema50):
        return None
        
    # 2. Momentum Filter: MACD bullish cross / positive hist
    if not (summary.macd_hist and summary.macd_hist > 0):
        return None
    if summary.macd is not None and summary.macd_signal is not None:
        if summary.macd <= summary.macd_signal:
            return None
            
    # 3. Volume Surge: Volume >= 1.3x VolSMA20
    if not (summary.vol_sma20 and summary.vol_sma20 > 0):
        return None
    if last_candle.volume < 1.3 * summary.vol_sma20:
        return None
        
    # 4. Bullish candle: Close > Open and Close > prev_close
    if not (last_candle.close > last_candle.open and last_candle.close > prev_candle.close):
        return None
        
    vol_ratio = last_candle.volume / summary.vol_sma20
    reason = (
        f"⚡ Tín hiệu Breakout: Giá ({last_candle.close:,.0f}) > EMA21 > EMA50, "
        f"MACD dương, Khối lượng bùng nổ ({vol_ratio:.1f}x VolSMA20)."
    )
    return Signal(
        symbol=series.symbol,
        signal_type=SignalType.BUY,
        strategy=StrategyName.BREAKOUT,
        price=last_candle.close,
        confidence=min(1.0, 0.7 + (vol_ratio - 1.3) * 0.1),
        reason=reason
    )

def evaluate_pullback_signal(series: OHLCVSeries, summary: TechnicalSummary) -> Optional[Signal]:
    """
    Evaluates Strategy B: Pullback / Buy on Dip.
    - Close > EMA50 or Close > EMA200 (Long term uptrend)
    - Low touches near EMA21 (within 1.01x) or touches Lower BB (within 1.01x)
    - RSI between 30 and 45 (cooling down)
    - Bullish reversal candle: Close > Open and Close > Low[t-1]
    """
    candles = series.candles
    if len(candles) < 30:
        return None
        
    last_candle = candles[-1]
    prev_candle = candles[-2]
    
    # 1. Macro Trend: Close > EMA50 or EMA200
    is_macro_uptrend = False
    if summary.ema50 and last_candle.close > summary.ema50:
        is_macro_uptrend = True
    elif summary.ema200 and last_candle.close > summary.ema200:
        is_macro_uptrend = True
        
    if not is_macro_uptrend:
        return None
        
    # 2. Pullback Condition: near EMA21 or near Lower BB
    touched_support = False
    if summary.ema21 and last_candle.low <= summary.ema21 * 1.01 and last_candle.close >= summary.ema21 * 0.985:
        touched_support = True
    elif summary.bb_lower and last_candle.low <= summary.bb_lower * 1.01:
        touched_support = True
        
    if not touched_support:
        return None
        
    # 3. RSI cool-down: 30 <= RSI <= 45
    if not (summary.rsi14 and 30.0 <= summary.rsi14 <= 45.0):
        return None
        
    # 4. Bullish reversal: Close > Open and Close > Low[t-1]
    if not (last_candle.close > last_candle.open and last_candle.close > prev_candle.low):
        return None
        
    reason = (
        f"🎯 Tín hiệu Bắt đáy (Pullback): Xu hướng tăng, giá kiểm định hỗ trợ "
        f"với RSI({summary.rsi14:.1f}) hạ nhiệt và xuất hiện nến đảo chiều rút chân."
    )
    return Signal(
        symbol=series.symbol,
        signal_type=SignalType.BUY,
        strategy=StrategyName.PULLBACK,
        price=last_candle.close,
        confidence=0.8,
        reason=reason
    )

def scan_signals(series: OHLCVSeries, summary: TechnicalSummary) -> Optional[Signal]:
    """Scans series with both Breakout and Pullback strategies; returns first valid signal."""
    # Priority: Breakout first, then Pullback
    sig = evaluate_breakout_signal(series, summary)
    if sig:
        return sig
    return evaluate_pullback_signal(series, summary)
