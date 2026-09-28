import re
from typing import List, Tuple, Dict, Set
from config.constants import VN30_SYMBOLS
from news.models import NewsArticle

COMPANY_ALIAS_MAP: Dict[str, str] = {
    "hòa phát": "HPG",
    "hoa phat": "HPG",
    "fpt": "FPT",
    "vinamilk": "VNM",
    "vingroup": "VIC",
    "vinhomes": "VHM",
    "vincom": "VRE",
    "vietcombank": "VCB",
    "techcombank": "TCB",
    "vietinbank": "CTG",
    "bidv": "BID",
    "masan": "MSN",
    "thế giới di động": "MWG",
    "the gioi di dong": "MWG",
    "bảo việt": "BVH",
    "bao viet": "BVH",
    "petrolimex": "PLX",
    "pv gas": "GAS",
    "vietjet": "VJC",
    "sabeco": "SAB",
    "ssi": "SSI",
    "acb": "ACB",
    "mbb": "MBB",
    "vpb": "VPB",
    "stb": "STB",
    "sacombank": "STB",
    "hdbank": "HDB",
    "tpbank": "TPB",
    "shb": "SHB",
    "vib": "VIB"
}

MARKET_KEYWORDS: Set[str] = {
    "vn-index", "vnindex", "thị trường", "thi truong", "khối ngoại",
    "khoi ngoai", "tự doanh", "tu doanh", "ngân hàng nhà nước",
    "dòng tiền cá mập", "chứng khoán việt nam"
}

# 1. Severe Crisis Keywords (-0.8 to -1.0, triggers is_severe_negative)
SEVERE_NEGATIVE_KEYWORDS: List[Tuple[str, float]] = [
    ("khởi tố", -0.9),
    ("khoi to", -0.9),
    ("bắt tạm giam", -1.0),
    ("bat tam giam", -1.0),
    ("bị bắt", -0.9),
    ("bi bat", -0.9),
    ("thao túng", -0.9),
    ("thao tung", -0.9),
    ("hủy niêm yết", -0.9),
    ("huy niem yet", -0.9),
    ("đình chỉ giao dịch", -0.9),
    ("dinh chi giao dich", -0.9),
    ("phá sản", -1.0),
    ("pha san", -1.0),
    ("vỡ nợ", -0.9),
    ("vo no", -0.9),
    ("lừa đảo", -0.9),
    ("chiếm đoạt", -0.8),
    ("sai phạm nghiêm trọng", -0.8)
]

# 2. General Negative Keywords (-0.2 to -0.6)
NEGATIVE_KEYWORDS: List[Tuple[str, float]] = [
    ("thua lỗ", -0.5),
    ("thua lo", -0.5),
    ("lỗ nặng", -0.6),
    ("lo nang", -0.6),
    ("báo lỗ", -0.5),
    ("bao lo", -0.5),
    ("lỗ ròng", -0.5),
    ("lo rong", -0.5),
    ("lỗ", -0.4),
    ("sụt giảm mạnh", -0.5),
    ("sut giam", -0.4),
    ("suy giảm", -0.4),
    ("suy giam", -0.4),
    ("giảm mạnh", -0.4),
    ("giam manh", -0.4),
    ("giảm sâu", -0.4),
    ("giảm", -0.3),
    ("giam", -0.3),
    ("lao dốc", -0.5),
    ("lao doc", -0.5),
    ("bán tháo", -0.5),
    ("ban thao", -0.5),
    ("bán ròng", -0.3),
    ("ban rong", -0.3),
    ("chậm trả", -0.4),
    ("nợ xấu tăng", -0.4),
    ("giảm sàn", -0.5),
    ("cảnh báo", -0.3),
    ("kiểm soát", -0.3),
    ("thanh tra", -0.4),
    ("bị phạt", -0.4),
    ("áp lực bán", -0.3),
    ("cạn kiệt", -0.4),
    ("thất thoát", -0.4)
]

# 3. High Positive Catalysts (+0.6 to +0.9)
HIGH_POSITIVE_KEYWORDS: List[Tuple[str, float]] = [
    ("lãi kỷ lục", 0.8),
    ("lai ky luc", 0.8),
    ("siêu dự án", 0.8),
    ("sieu du an", 0.8),
    ("đột biến", 0.7),
    ("dot bien", 0.7),
    ("trúng thầu", 0.7),
    ("trung thau", 0.7),
    ("vượt kế hoạch", 0.7),
    ("vuot ke hoach", 0.7),
    ("tăng trưởng khủng", 0.8),
    ("lãi nghìn tỷ", 0.8),
    ("nâng hạng", 0.8),
    ("nang hang", 0.8)
]

