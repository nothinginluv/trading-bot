import pytest
from unittest.mock import AsyncMock
from core.risk_safeguards import RiskSafeguards, TradingMode
from dnse.mock_client import MockDNSEClient
from strategy.live_trader import LiveTrader

@pytest.mark.asyncio
async def test_live_trader_routing():
    client = MockDNSEClient()
    safeguards = RiskSafeguards()
    notifier = AsyncMock()
    trader = LiveTrader(client=client, safeguards=safeguards, account_no="0001880229", notify_func=notifier)

    # 1. In PAPER mode, doesn't call live client
    safeguards.set_mode(TradingMode.PAPER)
    res_paper = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Test")
    assert res_paper["status"] == "PAPER_MODE"

    # 2. In LIVE_CONFIRM mode, generates confirmation callback
    safeguards.set_mode(TradingMode.LIVE_CONFIRM)
    res_confirm = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Test")
    assert res_confirm["status"] == "PENDING_CONFIRMATION"
    assert "confirm_id" in res_confirm

    # Test confirming the pending order
    confirm_res = await trader.confirm_pending_order(res_confirm["confirm_id"])
    assert confirm_res["status"] == "EXECUTED"
    assert confirm_res["order_id"] is not None

    # 3. In LIVE_AUTO mode, executes directly
    safeguards.set_mode(TradingMode.LIVE_AUTO)
    res_auto = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Test")
    assert res_auto["status"] == "EXECUTED"
    assert res_auto["order_id"] is not None

    # 4. In Kill switch active, rejects
    safeguards.activate_kill_switch("Khẩn cấp")
    res_kill = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Test")
    assert res_kill["status"] == "REJECTED"

    await client.close()
