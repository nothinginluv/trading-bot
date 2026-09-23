# Phase 3: Strategy Engine & Paper Trading Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a simulated paper trading broker and strategy engine running dual breakout/pullback strategies on VN30 daily candles with 5,000,000 VNĐ virtual capital, round/odd lot sizing, realistic fee/tax simulation, and T+2 settlement.

**Architecture:** Pure Python vector strategy evaluator (`strategy/signals.py`), flexible risk & position sizing (`strategy/risk.py`), SQLite-backed paper broker matching engine (`strategy/paper_engine.py` & `storage/db.py`), scheduled auto-trading evaluator in `core/scheduler.py`, and interactive Telegram commands in `bot/handlers/paper.py`.

**Tech Stack:** Python 3.12, SQLite (`aiosqlite`), NumPy, Pydantic, APScheduler, Aiogram 3.x, Pytest (`pytest-asyncio`).

**Spec:** [docs/superpowers/specs/2026-09-23-phase-3-strategy-and-paper-trading-design.md](file:///d:/TradingBot/docs/superpowers/specs/2026-09-23-phase-3-strategy-and-paper-trading-design.md)

---

## Global Constraints

- Initial capital: 5,000,000.0 VNĐ (`initial_balance`).
- Lot sizing: Both round lots (multiples of 100) and odd lots (1 to 99) supported.
- Fees & Taxes: Buy fee = 0.15%, Sell fee = 0.15% + 0.10% tax = 0.25%.
- Settlement cycle: Default T+2 (pending settlement table tracks shares until Day T+2).
- Auto-trade: Enabled by default (`auto_trade_enabled = True`), trades as long as available cash >= cost of buying >= 1 share (+ fee).
- Stop loss: -5.0% hard stop from avg_buy_price. Take profit: +8.0% (or +7.0% if RSI > 75). Trailing stop: 2.0% pullback from peak once profit reaches +5.0%.
- Zero live order API execution: 100% paper trading in SQLite.
- Telegram Admin Whitelist: Only user ID 7385637982.
- Natural Vietnamese diacritics on all bot outputs.

---

## Review Focus

1. **High stock price relative to small cash**: If FPT is at 130,000đ and remaining cash is only 300,000đ, odd-lot sizing must calculate 2 shares, and if cash < 1 share cost, safely reject with clear message without crashing.
2. **Attempting to sell unsettled shares before T+2**: Engine must strictly check `available_quantity` and block selling of `pending_settlement` tranches while still updating position market value.
3. **Trailing stop high-water mark tracking**: If price rises then falls, `highest_price` must never decrease and trailing stop triggers when `price <= highest_price * 0.98`.
4. **Multiple buys of same symbol**: Position average buy price (`avg_buy_price`) must compute accurate volume-weighted average price (VWAP) across all tranches.
5. **Reset account safety**: `/reset_paper` must wipe positions and tranches, reset cash to 5,000,000 VNĐ cleanly without foreign key / deadlock issues in SQLite.

---

## Task Breakdown

### Task 1: Strategy & Paper Data Models (`strategy/models.py`)

**Files:**
- Create: `strategy/__init__.py`
- Create: `strategy/models.py`
- Test: `tests/test_strategy_models.py`

**Interfaces:**
- Produces: `SignalType`, `StrategyName`, `Signal`, `OrderSide`, `OrderStatus`, `OrderType`, `PaperOrder`, `SettlementTranche`, `PaperPosition`, `PaperAccount`.

- [ ] **Step 1: Write failing test for strategy models**

```python
# tests/test_strategy_models.py
from datetime import datetime
from strategy.models import (
    SignalType, StrategyName, Signal,
    OrderSide, OrderStatus, OrderType,
    PaperOrder, SettlementTranche, PaperPosition, PaperAccount
)

def test_signal_model_creation():
    sig = Signal(
        symbol="HPG",
        signal_type=SignalType.BUY,
        strategy=StrategyName.BREAKOUT,
        price=26500.0,
        confidence=0.85,
        reason="Giá vượt EMA21 kèm khối lượng lớn"
    )
    assert sig.symbol == "HPG"
    assert sig.signal_type == SignalType.BUY
    assert sig.price == 26500.0

def test_paper_order_supports_odd_lot():
    order = PaperOrder(
        order_id="ORD-001",
        symbol="FPT",
        side=OrderSide.BUY,
        quantity=15,  # Odd lot
        price=130000.0,
        order_type=OrderType.MP,
        status=OrderStatus.FILLED,
        fee=2925.0
    )
    assert order.quantity == 15
    assert order.side == OrderSide.BUY

def test_paper_account_defaults():
    acc = PaperAccount(cash_balance=5000000.0)
    assert acc.initial_balance == 5000000.0
    assert acc.cash_balance == 5000000.0
    assert acc.auto_trade_enabled is True
    assert acc.nav == 5000000.0
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_strategy_models.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy')

- [ ] **Step 3: Implement data models in `strategy/models.py`**

```python
# strategy/__init__.py
"""Strategy and Paper Trading engine module."""
```

```python
# strategy/models.py
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field

class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class StrategyName(str, Enum):
    BREAKOUT = "BREAKOUT"
    PULLBACK = "PULLBACK"
    MANUAL = "MANUAL"

class Signal(BaseModel):
    symbol: str
    signal_type: SignalType
    strategy: StrategyName
    price: float
    confidence: float = 1.0
    reason: str
    timestamp: datetime = Field(default_factory=datetime.now)

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class OrderType(str, Enum):
    MP = "MP"  # Market Price
    LO = "LO"  # Limit Order

class PaperOrder(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    order_type: OrderType = OrderType.MP
    status: OrderStatus = OrderStatus.FILLED
    fee: float = 0.0
    tax: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)
    matched_at: Optional[datetime] = None

class SettlementTranche(BaseModel):
    id: Optional[int] = None
    symbol: str
    quantity: int
    buy_date: str   # YYYY-MM-DD
    settle_date: str # YYYY-MM-DD (T+2)
    is_settled: bool = False
    created_at: datetime = Field(default_factory=datetime.now)

class PaperPosition(BaseModel):
    symbol: str
    total_quantity: int = 0
    available_quantity: int = 0
    avg_buy_price: float = 0.0
    highest_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    updated_at: datetime = Field(default_factory=datetime.now)

class PaperAccount(BaseModel):
    initial_balance: float = 5_000_000.0
    cash_balance: float = 5_000_000.0
    stock_value: float = 0.0
    nav: float = 5_000_000.0
    total_realized_pnl: float = 0.0
    auto_trade_enabled: bool = True
    updated_at: datetime = Field(default_factory=datetime.now)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_strategy_models.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**
```bash
git add strategy/ tests/test_strategy_models.py
git commit -m "feat(strategy): add strategy and paper trading data models"
```

---

### Task 2: Strategy Signal Generator (`strategy/signals.py`)

**Files:**
- Create: `strategy/signals.py`
- Test: `tests/test_strategy_signals.py`

**Interfaces:**
- Consumes: `market.models.OHLCVSeries`, `indicators.models.TechnicalSummary`, `strategy.models.Signal`, `SignalType`, `StrategyName`.
- Produces: `evaluate_breakout_signal(...) -> Optional[Signal]`, `evaluate_pullback_signal(...) -> Optional[Signal]`, `scan_signals(series, summary) -> Optional[Signal]`.

- [ ] **Step 1: Write failing test for strategy signals**

```python
# tests/test_strategy_signals.py
import pytest
from market.models import Candle, OHLCVSeries
from indicators.calculator import VectorIndicatorCalculator
from strategy.signals import evaluate_breakout_signal, evaluate_pullback_signal, scan_signals
from strategy.models import SignalType, StrategyName

def _create_synthetic_series(num_candles: int = 60, uptrend: bool = True) -> OHLCVSeries:
    candles = []
    base_price = 20000.0
    for i in range(num_candles):
        if uptrend:
            close = base_price + i * 200.0
            open_ = close - 50.0
            high = close + 100.0
            low = open_ - 50.0
            volume = 1_000_000 if i < num_candles - 1 else 2_500_000  # Vol surge on last bar
        else:
            close = base_price - i * 100.0
            open_ = close + 50.0
            high = open_ + 50.0
            low = close - 50.0
            volume = 500_000
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{i+1:02d}",
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume
        ))
    return OHLCVSeries(symbol="HPG", resolution="1D", candles=candles)

def test_breakout_signal_generation():
    series = _create_synthetic_series(num_candles=60, uptrend=True)
    summary = VectorIndicatorCalculator.calculate_all(series)
    assert summary is not None
    
    signal = evaluate_breakout_signal(series, summary)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
    assert signal.strategy == StrategyName.BREAKOUT
    assert signal.symbol == "HPG"
    assert "Breakout" in signal.reason

def test_pullback_signal_generation():
    # Construct a series in an uptrend that pulls back to EMA21 with RSI ~35-40
    series = _create_synthetic_series(num_candles=60, uptrend=True)
    # Adjust last 3 candles to pull back
    summary = VectorIndicatorCalculator.calculate_all(series)
    # Signal should be None or validated cleanly
    signal = evaluate_pullback_signal(series, summary)
    # Verify return type is Optional[Signal]
    assert signal is None or signal.signal_type == SignalType.BUY
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_strategy_signals.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy.signals')

- [ ] **Step 3: Implement `strategy/signals.py`**

```python
# strategy/signals.py
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
        
    # 2. Momentum Filter: MACD bullish cross & hist > 0
    if not (summary.macd_hist and summary.macd_hist > 0):
        return None
    if summary.macd_line is not None and summary.macd_signal is not None:
        if summary.macd_line <= summary.macd_signal:
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
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_strategy_signals.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**
```bash
git add strategy/signals.py tests/test_strategy_signals.py
git commit -m "feat(strategy): implement breakout and pullback signal generator"
```

---

### Task 3: SQLite Paper Database Storage (`storage/db.py`, `storage/repository.py`)

**Files:**
- Modify: `storage/db.py`
- Modify: `storage/repository.py`
- Test: `tests/test_paper_storage.py`

**Interfaces:**
- Produces: `init_paper_account()`, `get_paper_account()`, `update_paper_account_balances()`, `upsert_paper_position()`, `get_paper_positions()`, `get_paper_position()`, `add_settlement_tranche()`, `settle_mature_tranches()`, `record_paper_order()`, `record_paper_trade()`, `reset_paper_account()`.

- [ ] **Step 1: Write failing test for paper database operations**

```python
# tests/test_paper_storage.py
import pytest
import aiosqlite
from storage.db import DatabaseManager
from storage.repository import PaperTradingRepository
from strategy.models import OrderSide, OrderStatus, OrderType, PaperOrder

@pytest.mark.asyncio
async def test_paper_repository_lifecycle():
    db = DatabaseManager(":memory:")
    await db.initialize()
    repo = PaperTradingRepository(db)
    
    # 1. Initialize account
    account = await repo.get_or_create_account(initial_capital=5000000.0)
    assert account.initial_balance == 5000000.0
    assert account.cash_balance == 5000000.0
    assert account.auto_trade_enabled is True
    
    # 2. Add position and tranche
    await repo.add_settlement_tranche("FPT", quantity=15, buy_date="2026-09-20", settle_date="2026-09-22")
    await repo.upsert_position("FPT", total_qty=15, available_qty=0, avg_price=130000.0, highest_price=130000.0)
    
    pos = await repo.get_position("FPT")
    assert pos is not None
    assert pos.symbol == "FPT"
    assert pos.total_quantity == 15
    assert pos.available_quantity == 0
    
    # 3. Settle tranches on day >= 2026-09-22
    settled_qty = await repo.settle_mature_tranches(current_date="2026-09-23")
    assert settled_qty == 15
    
    pos_after = await repo.get_position("FPT")
    assert pos_after.available_quantity == 15
    
    # 4. Record order & trade
    order = PaperOrder(
        order_id="TEST-ORD-1",
        symbol="FPT",
        side=OrderSide.BUY,
        quantity=15,
        price=130000.0,
        fee=2925.0
    )
    await repo.record_order(order)
    await repo.record_trade(order.order_id, "FPT", OrderSide.BUY, 15, 130000.0, 2925.0, 0.0, 0.0)
    
    # 5. Reset account
    await repo.reset_account(reset_balance=5000000.0)
    acc_reset = await repo.get_or_create_account()
    assert acc_reset.cash_balance == 5000000.0
    positions = await repo.get_positions()
    assert len(positions) == 0
    
    await db.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_paper_storage.py -v`
Expected: FAIL (AttributeError or ImportError)

- [ ] **Step 3: Update `storage/db.py` with Paper Trading tables**
Add tables `paper_account`, `paper_positions`, `paper_settlement_tranches`, `paper_orders`, `paper_trades` into `storage/db.py` initialization SQL.

- [ ] **Step 4: Implement `PaperTradingRepository` in `storage/repository.py`**
Implement async CRUD operations:
- `get_or_create_account()`
- `update_account_balance()`
- `set_auto_trade(enabled: bool)`
- `get_positions()`
- `get_position(symbol: str)`
- `upsert_position(symbol, total_qty, available_qty, avg_price, highest_price)`
- `delete_position(symbol)`
- `add_settlement_tranche(symbol, quantity, buy_date, settle_date)`
- `settle_mature_tranches(current_date: str)`
- `record_order(order: PaperOrder)`
- `record_trade(order_id, symbol, side, quantity, price, fee, tax, realized_pnl)`
- `reset_account(reset_balance: float = 5000000.0)`

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_paper_storage.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add storage/ tests/test_paper_storage.py
git commit -m "feat(storage): add paper trading tables and repository"
```

---

### Task 4: Risk Management & Position Sizing (`strategy/risk.py`)

**Files:**
- Create: `strategy/risk.py`
- Test: `tests/test_risk_management.py`

**Interfaces:**
- Consumes: `PaperPosition`, `PaperAccount`.
- Produces:
  - `calculate_position_size(available_cash: float, nav: float, price: float) -> int`
  - `check_exit_conditions(position: PaperPosition, current_price: float, current_rsi: Optional[float] = None) -> tuple[bool, str]`

- [ ] **Step 1: Write failing test for risk management**

```python
# tests/test_risk_management.py
from strategy.models import PaperPosition
from strategy.risk import calculate_position_size, check_exit_conditions

def test_position_sizing_round_and_odd_lot():
    # 5,000,000 VND capital, target ~ 2,500,000 VND
    # Case 1: HPG at 26,000đ -> 2,500,000 / 26,000 ~ 96 shares -> Odd lot = 96
    qty_odd = calculate_position_size(available_cash=5000000.0, nav=5000000.0, price=26000.0)
    assert qty_odd == 96
    
    # Case 2: Available cash = 4,000,000đ, price = 15,000đ -> ~2,000,000 / 15,000 = 133 shares -> Round lot = 100
    qty_round = calculate_position_size(available_cash=4000000.0, nav=4000000.0, price=15000.0)
    assert qty_round == 100
    
    # Case 3: Available cash = 200,000đ, FPT price = 130,000đ -> 1 share
    qty_min = calculate_position_size(available_cash=200000.0, nav=5000000.0, price=130000.0)
    assert qty_min == 1
    
    # Case 4: Insufficient cash for even 1 share
    qty_zero = calculate_position_size(available_cash=50000.0, nav=5000000.0, price=130000.0)
    assert qty_zero == 0

def test_exit_conditions_stop_loss():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=26000.0
    )
    # -5% from 26,000 = 24,700
    should_exit, reason = check_exit_conditions(pos, current_price=24600.0)
    assert should_exit is True
    assert "Cắt lỗ" in reason

