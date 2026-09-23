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
