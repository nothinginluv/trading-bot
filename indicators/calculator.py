from typing import Tuple, Optional
import numpy as np
from market.models import OHLCVSeries
from indicators.models import TechnicalSummary

def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
    if len(prices) == 0:
        return np.array([])
    alpha = 2.0 / (period + 1.0)
    ema = np.zeros_like(prices, dtype=float)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1.0 - alpha) * ema[i - 1]
    return ema

def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    if len(prices) <= period:
        return np.full_like(prices, 50.0, dtype=float)
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rsi = np.zeros_like(prices, dtype=float)
    rsi[:period] = 50.0
    if down == 0 and up == 0:
        rsi[period] = 50.0
    elif down == 0:
        rsi[period] = 100.0
    else:
        rsi[period] = 100.0 - 100.0 / (1.0 + (up / down))

    for i in range(period + 1, len(prices)):
        delta = deltas[i - 1]
        up_val = delta if delta > 0 else 0.0
        down_val = -delta if delta < 0 else 0.0
        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
        if down == 0 and up == 0:
            rsi[i] = 50.0
        elif down == 0:
            rsi[i] = 100.0
        else:
            rsi[i] = 100.0 - 100.0 / (1.0 + (up / down))
    return rsi

def calculate_macd(prices: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def calculate_bollinger_bands(prices: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if len(prices) < period:
        return prices.copy(), prices.copy(), prices.copy()
    mid = np.zeros_like(prices, dtype=float)
    std = np.zeros_like(prices, dtype=float)
    for i in range(len(prices)):
        if i < period - 1:
            mid[i] = prices[:i + 1].mean()
            std[i] = prices[:i + 1].std()
        else:
            window = prices[i - period + 1:i + 1]
            mid[i] = window.mean()
            std[i] = window.std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return upper, mid, lower

def calculate_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    if len(closes) < 2:
        return np.zeros_like(closes)
    tr = np.zeros_like(closes)
    tr[0] = highs[0] - lows[0]
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)
    return calculate_ema(tr, period)

def calculate_vol_sma(volumes: np.ndarray, period: int = 20) -> np.ndarray:
    sma = np.zeros_like(volumes, dtype=float)
    for i in range(len(volumes)):
        start_idx = max(0, i - period + 1)
        sma[i] = volumes[start_idx:i + 1].mean()
    return sma

def compute_technical_summary(series: OHLCVSeries) -> Optional[TechnicalSummary]:
    if len(series) < 15:
        return None
    closes = series.closes_np
    highs = series.highs_np
    lows = series.lows_np
    opens = series.opens_np
    volumes = series.volumes_np

    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200) if len(closes) >= 100 else None

    rsi14 = calculate_rsi(closes, 14)
    macd, signal, hist = calculate_macd(closes, 12, 26, 9)
    bb_upper, bb_mid, bb_lower = calculate_bollinger_bands(closes, 20, 2.0)
    atr = calculate_atr(highs, lows, closes, 14)
    vol_sma = calculate_vol_sma(volumes, 20)

    cur_price = float(closes[-1])
    prev_close = float(closes[-2]) if len(closes) >= 2 else cur_price
    change = cur_price - prev_close
    change_pct = (change / prev_close) * 100.0 if prev_close != 0 else 0.0

    cur_vol = int(volumes[-1])
    cur_vol_sma = float(vol_sma[-1])
    vol_ratio = (cur_vol / cur_vol_sma) if cur_vol_sma > 0 else 1.0

    # Trend logic
    if cur_price > ema21[-1] and ema21[-1] > ema50[-1]:
        trend = "UPTREND"
    elif cur_price < ema21[-1] and ema21[-1] < ema50[-1]:
        trend = "DOWNTREND"
    else:
        trend = "SIDEWAYS"

    # RSI status
    if rsi14[-1] < 35:
        rsi_status = "OVERSOLD"
    elif rsi14[-1] > 70:
        rsi_status = "OVERBOUGHT"
    else:
        rsi_status = "NEUTRAL"

    # MACD status
    if len(hist) >= 2:
        if hist[-2] < 0 and hist[-1] >= 0:
            macd_status = "BULLISH_CROSS"
        elif hist[-2] > 0 and hist[-1] <= 0:
            macd_status = "BEARISH_CROSS"
        elif hist[-1] >= 0:
            macd_status = "BULLISH"
        else:
            macd_status = "BEARISH"
    else:
        macd_status = "NEUTRAL"

    # Composite signal
    if trend == "UPTREND" and (macd_status in ("BULLISH_CROSS", "BULLISH")) and vol_ratio >= 1.2:
        composite = "MUA MẠNH"
    elif rsi_status == "OVERSOLD" or cur_price <= bb_lower[-1] * 1.01:
        composite = "THEO DÕI MUA"
    elif rsi_status == "OVERBOUGHT" or cur_price >= bb_upper[-1]:
        composite = "CẢNH BÁO BÁN"
    elif trend == "DOWNTREND" and macd_status == "BEARISH":
        composite = "BÁN"
    else:
        composite = "TRUNG LẬP"

    return TechnicalSummary(
        symbol=series.symbol,
        price=cur_price,
        change=round(change, 2),
        change_pct=round(change_pct, 2),
        open=float(opens[-1]),
        high=float(highs[-1]),
        low=float(lows[-1]),
        volume=cur_vol,
        vol_sma20=round(cur_vol_sma, 0),
        vol_ratio=round(vol_ratio, 2),
        ema9=round(float(ema9[-1]), 2),
        ema21=round(float(ema21[-1]), 2),
        ema50=round(float(ema50[-1]), 2),
        ema200=round(float(ema200[-1]), 2) if ema200 is not None else None,
        rsi14=round(float(rsi14[-1]), 1),
        macd=round(float(macd[-1]), 2),
        macd_signal=round(float(signal[-1]), 2),
        macd_hist=round(float(hist[-1]), 2),
        bb_upper=round(float(bb_upper[-1]), 2),
        bb_middle=round(float(bb_mid[-1]), 2),
        bb_lower=round(float(bb_lower[-1]), 2),
        atr14=round(float(atr[-1]), 2),
        trend=trend,
        rsi_status=rsi_status,
        macd_status=macd_status,
        composite_signal=composite
    )

