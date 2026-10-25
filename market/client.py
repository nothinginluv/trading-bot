import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
import httpx
from market.models import Candle, OHLCVSeries

logger = logging.getLogger(__name__)
VN_TZ = timezone(timedelta(hours=7))

class AsyncMarketClient:
    BASE_URL = "https://services.entrade.com.vn/chart-api/v2"

    def __init__(self, timeout: float = 10.0, max_concurrency: int = 5):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def get_candles(self, symbol: str, count: int = 150, resolution: str = "1D") -> OHLCVSeries:
        now = int(time.time())
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        if res_clean == "15":
            # 15m candles: 16 candles/day, 15 days is ~240 candles
            start = now - max(int(count * 15 * 60 * 3), 15 * 86400)
            date_fmt = "%Y-%m-%d %H:%M"
        else:
            start = now - int(count * 1.5 * 86400)
            date_fmt = "%Y-%m-%d"

        endpoint = "ohlcs/index" if symbol.upper() in ("VNINDEX", "VN30", "HNXINDEX") else "ohlcs/stock"
        url = f"{self.BASE_URL}/{endpoint}?from={start}&to={now}&symbol={symbol.upper()}&resolution={res_clean}"
        
        async with self.semaphore:
            for attempt in range(2):
                try:
                    resp = await self.client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        t_list = data.get("t", []) or []
                        o_list = data.get("o", []) or []
                        h_list = data.get("h", []) or []
                        l_list = data.get("l", []) or []
                        c_list = data.get("c", []) or []
                        v_list = data.get("v", []) or []
                        
                        candles = []
                        for i in range(len(t_list)):
                            t = int(t_list[i])
                            d_str = datetime.fromtimestamp(t, VN_TZ).strftime(date_fmt)
                            candles.append(Candle(
                                timestamp=t,
                                date_str=d_str,
                                open=float(o_list[i]),
                                high=float(h_list[i]),
                                low=float(l_list[i]),
                                close=float(c_list[i]),
                                volume=int(v_list[i])
                            ))
                        return OHLCVSeries(symbol=symbol.upper(), resolution=res_clean, candles=candles)
                    logger.warning(f"Entrade API {symbol} ({res_clean}) returned status {resp.status_code}")
                except Exception as e:
                    if attempt == 1:
                        logger.error(f"Failed to fetch {res_clean} candles for {symbol}: {e}")
                    await asyncio.sleep(0.5)

        return OHLCVSeries(symbol=symbol.upper(), resolution=res_clean, candles=[])

    async def get_all_vn30_candles(self, symbols: List[str], resolution: str = "1D") -> Dict[str, OHLCVSeries]:
        tasks = [self.get_candles(s, resolution=resolution) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        out = {}
        for s, res in zip(symbols, results):
            if isinstance(res, OHLCVSeries):
                out[s.upper()] = res
            else:
                logger.error(f"Error fetching {s} ({res_clean}): {res}")
                out[s.upper()] = OHLCVSeries(symbol=s.upper(), resolution=res_clean, candles=[])
        return out

    async def close(self):
        await self.client.aclose()
