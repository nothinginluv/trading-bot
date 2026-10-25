import math
import numpy as np
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class MonteCarloResult:
    num_simulations: int
    horizon_trades: int
    initial_capital: float
    median_final_capital: float
    p5_final_capital: float
    p95_final_capital: float
    var_95_pct: float
    var_99_pct: float
    cvar_95_pct: float
    max_drawdown_p50: float
    max_drawdown_p95: float
    risk_of_ruin_pct: float

def run_monte_carlo_simulation(
    trades_pnl: Optional[List[float]] = None,
    trade_returns_pct: Optional[List[float]] = None,
    initial_capital: float = 10_000_000.0,
    num_simulations: int = 1000,
    horizon_trades: int = 100,
    ruin_threshold_pct: float = 15.0,
    random_seed: Optional[int] = 42
) -> MonteCarloResult:
    """
    Institutional Monte Carlo & Portfolio Stress Testing Engine.
    Simulates thousands of forward equity trajectories using bootstrap resampling
    of historical fractional trade returns (scale-invariant geometric compounding),
    or institutional empirical prior if trade history < 3.
    
    Computes:
    - Median, 5th (downside), 95th (upside) percentile final capital
    - Value at Risk (VaR 95%, VaR 99%)
    - Conditional Value at Risk (CVaR 95% / Expected Shortfall)
    - Median & 95th percentile Maximum Drawdown
    - Risk of Ruin (Probability of hitting ruin_threshold_pct drawdown)
    """
    rng = np.random.default_rng(seed=random_seed)

    if trade_returns_pct and len(trade_returns_pct) >= 3:
        rets_arr = np.array(trade_returns_pct, dtype=float)
        sim_rets = rng.choice(rets_arr, size=(num_simulations, horizon_trades), replace=True)
    elif trades_pnl and len(trades_pnl) >= 3:
        # Scale-invariant normalization: convert nominal VND PnL to fractional return on capital
        rets_arr = np.array(trades_pnl, dtype=float) / max(initial_capital, 1.0)
        sim_rets = rng.choice(rets_arr, size=(num_simulations, horizon_trades), replace=True)
    else:
        # Institutional empirical prior for VN30 trend-following strategy:
        # 55% win rate, avg win = +2.5% on 25% slot (+0.625% NAV), avg loss = -1.8% on 25% slot (-0.45% NAV)
        win_ret = 0.25 * 0.025
        loss_ret = 0.25 * 0.018
        win_probs = rng.random((num_simulations, horizon_trades))
        sim_rets = np.where(win_probs < 0.55, win_ret, -loss_ret)

    # Scale-invariant geometric compounding of equity curves
    cum_growth = np.cumprod(1.0 + sim_rets, axis=1)
    equity_paths = initial_capital * cum_growth
    # Include starting point in equity paths for drawdown calculation
    full_equity = np.hstack([np.full((num_simulations, 1), initial_capital), equity_paths])

    # Final capital distribution
    final_capitals = full_equity[:, -1]
    returns_pct = ((final_capitals - initial_capital) / initial_capital) * 100.0

    # Calculate running peaks and drawdowns for each simulation path
    running_peaks = np.maximum.accumulate(full_equity, axis=1)
    drawdowns_pct = ((running_peaks - full_equity) / running_peaks) * 100.0
    mdds = np.max(drawdowns_pct, axis=1)

    # Value at Risk (VaR) & Conditional Value at Risk (CVaR)
    # VaR 95%: negative of 5th percentile return
    p5_ret = float(np.percentile(returns_pct, 5))
    p1_ret = float(np.percentile(returns_pct, 1))
    var_95_pct = round(max(0.0, -p5_ret), 2)
    var_99_pct = round(max(0.0, -p1_ret), 2)

    tail_losses = returns_pct[returns_pct <= p5_ret]
    cvar_95_pct = round(max(0.0, -float(np.mean(tail_losses))), 2) if len(tail_losses) > 0 else var_95_pct

    # Max Drawdowns
    max_dd_p50 = round(float(np.median(mdds)), 2)
    max_dd_p95 = round(float(np.percentile(mdds, 95)), 2)

    # Risk of Ruin
    ruin_count = np.sum(mdds >= ruin_threshold_pct)
    risk_of_ruin_pct = round(float((ruin_count / num_simulations) * 100.0), 2)

    return MonteCarloResult(
        num_simulations=num_simulations,
        horizon_trades=horizon_trades,
        initial_capital=round(initial_capital, 2),
        median_final_capital=round(float(np.median(final_capitals)), 2),
        p5_final_capital=round(float(np.percentile(final_capitals, 5)), 2),
        p95_final_capital=round(float(np.percentile(final_capitals, 95)), 2),
        var_95_pct=var_95_pct,
        var_99_pct=var_99_pct,
        cvar_95_pct=cvar_95_pct,
        max_drawdown_p50=max_dd_p50,
        max_drawdown_p95=max_dd_p95,
        risk_of_ruin_pct=risk_of_ruin_pct
    )
