VN30_SYMBOLS = [
    "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
    "MBB", "MCH", "MSN", "MWG", "POW", "SAB", "SHB", "SSB", "STB", "TCB",
    "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE"
]

HOSE_HOURS = {
    "morning_start": "09:00",
    "morning_end": "11:30",
    "afternoon_start": "13:00",
    "afternoon_end": "15:00",
    "ato_end": "09:15",
    "atc_start": "14:30"
}

DNSE_BASE_URL = "https://openapi.dnse.com.vn"

VN30_SECTOR_MAP = {
    # Ngân hàng (Banking)
    "ACB": "NGÂN HÀNG",
    "BID": "NGÂN HÀNG",
    "CTG": "NGÂN HÀNG",
    "HDB": "NGÂN HÀNG",
    "LPB": "NGÂN HÀNG",
    "MBB": "NGÂN HÀNG",
    "SHB": "NGÂN HÀNG",
    "SSB": "NGÂN HÀNG",
    "STB": "NGÂN HÀNG",
    "TCB": "NGÂN HÀNG",
    "VCB": "NGÂN HÀNG",
    "VIB": "NGÂN HÀNG",
    "VPB": "NGÂN HÀNG",
    # Bất động sản (Real Estate)
    "VHM": "BẤT ĐỘNG SẢN",
    "VIC": "BẤT ĐỘNG SẢN",
    "VRE": "BẤT ĐỘNG SẢN",
    # Thép & Vật liệu xây dựng (Materials & Steel)
    "HPG": "THÉP & VẬT LIỆU",
    # Bán lẻ & Tiêu dùng (Retail & Consumer)
    "MWG": "BÁN LẺ",
    # Công nghệ thông tin (Technology)
    "FPT": "CÔNG NGHỆ",
    # Thực phẩm & Đồ uống (Food & Beverage)
    "MSN": "THỰC PHẨM & ĐỒ UỐNG",
    "MCH": "THỰC PHẨM & ĐỒ UỐNG",
    "SAB": "THỰC PHẨM & ĐỒ UỐNG",
    "VNM": "THỰC PHẨM & ĐỒ UỐNG",
    # Dầu khí & Xăng dầu (Oil & Gas)
    "GAS": "DẦU KHÍ & XĂNG DẦU",
    "PLX": "DẦU KHÍ & XĂNG DẦU",
    "BSR": "DẦU KHÍ & XĂNG DẦU",
    # Điện & Tiện ích (Power & Utilities)
    "POW": "ĐIỆN & TIỆN ÍCH",
    # Chứng khoán (TCBS)
    "TCX": "CHỨNG KHOÁN (TCBS)",
    # Hàng không (Aviation)
    "VJC": "HÀNG KHÔNG",
    # Cao su & Vật liệu (Rubber & Industrial Materials)
    "GVR": "CAO SU & VẬT LIỆU",
    # Du lịch & Dịch vụ (Vinpearl)
    "VPL": "DỊCH VỤ & NGHỈ DƯỠNG",
}

def get_symbol_sector(symbol: str) -> str:
    return VN30_SECTOR_MAP.get(symbol.upper(), "KHÁC")

