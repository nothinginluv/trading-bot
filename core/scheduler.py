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

async def sync_market_data_job(market_client, state, repo, notifier=None, symbols=None):
    if not market_client:
        return
    from config.constants import VN30_SYMBOLS
    from indicators.calculator import compute_technical_summary
    target_symbols = symbols or VN30_SYMBOLS
    try:
        candles_dict = await market_client.get_all_vn30_candles(target_symbols)
        summaries_dict = {}
        for sym, series in candles_dict.items():
            if len(series) > 0:
                await repo.save_candles(sym, series)
                summary = compute_technical_summary(series)
                if summary:
                    summaries_dict[sym] = summary
                    if notifier and MarketHours.is_trading_time():
                        if summary.vol_ratio >= 2.0 and summary.change_pct >= 2.5:
                            alert_msg = (
                                f"🚀 **CẢNH BÁO ĐỘT BIẾN KHỐI LƯỢNG: {sym}**\n"
                                f"• Thị giá: `{summary.price:,.0f} đ` (`{summary.change_pct:+.2f}%`)\n"
                                f"• Khối lượng: `{summary.volume:,}` (Đạt `{summary.vol_ratio:.1f}x` TB20)\n"
                                f"• RSI (14): `{summary.rsi14:.1f}` | MACD: `{summary.macd_status}`"
                            )
                            await notifier.send_alert("Tín Hiệu Đột Biến VN30", alert_msg, level="INFO")

        state.set_market_data(candles_dict, summaries_dict)
        logger.info(f"Market sync complete: {len(summaries_dict)}/{len(target_symbols)} VN30 tickers calculated.")
    except Exception as e:
        logger.error(f"Market sync job failed: {e}")
        await repo.log_audit("ERROR", "MARKET_SYNC", f"Sync failed: {e}")

def setup_scheduler(client, state, repo, notifier=None, market_client=None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Periodic portfolio sync: every 60 seconds
    scheduler.add_job(sync_data_job, "interval", seconds=60, args=[client, state, repo, notifier])
    # Periodic market sync: every 3 minutes (180s)
    if market_client:
        scheduler.add_job(sync_market_data_job, "interval", seconds=180, args=[market_client, state, repo, notifier])
    # Daily market summary at 15:05 Mon-Fri
    scheduler.add_job(daily_summary_job, "cron", day_of_week="mon-fri", hour=15, minute=5, args=[state, notifier])
    return scheduler
