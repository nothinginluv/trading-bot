import pytest
from news.models import NewsArticle
from news.sentiment import NewsSentimentAnalyzer

def test_extract_tickers():
    analyzer = NewsSentimentAnalyzer()

    # Direct ticker mention
    tickers1 = analyzer.extract_tickers("Cổ phiếu HPG bứt phá mạnh mẽ vượt đỉnh 1 năm")
    assert "HPG" in tickers1

    # Company name alias mention
    tickers2 = analyzer.extract_tickers("Tập đoàn Hòa Phát và Vinamilk ký kết thỏa thuận cung ứng")
    assert "HPG" in tickers2
    assert "VNM" in tickers2

    # FPT AI project
    tickers3 = analyzer.extract_tickers("FPT hợp tác cùng đối tác Mỹ triển khai hạ tầng bán dẫn")
    assert "FPT" in tickers3

    # Market benchmark
    tickers4 = analyzer.extract_tickers("VN-Index tiếp đà phục hồi hướng về mốc 1.300 điểm")
    assert "VNINDEX" in tickers4

def test_sentiment_scoring_positive():
    analyzer = NewsSentimentAnalyzer()

    title = "Doanh nghiệp FPT báo lãi kỷ lục quý 3 vượt kế hoạch năm, dòng tiền ngoại mua ròng"
    score, label, is_severe = analyzer.analyze_sentiment(title)
    assert score >= 0.4
    assert label == "POSITIVE"
    assert is_severe is False

def test_sentiment_scoring_negative():
    analyzer = NewsSentimentAnalyzer()

    title = "Doanh nghiệp đối mặt thua lỗ nặng, dòng tiền cạn kiệt, bán tháo kỷ lục"
    score, label, is_severe = analyzer.analyze_sentiment(title)
    assert score <= -0.3
    assert label == "NEGATIVE"

def test_severe_negative_crisis_detection():
    analyzer = NewsSentimentAnalyzer()

    # Extreme legal / fraud / arrest crisis
    title1 = "Chủ tịch tập đoàn XYZ bị khởi tố bắt tạm giam vì tội thao túng thị trường chứng khoán"
    score1, label1, is_severe1 = analyzer.analyze_sentiment(title1)
    assert score1 <= -0.7
    assert label1 == "NEGATIVE"
    assert is_severe1 is True

    title2 = "Cổ phiếu ABC bị đình chỉ giao dịch bắt buộc do chậm nộp báo cáo kiểm toán"
    score2, label2, is_severe2 = analyzer.analyze_sentiment(title2)
    assert score2 <= -0.6
    assert is_severe2 is True

def test_process_article():
    analyzer = NewsSentimentAnalyzer()
    art = NewsArticle(
        id="test1",
        title="Tập đoàn Hòa Phát báo lãi tăng trưởng 40% trong quý 3",
        link="https://cafef.vn/test1.chn",
        source="CafeF"
    )
    processed = analyzer.process_article(art)
    assert "HPG" in processed.related_symbols
    assert processed.sentiment_score > 0
    assert processed.sentiment_label == "POSITIVE"
    assert processed.is_severe_negative is False

def test_sentiment_negation_handling():
    analyzer = NewsSentimentAnalyzer()

    # 1. Negated negative keywords should NOT produce negative score
    score1, label1, is_sev1 = analyzer.analyze_sentiment("Tập đoàn Hòa Phát không thua lỗ trong quý 3")
    assert score1 >= -0.1
    assert label1 in ("NEUTRAL", "POSITIVE")
    assert is_sev1 is False

    # 2. "Chưa lỗ" + positive keyword -> overall positive, not vetoed
    score2, label2, is_sev2 = analyzer.analyze_sentiment("Doanh nghiệp chưa lỗ, giữ vững đà tăng trưởng")
    assert score2 > 0.0
    assert label2 == "POSITIVE"
    assert is_sev2 is False

    # 3. "Không giảm" -> not negative
    score3, label3, is_sev3 = analyzer.analyze_sentiment("Lợi nhuận doanh nghiệp không giảm trong bối cảnh khó khăn")
    assert score3 >= -0.1
    assert label3 != "NEGATIVE"

    # 4. Crisis keyword negated: "Bác bỏ tin đồn bị khởi tố" -> severe flag MUST be False!
    score4, label4, is_sev4 = analyzer.analyze_sentiment("Tập đoàn FPT lên tiếng bác bỏ tin đồn bị khởi tố")
    assert is_sev4 is False
    assert label4 != "NEGATIVE"

    # 5. Non-negated negative keyword STILL produces true negative
    score5, label5, is_sev5 = analyzer.analyze_sentiment("Doanh nghiệp chìm trong thua lỗ nặng nề")
    assert score5 <= -0.3
    assert label5 == "NEGATIVE"

