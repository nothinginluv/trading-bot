import re
from dataclasses import dataclass
from typing import Optional
from news.models import CorporateEvent, EventType

@dataclass
class PositionAdjustmentInfo:
    adjustment_type: str       # "STOCK_DIVIDEND", "CASH_DIVIDEND", "STOCK_SPLIT"
    ratio: float               # e.g. 0.15 for 15%
    multiplier: float          # factor for quantity (new_qty = round(old_qty * multiplier))
    cash_per_share: float      # VND per share for cash dividend
    description: str = ""

def parse_event_adjustment(event: CorporateEvent) -> Optional[PositionAdjustmentInfo]:
    """
    Parses a CorporateEvent to determine if and how a held position's
    quantity, cost basis, and price thresholds should be adjusted on Ex-Date (ngày GDKHQ).
    
    Supported types:
    - Stock Dividend / Bonus Shares (DIVIDEND_STOCK or content mentions cổ tức cổ phiếu/thưởng)
    - Stock Split (chia tách cổ phiếu)
    - Cash Dividend (DIVIDEND_CASH or content mentions tiền mặt)
    """
    if not event or not event.content:
        return None

    content = event.content.lower().strip()
    ev_type = event.event_type

    # 1. Stock Split (Chia tách cổ phiếu)
    if "chia tách" in content or "tách cổ phiếu" in content:
        m = re.search(r'(?:tỷ\s*lệ\s*)?(\d+)\s*[:/]\s*(\d+)', content)
        if m:
            num1 = float(m.group(1))
            num2 = float(m.group(2))
            if num1 > 0 and num2 > 0:
                mult = num1 / num2 if num1 >= num2 else num2 / num1
                return PositionAdjustmentInfo(
                    adjustment_type="STOCK_SPLIT",
                    ratio=mult - 1.0,
                    multiplier=mult,
                    cash_per_share=0.0,
                    description=f"Chia tách cổ phiếu tỷ lệ {int(num1)}:{int(num2)} (hệ số x{mult:.2f})"
                )

    # 2. Stock Dividend / Bonus Shares (Cổ tức cổ phiếu / Thưởng cổ phiếu)
    is_stock_div = (
        ev_type == EventType.DIVIDEND_STOCK
        or ("cổ phiếu" in content and ("cổ tức" in content or "thưởng" in content))
    )
    if is_stock_div:
        # Check percentage pattern e.g. "tỷ lệ 15%", "15 %", "20%"
        m_pct = re.search(r'(\d+(?:\.\d+)?)\s*%', content)
        if m_pct:
            pct_val = float(m_pct.group(1))
            ratio = pct_val / 100.0
            mult = 1.0 + ratio
            return PositionAdjustmentInfo(
                adjustment_type="STOCK_DIVIDEND",
                ratio=ratio,
                multiplier=mult,
                cash_per_share=0.0,
                description=f"Cổ tức cổ phiếu tỷ lệ {pct_val:g}% (hệ số x{mult:.2f})"
            )
        
        # Check ratio pattern e.g. "tỷ lệ 100:15", "tỷ lệ 10:1", "100/15"
        m_ratio = re.search(r'(?:tỷ\s*lệ\s*)?(\d+)\s*[:/]\s*(\d+)', content)
        if m_ratio:
            a = float(m_ratio.group(1))
            b = float(m_ratio.group(2))
            if a > 0 and b > 0:
                ratio = min(a, b) / max(a, b)
                mult = 1.0 + ratio
                return PositionAdjustmentInfo(
                    adjustment_type="STOCK_DIVIDEND",
                    ratio=ratio,
                    multiplier=mult,
                    cash_per_share=0.0,
                    description=f"Cổ tức cổ phiếu tỷ lệ {int(a)}:{int(b)} (hệ số x{mult:.2f})"
                )

    # 3. Cash Dividend (Cổ tức tiền mặt)
    is_cash_div = (
        ev_type == EventType.DIVIDEND_CASH
        or "tiền mặt" in content
        or "bằng tiền" in content
    )
    if is_cash_div:
        # Look for explicit cash amount: "1.500 đ", "1,500đ", "1000 đồng", "1.000 đ/cp"
        m_vnd = re.search(r'(\d{1,3}(?:[.,]\d{3})+|\d{3,5})\s*(?:đ|đồng|vnd)', content)
        if m_vnd:
            raw_vnd = m_vnd.group(1).replace(".", "").replace(",", "")
            cash_per_share = float(raw_vnd)
            return PositionAdjustmentInfo(
                adjustment_type="CASH_DIVIDEND",
                ratio=0.0,
                multiplier=1.0,
                cash_per_share=cash_per_share,
                description=f"Cổ tức tiền mặt {cash_per_share:,.0f} đ/cp"
            )

        # Look for percentage of par value (10,000 VND)
        m_pct = re.search(r'(\d+(?:\.\d+)?)\s*%', content)
        if m_pct:
            pct_val = float(m_pct.group(1))
            cash_per_share = (pct_val / 100.0) * 10_000.0
            return PositionAdjustmentInfo(
                adjustment_type="CASH_DIVIDEND",
                ratio=0.0,
                multiplier=1.0,
                cash_per_share=cash_per_share,
                description=f"Cổ tức tiền mặt {pct_val:g}% mệnh giá ({cash_per_share:,.0f} đ/cp)"
            )

    return None
