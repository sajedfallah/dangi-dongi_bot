from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import json
import datetime

from database.database import AsyncSessionLocal
from models.ticket import Order
from states.user_event import BuyTicket

router = Router()

STATUS_MAP = {
    "AWAITING_PAYMENT": "⏳ منتظر پرداخت",
    "PENDING_APPROVAL": "🔄 در حال بررسی فیش",
    "APPROVED": "✅ تایید شده",
    "REJECTED": "❌ رد شده",
    "EXPIRED": "⌛️ منقضی شده (لغو)"
}

@router.message(F.text == "🧾 کیف پول من")
@router.callback_query(F.data == "show_my_invoices")
async def show_invoices_callback(update: types.Message | types.CallbackQuery):
    user_id = update.from_user.id
    async with AsyncSessionLocal() as session:
        # دریافت فاکتورهای کاربر به صورت نزولی
        result = await session.execute(
            select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())
        )
        orders = result.scalars().all()
        
    builder = InlineKeyboardBuilder()
    
    if not orders:
        text = "🧾 **کیف پول و فاکتورهای شما**\n\nشما تا کنون هیچ تراکنشی در سیستم نداشته‌اید."
    else:
        text = "🧾 **کیف پول و فاکتورهای شما**\n\nجهت مشاهده جزئیات یا پرداخت، روی فاکتور مورد نظر کلیک کنید:"
        for order in orders:
            status_fa = STATUS_MAP.get(order.status, "نامشخص")
            icon = "🟢" if order.status == "APPROVED" else "🟠" if order.status in ["AWAITING_PAYMENT", "PENDING_APPROVAL"] else "🔴"
            btn_text = f"{icon} فاکتور #{order.id} | {status_fa}"
            builder.button(text=btn_text, callback_data=f"invoice_{order.id}")
            
    builder.adjust(1)
    
    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await update.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

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
        f"💰 **مبلغ کل:** {order.total_amount:,} تومان\n"
    )
    
    kb = InlineKeyboardBuilder()
    now = datetime.datetime.now()
    
    if order.status == "AWAITING_PAYMENT":
        if order.expires_at and order.expires_at > now:
            delta = order.expires_at - now
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            text += f"\n⏳ **زمان باقیمانده برای پرداخت:** {hours} ساعت و {minutes} دقیقه\n\n⚠️ در صورت عدم پرداخت، این فاکتور باطل و ظرفیت رویداد آزاد خواهد شد."
            kb.button(text="💳 پرداخت و ارسال فیش", callback_data=f"payinvoice_{order.id}")
        else:
            text += "\n\n⚠️ مهلت پرداخت به پایان رسیده و سفارش لغو شده است."
            
    kb.button(text="🔙 بازگشت به کیف پول", callback_data="show_my_invoices")
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
            
    await state.update_data(order_id=order_id)
    await state.set_state(BuyTicket.waiting_for_receipt)
    
    text = (
        f"💳 **شماره کارت جهت واریز مبلغ {order.total_amount:,} تومان:**\n"
        "`1234-5678-1234-5678` (به نام Tikino)\n\n"
        "📸 **لطفاً عکس فیش یا اسکرین‌شات پرداخت خود را در همینجا ارسال کنید.**"
    )
    kb = InlineKeyboardBuilder().button(text="🔙 انصراف", callback_data="show_my_invoices")
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")