def evaluate_market_regime(summary: Optional[TechnicalSummary]) -> str:
    """
    Evaluates market regime based on benchmark index (e.g. VN-INDEX).
    Returns 'BULLISH', 'BEARISH', or 'SIDEWAYS'.
    - BEARISH: Price < EMA50 or (Price < EMA21 and RSI < 45) -> high risk, block new buys.
    - BULLISH: Price >= EMA21 and RSI >= 48 -> healthy uptrend, allow new buys.
    - SIDEWAYS: transitional / consolidation range.
    """
    if not summary:
        return "SIDEWAYS"
    
    price = summary.price
    ema21 = summary.ema21
    ema50 = summary.ema50
    rsi = summary.rsi14

    # 1. Bearish conditions: Price broken below EMA50 or broken EMA21 with weak momentum
    if ema50 is not None and price < ema50:
        return "BEARISH"
    if ema21 is not None and price < ema21 and rsi < 45.0:
        return "BEARISH"

    # 2. Bullish condition: Above short-term EMA21 with healthy momentum
    if ema21 is not None and price >= ema21 and rsi >= 48.0:
        return "BULLISH"

    return "SIDEWAYS"


def calculate_price_correlation(prices_a: np.ndarray, prices_b: np.ndarray, window: int = 30) -> float:
    """
    Calculates Pearson correlation of daily percentage returns between two price series
    over a rolling window (default 30 sessions).
    Returns a float in [-1.0, 1.0].
    Returns 0.0 if either series has insufficient data (< 4 points) or zero return variance.
    """
    if len(prices_a) < 4 or len(prices_b) < 4:
        return 0.0
    min_len = min(len(prices_a), len(prices_b), window + 1)
    sub_a = prices_a[-min_len:]
    sub_b = prices_b[-min_len:]

    if np.any(sub_a[:-1] <= 0) or np.any(sub_b[:-1] <= 0):
        return 0.0

    ret_a = np.diff(sub_a) / sub_a[:-1]
    ret_b = np.diff(sub_b) / sub_b[:-1]

    std_a = np.std(ret_a)
    std_b = np.std(ret_b)
    if std_a < 1e-9 or std_b < 1e-9:
        return 0.0

    corr = np.corrcoef(ret_a, ret_b)[0, 1]
    if np.isnan(corr) or np.isinf(corr):
        return 0.0
    return float(np.clip(corr, -1.0, 1.0))


def calculate_series_correlation(series_a: OHLCVSeries, series_b: OHLCVSeries, window: int = 30) -> float:
    """
    Calculates Pearson correlation between two OHLCVSeries by aligning dates/timestamps.
    Handles holidays, special sessions, and uneven series lengths cleanly.
    """
    if not series_a or not series_b or len(series_a.candles) < 4 or len(series_b.candles) < 4:
        return 0.0

    # Build date-to-close mappings
    map_a = {}
    for c in series_a.candles:
        date_key = c.timestamp.date() if hasattr(c.timestamp, "date") else str(c.timestamp)[:10]
        map_a[date_key] = c.close

    map_b = {}
    for c in series_b.candles:
        date_key = c.timestamp.date() if hasattr(c.timestamp, "date") else str(c.timestamp)[:10]
        map_b[date_key] = c.close

    common_dates = sorted(set(map_a.keys()) & set(map_b.keys()))
    if len(common_dates) < 4:
        return 0.0

    recent_dates = common_dates[-(window + 1):]
    prices_a = np.array([map_a[d] for d in recent_dates], dtype=float)
    prices_b = np.array([map_b[d] for d in recent_dates], dtype=float)

    return calculate_price_correlation(prices_a, prices_b, window=window)



