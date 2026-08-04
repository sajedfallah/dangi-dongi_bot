from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from database.database import AsyncSessionLocal
from services.user_service import get_user
from states.registration import Registration
from keyboards.reply import get_main_menu, get_admin_menu, get_checker_menu
from config import ADMIN_ID
from models.user import User

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    telegram_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        if telegram_id == ADMIN_ID:
            admin_user = await get_user(session, telegram_id)
            if not admin_user:
                new_admin = User(
                    telegram_id=telegram_id,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name,
                    role="ADMIN",
                    status="APPROVED"
                )
                session.add(new_admin)
                await session.commit()
            
            await message.answer("👑 به پنل مدیریت Tikino خوش آمدید.", reply_markup=get_admin_menu())
            return 

        user = await get_user(session, telegram_id)
        
        if user:
            if getattr(user, 'role', None) == "CHECKER":
                await message.answer("🔍 به پنل کنترل بلیت (Check-in) خوش آمدید.", reply_markup=get_checker_menu())
            elif user.status == "APPROVED":
                await message.answer("به Tikino خوش آمدید! 🎟", reply_markup=get_main_menu())
            elif user.status == "PENDING_APPROVAL":
                await message.answer("⏳ حساب شما در انتظار تایید مدیریت است.")
            elif user.status == "REJECTED":
                await message.answer("❌ حساب شما مسدود یا رد شده است.")
        else:
            await state.set_state(Registration.waiting_for_name)
            welcome_text = (
                "سلام! به **Tikino** خوش آمدید. 🎟\n\n"
                "برای استفاده از خدمات، لطفا **نام و نام خانوادگی** خود را وارد کنید (مثلاً: علی رضایی):"
            )
            await message.answer(welcome_text, parse_mode="Markdown")

@router.message(F.text == "ℹ️ راهنما")
async def show_help_guide(message: types.Message):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        guide_text = (
            "👑 **راهنمای جامع مدیریت (Admin Guide)**\n\n"
            "🔹 **رویدادها:** از این بخش می‌توانید رویداد بسازید، قیمت بلیت و ظرفیت تعیین کنید، و کدهای تخفیف را مدیریت کنید.\n"
            "🔹 **گزارشات:** آمار فروش، صندلی‌های باقیمانده و کدهای اسکن شده را لحظه‌ای ببینید.\n"
            "🔹 **بلیت اهدایی/لیست مهمان:** بدون پرداخت وجه، برای اسپانسرها و مهمانان ویژه بلیت صادر کنید.\n"
            "🔹 **ثبت هزینه:** هزینه‌های اجاره سالن یا دستمزد را وارد کنید تا به سیستم حسابداری (گوگل شیت) منتقل شود.\n"
            "🔹 **بررسی و اسکن بلیت:** برای روز برگزاری رویداد؛ از طریق دوربین گوشی بارکدها را اسکن و تایید کنید.\n"
            "🔹 **جستجوی فیش:** با وارد کردن شماره فاکتور، عکس فیش‌های قدیمی بایگانی شده را پیدا کنید.\n\n"
            "💡 _جهت لغو یا ابطال یک بلیتِ خاص، از بخش رویدادها > ویرایش/حذف بلیت اقدام نمایید._"
        )
    else:
        guide_text = (
            "👤 **راهنمای جامع خریداران (User Guide)**\n\n"
            "🔹 **خرید بلیت:** از منوی «رویدادها» کنسرت یا همایش مورد نظر را انتخاب کرده و بلیت خود را رزرو کنید.\n"
            "🔹 **کیف پول من:** اگر پیش‌فاکتور ثبت کرده‌اید اما پرداخت نکرده‌اید، تا ۵ ساعت فرصت دارید از این بخش پرداخت را تکمیل و فیش را ارسال کنید.\n"
            "🔹 **بلیت‌های من:** پس از تایید مدیریت، بلیت‌های شما (همراه با بارکد QR) اینجا قرار می‌گیرند. روز مراسم این بارکد را به متصدی نشان دهید.\n"
            "🔹 **عودت بلیت:** در بخش «بلیت‌های من»، با زدن دکمه لغو، شماره کارت خود را بدهید تا طبق قوانین، مبلغ استرداد شود.\n"
            "🔹 **پشتیبانی:** اگر مشکلی در پرداخت، تایید فیش یا ورود داشتید، از منوی پشتیبانی پیام بفرستید."
        )
        
    await message.answer(guide_text, parse_mode="Markdown")

@router.message(F.text == "📞 پشتیبانی و تیکت")
async def support_menu_direct(message: types.Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ ثبت تیکت جدید", callback_data="new_ticket")],
        [InlineKeyboardButton(text="🗂 سوابق تیکت‌های من", callback_data="my_tickets_history")]
    ])
    await message.answer("📞 **سیستم پشتیبانی Tikino**\n\nبرای ارتباط با مدیریت، لطفاً یک گزینه را انتخاب کنید:", reply_markup=kb)