from pydantic import BaseModel, Field
from typing import Dict, List
from indicators.models import TechnicalSummary

class ScanResults(BaseModel):
    breakout: List[TechnicalSummary] = Field(default_factory=list)
    oversold: List[TechnicalSummary] = Field(default_factory=list)
    overbought: List[TechnicalSummary] = Field(default_factory=list)
    strong_trend: List[TechnicalSummary] = Field(default_factory=list)

def scan_vn30_market(summaries: Dict[str, TechnicalSummary]) -> ScanResults:
    breakout = []
    oversold = []
    overbought = []
    strong_trend = []

    for sym, s in summaries.items():
        # 1. Breakout / Volume Momentum: Price > EMA21 and Vol Ratio >= 1.3 and MACD Hist > 0
        if s.price > s.ema21 and s.vol_ratio >= 1.3 and s.macd_hist > 0:
            breakout.append(s)

        # 2. Oversold: RSI < 35 or price <= bb_lower * 1.01
        if s.rsi14 < 35 or s.price <= s.bb_lower * 1.01:
            oversold.append(s)

        # 3. Overbought: RSI > 70 or price >= bb_upper
        if s.rsi14 > 70 or s.price >= s.bb_upper:
            overbought.append(s)

        # 4. Strong Trend: Price > EMA9 > EMA21 > EMA50
        if s.price > s.ema9 and s.ema9 > s.ema21 and s.ema21 > s.ema50:
            strong_trend.append(s)

    return ScanResults(
        breakout=sorted(breakout, key=lambda x: x.vol_ratio, reverse=True),
        oversold=sorted(oversold, key=lambda x: x.rsi14),
        overbought=sorted(overbought, key=lambda x: x.rsi14, reverse=True),
        strong_trend=sorted(strong_trend, key=lambda x: x.change_pct, reverse=True)
    )
