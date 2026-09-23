from pydantic import BaseModel, Field
from typing import List, Optional
import numpy as np

class Candle(BaseModel):
    timestamp: int
    date_str: str
    open: float
    high: float
    low: float
    close: float
    volume: int

class OHLCVSeries(BaseModel):
    symbol: str
    resolution: str = "1D"
    candles: List[Candle] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.candles)

    @property
    def closes_np(self) -> np.ndarray:
        return np.array([c.close for c in self.candles], dtype=float)

    @property
    def highs_np(self) -> np.ndarray:
        return np.array([c.high for c in self.candles], dtype=float)

    @property
    def lows_np(self) -> np.ndarray:
        return np.array([c.low for c in self.candles], dtype=float)

    @property
    def opens_np(self) -> np.ndarray:
        return np.array([c.open for c in self.candles], dtype=float)

    @property
    def volumes_np(self) -> np.ndarray:
        return np.array([c.volume for c in self.candles], dtype=float)

class SymbolQuote(BaseModel):
    symbol: str
    last_price: float
    change: float
    change_pct: float
    open: float
    high: float
    low: float
    volume: int
    vol_sma20: float = 0.0
    vol_ratio: float = 1.0
    updated_at: float = 0.0
