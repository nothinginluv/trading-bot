import math
from datetime import datetime
import aiosqlite
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

@asynccontextmanager
async def _connect_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA busy_timeout=10000;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        yield db

class Repository:
    def __init__(self, db_path: str = "storage/bot.db"):
        self.db_path = db_path

    async def save_balance_snapshot(self, account_no: str, total_cash: float, available_cash: float, total_debt: float, withdrawable_cash: float):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO account_snapshots (account_no, total_cash, available_cash, total_debt, withdrawable_cash)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_no, total_cash, available_cash, total_debt, withdrawable_cash)
            )
            await db.commit()

    async def get_latest_snapshot(self, account_no: str) -> Optional[Dict[str, Any]]:
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM account_snapshots WHERE account_no = ? ORDER BY id DESC LIMIT 1",
                (account_no,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def save_positions_snapshot(self, account_no: str, positions: list):
        async with _connect_db(self.db_path) as db:
            for p in positions:
                await db.execute(
                    """INSERT INTO positions_snapshot (account_no, symbol, quantity, cost_price, market_price, unrealized_pnl)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (account_no, p.symbol, p.tradeQuantity, p.costPrice, p.marketPrice, p.unrealizedPnl)
                )
            await db.commit()

    async def log_audit(self, level: str, source: str, message: str):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_logs (level, source, message) VALUES (?, ?, ?)",
                (level, source, message)
            )
            await db.commit()

    async def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def save_candles(self, symbol: str, series):
        if not series.candles:
            return
        import time
        now = time.time()
        async with _connect_db(self.db_path) as db:
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

    async def get_candles(self, symbol: str, limit: int = 150):
        from market.models import Candle, OHLCVSeries
        async with _connect_db(self.db_path) as db:
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

    async def save_news_articles(self, articles) -> int:
        import json
        inserted = 0
        async with _connect_db(self.db_path) as db:
            for a in articles:
                symbols_str = json.dumps(a.related_symbols) if hasattr(a, "related_symbols") else "[]"
                try:
                    await db.execute(
                        """INSERT INTO market_news (id, title, link, source, symbols, sentiment_score, sentiment_label, is_severe_negative)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                               symbols = excluded.symbols,
                               sentiment_score = excluded.sentiment_score,
                               sentiment_label = excluded.sentiment_label,
                               is_severe_negative = excluded.is_severe_negative""",
                        (
                            a.id, a.title, a.link, a.source, symbols_str,
                            a.sentiment_score, a.sentiment_label,
                            1 if a.is_severe_negative else 0
                        )
                    )
                    inserted += 1
                except Exception:
                    pass
            await db.commit()
        return inserted

    async def get_recent_news_for_symbol(self, symbol: str, limit: int = 10):
        from news.models import NewsArticle
        import json
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM market_news 
                   WHERE symbols LIKE ? 
                   ORDER BY created_at DESC 
                   LIMIT ?""",
                (f"%{symbol.upper()}%", limit)
            )
            rows = await cursor.fetchall()
            return [
                NewsArticle(
                    id=r["id"],
                    title=r["title"],
                    link=r["link"],
                    source=r["source"],
                    related_symbols=json.loads(r["symbols"]) if r["symbols"] else [],
                    sentiment_score=r["sentiment_score"],
                    sentiment_label=r["sentiment_label"],
                    is_severe_negative=bool(r["is_severe_negative"])
                )
                for r in rows
            ]

    async def get_latest_news(self, limit: int = 20):
        from news.models import NewsArticle
        import json
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM market_news ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            rows = await cursor.fetchall()
            return [
                NewsArticle(
                    id=r["id"],
                    title=r["title"],
                    link=r["link"],
                    source=r["source"],
                    related_symbols=json.loads(r["symbols"]) if r["symbols"] else [],
                    sentiment_score=r["sentiment_score"],
                    sentiment_label=r["sentiment_label"],
                    is_severe_negative=bool(r["is_severe_negative"])
                )
                for r in rows
            ]

    async def get_symbol_sentiment(self, symbol: str) -> float:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute(
                """SELECT AVG(sentiment_score) FROM market_news 
                   WHERE symbols LIKE ?""",
                (f"%{symbol.upper()}%",)
            )
            val = await cursor.fetchone()
            if val and val[0] is not None:
                return float(val[0])
            return 0.0

    async def save_corporate_events(self, events: List["CorporateEvent"]) -> int:
        from news.models import CorporateEvent
        inserted = 0
        async with _connect_db(self.db_path) as db:
            for ev in events:
                try:
                    await db.execute(
                        """INSERT INTO corporate_events (id, symbol, ex_date, record_date, event_type, content, source)
                           VALUES (?, ?, ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                               ex_date = excluded.ex_date,
                               record_date = excluded.record_date,
                               event_type = excluded.event_type,
                               content = excluded.content,
                               source = excluded.source""",
                        (
                            ev.id, ev.symbol.upper(), ev.ex_date, ev.record_date,
                            ev.event_type.value if hasattr(ev.event_type, "value") else str(ev.event_type),
                            ev.content, ev.source
                        )
                    )
                    inserted += 1
                except Exception:
                    pass
            await db.commit()
        return inserted

    async def get_upcoming_events(self, symbol: Optional[str] = None, from_date: Optional[str] = None, limit: int = 30) -> List["CorporateEvent"]:
        from news.models import CorporateEvent, EventType
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM corporate_events WHERE 1=1"
            params = []
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol.upper())
            if from_date:
                query += " AND (ex_date >= ? OR ex_date IS NULL OR ex_date = '')"
                params.append(from_date)
            query += " ORDER BY ex_date ASC, created_at DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(query, tuple(params))
            rows = await cursor.fetchall()
            events = []
            for r in rows:
                ev_type_val = r["event_type"]
                try:
                    ev_type = EventType(ev_type_val)
                except Exception:
                    ev_type = EventType.OTHER
                events.append(CorporateEvent(
                    id=r["id"],
                    symbol=r["symbol"],
                    ex_date=r["ex_date"],
                    record_date=r["record_date"],
                    event_type=ev_type,
                    content=r["content"],
                    source=r["source"]
                ))
            return events

    async def is_ex_date_near(self, symbol: str, target_date: str) -> bool:
        """Checks if target_date is an ex-dividend / ex-rights date (GDKHQ) for the symbol."""
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM corporate_events WHERE symbol = ? AND ex_date = ?",
                (symbol.upper(), target_date)
            )
            row = await cursor.fetchone()
            return bool(row and row[0] > 0)

    async def is_adjustment_applied(self, event_id: str) -> bool:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM position_adjustments WHERE event_id = ?", (event_id,))
            row = await cursor.fetchone()
            return bool(row and row[0] > 0)

    async def get_position_adjustments(self, symbol: Optional[str] = None, limit: int = 20):
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if symbol:
                cursor = await db.execute(
                    "SELECT * FROM position_adjustments WHERE symbol = ? ORDER BY applied_at DESC LIMIT ?",
                    (symbol.upper(), limit)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM position_adjustments ORDER BY applied_at DESC LIMIT ?",
                    (limit,)
                )
            return await cursor.fetchall()


