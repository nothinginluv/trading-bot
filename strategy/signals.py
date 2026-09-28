from typing import Optional
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary
from strategy.models import Signal, SignalType, StrategyName

def evaluate_breakout_signal(
    series: OHLCVSeries,
    summary: TechnicalSummary,
    series_15m: Optional[OHLCVSeries] = None,
    summary_15m: Optional[TechnicalSummary] = None
) -> Optional[Signal]:
    """
    Evaluates Strategy A: Trend Following Momentum Breakout (Multi-Timeframe 1D + 15m).
    - Khung 1D (Macro Trend):
        + Close > EMA21 > EMA50
        + MACD Line > Signal Line & Histogram > 0
        + Volume >= 1.3x VolSMA20
        + Bullish candle: Close > Open and Close > Close[t-1]
    - Khung 15m (Precision Trigger, if available):
        + Veto if 15m shows heavy dumping (strong red bar > 1.5x VolSMA20_15m)
        + Boost confidence if 15m confirms breakout surge (Vol15m >= 1.2x & MACD15m bullish)
    """
    candles = series.candles
    if len(candles) < 30:
        return None
        
    last_candle = candles[-1]
    prev_candle = candles[-2]
    
    # 1. 1D Macro Trend Filter: Close > EMA21 > EMA50
    if not (summary.ema21 and summary.ema50):
        return None
    if not (last_candle.close > summary.ema21 > summary.ema50):
        return None
        
    # 2. 1D Momentum Filter: MACD bullish cross / positive hist
    if not (summary.macd_hist and summary.macd_hist > 0):
        return None
    if summary.macd is not None and summary.macd_signal is not None:
        if summary.macd <= summary.macd_signal:
            return None
            
    # 3. 1D Volume Surge: Volume >= 1.3x VolSMA20
    if not (summary.vol_sma20 and summary.vol_sma20 > 0):
        return None
    if last_candle.volume < 1.3 * summary.vol_sma20:
        return None
        
    # 4. 1D Bullish candle: Close > Open and Close > prev_close
    if not (last_candle.close > last_candle.open and last_candle.close > prev_candle.close):
        return None
        
    vol_ratio = last_candle.volume / summary.vol_sma20
    confidence = min(1.0, 0.7 + (vol_ratio - 1.3) * 0.1)
    mtf_note = ""

    # 5. 15m Intraday Confirmation (Multi-Timeframe Timing)
    if series_15m and summary_15m and len(series_15m.candles) >= 10:
        c15 = series_15m.candles[-1]
        vol_sma15 = summary_15m.vol_sma20
        # 5.1 Veto if 15m shows massive dumping red bar
        if c15.close < c15.open and vol_sma15 and c15.volume > 1.8 * vol_sma15:
            return None
            
        # 5.2 Confirmation & Boost
        if c15.close >= c15.open and (summary_15m.macd_hist and summary_15m.macd_hist >= 0):
            confidence = min(1.0, confidence + 0.15)
            mtf_note = f" | ⏱️ 15m Xác nhận bứt phá (MACD 15m dương, nến xanh)"

    reason = (
        f"⚡ Tín hiệu Breakout MTF: Giá 1D ({last_candle.close:,.0f}) > EMA21 > EMA50, "
        f"MACD 1D dương, Vol bùng nổ ({vol_ratio:.1f}x VolSMA20){mtf_note}."
    )
    return Signal(
        symbol=series.symbol,
        signal_type=SignalType.BUY,
        strategy=StrategyName.BREAKOUT,
        price=last_candle.close,
        confidence=confidence,
        reason=reason
    )

def evaluate_pullback_signal(
    series: OHLCVSeries,
    summary: TechnicalSummary,
    series_15m: Optional[OHLCVSeries] = None,
    summary_15m: Optional[TechnicalSummary] = None
) -> Optional[Signal]:
    """
    Evaluates Strategy B: Pullback / Buy on Dip (Multi-Timeframe 1D + 15m).
    - Khung 1D:
        + Close > EMA50 or Close > EMA200 (Long term uptrend)
        + Low touches near EMA21 (within 1.01x) or touches Lower BB (within 1.01x)
        + RSI between 30 and 45 (cooling down)
        + Bullish reversal candle: Close > Open and Close > Low[t-1]
    - Khung 15m:
        + Boost confidence if 15m RSI is oversold/cooling (30-45) and bouncing back
    """
    candles = series.candles
    if len(candles) < 30:
        return None
        
    last_candle = candles[-1]
    prev_candle = candles[-2]
    
    # 1. 1D Macro Trend: Close > EMA50 or EMA200
    is_macro_uptrend = False
    if summary.ema50 and last_candle.close > summary.ema50:
        is_macro_uptrend = True
    elif summary.ema200 and last_candle.close > summary.ema200:
        is_macro_uptrend = True
        
    if not is_macro_uptrend:
        return None
        
    # 2. 1D Pullback Condition: near EMA21 or near Lower BB
    touched_support = False
    if summary.ema21 and last_candle.low <= summary.ema21 * 1.01 and last_candle.close >= summary.ema21 * 0.985:
        touched_support = True
    elif summary.bb_lower and last_candle.low <= summary.bb_lower * 1.01:
        touched_support = True
        
    if not touched_support:
        return None
        
    # 3. 1D RSI cool-down: 30 <= RSI <= 45
    if not (summary.rsi14 and 30.0 <= summary.rsi14 <= 45.0):
        return None
        
    # 4. 1D Bullish reversal: Close > Open and Close > Low[t-1]
    if not (last_candle.close > last_candle.open and last_candle.close > prev_candle.low):
        return None
        
    confidence = 0.80
    mtf_note = ""

    # 5. 15m Timing confirmation
    if series_15m and summary_15m and len(series_15m.candles) >= 10:
        c15 = series_15m.candles[-1]
        if summary_15m.rsi14 and summary_15m.rsi14 <= 45.0 and c15.close >= c15.open:
            confidence = min(1.0, confidence + 0.15)
            mtf_note = f" | ⏱️ 15m RSI({summary_15m.rsi14:.1f}) rút chân hỗ trợ"

    reason = (
        f"🎯 Tín hiệu Bắt đáy MTF (Pullback): Xu hướng tăng lớn 1D, giá kiểm định hỗ trợ "
        f"với RSI({summary.rsi14:.1f}) hạ nhiệt và xuất hiện nến đảo chiều rút chân{mtf_note}."
    )
    return Signal(
        symbol=series.symbol,
        signal_type=SignalType.BUY,
        strategy=StrategyName.PULLBACK,
        price=last_candle.close,
        confidence=confidence,
        reason=reason
    )

def scan_signals(
    series: OHLCVSeries,
    summary: TechnicalSummary,
    series_15m: Optional[OHLCVSeries] = None,
    summary_15m: Optional[TechnicalSummary] = None
) -> Optional[Signal]:
    """Scans series with both Breakout and Pullback strategies across multi-timeframes."""
    # Priority: Breakout first, then Pullback
    sig = evaluate_breakout_signal(series, summary, series_15m=series_15m, summary_15m=summary_15m)
    if sig:
        return sig
    return evaluate_pullback_signal(series, summary, series_15m=series_15m, summary_15m=summary_15m)
