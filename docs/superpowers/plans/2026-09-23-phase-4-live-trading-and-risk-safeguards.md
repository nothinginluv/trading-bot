# Phase 4: Live Order Execution & Risk Safeguards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real money Live Order Execution via DNSE LightSpeed API V2 with three-tier trading modes (PAPER, LIVE_CONFIRM, LIVE_AUTO), strict risk safeguards (Max Order Value 5M, Max Daily Orders 5, Daily Loss Limit -3%), and an Emergency Kill Switch.

**Architecture:** Extend `dnse/client.py` and `dnse/mock_client.py` with HMAC-SHA256 live order endpoints, implement stateful `core/risk_safeguards.py` for capital protection, create `strategy/live_trader.py` for order dispatching, and provide interactive Telegram commands in `bot/handlers/live.py`.

**Tech Stack:** Python 3.12, HTTPX, Pydantic, SQLite, APScheduler, Aiogram 3.x, Pytest (`pytest-asyncio`).

**Spec:** [docs/superpowers/specs/2026-09-23-phase-4-live-trading-and-risk-safeguards-design.md](file:///d:/TradingBot/docs/superpowers/specs/2026-09-23-phase-4-live-trading-and-risk-safeguards-design.md)

---

## Global Constraints

- API Authentication: HMAC-SHA256 signing using `DNSE_API_KEY` and `DNSE_API_SECRET` (`X-Signature`, `X-API-Key`, `Date`).
- Optional `trading-token` header support if provided, without blocking request submission.
- Three operating modes: `PAPER` (default), `LIVE_CONFIRM` (semi-auto with approval dialog), `LIVE_AUTO` (fully autonomous live).
- Capital constraints: Max order value = 5,000,000 VNĐ; Max daily orders = 5; Max daily loss = -3.0%.
- Emergency stop: `/kill_switch` instantly cancels all open orders and locks system to `READ_ONLY`.
- Non-blocking error handling: Any DNSE response errors are parsed and notified cleanly without crashing.
- Telegram Admin Whitelist: Only user ID `7385637982`.
- Natural Vietnamese diacritics on all user-facing text.

---

## Review Focus

1. **Dynamic `loanPackageId` resolution**: Ensure that when placing an order, if no `loanPackageId` is given, the client queries `/accounts/{id}/loan-packages?symbol={symbol}&marketType=STOCK` and extracts the first available package (e.g. ID `1258` for HPG/ZaloPay).
2. **Kill switch active state**: Ensure that when the kill switch is on, ANY attempt to place live orders (via auto-trader or manual `/buy_live`) is rejected immediately before making any HTTP request.
3. **Daily order count limit**: When 5 live orders have been placed in a single day, any subsequent 6th order must be blocked by `RiskSafeguards`.
4. **Price collar check**: Orders placed outside the HOSE daily price limits (ceiling/floor $\pm 7\%$) must be rejected before calling DNSE.
5. **Interactive approval callback**: In `LIVE_CONFIRM` mode, clicking `[✅ XÁC NHẬN]` must check that the order hasn't already been confirmed or expired, then place the order and update the message.

---

## Task Breakdown

### Task 1: Live Order Data Models & Client Extensions (`dnse/models.py`, `dnse/client.py`, `dnse/mock_client.py`)

**Files:**
- Modify: `dnse/models.py`
- Modify: `dnse/client.py`
- Modify: `dnse/mock_client.py`
- Test: `tests/test_dnse_live_orders.py`

**Interfaces:**
- Produces:
  - Models: `LiveOrder`, `LoanPackage`, `OrderPlacementResult`
  - Methods in `DNSEClient` and `MockDNSEClient`:
    - `get_loan_packages(account_no: str, symbol: str) -> list[dict]`
    - `place_order(account_no: str, symbol: str, side: str, order_type: str, quantity: int, price: float, loan_package_id: Optional[int] = None, trading_token: Optional[str] = None) -> OrderPlacementResult`
    - `get_orders(account_no: str) -> list[LiveOrder]`
    - `cancel_order(account_no: str, order_id: str) -> dict`

- [ ] **Step 1: Write failing test for live order client methods**

```python
# tests/test_dnse_live_orders.py
import pytest
from dnse.mock_client import MockDNSEClient
from dnse.models import LiveOrder, OrderPlacementResult

@pytest.mark.asyncio
async def test_mock_dnse_live_order_operations():
    client = MockDNSEClient()
    account_no = "0001880229"

    # 1. Test get loan packages
    pkgs = await client.get_loan_packages(account_no, "HPG")
    assert len(pkgs) > 0
    assert pkgs[0]["id"] == 1258

    # 2. Test place order
    res = await client.place_order(
        account_no=account_no,
        symbol="HPG",
        side="NB",
        order_type="LO",
        quantity=100,
        price=26000.0,
        loan_package_id=1258
    )
    assert res.success is True
    assert res.order_id is not None
    assert "HPG" in res.message

    # 3. Test get orders
    orders = await client.get_orders(account_no)
    assert len(orders) > 0
    assert orders[0].symbol == "HPG"
    assert orders[0].quantity == 100

    # 4. Test cancel order
    cancel_res = await client.cancel_order(account_no, res.order_id)
    assert cancel_res.get("success") is True

    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\pytest tests/test_dnse_live_orders.py -v`
Expected: FAIL (AttributeError: 'MockDNSEClient' object has no attribute 'get_loan_packages')

- [ ] **Step 3: Update `dnse/models.py`, `dnse/client.py`, and `dnse/mock_client.py`**
Implement the required models and methods.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\pytest tests/test_dnse_live_orders.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add dnse/ tests/test_dnse_live_orders.py
git commit -m "feat(dnse): add live order endpoints, models, and mock client support"
```

---

### Task 2: Risk Safeguards Manager (`core/risk_safeguards.py`)

**Files:**
- Create: `core/risk_safeguards.py`
- Test: `tests/test_risk_safeguards.py`

**Interfaces:**
- Produces:
  - `TradingMode` enum (`PAPER`, `LIVE_CONFIRM`, `LIVE_AUTO`)
  - `RiskSafeguards` class with:
    - `validate_order(symbol, side, quantity, price, reference_price) -> tuple[bool, str]`
    - `activate_kill_switch(reason: str)`
    - `deactivate_kill_switch()`
    - `set_mode(mode: TradingMode)`
    - `record_order_sent()`
    - `reset_daily_counters()`

- [ ] **Step 1: Write failing test for Risk Safeguards**

```python
# tests/test_risk_safeguards.py
from core.risk_safeguards import RiskSafeguards, TradingMode

def test_risk_safeguards_limits():
    guard = RiskSafeguards(max_order_value=5000000.0, max_daily_orders=5)

    # 1. Normal order passes
    valid, msg = guard.validate_order("HPG", "NB", 100, 26000.0, reference_price=26000.0)
    assert valid is True

    # 2. Exceeds max order value (100 * 60,000 = 6,000,000 > 5,000,000)
    valid_val, msg_val = guard.validate_order("VHM", "NB", 100, 60000.0)
    assert valid_val is False
    assert "Hạn mức" in msg_val

    # 3. Exceeds HOSE price collar (+7% of 26,000 is 27,820; order at 29,000)
    valid_collar, msg_collar = guard.validate_order("HPG", "NB", 100, 29000.0, reference_price=26000.0)
    assert valid_collar is False
    assert "Trần/Sàn" in msg_collar

    # 4. Daily orders limit
    for _ in range(5):
        guard.record_order_sent()
    valid_daily, msg_daily = guard.validate_order("HPG", "NB", 100, 26000.0)
    assert valid_daily is False
    assert "Số lệnh tối đa" in msg_daily

def test_kill_switch_blocking():
    guard = RiskSafeguards()
    guard.activate_kill_switch("Thị trường sập bất thường")
    assert guard.kill_switch_active is True

    valid, msg = guard.validate_order("HPG", "NB", 100, 26000.0)
    assert valid is False
    assert "Kill Switch" in msg

    guard.deactivate_kill_switch()
    assert guard.kill_switch_active is False
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\pytest tests/test_risk_safeguards.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'core.risk_safeguards')

