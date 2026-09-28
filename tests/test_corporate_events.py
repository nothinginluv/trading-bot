import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message
from news.models import CorporateEvent, EventType
from news.crawler import AsyncNewsCrawler
from storage.db import init_db
from storage.repository import SqliteRepository, PaperTradingRepository
from core.state import TradingState
from bot.handlers.news import cmd_events

SAMPLE_CAFEF_EVENTS_HTML = """
<table class="CafeF_LichSuKien">
    <tr>
        <th>Ngày GD không hưởng quyền</th>
        <th>Ngày ĐKCC</th>
        <th>Ngày thực hiện</th>
        <th>Mã CK</th>
        <th>Sàn</th>
        <th>Nội dung sự kiện</th>
    </tr>
    <tr>
        <td>15/05/2026</td>
        <td>16/05/2026</td>
        <td>01/06/2026</td>
        <td>FPT</td>
        <td>HSX</td>
        <td>Trả cổ tức đợt 2/2025 bằng tiền mặt tỷ lệ 10%</td>
    </tr>
    <tr>
        <td>20/05/2026</td>
        <td>21/05/2026</td>
        <td>15/06/2026</td>
        <td>MBB</td>
        <td>HSX</td>
        <td>Trả cổ tức bằng cổ phiếu tỷ lệ 15% và phát hành cổ phiếu thưởng</td>
    </tr>
    <tr>
        <td>25/05/2026</td>
        <td>26/05/2026</td>
        <td>01/07/2026</td>
        <td>SSI</td>
        <td>HSX</td>
        <td>Chào bán phát hành thêm cổ phiếu cho cổ đông hiện hữu tỷ lệ 10:1</td>
    </tr>
    <tr>
        <td>01/06/2026</td>
        <td>02/06/2026</td>
        <td>15/07/2026</td>
        <td>MWG</td>
        <td>HSX</td>
        <td>Phát hành 10.000.000 cổ phiếu theo chương trình ESOP</td>
    </tr>
    <tr>
        <td>01/01/0001</td>
        <td>01/01/0001</td>
        <td>10/08/2026</td>
        <td>VPB</td>
        <td>HSX</td>
        <td>Giao dịch 50.000.000 cp niêm yết bổ sung</td>
    </tr>
</table>
"""

def test_parse_corporate_events():
    crawler = AsyncNewsCrawler()
    events = crawler.parse_corporate_events(SAMPLE_CAFEF_EVENTS_HTML)
    assert len(events) == 5

    # Event 1: FPT Dividend Cash
    ev_fpt = next(e for e in events if e.symbol == "FPT")
    assert ev_fpt.ex_date == "2026-05-15"
    assert ev_fpt.record_date == "2026-05-16"
    assert ev_fpt.event_type == EventType.DIVIDEND_CASH
    assert "10%" in ev_fpt.content

    # Event 2: MBB Dividend Stock
    ev_mbb = next(e for e in events if e.symbol == "MBB")
    assert ev_mbb.ex_date == "2026-05-20"
    assert ev_mbb.event_type == EventType.DIVIDEND_STOCK

    # Event 3: SSI Issue Additional
    ev_ssi = next(e for e in events if e.symbol == "SSI")
    assert ev_ssi.ex_date == "2026-05-25"
    assert ev_ssi.event_type == EventType.ISSUE_ADDITIONAL

    # Event 4: MWG ESOP
    ev_mwg = next(e for e in events if e.symbol == "MWG")
    assert ev_mwg.ex_date == "2026-06-01"
    assert ev_mwg.event_type == EventType.ESOP

    # Event 5: VPB Listing (01/01/0001 should become None)
    ev_vpb = next(e for e in events if e.symbol == "VPB")
    assert ev_vpb.ex_date is None
    assert ev_vpb.event_type == EventType.LISTING

@pytest.mark.asyncio
async def test_corporate_events_repository_persistence(tmp_path):
    db_path = str(tmp_path / "test_events.db")
    await init_db(db_path)
    repo = SqliteRepository(db_path)

    events = [
        CorporateEvent(
            id="ev-1",
            symbol="TCB",
            ex_date="2026-06-10",
            record_date="2026-06-11",
            event_type=EventType.DIVIDEND_CASH,
            content="Trả cổ tức tiền mặt 15%",
            source="CafeF"
        ),
        CorporateEvent(
            id="ev-2",
            symbol="HPG",
            ex_date="2026-06-15",
            record_date="2026-06-16",
            event_type=EventType.DIVIDEND_STOCK,
            content="Chia cổ tức cổ phiếu 10%",
            source="CafeF"
        )
    ]

    saved = await repo.save_corporate_events(events)
    assert saved == 2

    # Query all upcoming events
    all_evs = await repo.get_upcoming_events()
    assert len(all_evs) == 2

    # Query by symbol
    tcb_evs = await repo.get_upcoming_events(symbol="TCB")
    assert len(tcb_evs) == 1
    assert tcb_evs[0].symbol == "TCB"
    assert tcb_evs[0].event_type == EventType.DIVIDEND_CASH

    # Test is_ex_date_near
    is_tcb_ex = await repo.is_ex_date_near("TCB", "2026-06-10")
    assert is_tcb_ex is True

    is_tcb_not_ex = await repo.is_ex_date_near("TCB", "2026-06-11")
    assert is_tcb_not_ex is False

    # Check via PaperTradingRepository helper
    paper_repo = PaperTradingRepository(db_path)
    assert await paper_repo.is_ex_date_near("TCB", "2026-06-10") is True

@pytest.mark.asyncio
async def test_cmd_events_telegram_handler(tmp_path):
    db_path = str(tmp_path / "test_cmd_events.db")
    await init_db(db_path)
    repo = SqliteRepository(db_path)

    state = TradingState()
    ev = CorporateEvent(
        id="ev-fpt",
        symbol="FPT",
        ex_date="2026-05-15",
        record_date="2026-05-16",
        event_type=EventType.DIVIDEND_CASH,
        content="Trả cổ tức tiền mặt 1.000 đ/cp (10%)"
    )
    state.set_corporate_events([ev])

    # 1. Query all events
    msg = MagicMock(spec=Message)
    msg.text = "/events"
    msg.answer = AsyncMock()

    await cmd_events(msg, state, repo=repo)
    msg.answer.assert_called_once()
    out = msg.answer.call_args[0][0]
    assert "LỊCH SỰ KIỆN" in out
    assert "FPT" in out
    assert "2026-05-15" in out

    # 2. Query specific symbol
    msg2 = MagicMock(spec=Message)
    msg2.text = "/events FPT"
    msg2.answer = AsyncMock()

    await cmd_events(msg2, state, repo=repo)
    msg2.answer.assert_called_once()
    out2 = msg2.answer.call_args[0][0]
    assert "LỊCH SỰ KIỆN DOANH NGHIỆP: FPT" in out2
    assert "DIVIDEND_CASH" in out2
    assert "1.000 đ/cp" in out2
