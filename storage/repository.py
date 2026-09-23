import aiosqlite
from typing import Optional, List, Dict, Any

class Repository:
    def __init__(self, db_path: str = "storage/bot.db"):
        self.db_path = db_path

    async def save_balance_snapshot(self, account_no: str, total_cash: float, available_cash: float, total_debt: float, withdrawable_cash: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO account_snapshots (account_no, total_cash, available_cash, total_debt, withdrawable_cash)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_no, total_cash, available_cash, total_debt, withdrawable_cash)
            )
            await db.commit()

    async def get_latest_snapshot(self, account_no: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM account_snapshots WHERE account_no = ? ORDER BY id DESC LIMIT 1",
                (account_no,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def save_positions_snapshot(self, account_no: str, positions: list):
        async with aiosqlite.connect(self.db_path) as db:
            for p in positions:
                await db.execute(
                    """INSERT INTO positions_snapshot (account_no, symbol, quantity, cost_price, market_price, unrealized_pnl)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (account_no, p.symbol, p.tradeQuantity, p.costPrice, p.marketPrice, p.unrealizedPnl)
                )
            await db.commit()

    async def log_audit(self, level: str, source: str, message: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_logs (level, source, message) VALUES (?, ?, ?)",
                (level, source, message)
            )
            await db.commit()

    async def get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
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

    async def get_candles(self, symbol: str, limit: int = 150):
        from market.models import Candle, OHLCVSeries
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


class PaperTradingRepository:
    def __init__(self, db_path: str = "storage/bot.db"):
        self.db_path = db_path

    async def get_or_create_account(self, initial_capital: float = 5000000.0):
        from strategy.models import PaperAccount
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE paper_account SET cash_balance = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (cash_balance,)
            )
            await db.commit()

    async def set_auto_trade(self, enabled: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE paper_account SET auto_trade_enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (1 if enabled else 0,)
            )
            await db.commit()

    async def get_positions(self):
        from strategy.models import PaperPosition
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM paper_positions WHERE total_quantity > 0 ORDER BY symbol ASC")
            rows = await cursor.fetchall()
            return [
                PaperPosition(
                    symbol=r["symbol"],
                    total_quantity=r["total_quantity"],
                    available_quantity=r["available_quantity"],
                    avg_buy_price=r["avg_buy_price"],
                    highest_price=r["highest_price"]
                )
                for r in rows
            ]

    async def get_position(self, symbol: str):
        from strategy.models import PaperPosition
        async with aiosqlite.connect(self.db_path) as db:
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
                highest_price=row["highest_price"]
            )

    async def upsert_position(self, symbol: str, total_qty: int, available_qty: int, avg_price: float, highest_price: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_positions (symbol, total_quantity, available_quantity, avg_buy_price, highest_price, updated_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(symbol) DO UPDATE SET
                       total_quantity = excluded.total_quantity,
                       available_quantity = excluded.available_quantity,
                       avg_buy_price = excluded.avg_buy_price,
                       highest_price = excluded.highest_price,
                       updated_at = CURRENT_TIMESTAMP""",
                (symbol.upper(), total_qty, available_qty, avg_price, highest_price)
            )
            await db.commit()

    async def delete_position(self, symbol: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM paper_positions WHERE symbol = ?", (symbol.upper(),))
            await db.commit()

    async def add_settlement_tranche(self, symbol: str, quantity: int, buy_date: str, settle_date: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_settlement_tranches (symbol, quantity, buy_date, settle_date, is_settled)
                   VALUES (?, ?, ?, ?, 0)""",
                (symbol.upper(), quantity, buy_date, settle_date)
            )
            await db.commit()

    async def settle_mature_tranches(self, current_date: str) -> int:
        """Settles tranches where settle_date <= current_date and is_settled = 0."""
        total_settled = 0
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO paper_trades (order_id, symbol, side, quantity, price, fee, tax, realized_pnl)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (order_id, symbol.upper(), side_str, quantity, price, fee, tax, realized_pnl)
            )
            await db.commit()

    async def get_total_realized_pnl(self) -> float:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COALESCE(SUM(realized_pnl), 0.0) FROM paper_trades")
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0

    async def reset_account(self, reset_balance: float = 5000000.0):
        async with aiosqlite.connect(self.db_path) as db:
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

