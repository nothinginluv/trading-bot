import os
import tempfile
import asyncio
import pytest
import aiosqlite
from storage.db import init_db
from storage.repository import Repository, PaperTradingRepository, _connect_db

@pytest.mark.asyncio
async def test_sqlite_wal_mode_and_pragmas():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_wal.db")
        
        # Initialize db
        await init_db(db_path)
        
        # Check pragmas using _connect_db
        async with _connect_db(db_path) as db:
            async with db.execute("PRAGMA journal_mode;") as cursor:
                row = await cursor.fetchone()
                journal_mode = row[0].lower() if row else ""
                assert journal_mode == "wal", f"Expected WAL mode, got {journal_mode}"

            async with db.execute("PRAGMA busy_timeout;") as cursor:
                row = await cursor.fetchone()
                busy_timeout = int(row[0]) if row else 0
                assert busy_timeout == 10000, f"Expected 10000ms busy timeout, got {busy_timeout}"

            async with db.execute("PRAGMA synchronous;") as cursor:
                row = await cursor.fetchone()
                sync_mode = int(row[0]) if row else -1
                # NORMAL mode is 1
                assert sync_mode == 1, f"Expected synchronous NORMAL (1), got {sync_mode}"

@pytest.mark.asyncio
async def test_concurrent_access_no_lock():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_concurrent.db")
        await init_db(db_path)
        
        repo = Repository(db_path)
        paper_repo = PaperTradingRepository(db_path)
        
        # Run concurrent writes and reads simultaneously
        async def write_audit(idx):
            for i in range(10):
                await repo.log_audit("INFO", f"WORKER_{idx}", f"Test log {i}")
                await asyncio.sleep(0.001)

        async def read_positions():
            for _ in range(10):
                await paper_repo.get_positions()
                await asyncio.sleep(0.001)

        # Launch 5 concurrent tasks
        tasks = [
            write_audit(1),
            write_audit(2),
            write_audit(3),
            read_positions(),
            read_positions()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            assert not isinstance(r, Exception), f"Concurrent task failed with: {r}"
