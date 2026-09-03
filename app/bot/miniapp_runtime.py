from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

_INSTALLED = False


def install(module) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    if not module.settings.mini_app_url:
        return

    existing = [list(row) for row in module.main_keyboard.keyboard]
    module.main_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 باز کردن مینی اپ", web_app=WebAppInfo(url=module.settings.mini_app_url))],
            *existing,
        ],
        resize_keyboard=True,
    )