# 4. Moderate Positive Catalysts (+0.2 to +0.5)
POSITIVE_KEYWORDS: List[Tuple[str, float]] = [
    ("tăng trưởng", 0.4),
    ("tang truong", 0.4),
    ("chia cổ tức", 0.4),
    ("mua ròng", 0.4),
    ("mua rong", 0.4),
    ("bứt phá", 0.5),
    ("but pha", 0.5),
    ("vượt đỉnh", 0.5),
    ("vuot dinh", 0.5),
    ("hút vốn", 0.4),
    ("hut von", 0.4),
    ("hợp tác", 0.3),
    ("hop tac", 0.3),
    ("khởi sắc", 0.4),
    ("hồi phục", 0.4),
    ("khả quan", 0.3),
    ("triển vọng", 0.3),
    ("dòng tiền ngoại", 0.4)
]

class NewsSentimentAnalyzer:
    """
    Vietnamese Financial Sentiment Lexicon & Ticker Extractor.
    Operates offline with near-zero latency (< 5ms).
    """
    def __init__(self):
        self.vn30_set = set(s.upper() for s in VN30_SYMBOLS)

    def extract_tickers(self, text: str) -> List[str]:
        found: Set[str] = set()
        text_lower = text.lower()

        # 1. Company alias match
        for alias, sym in COMPANY_ALIAS_MAP.items():
            if re.search(r'\b' + re.escape(alias) + r'\b', text_lower):
                found.add(sym)

        # 2. Direct stock ticker match (e.g. HPG, FPT...)
        words = re.findall(r'\b[A-Z]{3}\b', text)
        for w in words:
            if w in self.vn30_set:
                found.add(w)

        # 3. Market benchmark index keywords
        for mk in MARKET_KEYWORDS:
            if mk in text_lower:
                found.add("VNINDEX")
                break

        return sorted(list(found))

    @staticmethod
    def _is_negated(text_lower: str, kw_start_idx: int) -> bool:
        """
        Checks if the keyword starting at kw_start_idx is preceded by
        a Vietnamese negation prefix within a 1-5 word clause.
        """
        preceding = text_lower[max(0, kw_start_idx - 45):kw_start_idx].strip()
        if not preceding:
            return False

        # Split on punctuation or conjunctions to prevent crossing clause boundaries
        parts = re.split(r'[,.;:!?\-–—]|\b(?:nhưng|song|tuy nhiên|tuy thế)\b', preceding)
        clause = parts[-1].strip()
        if not clause:
            return False

        negation_tokens = [
            "không hề", "không có", "bác bỏ", "phủ nhận", "tránh được", "thoát khỏi",
            "chưa từng", "không phải", "ít bị", "miễn nhiễm",
            "không", "khong", "chưa", "chua", "chẳng", "chang"
        ]

        for neg in negation_tokens:
            if re.search(r'\b' + re.escape(neg) + r'\b', clause):
                return True
        return False

    def analyze_sentiment(self, text: str) -> Tuple[float, str, bool]:
        """
        Analyzes headline/text sentiment with Vietnamese negation handling.
        Returns: (score: float [-1.0, 1.0], label: str, is_severe_negative: bool)
        """
        text_lower = text.lower()
        score = 0.0
        matches_count = 0
        is_severe = False

        # 1. Check severe negative
        for kw, weight in SEVERE_NEGATIVE_KEYWORDS:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                if self._is_negated(text_lower, m.start()):
                    # Negated crisis keyword (e.g. "bác bỏ tin đồn bị khởi tố", "không bị thanh tra")
                    # Neutralize score, do NOT mark as severe crisis!
                    score += 0.0
                    matches_count += 1
                else:
                    score += weight
                    matches_count += 1
                    is_severe = True

        # 2. Check general negative
        for kw, weight in NEGATIVE_KEYWORDS:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                if self._is_negated(text_lower, m.start()):
                    # Negated negative keyword (e.g. "không thua lỗ", "chưa lỗ", "không bị phạt", "không giảm")
                    # Turns negative into mild positive / neutral (+0.1)
                    score += 0.1
                    matches_count += 1
                else:
                    score += weight
                    matches_count += 1

        # 3. Check high positive
        for kw, weight in HIGH_POSITIVE_KEYWORDS:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                if self._is_negated(text_lower, m.start()):
                    # Negated positive keyword (e.g. "không đạt lãi kỷ lục")
                    score -= 0.2
                    matches_count += 1
                else:
                    score += weight
                    matches_count += 1

        # 4. Check moderate positive
        for kw, weight in POSITIVE_KEYWORDS:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', text_lower):
                if self._is_negated(text_lower, m.start()):
                    # Negated positive keyword (e.g. "chưa bứt phá", "không tăng trưởng")
                    score -= 0.15
                    matches_count += 1
                else:
                    score += weight
                    matches_count += 1

        if matches_count > 0:
            final_score = max(-1.0, min(1.0, score / max(1.0, matches_count * 0.75)))
        else:
            final_score = 0.0

        if final_score >= 0.2:
            label = "POSITIVE"
        elif final_score <= -0.2:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"

        return round(final_score, 2), label, is_severe


    def process_article(self, article: NewsArticle) -> NewsArticle:
        tickers = self.extract_tickers(article.title)
        score, label, is_severe = self.analyze_sentiment(article.title)
        
        article.related_symbols = tickers
        article.sentiment_score = score
        article.sentiment_label = label
        article.is_severe_negative = is_severe
        return article
