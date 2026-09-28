import logging
import time
from datetime import datetime
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

async def sync_market_data_job(market_client, state, repo, notifier=None, symbols=None, auto_trader=None):
    if not market_client:
        return
    from config.constants import VN30_SYMBOLS
    from indicators.calculator import compute_technical_summary
    target_symbols = symbols or VN30_SYMBOLS
    try:
        # 1. Fetch Benchmark VNINDEX for Market Regime Filter
        try:
            vnindex_series = await market_client.get_candles("VNINDEX", count=150)
            if len(vnindex_series) > 0:
                vnindex_summary = compute_technical_summary(vnindex_series)
                # Fetch fresh intraday VNINDEX for realtime benchmark
                try:
                    vnindex_15m = await market_client.get_candles("VNINDEX", count=20, resolution="15")
                    if len(vnindex_15m) > 0 and vnindex_summary:
                        last_pt = vnindex_15m.candles[-1]
                        last_1d = vnindex_series.candles[-1]
                        if last_pt.timestamp > last_1d.timestamp:
                            prev_close = last_1d.close
                            cur_price = last_pt.close
                            change = cur_price - prev_close
                            change_pct = (change / prev_close) * 100.0 if prev_close else 0.0
                            vnindex_summary.price = round(cur_price, 2)
                            vnindex_summary.change = round(change, 2)
                            vnindex_summary.change_pct = round(change_pct, 2)
                except Exception as ex_intra:
                    logger.debug(f"Could not fetch intraday VNINDEX: {ex_intra}")

                if vnindex_summary:
                    prev_regime = state.market_regime
                    state.set_market_regime(vnindex_summary, vnindex_series)
                    logger.info(
                        f"VNINDEX synced: Price {vnindex_summary.price:,.1f}, "
                        f"Regime: {state.market_regime} (EMA21: {vnindex_summary.ema21}, RSI: {vnindex_summary.rsi14})"
                    )
                    if notifier and prev_regime != state.market_regime and MarketHours.is_trading_time():
                        status_emoji = "🟢" if state.market_regime == "BULLISH" else ("🔴" if state.market_regime == "BEARISH" else "🟡")
                        gate_text = "CHO PHÉP GIẢI NGÂN MỚI" if state.market_regime != "BEARISH" else "TẠM DỪNG MỞ VỊ THẾ MUA (BẢO TOÀN VỐN)"
                        regime_msg = (
                            f"{status_emoji} **THAY ĐỔI TRẠNG THÁI THỊ TRƯỜNG: {state.market_regime}**\n"
                            f"• VN-INDEX: `{vnindex_summary.price:,.1f}` (`{vnindex_summary.change_pct:+.2f}%`)\n"
                            f"• RSI(14): `{vnindex_summary.rsi14:.1f}` | EMA21: `{vnindex_summary.ema21:,.1f}`\n"
                            f"• Cơ chế: **{gate_text}**"
                        )
                        await notifier.send_alert("Bộ Lọc Thị Trường VN-Index", regime_msg, level="INFO")
        except Exception as e:
            logger.error(f"Failed to sync VNINDEX benchmark: {e}")

        # 2. Fetch VN30 components (1D Daily)
        candles_dict = await market_client.get_all_vn30_candles(target_symbols, resolution="1D")
        summaries_dict = {}
        for sym, series in candles_dict.items():
            if len(series) > 0:
                await repo.save_candles(sym, series)
                summary = compute_technical_summary(series)
                if summary:
                    summaries_dict[sym] = summary

        # 3. Fetch VN30 components (15m Intraday for precision timing triggers & realtime price update)
        try:
            candles_15m_dict = await market_client.get_all_vn30_candles(target_symbols, resolution="15")
            summaries_15m_dict = {}
            today_date_str = datetime.now(MarketHours.VN_TZ).strftime("%Y-%m-%d")

            for sym, series_15m in candles_15m_dict.items():
                if len(series_15m) > 0:
                    summary_15m = compute_technical_summary(series_15m)
                    if summary_15m:
                        summaries_15m_dict[sym] = summary_15m

                    # Patch 1D summary with live intraday price & session stats if 15m is newer than 1D
                    if sym in summaries_dict and sym in candles_dict and len(candles_dict[sym]) > 0:
                        series_1D = candles_dict[sym]
                        latest_1D = series_1D.candles[-1]
                        latest_15m = series_15m.candles[-1]

                        if latest_15m.timestamp > latest_1D.timestamp:
                            prev_close = latest_1D.close
                            cur_price = latest_15m.close
                            change = cur_price - prev_close
                            change_pct = (change / prev_close) * 100.0 if prev_close else 0.0

                            today_candles = [c for c in series_15m.candles if c.date_str.startswith(today_date_str)]
                            if today_candles:
                                today_vol = sum(c.volume for c in today_candles)
                                today_high = max(c.high for c in today_candles)
                                today_low = min(c.low for c in today_candles)
                                today_open = today_candles[0].open
                            else:
                                today_vol = latest_15m.volume
                                today_high = latest_15m.high
                                today_low = latest_15m.low
                                today_open = latest_15m.open

                            s = summaries_dict[sym]
                            s.price = cur_price
                            s.open = today_open
                            s.high = today_high
                            s.low = today_low
                            s.volume = today_vol
                            s.change = round(change, 2)
                            s.change_pct = round(change_pct, 2)
                            if s.vol_sma20 > 0:
                                s.vol_ratio = round(today_vol / s.vol_sma20, 2)

            state.set_market_data(candles_15m_dict, summaries_15m_dict, resolution="15")
        except Exception as e:
            logger.warning(f"Could not sync 15m candles: {e}")

        # Update 1D market data with live patched summaries
        state.set_market_data(candles_dict, summaries_dict, resolution="1D")

        # Volume spike alerts with live data
        if notifier and MarketHours.is_trading_time():
            for sym, summary in summaries_dict.items():
                if summary.vol_ratio >= 2.0 and summary.change_pct >= 2.5:
                    price_str = f"{summary.price:,.1f} ({summary.price*1000:,.0f} đ)" if summary.price < 1000 else f"{summary.price:,.0f} đ"
                    alert_msg = (
                        f"🚀 **CẢNH BÁO ĐỘT BIẾN KHỐI LƯỢNG: {sym}**\n"
                        f"• Thị giá: `{price_str}` (`{summary.change_pct:+.2f}%`)\n"
                        f"• Khối lượng: `{summary.volume:,}` (Đạt `{summary.vol_ratio:.1f}x` TB20)\n"
                        f"• RSI (14): `{summary.rsi14:.1f}` | MACD: `{summary.macd_status}`"
                    )
                    await notifier.send_alert("Tín Hiệu Đột Biến VN30", alert_msg, level="INFO")

        # 4. Update NAV Tracking for Circuit Breaker
        if auto_trader and hasattr(auto_trader, "engine"):
            try:
                current_prices = {s: summ.price for s, summ in summaries_dict.items()}
                acc = await auto_trader.engine.get_account_summary(current_prices)
                now_dt = datetime.now()
                today_str = now_dt.strftime("%Y-%m-%d")
                week_num = now_dt.isocalendar()[1]
                state.update_nav_tracker(acc.nav, today_str, week_num)
            except Exception as e:
                logger.debug(f"NAV tracking update skipped: {e}")

        logger.info(f"Market sync complete: {len(summaries_dict)}/{len(target_symbols)} VN30 tickers (1D & 15m). Regime: {state.market_regime}")

        # Process Auto-Trader cycle
        if auto_trader:
            await auto_trader.process_cycle()

    except Exception as e:
        logger.error(f"Market sync job failed: {e}")
        await repo.log_audit("ERROR", "MARKET_SYNC", f"Sync failed: {e}")

