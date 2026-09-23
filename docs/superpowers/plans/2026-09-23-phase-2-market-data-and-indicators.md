# Phase 2: Market Data Feed & Indicator Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a high-performance, real-time and historical market data feed and vector technical indicator engine for the official 30 VN30 stocks on HOSE, caching data in local SQLite and RAM, and serving instant technical analysis queries (`/quote`, `/indicators`, `/scan`, `/vn30`) on Telegram.

**Architecture:** Async HTTP client queries Entrade/DNSE Chart API with bounded concurrency (`asyncio.Semaphore(5)`). Daily candles are persisted in SQLite `daily_candles` table with upsert deduplication. A pure NumPy vector engine calculates EMA (9, 21, 50, 200), RSI (14), MACD (12, 26, 9), Bollinger Bands (20, 2), ATR (14), and Volume SMA (20). In-memory `TradingState` provides <5ms instant responses for Telegram queries and real-time breakout push alerts.

**Tech Stack:** Python 3.12, httpx, numpy, aiosqlite, aiogram 3.x, apscheduler, pytest, pytest-asyncio.

**Spec:** [docs/superpowers/specs/2026-09-23-phase-2-market-data-and-indicators-design.md](file:///d:/TradingBot/docs/superpowers/specs/2026-09-23-phase-2-market-data-and-indicators-design.md)

## Global Constraints
- Target Timeframe: Daily (`1D`) candles.
- VN30 Universe: Exactly 30 symbols: `ACB, BID, BSR, BVH, CTG, FPT, GAS, GVR, HDB, HPG, MBB, MCH, MSN, MWG, POW, SAB, SSB, SSI, STB, TCB, TCX, VCB, VHM, VIB, VIC, VJC, VNM, VPB, VPL, VRE`.
- Performance: Concurrency limit `<= 5` simultaneous requests; Telegram command responses from RAM cache `< 10ms`.
- Safety: 100% Read-Only / Analytical mode. Zero live order execution logic.
- Telegram Whitelist: Only Admin ID `7385637982` can interact with bot commands.

## Review Focus
1. Entrade API returns empty `c` array (e.g., weekend or newly listed ticker) -> Handled gracefully with empty series without raising unhandled IndexError.
2. Fewer than 50 or 200 candles available for a ticker -> Indicators (EMA200, MACD, etc.) return NaN / None without throwing exception or corrupting other tickers.
3. Market closed vs. market open -> Scheduler respects trading sessions (3 min in session, 15 min off session).
4. SQLite cold start (no internet connection on startup) -> Bot falls back to SQLite candles and operates in offline cached mode.
5. Telegram Markdown characters in ticker names or numbers (e.g. `_` or `*`) -> Escaped or wrapped in code spans to prevent Telegram API Markdown parsing errors.

---

### Task 1: Market Data Models & OHLCV Series

**Files:**
- Create: `market/models.py`
- Test: `tests/test_market_models.py`

**Interfaces:**
- Consumes: Standard types, `pydantic`, `numpy`.
- Produces: `Candle`, `OHLCVSeries`, `SymbolQuote`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_models.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'market'`

- [ ] **Step 3: Write minimal implementation**

```python
# market/models.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add market/models.py tests/test_market_models.py
git commit -m "feat(market): implement Candle, OHLCVSeries, and SymbolQuote models"
```

---

### Task 2: Async Market Client & Mock Client

**Files:**
- Create: `market/client.py`
- Create: `market/mock_client.py`
- Test: `tests/test_market_client.py`

**Interfaces:**
- Consumes: `market/models.py` (`Candle`, `OHLCVSeries`), `httpx`.
- Produces: `AsyncMarketClient`, `MockMarketClient`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_client.py
import pytest
from market.mock_client import MockMarketClient
from market.client import AsyncMarketClient

@pytest.mark.asyncio
async def test_mock_market_client():
    mock = MockMarketClient()
    series = await mock.get_candles("FPT", count=100)
    assert series.symbol == "FPT"
    assert len(series) == 100
    assert series.candles[-1].close > 0

@pytest.mark.asyncio
async def test_live_market_client():
    client = AsyncMarketClient()
    try:
        series = await client.get_candles("HPG", count=30)
        assert series.symbol == "HPG"
        assert len(series) > 0
        assert series.candles[-1].close > 0
    finally:
        await client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'market.mock_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# market/mock_client.py
import time
from datetime import datetime, timezone
import numpy as np
from market.models import Candle, OHLCVSeries

class MockMarketClient:
    async def get_candles(self, symbol: str, count: int = 150) -> OHLCVSeries:
        now = int(time.time())
        candles = []
        base_price = 50.0
        for i in range(count):
            t = now - (count - i) * 86400
            d_str = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
            noise = np.sin(i / 5.0) * 5.0 + (i * 0.1)
            c = base_price + noise
            h = c + 1.0
            l = c - 1.0
            o = c - 0.2
            v = int(1000000 + np.random.randint(100000, 500000))
            candles.append(Candle(
                timestamp=t,
                date_str=d_str,
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=v
            ))
        return OHLCVSeries(symbol=symbol, resolution="1D", candles=candles)

    async def get_all_vn30_candles(self, symbols: list[str]) -> dict[str, OHLCVSeries]:
        res = {}
        for s in symbols:
            res[s] = await self.get_candles(s)
        return res

    async def close(self):
        pass
```

```python
# market/client.py
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List
import httpx
from market.models import Candle, OHLCVSeries

logger = logging.getLogger(__name__)

class AsyncMarketClient:
    BASE_URL = "https://services.entrade.com.vn/chart-api/v2"

    def __init__(self, timeout: float = 10.0, max_concurrency: int = 5):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def get_candles(self, symbol: str, count: int = 150) -> OHLCVSeries:
        now = int(time.time())
        start = now - int(count * 1.5 * 86400)
        url = f"{self.BASE_URL}/ohlcs/stock?from={start}&to={now}&symbol={symbol.upper()}&resolution=1D"
        
        async with self.semaphore:
            for attempt in range(2):
                try:
                    resp = await self.client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        t_list = data.get("t", [])
                        o_list = data.get("o", [])
                        h_list = data.get("h", [])
                        l_list = data.get("l", [])
                        c_list = data.get("c", [])
                        v_list = data.get("v", [])
                        
                        candles = []
                        for i in range(len(t_list)):
                            t = int(t_list[i])
                            d_str = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
                            candles.append(Candle(
                                timestamp=t,
                                date_str=d_str,
                                open=float(o_list[i]),
                                high=float(h_list[i]),
                                low=float(l_list[i]),
                                close=float(c_list[i]),
                                volume=int(v_list[i])
                            ))
                        return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=candles)
                    logger.warning(f"Entrade API {symbol} returned status {resp.status_code}")
                except Exception as e:
                    if attempt == 1:
                        logger.error(f"Failed to fetch candles for {symbol}: {e}")
                    await asyncio.sleep(0.5)

        return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=[])

    async def get_all_vn30_candles(self, symbols: List[str]) -> Dict[str, OHLCVSeries]:
        tasks = [self.get_candles(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = {}
        for s, res in zip(symbols, results):
            if isinstance(res, OHLCVSeries):
                out[s] = res
            else:
                logger.error(f"Error fetching {s}: {res}")
                out[s] = OHLCVSeries(symbol=s, resolution="1D", candles=[])
        return out

    async def close(self):
        await self.client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add market/client.py market/mock_client.py tests/test_market_client.py
git commit -m "feat(market): implement AsyncMarketClient and MockMarketClient"
```

---

### Task 3: SQLite Candle Storage & Repository Extensions

**Files:**
- Modify: `storage/db.py`
- Modify: `storage/repository.py`
- Test: `tests/test_market_storage.py`

**Interfaces:**
- Consumes: `market/models.py` (`Candle`, `OHLCVSeries`), `aiosqlite`.
- Produces: `Repository.save_candles`, `Repository.get_candles`, `Repository.get_latest_candle`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_storage.py
import pytest
from storage.db import init_db
from storage.repository import Repository
from market.models import Candle, OHLCVSeries

@pytest.mark.asyncio
async def test_save_and_retrieve_candles(tmp_path):
    db_file = str(tmp_path / "test_market.db")
    await init_db(db_file)
    repo = Repository(db_file)

    candles = [
        Candle(timestamp=100, date_str="2026-09-20", open=10.0, high=11.0, low=9.5, close=10.5, volume=1000),
        Candle(timestamp=200, date_str="2026-09-21", open=10.5, high=12.0, low=10.0, close=11.5, volume=1200),
    ]
    series = OHLCVSeries(symbol="TCB", resolution="1D", candles=candles)
    await repo.save_candles("TCB", series)

    loaded = await repo.get_candles("TCB", limit=10)
    assert loaded.symbol == "TCB"
    assert len(loaded) == 2
    assert loaded.candles[-1].close == 11.5

    # Test deduplication / update
    updated_candles = [
        Candle(timestamp=200, date_str="2026-09-21", open=10.5, high=12.5, low=10.0, close=12.2, volume=1300),
    ]
    await repo.save_candles("TCB", OHLCVSeries(symbol="TCB", resolution="1D", candles=updated_candles))
    reloaded = await repo.get_candles("TCB", limit=10)
    assert len(reloaded) == 2
    assert reloaded.candles[-1].close == 12.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_storage.py -v`
Expected: FAIL with `AttributeError: 'Repository' object has no attribute 'save_candles'`

- [ ] **Step 3: Write minimal implementation**

Update `storage/db.py` to add `daily_candles` table:
```python
# in storage/db.py
"""
CREATE TABLE IF NOT EXISTS daily_candles (
    symbol TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    date_str TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (symbol, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_time ON daily_candles(symbol, timestamp DESC);
"""
```

Update `storage/repository.py`:
```python
# in storage/repository.py
from market.models import Candle, OHLCVSeries

class Repository:
    # ... existing methods ...
    async def save_candles(self, symbol: str, series: OHLCVSeries):
        if not series.candles:
            return
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            values = [
                (symbol.upper(), c.timestamp, c.date_str, c.open, c.high, c.low, c.close, c.volume, now)
                for c in series.candles
            ]
            await db.executemany(
                """
                INSERT OR REPLACE INTO daily_candles
                (symbol, timestamp, date_str, open, high, low, close, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values
            )
            await db.commit()

    async def get_candles(self, symbol: str, limit: int = 150) -> OHLCVSeries:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT timestamp, date_str, open, high, low, close, volume
                FROM daily_candles
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (symbol.upper(), limit)
            )
            rows = await cursor.fetchall()
            candles = [
                Candle(
                    timestamp=r["timestamp"],
                    date_str=r["date_str"],
                    open=r["open"],
                    high=r["high"],
                    low=r["low"],
                    close=r["close"],
                    volume=r["volume"]
                )
                for r in reversed(rows)
            ]
            return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=candles)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add storage/db.py storage/repository.py tests/test_market_storage.py
git commit -m "feat(storage): implement SQLite daily_candles schema and repository methods"
```

---

### Task 4: Technical Indicators Calculator

**Files:**
- Create: `indicators/models.py`
- Create: `indicators/calculator.py`
- Test: `tests/test_calculator.py`

**Interfaces:**
- Consumes: `market/models.py` (`OHLCVSeries`), `numpy`.
- Produces: `calculate_ema`, `calculate_rsi`, `calculate_macd`, `calculate_bollinger_bands`, `calculate_atr`, `calculate_vol_sma`, `TechnicalSummary`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calculator.py
import pytest
import numpy as np
from indicators.calculator import (
    calculate_ema,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_atr,
    calculate_vol_sma,
    compute_technical_summary
)
from market.models import Candle, OHLCVSeries

def test_ema_calculation():
    prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0])
    ema5 = calculate_ema(prices, period=5)
    assert len(ema5) == len(prices)
    assert ema5[-1] < 19.0
    assert ema5[-1] > 15.0

def test_rsi_calculation():
    # Uptrend prices
    prices = np.linspace(10, 30, 30)
    rsi = calculate_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    assert rsi[-1] > 70  # Strong uptrend leads to high RSI

    # Downtrend prices
    down_prices = np.linspace(30, 10, 30)
    down_rsi = calculate_rsi(down_prices, period=14)
    assert down_rsi[-1] < 30

def test_macd_calculation():
    prices = np.linspace(10, 50, 50)
    macd, signal, hist = calculate_macd(prices, 12, 26, 9)
    assert len(macd) == len(prices)
    assert len(signal) == len(prices)
    assert len(hist) == len(prices)

def test_bollinger_bands_calculation():
    prices = np.array([20.0] * 30)
    upper, mid, lower = calculate_bollinger_bands(prices, period=20, std_dev=2.0)
    assert np.isclose(mid[-1], 20.0)
    assert np.isclose(upper[-1], 20.0)
    assert np.isclose(lower[-1], 20.0)

def test_compute_technical_summary():
    candles = [
        Candle(timestamp=i*86400, date_str=f"2026-01-{i+1:02d}", open=10+i*0.5, high=11+i*0.5, low=9.5+i*0.5, close=10.5+i*0.5, volume=1000000)
        for i in range(50)
    ]
    series = OHLCVSeries(symbol="FPT", resolution="1D", candles=candles)
    summary = compute_technical_summary(series)
    assert summary is not None
    assert summary.symbol == "FPT"
    assert summary.rsi14 > 0
    assert summary.ema9 > 0
    assert summary.trend in ("UPTREND", "DOWNTREND", "SIDEWAYS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_calculator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'indicators'`

- [ ] **Step 3: Write minimal implementation**

```python
# indicators/models.py
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
```

```python
# indicators/calculator.py
from typing import Tuple, Optional
import numpy as np
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary

def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
    if len(prices) == 0:
        return np.array([])
    alpha = 2.0 / (period + 1.0)
    ema = np.zeros_like(prices, dtype=float)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1.0 - alpha) * ema[i - 1]
    return ema

def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    if len(prices) <= period:
        return np.full_like(prices, 50.0, dtype=float)
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices, dtype=float)
    rsi[:period] = 50.0
    rsi[period] = 100.0 - 100.0 / (1.0 + rs) if down != 0 else 100.0

    for i in range(period + 1, len(prices)):
        delta = deltas[i - 1]
        up_val = delta if delta > 0 else 0.0
        down_val = -delta if delta < 0 else 0.0
        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100.0 - 100.0 / (1.0 + rs) if down != 0 else 100.0
    return rsi

def calculate_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def calculate_bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(prices) < period:
        return prices.copy(), prices.copy(), prices.copy()
    mid = np.zeros_like(prices, dtype=float)
    std = np.zeros_like(prices, dtype=float)
    for i in range(len(prices)):
        if i < period - 1:
            mid[i] = prices[:i + 1].mean()
            std[i] = prices[:i + 1].std()
        else:
            window = prices[i - period + 1:i + 1]
            mid[i] = window.mean()
            std[i] = window.std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    if len(closes) < 2:
        return np.zeros_like(closes)
    tr = np.zeros_like(closes)
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    return calculate_ema(tr, period)

def calculate_vol_sma(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    sma = np.zeros_like(volumes, dtype=float)
    for i in range(len(volumes)):
        start_idx = max(0, i - period + 1)
        sma[i] = volumes[start_idx:i + 1].mean()
    return sma

def compute_technical_summary(series: OHLCVSeries) -> Optional[TechnicalSummary]:
    if len(series) < 15:
        return None
    closes = series.closes_np
    highs = series.highs_np
    lows = series.lows_np
    opens = series.opens_np
    volumes = series.volumes_np

    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200) if len(closes) >= 100 else None

    rsi14 = calculate_rsi(closes, 14)
    macd, signal, hist = calculate_macd(closes, 12, 26, 9)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(closes, 20, 2.0)
    atr = calculate_atr(highs, lows, closes, 14)
    vol_sma = calculate_vol_sma(volumes, 20)

    cur_price = float(closes[-1])
    prev_close = float(closes[-2]) if len(closes) >= 2 else cur_price
    change = cur_price - prev_close
    change_pct = (change / prev_close) * 100.0 if prev_close != 0 else 0.0

    cur_vol = int(volumes[-1])
    cur_vol_sma = float(vol_sma[-1])
    vol_ratio = (cur_vol / cur_vol_sma) if cur_vol_sma > 0 else 1.0

    # Trend logic
    if cur_price > ema21[-1] and ema21[-1] > ema50[-1]:
        trend = "UPTREND"
    elif cur_price < ema21[-1] and ema21[-1] < ema50[-1]:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    # RSI status
    if rsi14[-1] < 35:
        rsi_status = "OVERSOLD"
    elif rsi14[-1] > 70:
        rsi_status = "OVERBOUGHT"
    else:
        rsi_status = "NEUTRAL"

    # MACD status
    if len(hist) >= 2:
        if hist[-2] < 0 and hist[-1] >= 0:
            macd_status = "BULLISH_CROSS"
        elif hist[-2] > 0 and hist[-1] <= 0:
            macd_status = "BEARISH_CROSS"
        elif hist[-1] >= 0:
            macd_status = "BULLISH"
        else:
            macd_status = "BEARISH"
    else:
        macd_status = "NEUTRAL"

    # Composite signal
    if trend == "UPTREND" and (macd_status in ("BULLISH_CROSS", "BULLISH")) and vol_ratio >= 1.2:
        composite = "MUA MẠNH"
    elif rsi_status == "OVERSOLD" or cur_price <= bb_lower[-1] * 1.01:
        composite = "THEO DÕI MUA"
    elif rsi_status == "OVERBOUGHT" or cur_price >= bb_upper[-1]:
        composite = "CẢNH BÁO BÁN"
    elif trend == "DOWNTREND" and macd_status == "BEARISH":
        composite = "BÁN"
    else:
        composite = "TRUNG LẬP"

    return TechnicalSummary(
        symbol=series.symbol,
        price=cur_price,
        change=round(change, 2),
        change_pct=round(change_pct, 2),
        open=float(opens[-1]),
        high=float(highs[-1]),
        low=float(lows[-1]),
        volume=cur_vol,
        vol_sma20=round(cur_vol_sma, 0),
        vol_ratio=round(vol_ratio, 2),
        ema9=round(float(ema9[-1]), 2),
        ema21=round(float(ema21[-1]), 2),
        ema50=round(float(ema50[-1]), 2),
        ema200=round(float(ema200[-1]), 2) if ema200 is not None else None,
        rsi14=round(float(rsi14[-1]), 1),
        macd=round(float(macd[-1]), 2),
        macd_signal=round(float(signal[-1]), 2),
        macd_hist=round(float(hist[-1]), 2),
        bb_upper=round(float(bb_upper[-1]), 2),
        bb_middle=round(float(bb_mid[-1]), 2),
        bb_lower=round(float(bb_lower[-1]), 2),
        atr14=round(float(atr[-1]), 2),
        trend=trend,
        rsi_status=rsi_status,
        macd_status=macd_status,
        composite_signal=composite
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_calculator.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add indicators/models.py indicators/calculator.py tests/test_calculator.py
git commit -m "feat(indicators): implement pure NumPy vector technical indicators calculator"
```

---

### Task 5: Technical Summary Builder & Market Scanner

**Files:**
- Create: `indicators/scanner.py`
- Test: `tests/test_scanner.py`

**Interfaces:**
- Consumes: `indicators/models.py` (`TechnicalSummary`).
- Produces: `scan_vn30_market`, `ScanResults`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scanner.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_scanner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'indicators.scanner'`

- [ ] **Step 3: Write minimal implementation**

```python
# indicators/scanner.py
from pydantic import BaseModel
from typing import Dict, List
from indicators.models import TechnicalSummary

class ScanResults(BaseModel):
    breakout: List[TechnicalSummary] = []
    oversold: List[TechnicalSummary] = []
    overbought: List[TechnicalSummary] = []
    strong_trend: List[TechnicalSummary] = []

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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_scanner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add indicators/scanner.py tests/test_scanner.py
git commit -m "feat(indicators): implement scan_vn30_market filtering engine"
```

---

### Task 6: In-Memory Trading State Market Extensions

**Files:**
- Modify: `core/state.py`
- Test: `tests/test_market_state.py`

**Interfaces:**
- Consumes: `market/models.py`, `indicators/models.py`.
- Produces: `TradingState.vn30_candles`, `TradingState.vn30_summaries`, `TradingState.set_market_data`, `TradingState.get_summary`, `TradingState.get_top_movers`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_state.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_state.py -v`
Expected: FAIL with `AttributeError: 'TradingState' object has no attribute 'vn30_summaries'`

- [ ] **Step 3: Write minimal implementation**

Update `core/state.py`:
```python
# in core/state.py
from typing import Dict, List, Optional, Tuple
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary

class TradingState:
    def __init__(self):
        # existing fields...
        self.account: Optional[AccountInfo] = None
        self.balance: Optional[AccountBalance] = None
        self.positions: List[AccountPosition] = []
        self.is_connected: bool = False
        self.latency_ms: float = 0.0
        self.last_sync_time: float = 0.0
        self.mode: str = "READ_ONLY"

        # Market data additions
        self.vn30_candles: Dict[str, OHLCVSeries] = {}
        self.vn30_summaries: Dict[str, TechnicalSummary] = {}
        self.last_market_sync_time: float = 0.0

    def set_market_data(self, candles: Dict[str, OHLCVSeries], summaries: Dict[str, TechnicalSummary]):
        self.vn30_candles = candles
        self.vn30_summaries = summaries
        self.last_market_sync_time = time.time()

    def get_summary(self, symbol: str) -> Optional[TechnicalSummary]:
        return self.vn30_summaries.get(symbol.upper())

    def get_top_movers(self, limit: int = 5) -> Tuple[List[TechnicalSummary], List[TechnicalSummary]]:
        all_items = list(self.vn30_summaries.values())
        gainers = sorted(all_items, key=lambda x: x.change_pct, reverse=True)[:limit]
        losers = sorted(all_items, key=lambda x: x.change_pct)[:limit]
        return gainers, losers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/state.py tests/test_market_state.py
git commit -m "feat(state): extend TradingState with VN30 market data and lookup helpers"
```

---

### Task 7: Market Data Background Scheduler Job & Alerts

**Files:**
- Modify: `core/scheduler.py`
- Modify: `main.py`
- Test: `tests/test_market_scheduler.py`

**Interfaces:**
- Consumes: `market/client.py`, `indicators/calculator.py`, `core/state.py`, `storage/repository.py`, `bot/notifier.py`.
- Produces: `sync_market_data_job`, updated `setup_scheduler`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_scheduler.py
import pytest
from core.state import TradingState
from market.mock_client import MockMarketClient
from storage.db import init_db
from storage.repository import Repository
from core.scheduler import sync_market_data_job

@pytest.mark.asyncio
async def test_sync_market_data_job(tmp_path):
    db_file = str(tmp_path / "test_market_sched.db")
    await init_db(db_file)
    repo = Repository(db_file)
    state = TradingState()
    client = MockMarketClient()

    await sync_market_data_job(client, state, repo, symbols=["FPT", "HPG"])

    assert "FPT" in state.vn30_summaries
    assert "HPG" in state.vn30_summaries
    assert state.last_market_sync_time > 0

    saved_fpt = await repo.get_candles("FPT", limit=10)
    assert len(saved_fpt) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_scheduler.py -v`
Expected: FAIL with `ImportError: cannot import name 'sync_market_data_job' from 'core.scheduler'`

- [ ] **Step 3: Write minimal implementation**

Update `core/scheduler.py`:
```python
# in core/scheduler.py
from config.constants import VN30_SYMBOLS
from indicators.calculator import compute_technical_summary

async def sync_market_data_job(market_client, state, repo, notifier=None, symbols=None):
    if not market_client:
        return
    target_symbols = symbols or VN30_SYMBOLS
    try:
        candles_dict = await market_client.get_all_vn30_candles(target_symbols)
        summaries_dict = {}
        for sym, series in candles_dict.items():
            if len(series) > 0:
                await repo.save_candles(sym, series)
                summary = compute_technical_summary(series)
                if summary:
                    summaries_dict[sym] = summary
                    # Check real-time alert conditions if notifier provided and market open
                    if notifier and MarketHours.is_trading_time():
                        if summary.vol_ratio >= 2.0 and summary.change_pct >= 2.5:
                            alert_msg = (
                                f"🚀 **CẢNH BÁO ĐỘT BIẾN KHỐI LƯỢNG: {sym}**\n"
                                f"• Thị giá: `{summary.price:,.0f} đ` (`{summary.change_pct:+.2f}%`)\n"
                                f"• Khối lượng: `{summary.volume:,}` (Đạt `{summary.vol_ratio:.1f}x` TB20)\n"
                                f"• RSI (14): `{summary.rsi14:.1f}` | MACD: `{summary.macd_status}`"
                            )
                            await notifier.send_alert("Tín Hiệu Đột Biến VN30", alert_msg, level="INFO")

        state.set_market_data(candles_dict, summaries_dict)
        logger.info(f"Market sync complete: {len(summaries_dict)}/{len(target_symbols)} VN30 tickers calculated.")
    except Exception as e:
        logger.error(f"Market sync job failed: {e}")
        await repo.log_audit("ERROR", "MARKET_SYNC", f"Sync failed: {e}")
```

Update `setup_scheduler` to register `sync_market_data_job` (every 3 minutes) and wire `market_client` in `main.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_scheduler.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/scheduler.py main.py tests/test_market_scheduler.py
git commit -m "feat(scheduler): implement periodic VN30 market sync job and breakout alerts"
```

---

### Task 8: Telegram Bot Market Handlers & Keyboard UI

**Files:**
- Create: `bot/handlers/market.py`
- Modify: `bot/keyboards.py`
- Modify: `bot/app.py`
- Test: `tests/test_market_handlers.py`

**Interfaces:**
- Consumes: `core/state.py`, `indicators/scanner.py`, `aiogram`.
- Produces: `/quote`, `/indicators`, `/scan`, `/vn30` commands, updated keyboard.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from bot.handlers.market import cmd_quote, cmd_indicators, cmd_scan, cmd_vn30
from core.state import TradingState
from indicators.models import TechnicalSummary

def make_test_summary(symbol="FPT", price=66.6):
    return TechnicalSummary(
        symbol=symbol, price=price, change=1.2, change_pct=1.8, open=65.5, high=67.0, low=65.2,
        volume=4500000, vol_sma20=3200000, vol_ratio=1.4, ema9=65.8, ema21=64.5, ema50=62.0,
        rsi14=62.5, macd=0.8, macd_signal=0.5, macd_hist=0.3, bb_upper=68.0, bb_middle=64.5,
        bb_lower=61.0, atr14=1.2, trend="UPTREND", rsi_status="NEUTRAL", macd_status="BULLISH",
        composite_signal="MUA MẠNH"
    )

@pytest.mark.asyncio
async def test_quote_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT")})
    
    msg = MagicMock(spec=Message)
    msg.text = "/quote FPT"
    msg.answer = AsyncMock()
    
    await cmd_quote(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "FPT" in reply_text
    assert "66.6" in reply_text

@pytest.mark.asyncio
async def test_scan_command():
    state = TradingState()
    state.set_market_data({}, {"FPT": make_test_summary("FPT")})
    
    msg = MagicMock(spec=Message)
    msg.text = "/scan"
    msg.answer = AsyncMock()
    
    await cmd_scan(msg, state)
    assert msg.answer.called
    reply_text = msg.answer.call_args[0][0]
    assert "KẾT QUẢ QUÉT" in reply_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\pytest tests/test_market_handlers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers.market'`

- [ ] **Step 3: Write minimal implementation**

Create `bot/handlers/market.py`:
- Formats `/quote <SYMBOL>` with price, change, volume, ratio.
- Formats `/indicators <SYMBOL>` with full technical indicators, trend, and composite signal.
- Formats `/scan` grouping breakout, oversold, and overbought stocks.
- Formats `/vn30` showing top 5 gainers and losers.

Update `bot/keyboards.py`:
```python
def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="💰 Số dư"), KeyboardButton(text="📊 Vị thế")],
        [KeyboardButton(text="🔍 Quét VN30"), KeyboardButton(text="📈 Bảng giá VN30")],
        [KeyboardButton(text="🔄 Làm mới"), KeyboardButton(text="ℹ️ Trạng thái")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
```

Register market router in `bot/app.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.\.venv\Scripts\pytest tests/test_market_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add bot/handlers/market.py bot/keyboards.py bot/app.py tests/test_market_handlers.py
git commit -m "feat(bot): add /quote, /indicators, /scan, /vn30 commands and update menu keyboard"
```

---

### Task 9: End-to-End Integration & Live Smoke Test

**Files:**
- Create: `tests/test_market_smoke_live.py`
- Test: Full test suite (`pytest -v`)

**Interfaces:**
- Verifies live Entrade API ingestion, SQLite persistence, technical calculation, RAM cache, and live Telegram notification.

- [ ] **Step 1: Write live integration test**

```python
# tests/test_market_smoke_live.py
import pytest
from config.settings import settings
from config.constants import VN30_SYMBOLS
from storage.db import init_db
from storage.repository import Repository
from core.state import TradingState
from market.client import AsyncMarketClient
from indicators.calculator import compute_technical_summary
from indicators.scanner import scan_vn30_market
from bot.notifier import TelegramNotifier
from aiogram import Bot

@pytest.mark.asyncio
async def test_live_market_smoke_test(tmp_path):
    # 1. Init DB & Repo
    db_file = str(tmp_path / "smoke_market.db")
    await init_db(db_file)
    repo = Repository(db_file)
    state = TradingState()

    # 2. Query 3 representative VN30 stocks live from Entrade
    client = AsyncMarketClient()
    test_symbols = ["FPT", "HPG", "TCB"]
    candles_dict = await client.get_all_vn30_candles(test_symbols)
    
    assert len(candles_dict) == 3
    for s in test_symbols:
        series = candles_dict[s]
        assert len(series) > 0
        await repo.save_candles(s, series)

    # 3. Calculate indicators
    summaries = {}
    for s, series in candles_dict.items():
        summary = compute_technical_summary(series)
        assert summary is not None
        summaries[s] = summary

    state.set_market_data(candles_dict, summaries)
    assert state.get_summary("FPT") is not None

    # 4. Scan
    scan_results = scan_vn30_market(summaries)
    assert scan_results is not None

    # 5. Send Telegram live ping
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    notifier = TelegramNotifier(bot, settings.TELEGRAM_CHAT_ID)
    
    fpt_sum = summaries["FPT"]
    msg = (
        f"• Mã kiểm thử: FPT\n"
        f"• Thị giá: `{fpt_sum.price:,.1f} đ` (`{fpt_sum.change_pct:+.2f}%`)\n"
        f"• RSI (14): `{fpt_sum.rsi14:.1f}` ({fpt_sum.rsi_status})\n"
        f"• Xu hướng: `{fpt_sum.trend}`\n"
        f"• Tín hiệu: `{fpt_sum.composite_signal}`\n"
        f"• Trạng thái Phase 2: Sẵn sàng 100%!"
    )
    await notifier.send_alert("Kiểm Thử Dữ Liệu Thị Trường & Chỉ Báo", msg, level="INFO")

    await bot.session.close()
    await client.close()
```

- [ ] **Step 2: Run test suite to verify everything passes**

Run: `.\.venv\Scripts\pytest -v`
Expected: 19+ tests passed in under 15 seconds.

- [ ] **Step 3: Commit and Tag Release**

```bash
git add tests/test_market_smoke_live.py
git commit -m "feat(test): add Phase 2 live market smoke test and complete verification"
git tag -a v0.2.0-indicators -m "Phase 2 Market Data Feed & Indicator Engine Release"
```
