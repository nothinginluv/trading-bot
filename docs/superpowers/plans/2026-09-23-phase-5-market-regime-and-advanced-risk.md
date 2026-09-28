# Phase 5: VN-Index Market Regime Filter & Dynamic ATR Risk Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a VN-Index Market Regime Filter to gate new buy positions during market corrections, dynamic volatility-adjusted Stop Loss & Take Profit thresholds using ATR(14), and a 2-Step Partial Take Profit (sell 50% at Target 1, move stop to breakeven, let remainder run with trailing stop).

**Architecture:** Extend `AsyncMarketClient` with automatic routing for index endpoints (`ohlcs/index`), update `TradingState` and `core/scheduler.py` with market regime classification (`BULLISH`, `SIDEWAYS`, `BEARISH`), refactor `strategy/risk.py` with dynamic ATR formulas and a two-stage `ExitDecision` structure, update `PaperTradingRepository` and SQLite schema for partial exit state (`tp1_taken`), and wire into `strategy/auto_trader.py` and Telegram handlers.

**Tech Stack:** Python 3.12, HTTPX, NumPy, SQLite / aiosqlite, Pydantic, APScheduler, Aiogram 3.x, Pytest.

---

## Global Constraints

- Index endpoint routing: `VNINDEX`, `VN30`, `HNXINDEX` use Entrade `/ohlcs/index` endpoint; stock symbols use `/ohlcs/stock`.
- Non-breaking database migration: Add column `tp1_taken INTEGER NOT NULL DEFAULT 0` to `paper_positions` gracefully without data loss.
- HOSE price collars & lot compliance: Odd-lots (1-99) and round-lots (multiples of 100) are respected during 50% partial sales.
- Capital safety gate: When `market_regime == "BEARISH"`, no new BUY positions are opened in both PAPER and LIVE modes. Position monitoring and SELL exits remain 100% active.
- Telegram Admin Whitelist: Protected by Chat ID `7385637982`.
- Natural Vietnamese diacritics on all user-facing notifications.

---

## Review Focus

1. **Index API response parsing**: Ensure `AsyncMarketClient.get_candles("VNINDEX")` correctly queries `ohlcs/index` and returns non-empty OHLCV candles.
2. **50% Partial Sale Lot Sizing**: Ensure `calculate_partial_exit_quantity` properly rounds to 100 for round-lot holdings and handles odd lots cleanly.
3. **Breakeven trigger**: After TP1 is executed (`tp1_taken=True`), if price falls back to cost price, the remaining position must trigger `BREAKEVEN` and fully exit.
4. **Trailing stop on remaining position**: After TP1 is executed, if the stock continues making new highs, trailing stop must track from the peak and trigger when falling by `trail_step`.
5. **AutoTrader Market Gate**: Ensure `AutoTrader` evaluates `market_regime` and refuses candidate buys when `BEARISH`, while position exits (SL/TP) continue uninterrupted.

---

## Task Breakdown

### Task 1: VN-Index Data Feed & Market Regime Classification
- Files: `market/client.py`, `core/state.py`, `core/scheduler.py`
- Test: `tests/test_market_regime.py`

### Task 2: Advanced Risk Management (ATR Dynamic SL/TP & 2-Step Partial TP)
- Files: `strategy/models.py`, `storage/db.py`, `storage/repository.py`, `strategy/risk.py`
- Test: `tests/test_dynamic_risk.py`

### Task 3: Auto-Trader Integration & Execution Dispatcher
- Files: `strategy/auto_trader.py`
- Test: `tests/test_auto_trader_regime.py`

### Task 4: Telegram Bot User Interface & Commands
- Files: `bot/handlers/basic.py`, `bot/handlers/market.py`
- Test: Manual verification with Telegram commands `/market` and `/scan`
