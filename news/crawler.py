import asyncio
import hashlib
import html
import logging
import re
from typing import List, Dict
import httpx
from news.models import NewsArticle, CorporateEvent, EventType

logger = logging.getLogger(__name__)

class AsyncNewsCrawler:
    """
    High-speed asynchronous news crawler for CafeF and Vietstock.
    Scrapes market, corporate news and official disclosures / events.
    """
    EVENTS_URL = "https://cafef.vn/du-lieu/lich-su-kien.chn"
    CAFEF_CATEGORIES = [
        ("https://cafef.vn/thi-truong-chung-khoan.chn", "CafeF"),
        ("https://cafef.vn/doanh-nghiep.chn", "CafeF")
    ]
    VIETSTOCK_CATEGORIES = [
        ("https://vietstock.vn/chung-khoan.htm", "Vietstock"),
        ("https://vietstock.vn/doanh-nghiep.htm", "Vietstock")
    ]

    def __init__(self, timeout: float = 8.0, max_concurrency: int = 4):
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi,en-US;q=0.9,en;q=0.8"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=timeout, follow_redirects=True)

    def _generate_article_id(self, source: str, title: str) -> str:
        clean = re.sub(r'\s+', ' ', title).strip().lower()
        return hashlib.sha256(f"{source}:{clean}".encode("utf-8")).hexdigest()[:16]

    def parse_cafef_html(self, html_text: str) -> List[NewsArticle]:
        articles: List[NewsArticle] = []
        # Pattern 1: <h3 ...><a href="..." title="...">
        items = re.findall(r'<h[234][^>]*>[\s\S]*?<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"', html_text)
        if not items:
            # Pattern 2: <h3 ...><a title="..." href="...">
            items = re.findall(r'<h[234][^>]*>[\s\S]*?<a[^>]*title="([^"]+)"[^>]*href="([^"]+)"', html_text)
            items = [(href, title) for title, href in items]
        
        seen_ids = set()
        for href, title in items:
            clean_title = html.unescape(title).strip()
            if len(clean_title) < 15:
                continue
            art_id = self._generate_article_id("CafeF", clean_title)
            if art_id in seen_ids:
                continue
            seen_ids.add(art_id)
            link = href if href.startswith("http") else "https://cafef.vn" + href
            articles.append(NewsArticle(
                id=art_id,
                title=clean_title,
                link=link,
                source="CafeF"
            ))
        return articles

    def parse_vietstock_html(self, html_text: str) -> List[NewsArticle]:
        articles: List[NewsArticle] = []
        # Match news article links on Vietstock
        items = re.findall(r'<a[^>]+href="(\/[0-9]{4}\/[0-9]{2}\/[^"]+\.htm)"[^>]*>([\s\S]*?)<\/a>', html_text)
        seen_ids = set()
        for href, raw_title in items:
            clean_title = re.sub(r'<[^>]+>', '', raw_title).strip()
            clean_title = html.unescape(clean_title)
            if len(clean_title) < 15:
                continue
            art_id = self._generate_article_id("Vietstock", clean_title)
            if art_id in seen_ids:
                continue
            seen_ids.add(art_id)
            link = "https://vietstock.vn" + href
            articles.append(NewsArticle(
                id=art_id,
                title=clean_title,
                link=link,
                source="Vietstock"
            ))
        return articles

    async def fetch_category(self, url: str, source: str) -> List[NewsArticle]:
        async with self.semaphore:
            try:
                resp = await self.client.get(url)
                if resp.status_code == 200:
                    if source == "CafeF":
                        return self.parse_cafef_html(resp.text)
                    elif source == "Vietstock":
                        return self.parse_vietstock_html(resp.text)
                else:
                    logger.warning(f"Failed to fetch {url}: status {resp.status_code}")
            except Exception as e:
                logger.error(f"Error fetching news from {url}: {e}")
        return []

    async def fetch_all_news(self) -> List[NewsArticle]:
        tasks = []
        for url, src in self.CAFEF_CATEGORIES:
            tasks.append(self.fetch_category(url, src))
        for url, src in self.VIETSTOCK_CATEGORIES:
            tasks.append(self.fetch_category(url, src))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        dedup_map: Dict[str, NewsArticle] = {}
        for r in results:
            if isinstance(r, list):
                for art in r:
                    if art.id not in dedup_map:
                        dedup_map[art.id] = art

        articles = list(dedup_map.values())
        logger.info(f"Crawled {len(articles)} total articles from CafeF & Vietstock.")
        return articles

    def parse_corporate_events(self, html_text: str) -> List[CorporateEvent]:
        events: List[CorporateEvent] = []
        rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', html_text)
        for r_content in rows:
            cols = re.findall(r'<td[^>]*>([\s\S]*?)</td>', r_content)
            if len(cols) >= 6:
                clean_cols = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip() for c in cols]
                date_gdkhq, date_dkcc, date_th, sym, floor, content = clean_cols[:6]
                sym = sym.upper().strip()
                if not sym or len(sym) < 3 or len(sym) > 5:
                    continue

                # Parse and standardize date dd/mm/yyyy -> yyyy-mm-dd
                ex_date_std = None
                if date_gdkhq and "/" in date_gdkhq:
                    parts = date_gdkhq.split("/")
                    if len(parts) == 3 and parts[2] != "0001":
                        ex_date_std = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

                record_date_std = None
                if date_dkcc and "/" in date_dkcc:
                    parts = date_dkcc.split("/")
                    if len(parts) == 3 and parts[2] != "0001":
                        record_date_std = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

                # Classify event_type
                content_lower = content.lower()
                if "esop" in content_lower:
                    ev_type = EventType.ESOP
                elif "tiền mặt" in content_lower or ("cổ tức" in content_lower and "%" in content_lower and "cổ phiếu" not in content_lower):
                    ev_type = EventType.DIVIDEND_CASH
                elif "cổ phiếu" in content_lower and ("cổ tức" in content_lower or "thưởng" in content_lower):
                    ev_type = EventType.DIVIDEND_STOCK
                elif "phát hành" in content_lower or "chào bán" in content_lower:
                    ev_type = EventType.ISSUE_ADDITIONAL
                elif "đại hội" in content_lower or "đhđcđ" in content_lower:
                    ev_type = EventType.AGM
                elif "bổ nhiệm" in content_lower or "miễn nhiệm" in content_lower or "từ nhiệm" in content_lower:
                    ev_type = EventType.PERSONNEL
                elif "niêm yết" in content_lower or "giao dịch bổ sung" in content_lower:
                    ev_type = EventType.LISTING
                else:
                    ev_type = EventType.OTHER

                ev_id = hashlib.sha256(f"{sym}:{ex_date_std}:{content}".encode("utf-8")).hexdigest()[:16]
                events.append(CorporateEvent(
                    id=ev_id,
                    symbol=sym,
                    ex_date=ex_date_std,
                    record_date=record_date_std,
                    event_type=ev_type,
                    content=content,
                    source="CafeF Official / CBTT"
                ))
        return events

    async def fetch_corporate_events(self) -> List[CorporateEvent]:
        async with self.semaphore:
            try:
                resp = await self.client.get(self.EVENTS_URL)
                if resp.status_code == 200:
                    evs = self.parse_corporate_events(resp.text)
                    logger.info(f"Parsed {len(evs)} corporate events from CafeF.")
                    return evs
                else:
                    logger.warning(f"Failed to fetch corporate events from {self.EVENTS_URL}: status {resp.status_code}")
            except Exception as e:
                logger.error(f"Error fetching corporate events: {e}")
        return []

    async def close(self):
        await self.client.aclose()