class PaperTradingRepository:
    def __init__(self, db_path: str = "storage/bot.db"):
        self.db_path = db_path

    @asynccontextmanager
    async def transaction(self):
        """Atomic transaction context manager for multi-step order execution."""
        async with _connect_db(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE;")
            try:
                yield db
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def get_or_create_account(self, initial_capital: float = 5000000.0):
        from strategy.models import PaperAccount
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM paper_account WHERE id = 1")
            row = await cursor.fetchone()
            if row:
                return PaperAccount(
                    initial_balance=row["initial_balance"],
                    cash_balance=row["cash_balance"],
                    auto_trade_enabled=bool(row["auto_trade_enabled"]),
                    updated_at=row["updated_at"]
                )
            # Create row
            await db.execute(
                """INSERT INTO paper_account (id, initial_balance, cash_balance, auto_trade_enabled)
                   VALUES (1, ?, ?, 1)""",
                (initial_capital, initial_capital)
            )
            await db.commit()
            return PaperAccount(
                initial_balance=initial_capital,
                cash_balance=initial_capital,
                auto_trade_enabled=True
            )

    async def update_account_balance(self, cash_balance: float, db: Optional[Any] = None):
        if db is not None:
            await db.execute(
                "UPDATE paper_account SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (cash_balance,)
            )
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(
                "UPDATE paper_account SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (cash_balance,)
            )
            await conn.commit()

    async def set_auto_trade(self, enabled: bool):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "UPDATE paper_account SET auto_trade_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (1 if enabled else 0,)
            )
            await db.commit()

    async def get_positions(self):
        from strategy.models import PaperPosition
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM paper_positions WHERE total_quantity > 0 ORDER BY symbol ASC")
            rows = await cursor.fetchall()
            return [
                PaperPosition(
                    symbol=r["symbol"],
                    total_quantity=r["total_quantity"],
                    available_quantity=r["available_quantity"],
                    avg_buy_price=r["avg_buy_price"],
                    highest_price=r["highest_price"],
                    tp1_taken=bool(r["tp1_taken"]) if "tp1_taken" in r.keys() else False
                )
                for r in rows
            ]

    async def get_position(self, symbol: str):
        from strategy.models import PaperPosition
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM paper_positions WHERE symbol = ?", (symbol.upper(),))
            row = await cursor.fetchone()
            if not row:
                return None
            return PaperPosition(
                symbol=row["symbol"],
                total_quantity=row["total_quantity"],
                available_quantity=row["available_quantity"],
                avg_buy_price=row["avg_buy_price"],
                highest_price=row["highest_price"],
                tp1_taken=bool(row["tp1_taken"]) if "tp1_taken" in row.keys() else False
            )

    async def upsert_position(self, symbol: str, total_qty: int, available_qty: int, avg_price: float, highest_price: float, tp1_taken: bool = False, db: Optional[Any] = None):
        sql = """INSERT INTO paper_positions (symbol, total_quantity, available_quantity, avg_buy_price, highest_price, tp1_taken, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                 ON CONFLICT(symbol) DO UPDATE SET
                     total_quantity = excluded.total_quantity,
                     available_quantity = excluded.available_quantity,
                     avg_buy_price = excluded.avg_buy_price,
                     highest_price = excluded.highest_price,
                     tp1_taken = excluded.tp1_taken,
                     updated_at = CURRENT_TIMESTAMP"""
        params = (symbol.upper(), total_qty, available_qty, avg_price, highest_price, 1 if tp1_taken else 0)
        if db is not None:
            await db.execute(sql, params)
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def set_position_tp1_taken(self, symbol: str, taken: bool = True):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "UPDATE paper_positions SET tp1_taken = ?, updated_at = CURRENT_TIMESTAMP WHERE symbol = ?",
                (1 if taken else 0, symbol.upper())
            )
            await db.commit()

    async def delete_position(self, symbol: str, db: Optional[Any] = None):
        sql = "DELETE FROM paper_positions WHERE symbol = ?"
        params = (symbol.upper(),)
        if db is not None:
            await db.execute(sql, params)
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def update_highest_price(self, symbol: str, highest_price: float):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "UPDATE paper_positions SET highest_price = ?, updated_at = CURRENT_TIMESTAMP WHERE symbol = ?",
                (highest_price, symbol.upper())
            )
            await db.commit()

    async def is_adjustment_applied(self, event_id: str) -> bool:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM position_adjustments WHERE event_id = ?", (event_id,))
            row = await cursor.fetchone()
            return bool(row and row[0] > 0)

    async def record_position_adjustment(
        self,
        event_id: str,
        symbol: str,
        adjustment_type: str,
        ratio: float,
        cash_per_share: float,
        old_quantity: int,
        new_quantity: int,
        old_avg_price: float,
        new_avg_price: float,
        old_highest_price: float,
        new_highest_price: float,
        applied_date: str
    ):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO position_adjustments (
                    event_id, symbol, adjustment_type, ratio, cash_per_share,
                    old_quantity, new_quantity, old_avg_price, new_avg_price,
                    old_highest_price, new_highest_price, applied_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id, symbol.upper(), adjustment_type, ratio, cash_per_share,
                    old_quantity, new_quantity, old_avg_price, new_avg_price,
                    old_highest_price, new_highest_price, applied_date
                )
            )
            await db.commit()

    async def apply_position_adjustment(
        self,
        symbol: str,
        new_total_qty: int,
        new_available_qty: int,
        new_avg_price: float,
        new_highest_price: float,
        cash_delta: float = 0.0
    ):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """UPDATE paper_positions
                   SET total_quantity = ?,
                       available_quantity = ?,
                       avg_buy_price = ?,
                       highest_price = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE symbol = ?""",
                (new_total_qty, new_available_qty, new_avg_price, new_highest_price, symbol.upper())
            )
            if cash_delta != 0.0:
                await db.execute(
                    "UPDATE paper_account SET cash_balance = cash_balance + ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                    (cash_delta,)
                )
            await db.commit()

    async def get_position_adjustments(self, symbol: Optional[str] = None, limit: int = 20):
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if symbol:
                cursor = await db.execute(
                    "SELECT * FROM position_adjustments WHERE symbol = ? ORDER BY applied_at DESC LIMIT ?",
                    (symbol.upper(), limit)
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM position_adjustments ORDER BY applied_at DESC LIMIT ?",
                    (limit,)
                )
            return await cursor.fetchall()

    async def add_settlement_tranche(self, symbol: str, quantity: int, buy_date: str, settle_date: str, db: Optional[Any] = None):
        sql = """INSERT INTO paper_settlement_tranches (symbol, quantity, buy_date, settle_date, is_settled)
                 VALUES (?, ?, ?, ?, 0)"""
        params = (symbol.upper(), quantity, buy_date, settle_date)
        if db is not None:
            await db.execute(sql, params)
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def settle_mature_tranches(self, current_date: str) -> int:
        """Settles tranches where settle_date <= current_date and is_settled = 0."""
        total_settled = 0
        async with _connect_db(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, symbol, quantity FROM paper_settlement_tranches WHERE settle_date <= ? AND is_settled = 0",
                (current_date,)
            )
            tranches = await cursor.fetchall()
            for t in tranches:
                await db.execute(
                    """UPDATE paper_positions 
                       SET available_quantity = available_quantity + ?
                       WHERE symbol = ?""",
                    (t["quantity"], t["symbol"])
                )
                await db.execute(
                    "UPDATE paper_settlement_tranches SET is_settled = 1 WHERE id = ?",
                    (t["id"],)
                )
                total_settled += t["quantity"]
            await db.commit()
        return total_settled

    async def record_order(self, order, db: Optional[Any] = None):
        sql = """INSERT INTO paper_orders (order_id, symbol, side, quantity, order_type, price, status, fee, tax)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"""
        params = (
            order.order_id,
            order.symbol.upper(),
            order.side.value if hasattr(order.side, "value") else str(order.side),
            order.quantity,
            order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type),
            order.price,
            order.status.value if hasattr(order.status, "value") else str(order.status),
            order.fee,
            order.tax
        )
        if db is not None:
            await db.execute(sql, params)
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def record_trade(self, order_id: str, symbol: str, side, quantity: int, price: float, fee: float, tax: float, realized_pnl: float, db: Optional[Any] = None):
        side_str = side.value if hasattr(side, "value") else str(side)
        sql = """INSERT INTO paper_trades (order_id, symbol, side, quantity, price, fee, tax, realized_pnl)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        params = (order_id, symbol.upper(), side_str, quantity, price, fee, tax, realized_pnl)
        if db is not None:
            await db.execute(sql, params)
            return

        async with _connect_db(self.db_path) as conn:
            await conn.execute(sql, params)
            await conn.commit()

    async def get_total_realized_pnl(self) -> float:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute("SELECT COALESCE(SUM(realized_pnl), 0.0) FROM paper_trades")
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0

    async def get_closed_trade_pnls(self) -> List[float]:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute("SELECT realized_pnl FROM paper_trades WHERE side = 'SELL' ORDER BY id ASC")
            rows = await cursor.fetchall()
            return [float(r[0]) for r in rows]

    async def get_closed_trade_returns_pct(self) -> List[float]:
        async with _connect_db(self.db_path) as db:
            acc_cursor = await db.execute("SELECT initial_balance FROM paper_account WHERE id = 1")
            acc_row = await acc_cursor.fetchone()
            equity = float(acc_row[0]) if acc_row and acc_row[0] else 5_000_000.0

            cursor = await db.execute("SELECT realized_pnl FROM paper_trades WHERE side = 'SELL' ORDER BY id ASC")
            rows = await cursor.fetchall()
            returns = []
            for r in rows:
                pnl = float(r[0])
                ret = (pnl / equity) if equity > 0 else 0.0
                returns.append(ret)
                equity += pnl
            return returns

    async def reset_account(self, reset_balance: float = 5000000.0):
        async with _connect_db(self.db_path) as db:
            await db.execute("DELETE FROM paper_positions")
            await db.execute("DELETE FROM paper_settlement_tranches")
            await db.execute("DELETE FROM paper_orders")
            await db.execute("DELETE FROM paper_trades")
            await db.execute(
                """INSERT INTO paper_account (id, initial_balance, cash_balance, auto_trade_enabled, updated_at)
                   VALUES (1, ?, ?, 1, CURRENT_TIMESTAMP)
                   ON CONFLICT(id) DO UPDATE SET
                       initial_balance = excluded.initial_balance,
                       cash_balance = excluded.cash_balance,
                       auto_trade_enabled = 1,
                       updated_at = CURRENT_TIMESTAMP""",
                (reset_balance, reset_balance)
            )
            await db.commit()

    async def get_performance_statistics(self) -> Dict[str, Any]:
        """
        Calculates trading performance analytics:
        - total_trades (sell trades)
        - winning_trades (realized_pnl > 0)
        - losing_trades (realized_pnl < 0)
        - break_even_trades (realized_pnl == 0)
        - win_rate_pct
        - total_realized_pnl
        - best_trade
        - worst_trade
        - profit_factor
        - avg_win
        - avg_loss
        - win_loss_ratio
        - expectancy_vnd
        - max_drawdown_vnd
        - max_drawdown_pct
        - sharpe_ratio
        - sortino_ratio
        - calmar_ratio
        """
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT 
                    COUNT(*) as total_trades,
                    COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END), 0) as winning_trades,
                    COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END), 0) as losing_trades,
                    COALESCE(SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END), 0) as break_even_trades,
                    COALESCE(SUM(realized_pnl), 0.0) as total_realized_pnl,
                    COALESCE(MAX(realized_pnl), 0.0) as best_trade,
                    COALESCE(MIN(realized_pnl), 0.0) as worst_trade,
                    COALESCE(SUM(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE 0.0 END), 0.0) as gross_profit,
                    COALESCE(SUM(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) ELSE 0.0 END), 0.0) as gross_loss
                FROM paper_trades
                WHERE side = 'SELL'
                """
            )
            row = await cursor.fetchone()
            if not row or row[0] == 0:
                return {
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "break_even_trades": 0,
                    "win_rate_pct": 0.0,
                    "total_realized_pnl": 0.0,
                    "best_trade": 0.0,
                    "worst_trade": 0.0,
                    "profit_factor": 0.0,
                    "avg_win": 0.0,
                    "avg_loss": 0.0,
                    "win_loss_ratio": 0.0,
                    "expectancy_vnd": 0.0,
                    "max_drawdown_vnd": 0.0,
                    "max_drawdown_pct": 0.0,
                    "sharpe_ratio": 0.0,
                    "sortino_ratio": 0.0,
                    "calmar_ratio": 0.0
                }

            total_trades = row[0]
            winning_trades = row[1]
            losing_trades = row[2]
            break_even_trades = row[3]
            total_realized_pnl = float(row[4])
            best_trade = float(row[5])
            worst_trade = float(row[6])
            gross_profit = float(row[7])
            gross_loss = float(row[8])

            win_rate_pct = round((winning_trades / total_trades) * 100, 2) if total_trades > 0 else 0.0
            profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
            avg_win = round(gross_profit / winning_trades, 2) if winning_trades > 0 else 0.0
            avg_loss = round(gross_loss / losing_trades, 2) if losing_trades > 0 else 0.0
            win_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else (99.0 if avg_win > 0 else 0.0)
            expectancy_vnd = round(total_realized_pnl / total_trades, 2) if total_trades > 0 else 0.0

            # Fetch account initial balance for equity curve calculation
            acc_cursor = await db.execute("SELECT initial_balance FROM paper_account WHERE id = 1")
            acc_row = await acc_cursor.fetchone()
            initial_balance = float(acc_row[0]) if acc_row and acc_row[0] else 5_000_000.0

            # Chronological trades for equity curve and institutional risk metrics
            trades_cursor = await db.execute(
                "SELECT realized_pnl, created_at FROM paper_trades WHERE side = 'SELL' ORDER BY id ASC"
            )
            trade_rows = await trades_cursor.fetchall()
            pnls = [float(r[0]) for r in trade_rows]
            timestamps = [r[1] for r in trade_rows if r[1]]

            equity = initial_balance
            peak = equity
            max_drawdown_vnd = 0.0
            max_drawdown_pct = 0.0
            trade_returns = []

            for pnl in pnls:
                prev_equity = equity
                equity += pnl
                ret = (pnl / prev_equity) if prev_equity > 0 else 0.0
                trade_returns.append(ret)

                if equity > peak:
                    peak = equity

                dd_vnd = peak - equity
                dd_pct = (dd_vnd / peak * 100.0) if peak > 0 else 0.0

                if dd_vnd > max_drawdown_vnd:
                    max_drawdown_vnd = dd_vnd
                if dd_pct > max_drawdown_pct:
                    max_drawdown_pct = dd_pct

            # Calculate actual holding time span and dynamic annualization factors
            days_span = 1.0
            if len(timestamps) >= 2:
                try:
                    t0 = datetime.fromisoformat(str(timestamps[0]).replace("Z", ""))
                    t1 = datetime.fromisoformat(str(timestamps[-1]).replace("Z", ""))
                    days_span = max(1.0, (t1 - t0).total_seconds() / 86400.0)
                except Exception:
                    days_span = max(1.0, float(len(pnls)))
            else:
                days_span = max(1.0, float(len(pnls)))

            # Estimated trades per year (assuming 250 trading days in Vietnam)
            trades_per_year = max(1.0, min(500.0, len(pnls) * (250.0 / days_span)))
            ann_factor = math.sqrt(trades_per_year)
            rf_per_trade = 0.05 / trades_per_year

            if len(trade_returns) > 0:
                mean_ret = sum(trade_returns) / len(trade_returns)
                if len(trade_returns) > 1:
                    variance = sum((r - mean_ret) ** 2 for r in trade_returns) / (len(trade_returns) - 1)
                    std_ret = math.sqrt(variance)
                else:
                    std_ret = 0.0

                if std_ret > 1e-9:
                    sharpe_ratio = round(((mean_ret - rf_per_trade) / std_ret) * ann_factor, 2)
                else:
                    sharpe_ratio = 99.0 if (mean_ret - rf_per_trade) > 0 else 0.0

                downside_diffs = [min(0.0, r - rf_per_trade) for r in trade_returns]
                downside_variance = sum(d ** 2 for d in downside_diffs) / len(downside_diffs)
                downside_dev = math.sqrt(downside_variance)
                if downside_dev > 1e-9:
                    sortino_ratio = round(((mean_ret - rf_per_trade) / downside_dev) * ann_factor, 2)
                else:
                    sortino_ratio = 99.0 if (mean_ret - rf_per_trade) > 0 else 0.0

                # Calmar Ratio based on annualized CAGR
                years = max(days_span / 250.0, 1.0 / 250.0)
                if equity > 0 and initial_balance > 0:
                    cagr = (((equity / initial_balance) ** (1.0 / years)) - 1.0) * 100.0
                else:
                    cagr = -100.0

                if max_drawdown_pct > 1e-6:
                    calmar_ratio = round(cagr / max_drawdown_pct, 2)
                else:
                    calmar_ratio = 99.0 if cagr > 0 else 0.0
            else:
                sharpe_ratio = 0.0
                sortino_ratio = 0.0
                calmar_ratio = 0.0

            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "break_even_trades": break_even_trades,
                "win_rate_pct": win_rate_pct,
                "total_realized_pnl": total_realized_pnl,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "profit_factor": profit_factor,
                "avg_win": avg_win,
                "avg_loss": avg_loss,
                "win_loss_ratio": win_loss_ratio,
                "expectancy_vnd": expectancy_vnd,
                "max_drawdown_vnd": round(max_drawdown_vnd, 2),
                "max_drawdown_pct": round(max_drawdown_pct, 2),
                "sharpe_ratio": sharpe_ratio,
                "sortino_ratio": sortino_ratio,
                "calmar_ratio": calmar_ratio
            }

    async def save_corporate_events(self, events: List["CorporateEvent"]) -> int:
        return await Repository(self.db_path).save_corporate_events(events)

    async def get_upcoming_events(self, symbol: Optional[str] = None, from_date: Optional[str] = None, limit: int = 30) -> List["CorporateEvent"]:
        return await Repository(self.db_path).get_upcoming_events(symbol, from_date, limit)

    async def is_ex_date_near(self, symbol: str, target_date: str) -> bool:
        return await Repository(self.db_path).is_ex_date_near(symbol, target_date)

# Alias for backwards compatibility / clarity
SqliteRepository = Repository