- [ ] **Step 3: Implement `core/risk_safeguards.py`**
Implement `TradingMode` and `RiskSafeguards`.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\pytest tests/test_risk_safeguards.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add core/risk_safeguards.py tests/test_risk_safeguards.py
git commit -m "feat(core): implement risk safeguards and emergency kill switch"
```

---

### Task 3: Live Order Execution Router & Auto-Trader Live Integration (`strategy/live_trader.py`, `strategy/auto_trader.py`)

**Files:**
- Create: `strategy/live_trader.py`
- Modify: `strategy/auto_trader.py`
- Test: `tests/test_live_trader.py`

**Interfaces:**
- Consumes: `RiskSafeguards`, `DNSEClient`, `PaperEngine`, `TradingState`, `TelegramNotifier`
- Produces:
  - `LiveTrader.route_order(symbol, side, quantity, price, reference_price, strategy_name, reason) -> dict`

- [ ] **Step 1: Write failing test for LiveTrader**

```python
# tests/test_live_trader.py
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

    # 3. In LIVE_AUTO mode, executes directly
    safeguards.set_mode(TradingMode.LIVE_AUTO)
    res_auto = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Test")
    assert res_auto["status"] == "EXECUTED"
    assert res_auto["order_id"] is not None

    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\pytest tests/test_live_trader.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'strategy.live_trader')

