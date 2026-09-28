import time
from datetime import datetime, timezone
import numpy as np
from market.models import Candle, OHLCVSeries

class MockMarketClient:
    async def get_candles(self, symbol: str, count: int = 150, resolution: str = "1D") -> OHLCVSeries:
        now = int(time.time())
        candles = []
        base_price = 50.0
        res_clean = "15" if resolution in ("15", "15m", "15M") else "1D"
        step = 900 if res_clean == "15" else 86400
        date_fmt = "%Y-%m-%d %H:%M" if res_clean == "15" else "%Y-%m-%d"
        for i in range(count):
            t = now - (count - i) * step
            d_str = datetime.fromtimestamp(t, timezone.utc).strftime(date_fmt)
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
        return OHLCVSeries(symbol=symbol.upper(), resolution=res_clean, candles=candles)

    async def get_all_vn30_candles(self, symbols: list[str], resolution: str = "1D") -> dict[str, OHLCVSeries]:
        res = {}
        for s in symbols:
            res[s.upper()] = await self.get_candles(s, resolution=resolution)
        return res

    async def close(self):
        pass