def test_exit_conditions_take_profit():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=26000.0
    )
    # +8% from 26,000 = 28,080
    should_exit, reason = check_exit_conditions(pos, current_price=28100.0)
    assert should_exit is True
    assert "Chốt lời" in reason

def test_exit_conditions_trailing_stop():
    pos = PaperPosition(
        symbol="HPG",
        total_quantity=100,
        available_quantity=100,
        avg_buy_price=26000.0,
        highest_price=28000.0  # +7.6% gain reached
    )
    # -2% from peak 28,000 = 27,440
    should_exit, reason = check_exit_conditions(pos, current_price=27400.0)
    assert should_exit is True
    assert "Trailing Stop" in reason
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_risk_management.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy.risk')

- [ ] **Step 3: Implement `strategy/risk.py`**

```python
# strategy/risk.py
import math
from typing import Optional, Tuple
from strategy.models import PaperPosition

def calculate_position_size(available_cash: float, nav: float, price: float) -> int:
    """
    Calculates the allowable share quantity given available cash and NAV.
    Supports both Round Lots (>= 100) and Odd Lots (1 to 99).
    Fee rate of 0.15% is accounted for.
    """
    if price <= 0:
        return 0
        
    fee_rate = 0.0015
    # Allocate up to NAV / 2 per position, bounded by available cash
    target_budget = min(available_cash, max(nav * 0.5, available_cash))
    
    # Raw affordable shares including fee
    raw_shares = int(target_budget // (price * (1.0 + fee_rate)))
    
    if raw_shares <= 0:
        # Check if available cash can buy at least 1 share
        if available_cash >= price * (1.0 + fee_rate):
            return 1
        return 0
        
    if raw_shares >= 100:
        # Round down to nearest 100 (Round Lot)
        return (raw_shares // 100) * 100
    else:
        # Odd Lot (1 to 99)
        return raw_shares

def check_exit_conditions(
    position: PaperPosition,
    current_price: float,
    current_rsi: Optional[float] = None
) -> Tuple[bool, str]:
    """
    Checks if a position triggers Stop Loss, Take Profit, or Trailing Stop.
    Returns (should_exit, reason).
    """
    if position.avg_buy_price <= 0 or current_price <= 0:
        return False, ""
        
    avg_price = position.avg_buy_price
    pnl_pct = (current_price - avg_price) / avg_price
    
    # 1. Hard Stop-Loss (-5.0%)
    if pnl_pct <= -0.05:
        return True, f"🚨 Cắt lỗ tự động (Stop Loss): Lỗ {pnl_pct*100:.2f}% (Giá {current_price:,.0f} so với giá vốn {avg_price:,.0f})."
        
    # 2. Take Profit (+8.0% baseline, or +7.0% if RSI > 75)
    tp_threshold = 0.07 if (current_rsi is not None and current_rsi > 75.0) else 0.08
    if pnl_pct >= tp_threshold:
        return True, f"🎯 Chốt lời tự động (Take Profit): Lãi {pnl_pct*100:.2f}% (Giá {current_price:,.0f} đạt mục tiêu TP {tp_threshold*100:.1f}%)."
        
    # 3. Dynamic Trailing Stop:
    # If position has ever achieved >= +5.0% gain
    peak_gain_pct = (position.highest_price - avg_price) / avg_price
    if peak_gain_pct >= 0.05 and position.highest_price > 0:
        # Trigger if price falls 2.0% from the peak
        trailing_stop_price = position.highest_price * 0.98
        if current_price <= trailing_stop_price:
            return True, (
                f"🛡️ Kích hoạt Trailing Stop: Giá giảm 2.0% từ đỉnh "
                f"({position.highest_price:,.0f} -> {current_price:,.0f}) để bảo toàn lợi nhuận (Lãi hiện tại: {pnl_pct*100:.2f}%)."
            )
            
    return False, ""
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_risk_management.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**
```bash
git add strategy/risk.py tests/test_risk_management.py
git commit -m "feat(strategy): implement risk management and lot sizing"
```

---

### Task 5: Paper Matching Engine (`strategy/paper_engine.py`)

**Files:**
- Create: `strategy/paper_engine.py`
- Test: `tests/test_paper_engine.py`

**Interfaces:**
- Consumes: `storage.repository.PaperTradingRepository`, `strategy.models.*`.
- Produces: `PaperEngine` class with:
  - `execute_buy(symbol, quantity, price, order_type) -> PaperOrder`
  - `execute_sell(symbol, quantity, price, order_type) -> PaperOrder`
  - `update_highest_prices(symbol_prices: dict[str, float])`
  - `get_account_summary() -> PaperAccount`
  - `settle_daily_tranches(date_str) -> int`

- [ ] **Step 1: Write failing test for PaperEngine**

```python
# tests/test_paper_engine.py
import pytest
from datetime import datetime
from storage.db import DatabaseManager
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.models import OrderStatus