- [ ] **Step 3: Implement `strategy/live_trader.py` and modify `strategy/auto_trader.py`**
Implement `LiveTrader` and update `AutoTrader` to check safeguards and route through `LiveTrader`.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\pytest tests/test_live_trader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add strategy/live_trader.py strategy/auto_trader.py tests/test_live_trader.py
git commit -m "feat(strategy): implement live trader router and auto-trader live mode support"
```

---

### Task 4: Telegram Live Commands & Interactive Handlers (`bot/handlers/live.py`, `bot/keyboards.py`, `bot/app.py`, `main.py`)

**Files:**
- Create: `bot/handlers/live.py`
- Modify: `bot/keyboards.py`
- Modify: `bot/app.py`
- Modify: `main.py`
- Test: `tests/test_live_bot_handlers.py`

**Interfaces:**
- Produces Telegram commands:
  - `/mode [paper | live_confirm | live_auto]`
  - `/buy_live <SYMBOL> <QUANTITY> [PRICE]`
  - `/sell_live <SYMBOL> <QUANTITY> [PRICE]`
  - `/orders_live`
  - `/cancel_live <ORDER_ID>`
  - `/kill_switch`
  - `/resume`
  - Callback queries: `cb_confirm_live_order:<id>`, `cb_cancel_live_order:<id>`

- [ ] **Step 1: Write failing test for live bot handlers**

```python
# tests/test_live_bot_handlers.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, Chat, User
from bot.handlers.live import cmd_mode, cmd_kill_switch, cmd_resume
from core.risk_safeguards import RiskSafeguards, TradingMode
from dnse.mock_client import MockDNSEClient

@pytest.mark.asyncio
async def test_cmd_mode_and_kill_switch():
    safeguards = RiskSafeguards()
    client = MockDNSEClient()

    msg = MagicMock(spec=Message)
    msg.from_user = User(id=7385637982, is_bot=False, first_name="Admin")
    msg.chat = Chat(id=7385637982, type="private")
    msg.answer = AsyncMock()

    # 1. Check mode command
    msg.text = "/mode"
    await cmd_mode(msg, safeguards)
    assert "CHẾ ĐỘ GIAO DỊCH" in msg.answer.call_args[0][0]

    # 2. Switch mode to live_confirm
    msg.text = "/mode live_confirm"
    await cmd_mode(msg, safeguards)
    assert safeguards.mode == TradingMode.LIVE_CONFIRM

    # 3. Kill Switch command
    await cmd_kill_switch(msg, safeguards, client, "0001880229")
    assert safeguards.kill_switch_active is True
    assert "CẦU DAO KHẨN CẤP" in msg.answer.call_args[0][0]

    # 4. Resume command
    await cmd_resume(msg, safeguards)
    assert safeguards.kill_switch_active is False
    assert "ĐÃ KHÔI PHỤC" in msg.answer.call_args[0][0]

    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv\Scripts\pytest tests/test_live_bot_handlers.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'bot.handlers.live')

