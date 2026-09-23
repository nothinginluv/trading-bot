import pytest
from unittest.mock import AsyncMock, MagicMock
from core.scheduler import sync_data_job
from core.state import TradingState
from storage.repository import Repository
from dnse.mock_client import MockDNSEClient

@pytest.mark.asyncio
async def test_sync_data_job():
    client = MockDNSEClient()
    state = TradingState()
    repo = MagicMock(spec=Repository)
    repo.save_balance_snapshot = AsyncMock()
    repo.log_audit = AsyncMock()
    
    # Init account
    acc = await client.get_accounts()
    state.set_account(acc)
    
    await sync_data_job(client, state, repo)
    assert state.balance is not None
    assert state.balance.stock.availableCash == 27856.0
    repo.save_balance_snapshot.assert_awaited_once()
