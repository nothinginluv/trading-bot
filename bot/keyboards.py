from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    Standard 4-row categorized menu for mobile & desktop Telegram layout:
    - Row 1: Market & VN30 Intelligence
    - Row 2: Account & Positions
    - Row 3: Trading Performance & Orders
    - Row 4: System Risk & Safeguards
    """
    kb = [
        [
            KeyboardButton(text="📈 Bảng giá VN30"),
            KeyboardButton(text="🔍 Quét VN30"),
            KeyboardButton(text="🎯 Tín hiệu VN30")
        ],
        [
            KeyboardButton(text="💼 Tài khoản Giả lập"),
            KeyboardButton(text="💰 Số dư"),
            KeyboardButton(text="📊 Vị thế")
        ],
        [
            KeyboardButton(text="📊 Hiệu suất PnL"),
            KeyboardButton(text="📋 Sổ lệnh Thật"),
            KeyboardButton(text="📰 Tin tức")
        ],
        [
            KeyboardButton(text="⚙️ Chế độ GD"),
            KeyboardButton(text="🛑 CẦU DAO KHẨN CẤP"),
            KeyboardButton(text="ℹ️ Trạng thái")
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_vn30_inline_keyboard(active_view: str = "gainers") -> InlineKeyboardMarkup:
    """Inline navigation for VN30 Price Board (Top Gainers / Losers / Refresh)."""
    btn_gainers_text = "🟢 Top Tăng ✓" if active_view == "gainers" else "🟢 Top Tăng"
    btn_losers_text = "🔴 Top Giảm ✓" if active_view == "losers" else "🔴 Top Giảm"
    
    kb = [
        [
            InlineKeyboardButton(text=btn_gainers_text, callback_data="vn30_view:gainers"),
            InlineKeyboardButton(text=btn_losers_text, callback_data="vn30_view:losers")
        ],
        [
            InlineKeyboardButton(text="🔄 Cập nhật bảng giá", callback_data=f"vn30_refresh:{active_view}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_quote_inline_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """Inline shortcuts for individual stock quotes."""
    kb = [
        [
            InlineKeyboardButton(text="📊 Phân tích Kỹ thuật", callback_data=f"q_ind:{symbol}"),
            InlineKeyboardButton(text="📰 Tin tức CafeF", callback_data=f"q_news:{symbol}")
        ],
        [
            InlineKeyboardButton(text="🔄 Cập nhật giá", callback_data=f"q_refresh:{symbol}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_positions_inline_keyboard() -> InlineKeyboardMarkup:
    """Inline shortcuts for portfolio positions."""
    kb = [
        [
            InlineKeyboardButton(text="🔄 Làm mới vị thế", callback_data="pos_refresh"),
            InlineKeyboardButton(text="📊 Xem Hiệu suất PnL", callback_data="pos_pnl")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)
