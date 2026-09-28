import aiosqlite
import os

SCHEMA = """
CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_no TEXT NOT NULL,
    total_cash REAL NOT NULL,
    available_cash REAL NOT NULL,
    total_debt REAL DEFAULT 0,
    withdrawable_cash REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS positions_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    account_no TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    cost_price REAL NOT NULL,
    market_price REAL NOT NULL,
    unrealized_pnl REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    level TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS paper_account (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    initial_balance REAL NOT NULL DEFAULT 5000000.0,
    cash_balance REAL NOT NULL DEFAULT 5000000.0,
    auto_trade_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    total_quantity INTEGER NOT NULL DEFAULT 0,
    available_quantity INTEGER NOT NULL DEFAULT 0,
    avg_buy_price REAL NOT NULL DEFAULT 0.0,
    highest_price REAL NOT NULL DEFAULT 0.0,
    tp1_taken INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_settlement_tranches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    buy_date TEXT NOT NULL,
    settle_date TEXT NOT NULL,
    is_settled INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    order_type TEXT NOT NULL DEFAULT 'MP',
    price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'FILLED',
    fee REAL NOT NULL DEFAULT 0.0,
    tax REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    tax REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0.0,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_news (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL,
    source TEXT NOT NULL,
    symbols TEXT,
    sentiment_score REAL NOT NULL DEFAULT 0.0,
    sentiment_label TEXT NOT NULL DEFAULT 'NEUTRAL',
    is_severe_negative INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_news_created ON market_news(created_at DESC);

CREATE TABLE IF NOT EXISTS corporate_events (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    ex_date TEXT,
    record_date TEXT,
    event_type TEXT NOT NULL DEFAULT 'OTHER',
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'CafeF Official / CBTT',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_sym_ex ON corporate_events(symbol, ex_date);
CREATE INDEX IF NOT EXISTS idx_events_ex_date ON corporate_events(ex_date);

CREATE TABLE IF NOT EXISTS position_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    adjustment_type TEXT NOT NULL,
    ratio REAL NOT NULL DEFAULT 0.0,
    cash_per_share REAL NOT NULL DEFAULT 0.0,
    old_quantity INTEGER NOT NULL,
    new_quantity INTEGER NOT NULL,
    old_avg_price REAL NOT NULL,
    new_avg_price REAL NOT NULL,
    old_highest_price REAL NOT NULL,
    new_highest_price REAL NOT NULL,
    applied_date TEXT NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_adj_sym ON position_adjustments(symbol);
CREATE INDEX IF NOT EXISTS idx_adj_date ON position_adjustments(applied_date);
"""

async def init_db(db_path: str = "storage/bot.db"):
    dir_name = os.path.dirname(os.path.abspath(db_path))
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=10000;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.executescript(SCHEMA)
        # Migration for existing databases: ensure tp1_taken column exists
        try:
            await db.execute("ALTER TABLE paper_positions ADD COLUMN tp1_taken INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # Already exists
        await db.commit()