- [ ] **Step 3: Implement `bot/handlers/live.py`, update `bot/keyboards.py`, `bot/app.py`, and `main.py`**
Implement the handlers and register dependencies.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv\Scripts\pytest tests/test_live_bot_handlers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add bot/handlers/live.py bot/keyboards.py bot/app.py main.py tests/test_live_bot_handlers.py
git commit -m "feat(bot): add live trading commands, kill switch, and interactive approval"
```

---

### Task 5: End-to-End Live Order & Safeguards Verification (`tests/test_live_e2e.py`)

**Files:**
- Create: `tests/test_live_e2e.py`
- Modify: `README.md`
- Test: Full Pytest test suite (`pytest`)

**Interfaces:**
- Validates the entire integrated pipeline: Mode change -> Risk guard validation -> Order placement -> Order cancellation -> Kill switch emergency shutdown -> Tag `v0.4.0-live`.

- [ ] **Step 1: Write comprehensive end-to-end live simulation test**

```python
# tests/test_live_e2e.py
import pytest
from dnse.mock_client import MockDNSEClient
from core.risk_safeguards import RiskSafeguards, TradingMode
from strategy.live_trader import LiveTrader
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_full_live_trading_lifecycle():
    client = MockDNSEClient()
    safeguards = RiskSafeguards()
    notifier = AsyncMock()
    account_no = "0001880229"
    trader = LiveTrader(client=client, safeguards=safeguards, account_no=account_no, notify_func=notifier)

    # 1. Switch to LIVE_AUTO
    safeguards.set_mode(TradingMode.LIVE_AUTO)

    # 2. Place 100 shares of HPG
    res = await trader.route_order("HPG", "NB", 100, 26000.0, 26000.0, "BREAKOUT", "Strong volume")
    assert res["status"] == "EXECUTED"
    order_id = res["order_id"]

    # 3. Verify order in book
    orders = await client.get_orders(account_no)
    assert any(o.id == order_id for o in orders)

    # 4. Trigger Kill Switch
    safeguards.activate_kill_switch("Khẩn cấp: Thị trường rơi tự do")
    # Cancel all open orders
    for o in orders:
        await client.cancel_order(account_no, o.id)

    # 5. Subsequent orders blocked by Kill Switch
    res_blocked = await trader.route_order("TCB", "NB", 100, 22000.0, 22000.0, "BREAKOUT", "Test")
    assert res_blocked["status"] == "REJECTED"
    assert "Kill Switch" in res_blocked["reason"]

    # 6. Resume
    safeguards.deactivate_kill_switch()
    assert safeguards.kill_switch_active is False

    await client.close()
```

- [ ] **Step 2: Run full test suite**
Run: `.venv\Scripts\pytest -v`
Expected: ALL 50+ tests pass across Phase 1, Phase 2, Phase 3, and Phase 4.

- [ ] **Step 3: Update documentation and release tagging**
Update `README.md` with Phase 4 Live Trading & Safeguards documentation. Tag Git release `v0.4.0-live`.

- [ ] **Step 4: Commit and tag**
```bash
git add README.md tests/test_live_e2e.py
git commit -m "feat: complete Phase 4 live order execution and risk safeguards"
git tag -a v0.4.0-live -m "Release v0.4.0 - Live Order Execution & Risk Safeguards"
```