@pytest.mark.asyncio
async def test_paper_engine_buy_and_sell_lifecycle():
    db = DatabaseManager(":memory:")
    await db.initialize()
    repo = PaperTradingRepository(db)
    engine = PaperEngine(repo)
    await engine.initialize(initial_capital=5000000.0)
    
    # 1. Execute BUY 10 shares of FPT at 130,000đ
    # Cost = 1,300,000 + 0.15% fee (1,950) = 1,301,950đ
    order_buy = await engine.execute_buy(symbol="FPT", quantity=10, price=130000.0)
    assert order_buy.status == OrderStatus.FILLED
    assert order_buy.fee == 1950.0
    
    acc = await engine.get_account_summary(current_prices={"FPT": 130000.0})
    assert acc.cash_balance == 5000000.0 - 1301950.0
    assert acc.stock_value == 1300000.0
    
    # Check position T+2
    pos = await repo.get_position("FPT")
    assert pos.total_quantity == 10
    assert pos.available_quantity == 0  # Not yet settled
    
    # Settle tranches for T+2
    today_str = datetime.now().strftime("%Y-%m-%d")
    await repo.settle_mature_tranches(current_date="2099-01-01")  # Future date ensures settlement
    
    # Now available_quantity = 10, execute SELL at 140,000đ (+7.69%)
    # Gross = 1,400,000. Fee = 0.15% (2,100). Tax = 0.1% (1,400). Net = 1,396,500đ
    order_sell = await engine.execute_sell(symbol="FPT", quantity=10, price=140000.0)
    assert order_sell.status == OrderStatus.FILLED
    assert order_sell.fee == 2100.0
    assert order_sell.tax == 1400.0
    
    acc_after = await engine.get_account_summary()
    assert acc_after.total_realized_pnl == (1396500.0 - 1300000.0)  # +96,500đ
    assert acc_after.cash_balance == (5000000.0 - 1301950.0 + 1396500.0)
    
    await db.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_paper_engine.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy.paper_engine')

