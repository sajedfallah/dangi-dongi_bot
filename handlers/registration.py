from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from states.registration import Registration
from keyboards.reply import get_phone_keyboard
from keyboards.inline import get_admin_approval_keyboard
from services.user_service import create_user, get_user
from services.google_sheets import send_to_sheet
from database.database import AsyncSessionLocal
from config import ADMIN_ID
import logging

router = Router()

@router.message(Registration.waiting_for_name, F.text)
async def process_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip().split(maxsplit=1)
    first_name = full_name[0]
    last_name = full_name[1] if len(full_name) > 1 else ""
    
    await state.update_data(first_name=first_name, last_name=last_name)
    await state.set_state(Registration.waiting_for_phone)
    await message.answer(
        "لطفاً شماره تماس خود را از طریق دکمه زیر ارسال کنید (یا آن را تایپ کنید):", 
        reply_markup=get_phone_keyboard()
    )

@router.message(Registration.waiting_for_phone, F.contact | F.text)
async def process_phone(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    first_name = user_data.get('first_name', '')
    last_name = user_data.get('last_name', '')
    
    phone = message.contact.phone_number if message.contact else message.text
    telegram_id = message.from_user.id

    try:
        async with AsyncSessionLocal() as session:
            existing_user = await get_user(session, telegram_id)
            if not existing_user:
                await create_user(session, telegram_id, first_name, last_name, phone)
                
                # ارسال اطلاعات به شیت به صورت قطعی (بدون Task پس‌زمینه) برای جلوگیری از قطعی
                await send_to_sheet("add_user", {
                    "user_id": telegram_id,
                    "name": f"{first_name} {last_name}".strip(),
                    "phone": phone,
                    "role": "USER"
                })
                
    except Exception as e:
        logging.error(f"خطای دیتابیس در ثبت نام: {e}")
        await message.answer("❌ خطایی در سرور رخ داد. لطفا مجددا /start را بزنید.")
        return

    await state.clear()
    await message.answer(
        "✅ اطلاعات شما با موفقیت ثبت شد.\nلطفاً منتظر تایید توسط مدیریت بمانید.",
        reply_markup=types.ReplyKeyboardRemove()
    )

    admin_text = (
        "🔔 **درخواست ثبت‌نام جدید**\n\n"
        f"👤 نام: {first_name} {last_name}\n"
        f"📱 شماره: {phone}\n"
        f"🆔 آیدی: `{telegram_id}`"
    )
    
    try:
        await message.bot.send_message(
            chat_id=ADMIN_ID, 
            text=admin_text, 
            reply_markup=get_admin_approval_keyboard(telegram_id),
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"خطا در ارسال به ادمین: {e}")