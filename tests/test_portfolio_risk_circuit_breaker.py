import pytest
from core.risk_safeguards import RiskSafeguards, TradingMode
from core.state import TradingState
from strategy.paper_engine import PaperEngine
from strategy.auto_trader import AutoTrader
from strategy.live_trader import LiveTrader
from storage.repository import PaperTradingRepository
from market.models import Candle, OHLCVSeries
from indicators.calculator import compute_technical_summary
import time

def test_circuit_breaker_daily_drawdown_triggers_kill_switch():
    safeguards = RiskSafeguards(max_daily_loss_pct=-0.03)
    assert not safeguards.kill_switch_active

    # Day start NAV = 10,000,000. Current NAV = 9,800,000 (-2%) -> OK
    tripped, reason = safeguards.check_drawdown_circuit_breaker(
        current_nav=9_800_000.0,
        nav_day_start=10_000_000.0,
        nav_week_start=10_000_000.0
    )
    assert not tripped
    assert not safeguards.kill_switch_active

    # Current NAV = 9,650,000 (-3.5% > 3%) -> Circuit breaker trips!
    tripped, reason = safeguards.check_drawdown_circuit_breaker(
        current_nav=9_650_000.0,
        nav_day_start=10_000_000.0,
        nav_week_start=10_000_000.0
    )
    assert tripped
    assert safeguards.kill_switch_active
    assert "CIRCUIT BREAKER: Drawdown ngày" in reason

def test_circuit_breaker_weekly_drawdown_triggers_kill_switch():
    safeguards = RiskSafeguards(max_weekly_drawdown_pct=-0.07)
    assert not safeguards.kill_switch_active

    # Week start NAV = 10,000,000. Current NAV = 9,200,000 (-8% > 7%) -> Circuit breaker trips!
    # Day start NAV = 9,300,000 (-1.07% < 3% -> daily does not trip)
    tripped, reason = safeguards.check_drawdown_circuit_breaker(
        current_nav=9_200_000.0,
        nav_day_start=9_300_000.0,
        nav_week_start=10_000_000.0
    )
    assert tripped
    assert safeguards.kill_switch_active
    assert "CIRCUIT BREAKER: Drawdown tuần" in reason

def test_validate_portfolio_exposure_cap_100_pct():
    safeguards = RiskSafeguards(max_portfolio_exposure_pct=1.0)
    nav = 10_000_000.0
    
    # Current exposure = 8,000,000. New order = 1,500,000. Total = 9,500,000 (95% <= 100%) -> OK
    valid, msg = safeguards.validate_portfolio_exposure(
        current_exposure=8_000_000.0,
        new_order_value=1_500_000.0,
        nav=nav
    )
    assert valid
    assert msg == "OK"

    # Current exposure = 9,000,000. New order = 2,000,000. Total = 11,000,000 (110% > 100%) -> Rejected!
    valid, msg = safeguards.validate_portfolio_exposure(
        current_exposure=9_000_000.0,
        new_order_value=2_000_000.0,
        nav=nav
    )
    assert not valid
    assert "vượt quá trần cho phép" in msg

def test_validate_position_slots():
    safeguards = RiskSafeguards(max_concurrent_positions=4)

    assert safeguards.validate_position_slots(0)[0]
    assert safeguards.validate_position_slots(1)[0]
    assert safeguards.validate_position_slots(2)[0]
    assert safeguards.validate_position_slots(3)[0]

    # Reaching 4 positions -> rejected
    valid, msg = safeguards.validate_position_slots(4)
    assert not valid
    assert "Đã đạt giới hạn tối đa 4 vị thế" in msg

@pytest.mark.asyncio
async def test_autotrader_stops_when_circuit_breaker_tripped(tmp_path):
    test_db = str(tmp_path / "test_cb.db")
    from storage.db import init_db
    await init_db(test_db)
    repo = PaperTradingRepository(db_path=test_db)
    engine = PaperEngine(repo)
    state = TradingState()
    
    safeguards = RiskSafeguards(max_daily_loss_pct=-0.03)
    live_trader = LiveTrader(client=None, safeguards=safeguards, account_no="0001880229")
    auto_trader = AutoTrader(engine, state, live_trader=live_trader)

    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    state.last_nav_reset_day = today_str
    state.nav_day_start = 10_000_000.0
    # Paper account default NAV = 5,000,000 (-50% vs 10M -> huge drawdown)
    alerts = await auto_trader.process_cycle()
    
    assert safeguards.kill_switch_active
    assert any("KÍCH HOẠT CIRCUIT BREAKER" in a for a in alerts)
