# Phase 6: Market & Stock News Intelligence Engine (CafeF & Vietstock Combo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real-time market and stock news gathering from CafeF and Vietstock, financial sentiment scoring with Vietnamese financial lexicon, and combo decision matrix (Technical Indicators + News Sentiment) to veto bad-news entries and boost high-catalyst trades.

**Architecture:** Create `news/` package (`crawler.py`, `models.py`, `sentiment.py`), store articles in SQLite `market_news` table, schedule periodic 10-minute crawl jobs in `core/scheduler.py`, integrate sentiment veto checks into `strategy/auto_trader.py`, and expose `/news [symbol]` via `bot/handlers/news.py`.

**Tech Stack:** Python 3.12, HTTPX, SQLite / aiosqlite, Pydantic, APScheduler, Aiogram 3.x, Pytest.

---

## Global Constraints

- News sources: CafeF (`thi-truong-chung-khoan.chn`, `doanh-nghiep.chn`) and Vietstock (`chung-khoan.htm`, `doanh-nghiep.htm`).
- No external browser or heavy headless browser dependency: Use high-speed HTTPX async client with regex/HTML parsing.
- Financial Lexicon Sentiment: Ultra-fast local dictionary engine (< 5ms) for Vietnamese financial terms.
- Veto Logic: If a stock has negative sentiment $\le -0.3$ within 48h, technical BUY signals are vetoed.
- Telegram Admin Whitelist: Protected by Chat ID `7385637982`.
- Natural Vietnamese diacritics on all user-facing notifications.

---

## Tasks Breakdown

### Task 1: News Data Models, Crawler & SQLite Storage
- Files: `news/models.py`, `news/crawler.py`, `storage/db.py`, `storage/repository.py`
- Test: `tests/test_news_crawler.py`

### Task 2: Financial Sentiment Lexicon & Ticker Extractor
- Files: `news/sentiment.py`
- Test: `tests/test_news_sentiment.py`

### Task 3: Indicator + News Sentiment Combo Decision in Auto-Trader
- Files: `core/state.py`, `core/scheduler.py`, `strategy/auto_trader.py`
- Test: `tests/test_news_strategy_combo.py`

### Task 4: Telegram Bot News Commands & Dashboard
- Files: `bot/handlers/news.py`, `bot/keyboards.py`, `bot/app.py`
- Test: `tests/test_news_bot_handlers.py`
