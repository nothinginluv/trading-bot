from datetime import datetime
from zoneinfo import ZoneInfo
from core.market_hours import MarketHours
from core.state import TradingState
from dnse.models import AccountInfo, SubAccount, AccountBalance, StockBalance, PositionItem

def test_market_hours():
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    # Saturday
    dt_sat = datetime(2026, 9, 26, 10, 0, tzinfo=tz)
    assert MarketHours.get_session(dt_sat) == "CLOSED"
    
    # Monday 09:05 -> ATO
    dt_ato = datetime(2026, 9, 28, 9, 5, tzinfo=tz)
    assert MarketHours.get_session(dt_ato) == "ATO"

    # Monday 10:00 -> CONTINUOUS
    dt_cont = datetime(2026, 9, 28, 10, 0, tzinfo=tz)
    assert MarketHours.get_session(dt_cont) == "CONTINUOUS"

    # Monday 12:00 -> LUNCH_BREAK
    dt_lunch = datetime(2026, 9, 28, 12, 0, tzinfo=tz)
    assert MarketHours.get_session(dt_lunch) == "LUNCH_BREAK"

    # Monday 14:35 -> ATC
    dt_atc = datetime(2026, 9, 28, 14, 35, tzinfo=tz)
    assert MarketHours.get_session(dt_atc) == "ATC"

    # Monday 15:10 -> CLOSED
    dt_closed = datetime(2026, 9, 28, 15, 10, tzinfo=tz)
    assert MarketHours.get_session(dt_closed) == "CLOSED"

def test_trading_state():
    state = TradingState()
    assert state.is_connected is False
    
    account = AccountInfo(
        name="Nguyễn Doãn Minh Hiếu",
        custodyCode="064C551408",
        investorId="1001382802",
        accounts=[SubAccount(id="0001880229")]
    )
    state.set_account(account)
    assert state.account.custodyCode == "064C551408"
    assert state.is_connected is True

    balance = AccountBalance(
        stock=StockBalance(totalCash=27860.0, availableCash=27856.0)
    )
    state.set_balance(balance)
    assert state.balance.stock.availableCash == 27856.0
    assert state.is_cache_valid(ttl_seconds=10.0) is True
