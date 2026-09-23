import pytest
from unittest.mock import AsyncMock
from dnse.mock_client import MockDNSEClient
from core.risk_safeguards import RiskSafeguards, TradingMode
from strategy.live_trader import LiveTrader

@pytest.mark.asyncio
async def test_full_live_trading_lifecycle():
    client = MockDNSEClient()
    safeguards = RiskSafeguards(max_order_value=5_000_000.0, max_daily_orders=5)
    notifier = AsyncMock()
    account_no = "0001880229"
    trader = LiveTrader(client=client, safeguards=safeguards, account_no=account_no, notify_func=notifier)

    # 1. Switch to LIVE_AUTO mode
    safeguards.set_mode(TradingMode.LIVE_AUTO)
    assert safeguards.mode == TradingMode.LIVE_AUTO

    # 2. Place 100 shares of HPG (Value: 2,600,000 VND <= 5M limit)
    res = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Strong volume breakout")
    assert res["status"] == "EXECUTED"
    order_id = res["order_id"]
    assert safeguards.daily_orders_count == 1

    # 3. Verify order exists in DNSE order book
    orders = await client.get_orders(account_no)
    assert any(o.id == order_id for o in orders)

    # 4. Trigger Kill Switch
    safeguards.activate_kill_switch("Khẩn cấp: Thị trường biến động tiêu cực mạnh")
    assert safeguards.kill_switch_active is True

    # Cancel all open orders
    for o in orders:
        await client.cancel_order(account_no, o.id)

    # 5. Subsequent orders blocked by Kill Switch
    res_blocked = await trader.route_order("TCB", "NB", 100, 22000.0, 22000.0, "BREAKOUT", "Test")
    assert res_blocked["status"] == "REJECTED"
    assert "Kill Switch" in res_blocked["reason"]

    # 6. Resume from Kill Switch
    safeguards.deactivate_kill_switch()
    assert safeguards.kill_switch_active is False

    # 7. Test LIVE_CONFIRM mode workflow
    safeguards.set_mode(TradingMode.LIVE_CONFIRM)
    res_confirm = await trader.route_order("FPT", "NB", 10, 120000.0, 120000.0, "PULLBACK", "MA20 bounce")
    assert res_confirm["status"] == "PENDING_CONFIRMATION"
    confirm_id = res_confirm["confirm_id"]

    # Confirm the pending order
    res_confirmed = await trader.confirm_pending_order(confirm_id)
    assert res_confirmed["status"] == "EXECUTED"
    assert safeguards.daily_orders_count == 2

    # 8. Test Price Collar Violation (HOSE limit +-7%)
    # Attempt to place order at +10% above reference price
    res_collar = await trader.route_order("MBB", "NB", 100, 27500.0, 25000.0, "BREAKOUT", "Chasing price")
    assert res_collar["status"] == "REJECTED"
    assert "biên độ" in res_collar["reason"]

    # 9. Test Max Order Value Limit (> 5,000,000 VND)
    res_value = await trader.route_order("VNM", "NB", 100, 70000.0, 70000.0, "BREAKOUT", "Too big")
    assert res_value["status"] == "REJECTED"
    assert "vượt quá Hạn mức" in res_value["reason"]

    # 10. Test Max Daily Orders Limit (Fill up to 5 orders)
    safeguards.set_mode(TradingMode.LIVE_AUTO)
    # Already 2 orders sent, send 3 more
    for i in range(3):
        r = await trader.route_order("SSI", "NB", 10, 30000.0, 30000.0, "BREAKOUT", f"Order {i+3}")
        assert r["status"] == "EXECUTED"
    assert safeguards.daily_orders_count == 5

    # 6th order should be rejected by daily limit
    r_exceed = await trader.route_order("SSI", "NB", 10, 30000.0, 30000.0, "BREAKOUT", "6th order")
    assert r_exceed["status"] == "REJECTED"
    assert "Số lệnh tối đa trong ngày" in r_exceed["reason"]

    await client.close()