- [ ] **Step 3: Implement `strategy/paper_engine.py`**
Implement `PaperEngine` with:
- `execute_buy`: Validates cash $\ge \text{cost}$, creates order, updates `paper_account.cash_balance`, computes volume-weighted average price for position, inserts T+2 settlement tranche (`settle_date` calculated by adding 2 business days), records order and trade.
- `execute_sell`: Validates available settled quantity $\ge$ sell quantity, deducts fee (0.15%) and tax (0.10%), records realized PnL, updates cash balance and position quantity.
- `get_account_summary`: Calculates NAV, current stock values based on current market prices.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_paper_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add strategy/paper_engine.py tests/test_paper_engine.py
git commit -m "feat(strategy): implement paper matching engine with fee, tax and T+2 settlement"
```

---

### Task 6: Autonomous Auto-Trader Service & Scheduler Integration (`strategy/auto_trader.py`, `core/scheduler.py`)

**Files:**
- Create: `strategy/auto_trader.py`
- Modify: `core/scheduler.py`
- Modify: `core/state.py`
- Test: `tests/test_auto_trader.py`

**Interfaces:**
- Consumes: `strategy.paper_engine.PaperEngine`, `strategy.signals.*`, `strategy.risk.*`, `market.client.AsyncMarketClient`, `core.state.TradingState`.
- Produces: `AutoTrader.process_cycle() -> list[str]` (returns alert messages sent to Telegram).

- [ ] **Step 1: Write failing test for AutoTrader service**

```python
# tests/test_auto_trader.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from strategy.auto_trader import AutoTrader
from strategy.paper_engine import PaperEngine
from storage.db import DatabaseManager
from storage.repository import PaperTradingRepository
from core.state import TradingState

