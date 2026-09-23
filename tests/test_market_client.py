import pytest
from market.mock_client import MockMarketClient
from market.client import AsyncMarketClient

@pytest.mark.asyncio
async def test_mock_market_client():
    mock = MockMarketClient()
    series = await mock.get_candles("FPT", count=100)
    assert series.symbol == "FPT"
    assert len(series) == 100
    assert series.candles[-1].close > 0

@pytest.mark.asyncio
async def test_live_market_client():
    client = AsyncMarketClient()
    try:
        series = await client.get_candles("HPG", count=30)
        assert series.symbol == "HPG"
        assert len(series) > 0
        assert series.candles[-1].close > 0
    finally:
        await client.close()
