import time
from datetime import datetime, timezone
import numpy as np
from market.models import Candle, OHLCVSeries

class MockMarketClient:
    async def get_candles(self, symbol: str, count: int = 150) -> OHLCVSeries:
        now = int(time.time())
        candles = []
        base_price = 50.0
        for i in range(count):
            t = now - (count - i) * 86400
            d_str = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
            noise = np.sin(i / 5.0) * 5.0 + (i * 0.1)
            c = base_price + noise
            h = c + 1.0
            l = c - 1.0
            o = c - 0.2
            v = int(1000000 + (i * 10000) % 500000)
            candles.append(Candle(
                timestamp=t,
                date_str=d_str,
                open=round(float(o), 2),
                high=round(float(h), 2),
                low=round(float(l), 2),
                close=round(float(c), 2),
                volume=int(v)
            ))
        return OHLCVSeries(symbol=symbol.upper(), resolution="1D", candles=candles)

    async def get_all_vn30_candles(self, symbols: list[str]) -> dict[str, OHLCVSeries]:
        res = {}
        for s in symbols:
            res[s.upper()] = await self.get_candles(s)
        return res

    async def close(self):
        pass
