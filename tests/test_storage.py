import pytest
import os
from storage.db import init_db
from storage.repository import Repository

@pytest.mark.asyncio
async def test_sqlite_repository(tmp_path):
    db_file = str(tmp_path / "test.db")
    await init_db(db_file)
    repo = Repository(db_file)
    
    await repo.save_balance_snapshot(
        account_no="0001880229",
        total_cash=27860.0,
        available_cash=27856.0,
        total_debt=0.0,
        withdrawable_cash=27856.0
    )
    
    snapshot = await repo.get_latest_snapshot("0001880229")
    assert snapshot is not None
    assert snapshot["available_cash"] == 27856.0
    assert snapshot["total_cash"] == 27860.0
    
    await repo.log_audit("INFO", "TEST", "Test audit entry")
    logs = await repo.get_recent_logs(limit=5)
    assert len(logs) == 1
    assert logs[0]["message"] == "Test audit entry"
