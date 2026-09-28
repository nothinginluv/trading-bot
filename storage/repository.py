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

    async def update_account_balance(self, cash_balance: float):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "UPDATE paper_account SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (cash_balance,)
            )
            await db.commit()

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

    async def upsert_position(self, symbol: str, total_qty: int, available_qty: int, avg_price: float, highest_price: float, tp1_taken: bool = False):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_positions (symbol, total_quantity, available_quantity, avg_buy_price, highest_price, tp1_taken, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(symbol) DO UPDATE SET
                       total_quantity = excluded.total_quantity,
                       available_quantity = excluded.available_quantity,
                       avg_buy_price = excluded.avg_buy_price,
                       highest_price = excluded.highest_price,
                       tp1_taken = excluded.tp1_taken,
                       updated_at = CURRENT_TIMESTAMP""",
                (symbol.upper(), total_qty, available_qty, avg_price, highest_price, 1 if tp1_taken else 0)
            )
            await db.commit()

    async def set_position_tp1_taken(self, symbol: str, taken: bool = True):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                "UPDATE paper_positions SET tp1_taken = ?, updated_at = CURRENT_TIMESTAMP WHERE symbol = ?",
                (1 if taken else 0, symbol.upper())
            )
            await db.commit()

    async def delete_position(self, symbol: str):
        async with _connect_db(self.db_path) as db:
            await db.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol.upper(),))
            await db.commit()

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

    async def add_settlement_tranche(self, symbol: str, quantity: int, buy_date: str, settle_date: str):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_settlement_tranches (symbol, quantity, buy_date, settle_date, is_settled)
                   VALUES (?, ?, ?, ?, 0)""",
                (symbol.upper(), quantity, buy_date, settle_date)
            )
            await db.commit()

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

    async def record_order(self, order):
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_orders (order_id, symbol, side, quantity, order_type, price, status, fee, tax)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
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
            )
            await db.commit()

    async def record_trade(self, order_id: str, symbol: str, side, quantity: int, price: float, fee: float, tax: float, realized_pnl: float):
        side_str = side.value if hasattr(side, "value") else str(side)
        async with _connect_db(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_trades (order_id, symbol, side, quantity, price, fee, tax, realized_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, symbol.upper(), side_str, quantity, price, fee, tax, realized_pnl)
            )
            await db.commit()

    async def get_total_realized_pnl(self) -> float:
        async with _connect_db(self.db_path) as db:
            cursor = await db.execute("SELECT COALESCE(SUM(realized_pnl), 0.0) FROM paper_trades")
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0

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
                    "profit_factor": 0.0
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

            return {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "break_even_trades": break_even_trades,
                "win_rate_pct": win_rate_pct,
                "total_realized_pnl": total_realized_pnl,
                "best_trade": best_trade,
                "worst_trade": worst_trade,
                "profit_factor": profit_factor
            }

    async def save_corporate_events(self, events: List["CorporateEvent"]) -> int:
        return await Repository(self.db_path).save_corporate_events(events)

    async def get_upcoming_events(self, symbol: Optional[str] = None, from_date: Optional[str] = None, limit: int = 30) -> List["CorporateEvent"]:
        return await Repository(self.db_path).get_upcoming_events(symbol, from_date, limit)

    async def is_ex_date_near(self, symbol: str, target_date: str) -> bool:
        return await Repository(self.db_path).is_ex_date_near(symbol, target_date)

# Alias for backwards compatibility / clarity
SqliteRepository = Repository