@pytest.mark.asyncio
async def test_auto_trader_cycle():
    db = DatabaseManager(":memory:")
    await db.initialize()
    repo = PaperTradingRepository(db)
    engine = PaperEngine(repo)
    await engine.initialize(initial_capital=5000000.0)
    
    state = TradingState()
    notifier = AsyncMock()
    
    auto_trader = AutoTrader(engine=engine, state=state, notify_func=notifier)
    
    # Process cycle with empty state
    alerts = await auto_trader.process_cycle()
    assert isinstance(alerts, list)
    
    await db.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_auto_trader.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy.auto_trader')

- [ ] **Step 3: Implement `strategy/auto_trader.py`**
Implement logic:
1. Settle mature T+2 tranches for today.
2. Update `highest_price` for all open positions based on latest cache prices.
3. Check exit conditions (Stop Loss -5%, Take Profit +8%, Trailing Stop -2% from peak) for positions with `available_quantity > 0`. If triggered, call `engine.execute_sell()` and notify via Telegram.
4. If `account.auto_trade_enabled` is True:
   - Check if current held stocks count < 3.
   - If available cash can purchase $\ge 1$ share:
     - Scan VN30 summaries for BUY signals.
     - Pick top-scoring signal not already owned.
     - Calculate size via `calculate_position_size(...)`.
     - Call `engine.execute_buy()` and notify via Telegram.

