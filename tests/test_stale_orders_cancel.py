import time
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock
from dnse.models import LiveOrder
from dnse.mock_client import MockDNSEClient
from core.risk_safeguards import RiskSafeguards, TradingMode
from strategy.live_trader import LiveTrader
from strategy.auto_trader import AutoTrader
from strategy.paper_engine import PaperEngine
from core.state import TradingState

@pytest.mark.asyncio
async def test_auto_cancel_stale_orders_locally_tracked():
    mock_client = MockDNSEClient()
    safeguards = RiskSafeguards(mode=TradingMode.LIVE_AUTO)
    alerts = []
    async def capture_alert(msg: str):
        alerts.append(msg)

    live_trader = LiveTrader(
        client=mock_client,
        safeguards=safeguards,
        account_no="0001880229",
        notify_func=capture_alert
    )

    now = time.time()
    # Add two orders to mock client
    ord_fresh = LiveOrder(
        id="ord-fresh",
        symbol="HPG",
        side="NB",
        orderType="LO",
        quantity=100,
        price=28000.0,
        orderStatus="PENDING"
    )
    ord_stale = LiveOrder(
        id="ord-stale",
        symbol="FPT",
        side="NB",
        orderType="LO",
        quantity=100,
        price=110000.0,
        orderStatus="PENDING"
    )
    mock_client.orders = [ord_fresh, ord_stale]

    # Track them locally: fresh is 5 minutes ago, stale is 20 minutes ago
    live_trader.track_live_order("ord-fresh", "HPG", "NB", 100, 28000.0, created_at=now - 300)
    live_trader.track_live_order("ord-stale", "FPT", "NB", 100, 110000.0, created_at=now - 1200)

    cancelled_ids = await live_trader.auto_cancel_stale_orders(stale_timeout_minutes=15.0)

    assert cancelled_ids == ["ord-stale"]
    # ord-fresh is still active and tracked
    assert "ord-fresh" in live_trader.tracked_live_orders
    # ord-stale is removed from tracked
    assert "ord-stale" not in live_trader.tracked_live_orders

    # Mock client order status updated to CANCELLED
    assert ord_stale.orderStatus == "CANCELLED"
    assert ord_fresh.orderStatus == "PENDING"

    # Notification sent
    assert len(alerts) == 1
    assert "TỰ ĐỘNG HỦY LỆNH TREO" in alerts[0]
    assert "FPT" in alerts[0]

@pytest.mark.asyncio
async def test_auto_cancel_stale_orders_created_time_fallback():
    mock_client = MockDNSEClient()
    safeguards = RiskSafeguards(mode=TradingMode.LIVE_AUTO)
    live_trader = LiveTrader(client=mock_client, safeguards=safeguards, account_no="0001880229")

    # Order created 25 minutes ago via ISO string
    created_dt = datetime.now(timezone.utc).timestamp() - 1500
    iso_time = datetime.fromtimestamp(created_dt, timezone.utc).isoformat()

    ord_fallback = LiveOrder(
        id="ord-fallback",
        symbol="TCB",
        side="NB",
        orderType="LO",
        quantity=200,
        price=24500.0,
        orderStatus="PENDING",
        createdTime=iso_time
    )
    mock_client.orders = [ord_fallback]

    cancelled = await live_trader.auto_cancel_stale_orders(stale_timeout_minutes=15.0)
    assert cancelled == ["ord-fallback"]
    assert ord_fallback.orderStatus == "CANCELLED"

@pytest.mark.asyncio
async def test_auto_trader_cycle_triggers_stale_cancellation(tmp_path):
    from storage.db import init_db
    from storage.repository import PaperTradingRepository

    db_path = str(tmp_path / "test_cycle_cancel.db")
    await init_db(db_path)
    paper_repo = PaperTradingRepository(db_path)
    engine = PaperEngine(paper_repo)
    await engine.initialize(5_000_000.0)

    state = TradingState()
    mock_client = MockDNSEClient()
    safeguards = RiskSafeguards(mode=TradingMode.LIVE_AUTO)

    live_trader = LiveTrader(client=mock_client, safeguards=safeguards, account_no="0001880229")

    now = time.time()
    ord_stale = LiveOrder(
        id="ord-auto-1",
        symbol="VNM",
        side="NB",
        orderType="LO",
        quantity=100,
        price=68000.0,
        orderStatus="PENDING"
    )
    mock_client.orders = [ord_stale]
    live_trader.track_live_order("ord-auto-1", "VNM", "NB", 100, 68000.0, created_at=now - 1000)

    auto_trader = AutoTrader(
        engine=engine,
        state=state,
        live_trader=live_trader
    )

    alerts = await auto_trader.process_cycle()
    assert any("tự động hủy 1 lệnh treo" in a.lower() for a in alerts)
    assert ord_stale.orderStatus == "CANCELLED"
