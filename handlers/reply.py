import json
import datetime
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from database.database import AsyncSessionLocal
from models.ticket import Order
from states.user_event import BuyTicket

router = Router()

STATUS_MAP = {
    "AWAITING_PAYMENT": "⏳ در انتظار پرداخت",
    "PENDING_APPROVAL": "🔄 در انتظار تایید مدیریت",
    "APPROVED": "✅ پرداخت و تایید شده",
    "REJECTED": "❌ فیش رد شده",
    "EXPIRED": "⌛️ منقضی و لغو شده"
}

@router.message(F.text == "🧾 فاکتورهای من")
async def list_invoices(message: types.Message):
    user_id = message.from_user.id
    await show_invoices_list(message, user_id)

async def show_invoices_list(message_or_callback, user_id: int):
    # دریافت لیست تمام فاکتورهای کاربر به ترتیب جدیدترین‌ها
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())
        )
        orders = result.scalars().all()
        
    if not orders:
        text = "شما تا کنون هیچ سفارش یا فاکتوری ثبت نکرده‌اید. 🧾"
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(text)
        else:
            await message_or_callback.message.edit_text(text)
        return
        
    text = "🧾 **فاکتورها و سفارشات شما**\n\nبرای مشاهده جزئیات یا پرداخت، روی فاکتور مورد نظر کلیک کنید:"
    builder = InlineKeyboardBuilder()
    
    # ساخت لیست دکمه‌ها برای فاکتورها
    for order in orders:
        status_fa = STATUS_MAP.get(order.status, "نامشخص")
        btn_text = f"فاکتور #{order.id} | {status_fa}"
        builder.button(text=btn_text, callback_data=f"invoice_{order.id}")
        
    builder.adjust(1)
    
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("invoice_"))
async def view_invoice(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        order = await session.execute(select(Order).where(Order.id == order_id))
        order = order.scalar_one_or_none()
        
    if not order:
        await callback.answer("❌ فاکتور یافت نشد.", show_alert=True)
        return
        
    cart = json.loads(order.cart_data)
    
    text = (
        f"🧾 **جزئیات فاکتور #{order.id}**\n"
        f"📊 وضعیت: **{STATUS_MAP.get(order.status, order.status)}**\n"
        "━━━━━━━━━━━━━━━━━━\n"
    )
    for tt_id, item in cart.items():
        text += f"🔹 {item['qty']} عدد بلیت {item['name']}\n"
    
    text += (
        "━━━━━━━━━━━━━━━━━━\n"
        f"💰 **مبلغ کل پرداخت:** {order.total_amount:,} تومان\n"
    )
    
    kb = InlineKeyboardBuilder()
    now = datetime.datetime.now()
    
    # بررسی زمان برای فاکتورهای پرداخت نشده
    if order.status == "AWAITING_PAYMENT":
        if order.expires_at and order.expires_at > now:
            delta = order.expires_at - now
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            text += f"\n⏳ **زمان باقیمانده مهلت پرداخت:** {hours} ساعت و {minutes} دقیقه"
            text += "\n\n⚠️ **شما هنوز این فاکتور را پرداخت نکرده‌اید.**\nبرای جلوگیری از لغو شدن، لطفاً هرچه سریع‌تر دکمه پرداخت را بزنید."
            kb.button(text="💳 پرداخت و ارسال فیش", callback_data=f"payinvoice_{order.id}")
        else:
            text += "\n\n⚠️ **مهلت ۵ ساعته این فاکتور به پایان رسیده و ظرفیت لغو شده است.**"
    
    kb.button(text="🔙 بازگشت به لیست", callback_data="back_to_invoices")
    kb.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("payinvoice_"))
async def start_paying_invoice(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[1])
    
    async with AsyncSessionLocal() as session:
        order = await session.execute(select(Order).where(Order.id == order_id))
        order = order.scalar_one_or_none()
        
        if not order or order.status != "AWAITING_PAYMENT":
            await callback.answer("این فاکتور قابل پرداخت نیست.", show_alert=True)
            return
            
    # ارجاع به State تایید فیش در بخش قبلی
    await state.update_data(order_id=order_id)
    await state.set_state(BuyTicket.waiting_for_receipt)
    
    text = (
        f"💳 **شماره کارت جهت واریز مبلغ {order.total_amount:,} تومان:**\n"
        "`1234-5678-1234-5678` (به نام فلانی)\n\n"
        "📸 **لطفاً عکس فیش یا اسکرین‌شات پرداخت خود را در همینجا ارسال کنید.**"
    )
    await callback.message.edit_text(text, parse_mode="Markdown")

@router.callback_query(F.data == "back_to_invoices")
async def go_back_to_invoices(callback: types.CallbackQuery):
    await show_invoices_list(callback, callback.from_user.id)
    await callback.answer()