- [ ] **Step 4: Wire AutoTrader into `core/scheduler.py`**
In `TradingScheduler`, instantiate `AutoTrader` and run `process_cycle()` after the market sync job finishes in session.

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_auto_trader.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add strategy/auto_trader.py core/scheduler.py core/state.py tests/test_auto_trader.py
git commit -m "feat(strategy): implement auto-trader service and wire into scheduler"
```

---

### Task 7: Telegram Paper Trading Handlers & Keyboards (`bot/handlers/paper.py`, `bot/keyboards.py`)

**Files:**
- Create: `bot/handlers/paper.py`
- Modify: `bot/keyboards.py`
- Modify: `main.py`
- Test: `tests/test_paper_bot_handlers.py`

**Interfaces:**
- Produces: Telegram commands `/paper`, `/signals`, `/buy_paper`, `/sell_paper`, `/autotrade_paper`, `/reset_paper`.

- [ ] **Step 1: Write failing test for Telegram handlers**

```python
# tests/test_paper_bot_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from bot.handlers.paper import cmd_paper, cmd_signals, cmd_autotrade_paper
from strategy.paper_engine import PaperEngine
from storage.db import DatabaseManager
from storage.repository import PaperTradingRepository
from core.state import TradingState

@pytest.mark.asyncio
async def test_cmd_paper_dashboard():
    db = DatabaseManager(":memory:")
    await db.initialize()
    repo = PaperTradingRepository(db)
    engine = PaperEngine(repo)
    await engine.initialize(5000000.0)
    state = TradingState()
    
    msg = MagicMock(spec=Message)
    msg.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=7385637982, type="private")
    msg.answer = AsyncMock()
    
    await cmd_paper(msg, engine, state)
    msg.answer.assert_called_once()
    assert "TÀI KHOẢN GIẢ LẬP" in msg.answer.call_args[0][0]
    assert "5,000,000" in msg.answer.call_args[0][0]
    
    await db.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_paper_bot_handlers.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'bot.handlers.paper')

