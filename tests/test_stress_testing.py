import pytest
from unittest.mock import AsyncMock
from strategy.stress_test import run_monte_carlo_simulation
from storage.db import init_db
from storage.repository import PaperTradingRepository
from strategy.paper_engine import PaperEngine
from core.state import TradingState
from bot.handlers.portfolio import cmd_stress_test

def test_monte_carlo_simulation_prior():
    res = run_monte_carlo_simulation(
        trades_pnl=None,
        initial_capital=10_000_000.0,
        num_simulations=500,
        horizon_trades=50,
        random_seed=42
    )

    assert res.num_simulations == 500
    assert res.horizon_trades == 50
    assert res.initial_capital == 10_000_000.0
    assert res.p95_final_capital >= res.median_final_capital >= res.p5_final_capital
    assert res.var_99_pct >= res.var_95_pct >= 0.0
    assert res.cvar_95_pct >= res.var_95_pct
    assert res.max_drawdown_p95 >= res.max_drawdown_p50 >= 0.0
    assert 0.0 <= res.risk_of_ruin_pct <= 100.0

def test_monte_carlo_simulation_bootstrap():
    historical_trades = [
        150000.0, -80000.0, 220000.0, -120000.0, 300000.0,
        -90000.0, 180000.0, 250000.0, -150000.0, 190000.0
    ]
    res = run_monte_carlo_simulation(
        trades_pnl=historical_trades,
        initial_capital=20_000_000.0,
        num_simulations=1000,
        horizon_trades=80,
        random_seed=123
    )

    assert res.num_simulations == 1000
    assert res.horizon_trades == 80
    assert res.initial_capital == 20_000_000.0
    # Positive expectancy trades should have median capital > initial
    assert res.median_final_capital > res.initial_capital
    assert res.p95_final_capital > res.median_final_capital > res.p5_final_capital
    assert res.var_95_pct >= 0.0
    assert res.cvar_95_pct >= res.var_95_pct

def test_monte_carlo_simulation_fractional_returns():
    trade_rets = [0.03, -0.015, 0.04, -0.02, 0.025, -0.01, 0.035]
    res = run_monte_carlo_simulation(
        trade_returns_pct=trade_rets,
        initial_capital=50_000_000.0,
        num_simulations=500,
        horizon_trades=60,
        random_seed=42
    )
    assert res.num_simulations == 500
    assert res.median_final_capital > res.initial_capital
    assert res.var_95_pct >= 0.0

@pytest.mark.asyncio
async def test_cmd_stress_test_telegram_handler(tmp_path):
    db_path = str(tmp_path / "test_stress.db")
    await init_db(db_path)
    paper_repo = PaperTradingRepository(db_path)
    engine = PaperEngine(paper_repo)
    await engine.initialize(10_000_000.0)

    # Record some trades
    await paper_repo.record_trade("t1", "FPT", "BUY", 100, 100000.0, 0.0, 0.0, 0.0)
    await paper_repo.record_trade("t2", "FPT", "SELL", 100, 110000.0, 0.0, 0.0, 1000000.0)

    state = TradingState()
    mock_msg = AsyncMock()
    mock_msg.text = "/stress"

    await cmd_stress_test(
        message=mock_msg,
        state_obj=state,
        paper_engine=engine,
        paper_repo=paper_repo
    )

    mock_msg.answer.assert_called_once()
    reply_text = mock_msg.answer.call_args[0][0]

    assert "BÁO CÁO MÔ PHỎNG MONTE CARLO & STRESS-TEST" in reply_text
    assert "Kịch bản Lạc quan" in reply_text
    assert "Kịch bản Kỳ vọng" in reply_text
    assert "Kịch bản Bất lợi" in reply_text
    assert "VaR 95%" in reply_text
    assert "VaR 99%" in reply_text
    assert "CVaR 95%" in reply_text
    assert "Max Drawdown Khủng hoảng" in reply_text
    assert "Risk of Ruin" in reply_text
