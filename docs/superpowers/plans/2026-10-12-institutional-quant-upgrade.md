# Institutional Quantitative Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade TradingBot from retail fund level to institutional hedge-fund grade (target rating 9.6-9.8/10) with 4 prioritized quantitative modules:
1. **Institutional Performance Metrics Engine:** Sharpe Ratio, Sortino Ratio, Calmar Ratio, Expectancy, Max Drawdown %/VND, and Payoff Ratio in `storage/repository.py` and `bot/handlers/portfolio.py`.
2. **Rolling 30-Day Correlation Matrix Filter:** Cross-asset Pearson correlation across VN30 in `indicators/calculator.py` and gating in `strategy/auto_trader.py` to prevent redundant portfolio exposure (correlation > 0.70).
3. **Volatility Targeting Position Sizing:** Institutional Volatility Targeting sizing engine adapting to market regime and annualized volatility in `strategy/risk.py` and `strategy/auto_trader.py`.
4. **Monte Carlo Simulation & Stress Testing Engine:** 1,000+ path bootstrap simulation, Value-at-Risk (VaR 95%, 99%), Conditional VaR (CVaR / Expected Shortfall), and Risk of Ruin in `strategy/stress_test.py` with Telegram `/stress` command in `bot/handlers/portfolio.py`.

**Architecture:**
- `storage/repository.py`: Compute cumulative equity curve from closed paper/live trades, drawdown series, Sharpe (Rf=5.0%), Sortino, Calmar, and Expectancy.
- `bot/handlers/portfolio.py`: Rich visual formatting of institutional performance and stress test dashboard in Telegram.
- `indicators/calculator.py`: Return series calculation, rolling covariance, and Pearson correlation matrix across VN30 symbols.
- `strategy/auto_trader.py`: Check correlation between candidate buy signal and existing portfolio positions before sizing and ordering.
- `strategy/risk.py`: Integrate volatility targeting formula $\text{weight} = \text{Target Vol} / \text{Asset Vol}$ with hard constraints.
- `strategy/stress_test.py`: Standalone Monte Carlo simulation engine with percentile distributions, VaR, CVaR, and max simulated drawdown.

**Tech Stack:** Python 3.12, NumPy, SQLite / aiosqlite, Pydantic, Aiogram 3.x, Pytest.

---

## Global Constraints

- Financial realism: Risk-free rate $R_f = 5.0\%$ (standard Vietnam Government 1-year bond / deposit benchmark).
- Annualization factor: 250 trading days per year for Vietnam equity markets (HOSE/HNX).
- Cash-only & HOSE lot compliance: Odd-lots (1-99) and round-lots (multiples of 100) must remain strictly enforced.
- Zero external dependency bloat: Use NumPy and standard library math for high performance without requiring heavy external C-extensions.
- Natural Vietnamese diacritics on all user-facing Telegram dashboards and notifications.
- Admin whitelist: Protected by Chat ID `7385637982`.

---

## Review Focus

1. **Sharpe & Sortino Math**: Zero division handling when volatility or downside deviation is zero. Sharpe annualized factor $\sqrt{250}$.
2. **Correlation Matrix Gating**: Correct alignment of time-series dates between symbols when computing returns. Threshold $\rho \le 0.70$.
3. **Volatility Targeting**: Caps and floors to ensure position size cannot exceed available cash, 25% NAV single-stock cap, or 85% total exposure.
4. **Monte Carlo Robustness**: Fast bootstrap resampling of trade PnL distribution with reproducible seed or random generation.

---

## Tasks

### Task 1: Institutional Performance Metrics Engine
- [x] Implement enhanced statistics calculation in `storage/repository.py`:
  - Fetch trade chronological history from `paper_trades`
  - Calculate cumulative equity curve
  - Calculate `max_drawdown_vnd` and `max_drawdown_pct`
  - Calculate trade returns, mean return, standard deviation, downside standard deviation
  - Calculate annualized `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`
  - Calculate `expectancy_vnd` and `win_loss_ratio`
- [x] Update Telegram dashboard in `bot/handlers/portfolio.py` (`cmd_pnl`) to display the institutional metrics
- [x] Add unit tests in `tests/test_performance_analytics.py` verifying mathematical correctness

### Task 2: Rolling 30-Day Correlation Matrix Filter across VN30
- [x] Implement rolling correlation calculation in `indicators/calculator.py`:
  - `calculate_price_correlation(prices_a: np.ndarray, prices_b: np.ndarray) -> float`
  - Handling of uneven lengths or flat price arrays
- [x] Integrate correlation filter into `strategy/auto_trader.py`:
  - Before buying candidate `top_signal`, compute correlation against all held positions using daily closes
  - Reject candidate if correlation > 0.70 with any active holding
  - Dispatch Telegram notification and audit alert
- [x] Add unit tests in `tests/test_correlation_filter.py`

### Task 3: Volatility Targeting Position Sizing
- [x] Enhance position sizing in `strategy/risk.py`:
  - Add `calculate_volatility_target_size()` / enhance `calculate_position_size()` with `target_vol_annualized: float = 0.15`
  - Sizing adapts inversely to asset's historical volatility: $\text{size} = \min(\text{cap}, (\text{Target Vol} / \text{Asset Vol}) \times \text{NAV})$
- [x] Integrate into `strategy/auto_trader.py`
- [x] Add unit tests in `tests/test_volatility_position_sizing.py`

### Task 4: Monte Carlo Simulation & Stress Testing Engine
- [x] Create `strategy/stress_test.py`:
  - `run_monte_carlo_simulation(trades_pnl: List[float], initial_capital: float, num_simulations: int = 1000, horizon_trades: int = 100) -> MonteCarloResult`
  - Compute VaR (95%, 99%), CVaR (95%), Max Drawdown distribution (50th, 95th, 99th percentile), Probability of Ruin (< 15% drawdown)
- [x] Add `/stress` Telegram command in `bot/handlers/portfolio.py`
- [x] Add comprehensive tests in `tests/test_stress_testing.py`