- [ ] **Step 3: Implement `bot/handlers/paper.py`**
Implement message handlers with rich formatted Vietnamese text:
- `cmd_paper`: Renders NAV, Cash, Stocks value, Realized/Unrealized PnL, and position table with total vs available T+2 shares.
- `cmd_signals`: Scans VN30 tickers in cache, returns list of tickers with active Buy/Sell breakout or pullback signals.
- `cmd_buy_paper`: Parses `/buy_paper <SYMBOL> <QUANTITY> [PRICE]` (supports both round and odd lots).
- `cmd_sell_paper`: Parses `/sell_paper <SYMBOL> <QUANTITY> [PRICE]` (verifies settled quantity).
- `cmd_autotrade_paper`: Toggles auto trade on/off.
- `cmd_reset_paper`: Renders confirmation inline button to reset to 5M VND.

- [ ] **Step 4: Update `bot/keyboards.py` and register in `main.py`**
Add inline/reply buttons: `[💼 Danh mục Giả lập]`, `[🎯 Tín hiệu VN30]`, `[🤖 Auto-Trade On/Off]`. Register `paper_router` in `main.py`.

- [ ] **Step 5: Run test to verify it passes**
Run: `pytest tests/test_paper_bot_handlers.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add bot/handlers/paper.py bot/keyboards.py main.py tests/test_paper_bot_handlers.py
git commit -m "feat(bot): add paper trading commands /paper, /signals, /buy_paper, /sell_paper, /autotrade_paper"
```

