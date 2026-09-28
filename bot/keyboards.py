from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="💼 Tài khoản Giả lập"), KeyboardButton(text="🎯 Tín hiệu VN30")],
        [KeyboardButton(text="💰 Số dư"), KeyboardButton(text="📊 Vị thế")],
        [KeyboardButton(text="📊 Hiệu suất PnL"), KeyboardButton(text="📋 Sổ lệnh Thật")],
        [KeyboardButton(text="🔍 Quét VN30"), KeyboardButton(text="📈 Bảng giá VN30")],
        [KeyboardButton(text="📰 Tin tức"), KeyboardButton(text="⚙️ Chế độ GD")],
        [KeyboardButton(text="🛑 CẦU DAO KHẨN CẤP"), KeyboardButton(text="ℹ️ Trạng thái")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