async def sync_news_job(crawler, analyzer, state, repo, notifier=None, auto_trader=None):
    if not crawler or not analyzer:
        return
    try:
        raw_articles = await crawler.fetch_all_news()
        processed_articles = [analyzer.process_article(a) for a in raw_articles]
        
        if repo and hasattr(repo, "save_news_articles"):
            await repo.save_news_articles(processed_articles)

        prev_crises = set(state.severe_crisis_symbols.keys())
        state.set_news(processed_articles)
        new_crises = set(state.severe_crisis_symbols.keys()) - prev_crises

        # Fetch Corporate Events & Official Disclosures (CafeF Events Feed)
        if hasattr(crawler, "fetch_corporate_events"):
            try:
                events = await crawler.fetch_corporate_events()
                if events:
                    if repo and hasattr(repo, "save_corporate_events"):
                        await repo.save_corporate_events(events)
                    state.set_corporate_events(events)
                    logger.info(f"Corporate events sync complete: {len(events)} events loaded.")
            except Exception as ev_err:
                logger.error(f"Error syncing corporate events: {ev_err}")

        logger.info(f"News sync complete: {len(processed_articles)} articles processed. Crises: {list(state.severe_crisis_symbols.keys())}")

        if notifier and new_crises:
            for c_sym in new_crises:
                reason = state.severe_crisis_symbols[c_sym]
                await notifier.send_alert(
                    "Cảnh Báo Tin Tức Khủng Hoảng",
                    f"🚨 **PHÁT HIỆN TIN CỰC XẤU: {c_sym}**\n"
                    f"• Tiêu đề: {reason}\n"
                    f"• Nguồn: CafeF / Vietstock\n"
                    f"• Hệ thống áp dụng cơ chế tự động bảo vệ vốn (2B)!",
                    level="ERROR"
                )

        if auto_trader and state.severe_crisis_symbols:
            await auto_trader.process_cycle()

    except Exception as e:
        logger.error(f"News sync job failed: {e}")
        if repo and hasattr(repo, "log_audit"):
            await repo.log_audit("ERROR", "NEWS_SYNC", f"Sync failed: {e}")

def setup_scheduler(client, state, repo, notifier=None, market_client=None, auto_trader=None, news_crawler=None, news_analyzer=None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MarketHours.VN_TZ)
    # Periodic portfolio sync: every 60 seconds
    scheduler.add_job(sync_data_job, "interval", seconds=60, args=[client, state, repo, notifier])
    # Periodic market sync: every 3 minutes (180s)
    if market_client:
        scheduler.add_job(sync_market_data_job, "interval", seconds=180, args=[market_client, state, repo, notifier, None, auto_trader])
    # Periodic news sync: every 10 minutes (600s)
    if news_crawler and news_analyzer:
        scheduler.add_job(sync_news_job, "interval", seconds=600, args=[news_crawler, news_analyzer, state, repo, notifier, auto_trader])
    # Daily market summary at 15:05 Mon-Fri
    scheduler.add_job(daily_summary_job, "cron", day_of_week="mon-fri", hour=15, minute=5, args=[state, notifier])
    return scheduler