---

### Task 8: End-to-End Paper Simulation & System Verification (`tests/test_paper_e2e.py`)

**Files:**
- Create: `tests/test_paper_e2e.py`
- Modify: `README.md`
- Test: Full Pytest test suite (`pytest`)

**Interfaces:**
- Validates the entire integrated pipeline: Signal -> Order sizing -> T+2 settlement -> Exit trigger -> PnL accounting.

- [ ] **Step 1: Write comprehensive end-to-end simulation test**

```python
# tests/test_paper_e2e.py
import pytest
from storage.db import DatabaseManager
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from strategy.models import OrderStatus
from core.state import TradingState
from market.models import Candle, OHLCVSeries
from indicators.calculator import VectorIndicatorCalculator

@pytest.mark.asyncio
async def test_full_paper_trading_pipeline():
    db = DatabaseManager(":memory:")
    await db.initialize()
    repo = PaperTradingRepository(db)
    engine = PaperEngine(repo)
    await engine.initialize(initial_capital=5000000.0)
    
    state = TradingState()
    
    # 1. Setup synthetic series with Breakout
    candles = []
    for i in range(50):
        c = 25000.0 + i * 200.0
        candles.append(Candle(
            timestamp=1700000000 + i * 86400,
            date_str=f"2026-01-{i+1:02d}",
            open=c - 100, high=c + 100, low=c - 100, close=c,
            volume=1000000 if i < 49 else 2500000
        ))
    series = OHLCVSeries(symbol="HPG", resolution="1D", candles=candles)
    summary = VectorIndicatorCalculator.calculate_all(series)
    state.update_candles("HPG", series)
    state.update_summary("HPG", summary)
    
    # 2. Run AutoTrader cycle -> should trigger BUY
    notifications = []
    async def capture_notify(text: str):
        notifications.append(text)
        
    trader = AutoTrader(engine=engine, state=state, notify_func=capture_notify)
    await trader.process_cycle()
    
    # Verify buy order executed
    pos = await repo.get_position("HPG")
    assert pos is not None
    assert pos.total_quantity > 0
    assert pos.available_quantity == 0  # Pending T+2
    
    # 3. Simulate passage of T+2 days
    await repo.settle_mature_tranches("2099-01-01")
    pos_settled = await repo.get_position("HPG")
    assert pos_settled.available_quantity == pos.total_quantity
    
    # 4. Trigger Take Profit (+10% gain)
    tp_price = pos.avg_buy_price * 1.10
    summary.current_price = tp_price
    state.update_summary("HPG", summary)
    
    # Next cycle should trigger Take-Profit SELL
    await trader.process_cycle()
    
    acc = await engine.get_account_summary()
    assert acc.total_realized_pnl > 0  # Profitable trade
    assert any("Chốt lời" in n for n in notifications)
    
    await db.close()
```

- [ ] **Step 2: Run full test suite**
Run: `pytest -v`
Expected: ALL tests pass across Phase 1, Phase 2, and Phase 3.

- [ ] **Step 3: Update documentation and release tagging**
Update `README.md` with new Paper Trading commands and architecture. Tag Git release `v0.3.0-paper`.

- [ ] **Step 4: Commit and tag**
```bash
git add README.md tests/test_paper_e2e.py
git commit -m "feat: complete Phase 3 strategy and paper trading simulation engine"
git tag -a v0.3.0-paper -m "Release v0.3.0 - Paper Trading Simulation Engine"
```
