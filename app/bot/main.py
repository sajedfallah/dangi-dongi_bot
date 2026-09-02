import asyncio
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from app.core.config import settings


class CreateGroupFlow(StatesGroup):
    waiting_name = State()


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ ساخت حساب جدید"), KeyboardButton(text="📂 حساب‌های من")],
        [KeyboardButton(text="❓ راهنما")],
    ], resize_keyboard=True,
)


async def ensure_user(message: Message) -> dict:
    payload = {
        "telegram_id": message.from_user.id,
        "display_name": message.from_user.full_name or str(message.from_user.id),
    }
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=10) as client:
        r = await client.post("/api/v1/users", json=payload)
        r.raise_for_status()
        return r.json()


async def run_bot():
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    bot = Bot(settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def start(message: Message):
        await ensure_user(message)
        await message.answer(
            "سلام 👋\nاینجا می‌تونی خرج‌های مشترک و دونگ‌ها رو بدون حساب‌وکتاب دستی مدیریت کنی.",
            reply_markup=main_keyboard,
        )

    @dp.message(F.text == "➕ ساخت حساب جدید")
    async def new_group(message: Message, state: FSMContext):
        await state.set_state(CreateGroupFlow.waiting_name)
        await message.answer("اسم حساب رو وارد کن.\nمثال: سفر شمال")

    @dp.message(CreateGroupFlow.waiting_name)
    async def group_name(message: Message, state: FSMContext):
        user = await ensure_user(message)
        async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=10) as client:
            r = await client.post("/api/v1/groups", json={
                "name": message.text.strip(),
                "owner_user_id": user["id"],
                "currency": "IRR",
            })
            r.raise_for_status()
            group = r.json()
        await state.clear()
        await message.answer(
            f"✅ حساب «{group['name']}» ساخته شد.\nشناسه حساب: {group['id']}\n\nمرحله بعد: اعضا را اضافه کن و اولین هزینه را ثبت کن.",
            reply_markup=main_keyboard,
        )

    @dp.message(F.text == "❓ راهنما")
    async def help_msg(message: Message):
        await message.answer("۱) یک حساب بساز\n۲) اعضا را اضافه کن\n۳) هزینه‌ها را ثبت کن\n۴) بات می‌گوید چه کسی باید به چه کسی پرداخت کند.")

    @dp.message(F.text == "📂 حساب‌های من")
    async def groups_placeholder(message: Message):
        await message.answer("نمایش لیست حساب‌ها در مرحله بعدی رابط بات تکمیل می‌شود.")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
