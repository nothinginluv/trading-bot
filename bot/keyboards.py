from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="💰 Số dư"), KeyboardButton(text="📊 Vị thế")],
        [KeyboardButton(text="🔄 Làm mới"), KeyboardButton(text="ℹ️ Trạng thái")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
