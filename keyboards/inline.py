from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_admin_approval_keyboard(telegram_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_{telegram_id}"),
                InlineKeyboardButton(text="❌ رد کردن", callback_data=f"reject_{telegram_id}")
            ]
        ]
    )