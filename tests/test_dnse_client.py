import pytest
from dnse.mock_client import MockDNSEClient
from dnse.client import DNSEClient
from config.settings import settings

@pytest.mark.asyncio
async def test_mock_dnse_client():
    client = MockDNSEClient()
    accounts = await client.get_accounts()
    assert accounts.custodyCode == "064C551408"
    assert accounts.name == "Nguyễn Doãn Minh Hiếu"
    assert len(accounts.accounts) > 0

    sub_id = accounts.accounts[0].id
    balances = await client.get_balances(sub_id)
    assert balances.stock.availableCash > 0

    positions = await client.get_positions(sub_id)
    assert isinstance(positions, list)
    assert len(positions) == 1
    assert positions[0].symbol == "HPG"
    await client.close()

@pytest.mark.asyncio
async def test_live_dnse_client_if_credentials_available():
    if not settings or not settings.DNSE_API_KEY or settings.DRY_RUN:
        pytest.skip("Credentials not provided or in DRY_RUN mode")

    client = DNSEClient(
        api_key=settings.DNSE_API_KEY,
        api_secret=settings.DNSE_API_SECRET
    )
    try:
        accounts = await client.get_accounts()
        assert accounts.custodyCode == "064C551408"
        assert len(accounts.accounts) > 0
        
        sub_id = accounts.accounts[0].id
        balances = await client.get_balances(sub_id)
        assert balances.stock.totalCash >= 0
        
        positions = await client.get_positions(sub_id)
        assert isinstance(positions, list)
    finally:
        await client.close()
