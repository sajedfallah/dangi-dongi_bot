from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 ارسال شماره تماس", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎵 رویدادها")],
            [KeyboardButton(text="🎫 بلیت‌های من"), KeyboardButton(text="🧾 کیف پول من")],
            [KeyboardButton(text="📞 پشتیبانی و تیکت"), KeyboardButton(text="ℹ️ راهنما")]
        ],
        resize_keyboard=True
    )

def get_admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎵 رویدادها")],
            [KeyboardButton(text="💰 ثبت هزینه"), KeyboardButton(text="📷 بررسی و اسکن بلیت")],
            [KeyboardButton(text="🔍 جستجوی فیش"), KeyboardButton(text="ℹ️ راهنما")]
        ],
        resize_keyboard=True
    )

def get_checker_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📷 بررسی و اسکن بلیت")]],
        resize_keyboard=True
    )