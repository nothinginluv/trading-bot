import pytest
from core.state import TradingState
from market.mock_client import MockMarketClient
from storage.db import init_db
from storage.repository import Repository
from core.scheduler import sync_market_data_job

@pytest.mark.asyncio
async def test_sync_market_data_job(tmp_path):
    db_file = str(tmp_path / "test_market_sched.db")
    await init_db(db_file)
    repo = Repository(db_file)
    state = TradingState()
    client = MockMarketClient()

    await sync_market_data_job(client, state, repo, symbols=["FPT", "HPG"])

    assert "FPT" in state.vn30_summaries
    assert "HPG" in state.vn30_summaries
    assert state.last_market_sync_time > 0

    saved_fpt = await repo.get_candles("FPT", limit=10)
    assert len(saved_fpt) > 0
