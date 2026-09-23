import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List
import httpx
from market.models import Candle, OHLCVSeries

logger = logging.getLogger(__name__)

class AsyncMarketClient:
    BASE_URL = "https://services.entrade.com.vn/chart-api/v2"

    def __init__(self, timeout: float = 10.0, max_concurrency: int = 5):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def get_candles(self, symbol: str, count: int = 150) -> OHLCVSeries:
        now = int(time.time())
        start = now - int(count * 1.5 * 86400)
        url = f"{self.BASE_URL}/ohlcs/stock?from={start}&to={now}&symbol={symbol.upper()}&resolution=1D"
        
        async with self.semaphore:
            for attempt in range(2):
                try:
                    resp = await self.client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        t_list = data.get("t", [])
                        o_list = data.get("o", [])
                        h_list = data.get("h", [])
                        l_list = data.get("l", [])
                        c_list = data.get("c", [])
                        v_list = data.get("v", [])
                        
                        candles = []
                        for i in range(len(t_list)):
                            t = int(t_list[i])
                            d_str = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
                            candles.append(Candle(
                                timestamp=t,
                                date_str=d_str,
                                open=float(o_list[i]),
                                high=float(h_list[i]),
                                low=float(l_list[i]),
                                close=float(c_list[i]),
                                volume=int(v_list[i])
                            ))
                        return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=candles)
                    logger.warning(f"Entrade API {symbol} returned status {resp.status_code}")
                except Exception as e:
                    if attempt == 1:
                        logger.error(f"Failed to fetch candles for {symbol}: {e}")
                    await asyncio.sleep(0.5)

        return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=[])

    async def get_all_vn30_candles(self, symbols: List[str]) -> Dict[str, OHLCVSeries]:
        tasks = [self.get_candles(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = {}
        for s, res in zip(symbols, results):
            if isinstance(res, OHLCVSeries):
                out[s.upper()] = res
            else:
                logger.error(f"Error fetching {s}: {res}")
                out[s.upper()] = OHLCVSeries(symbol=s.upper(), resolution="1D", candles=[])
        return out

    async def close(self):
        await self.client.aclose()
