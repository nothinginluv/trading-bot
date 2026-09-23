import logging
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.market_hours import MarketHours

logger = logging.getLogger(__name__)

async def sync_data_job(client, state, repo, notifier=None):
    if not client or not state.account:
        return
    sub_id = state.account.accounts[0].id
    try:
        start = time.time()
        bal = await client.get_balances(sub_id)
        pos = await client.get_positions(sub_id)
        state.latency_ms = (time.time() - start) * 1000
        state.set_balance(bal)
        state.set_positions(pos)
        await repo.save_balance_snapshot(
            sub_id, bal.stock.totalCash, bal.stock.availableCash, bal.stock.totalDebt, bal.stock.withdrawableCash
        )
        logger.debug(f"Background sync complete ({state.latency_ms:.1f}ms)")
    except Exception as e:
        logger.error(f"Background sync error: {e}")
        await repo.log_audit("ERROR", "SCHEDULER", f"Sync failed: {e}")

async def daily_summary_job(state, notifier):
    if not notifier or not state.balance:
        return
    bal = state.balance.stock
    acc = state.account
    msg = (
        f"📊 **TỔNG KẾT PHIÊN GIAO DỊCH (15:05)**\n"
        f"• Tài khoản: `{acc.custodyCode if acc else 'N/A'}`\n"
        f"• Tiền mặt: `{bal.totalCash:,.0f} đ`\n"
        f"• Số vị thế nắm giữ qua đêm: {len(state.positions)} mã"
    )
    await notifier.send_alert("Tổng kết cuối phiên", msg, level="INFO")

def setup_scheduler(client, state, repo, notifier=None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Periodic sync: every 60 seconds
    scheduler.add_job(sync_data_job, "interval", seconds=60, args=[client, state, repo, notifier])
    # Daily market summary at 15:05 Mon-Fri
    scheduler.add_job(daily_summary_job, "cron", day_of_week="mon-fri", hour=15, minute=5, args=[state, notifier])
    return scheduler
