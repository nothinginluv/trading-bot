import pytest
from unittest.mock import patch, MagicMock
from news.models import NewsArticle
from news.crawler import AsyncNewsCrawler

SAMPLE_CAFEF_HTML = """
<div class="tlitem">
    <h3><a href="/tin-tuc-1.chn" title="Doanh nghiệp HPG công bố lãi kỷ lục quý 3 vượt 10.000 tỷ">Doanh nghiệp HPG công bố lãi kỷ lục</a></h3>
</div>
<div class="box-category-item">
    <h3><a href="https://cafef.vn/tin-tuc-2.chn" title="Chủ tịch công ty XYZ bị khởi tố bắt tạm giam vì thao túng giá">Chủ tịch XYZ bị bắt</a></h3>
</div>
"""

SAMPLE_VIETSTOCK_HTML = """
<h3 class="channel-title">
    <a href="/2026/09/fpt-ky-hop-dong-ai-sieu-du-an-nghin-ty-12345.htm">FPT ký hợp đồng AI siêu dự án nghìn tỷ với đối tác Mỹ</a>
</h3>
<h3 class="channel-title">
    <a href="/2026/09/thi-truong-chung-khoan-rung-lac-duoi-ema21-54321.htm">Thị trường chứng khoán rung lắc phân hóa mạnh</a>
</h3>
"""

@pytest.mark.asyncio
async def test_crawler_parsing_mocked():
    crawler = AsyncNewsCrawler()
    
    # Test CafeF parsing
    cafef_articles = crawler.parse_cafef_html(SAMPLE_CAFEF_HTML)
    assert len(cafef_articles) == 2
    assert "HPG" in cafef_articles[0].title
    assert cafef_articles[0].source == "CafeF"
    assert cafef_articles[0].link == "https://cafef.vn/tin-tuc-1.chn"
    assert "khởi tố" in cafef_articles[1].title

    # Test Vietstock parsing
    vs_articles = crawler.parse_vietstock_html(SAMPLE_VIETSTOCK_HTML)
    assert len(vs_articles) == 2
    assert "FPT" in vs_articles[0].title
    assert vs_articles[0].source == "Vietstock"
    assert vs_articles[0].link == "https://vietstock.vn/2026/09/fpt-ky-hop-dong-ai-sieu-du-an-nghin-ty-12345.htm"

@pytest.mark.asyncio
async def test_crawler_live_smoke():
    crawler = AsyncNewsCrawler(timeout=6.0)
    try:
        articles = await crawler.fetch_all_news()
        # Should successfully fetch articles from live web
        assert len(articles) > 0
        assert any(a.source == "CafeF" for a in articles)
        assert any(a.source == "Vietstock" for a in articles)
    finally:
        await crawler.close()
