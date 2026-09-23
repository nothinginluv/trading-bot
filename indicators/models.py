from pydantic import BaseModel
from typing import Optional

class TechnicalSummary(BaseModel):
    symbol: str
    price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: int
    vol_sma20: float
    vol_ratio: float
    ema9: float
    ema21: float
    ema50: float
    ema200: Optional[float] = None
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float
    bb_upper: float
    bb_middle: float
    bb_lower: float
    atr14: float
    trend: str           # "UPTREND", "DOWNTREND", "SIDEWAYS"
    rsi_status: str      # "OVERSOLD", "OVERBOUGHT", "NEUTRAL"
    macd_status: str     # "BULLISH_CROSS", "BEARISH_CROSS", "BULLISH", "BEARISH"
    composite_signal: str # "MUA MẠNH", "THEO DÕI MUA", "TRUNG LẬP", "CẢNH BÁO BÁN", "BÁN"
