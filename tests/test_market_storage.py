import pytest
from storage.db import init_db
from storage.repository import Repository
from market.models import Candle, OHLCVSeries

@pytest.mark.asyncio
async def test_save_and_retrieve_candles(tmp_path):
    db_file = str(tmp_path / "test_market.db")
    await init_db(db_file)
    repo = Repository(db_file)

    candles = [
        Candle(timestamp=100, date_str="2026-09-20", open=10.0, high=11.0, low=9.5, close=10.5, volume=1000),
        Candle(timestamp=200, date_str="2026-09-21", open=10.5, high=12.0, low=10.0, close=11.5, volume=1200),
    ]
    series = OHLCVSeries(symbol="TCB", resolution="1D", candles=candles)
    await repo.save_candles("TCB", series)

    loaded = await repo.get_candles("TCB", limit=10)
    assert loaded.symbol == "TCB"
    assert len(loaded) == 2
    assert loaded.candles[-1].close == 11.5

    # Test deduplication / update
    updated_candles = [
        Candle(timestamp=200, date_str="2026-09-21", open=10.5, high=12.5, low=10.0, close=12.2, volume=1300),
    ]
    await repo.save_candles("TCB", OHLCVSeries(symbol="TCB", resolution="1D", candles=updated_candles))
    reloaded = await repo.get_candles("TCB", limit=10)
    assert len(reloaded) == 2
    assert reloaded.candles[-1].close == 12.2
