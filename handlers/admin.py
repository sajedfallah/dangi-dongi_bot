import json
import logging
from aiogram import Router, types, F
from filters.admin import AdminFilter
from database.database import AsyncSessionLocal
from services.user_service import update_user_status, get_user
from services.event_service import (
    get_order_by_id, get_event_by_id
)
from services.secure_transactions import approve_order_atomic, release_order
from models.enums import OrderStatus
from services.google_sheets import send_to_sheet
from keyboards.reply import get_main_menu
from aiogram.fsm.context import FSMContext
from states.admin_event import AdminSearchInvoice

router = Router()
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

@router.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def process_approval(callback: types.CallbackQuery):
    action, user_id_str = callback.data.split("_")
    target_user_id = int(user_id_str)
    try:
        async with AsyncSessionLocal() as session:
            if action == "approve":
                await update_user_status(session, target_user_id, "APPROVED")
                await callback.bot.send_message(
                    chat_id=target_user_id, 
                    text="🎉 حساب شما تایید شد!\nحالا می‌توانید از منو استفاده کنید.", 
                    reply_markup=get_main_menu()
                )
                await callback.message.edit_text(
                    text=callback.message.text + "\n\n✅ وضعیت: تایید شد.", 
                    reply_markup=None
                )
            elif action == "reject":
                await update_user_status(session, target_user_id, "REJECTED")
                await callback.bot.send_message(
                    chat_id=target_user_id, 
                    text="❌ متاسفانه درخواست شما توسط مدیریت رد شد."
                )
                await callback.message.edit_text(
                    text=callback.message.text + "\n\n❌ وضعیت: رد شد.", 
                    reply_markup=None
                )
    except Exception as e:
        logging.error(f"Error in approval: {e}")
    finally:
        await callback.answer()

@router.callback_query(F.data.startswith("orderapprove_"))
async def approve_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    try:
        async with AsyncSessionLocal() as session:
            order, tickets = await approve_order_atomic(session, order_id=order_id, admin_id=callback.from_user.id)
            event = await get_event_by_id(session, order.event_id)
            buyer = await get_user(session, order.user_id)
        tickets_for_sheet = [{"tracking_code": t.tracking_code, "owner_name": t.owner_name, "event_title": event.title, "buyer_id": buyer.telegram_id} for t in tickets]
        await send_to_sheet("add_tickets", {"tickets": tickets_for_sheet})
        await send_to_sheet("add_income", {"order_id": order.id, "buyer_id": buyer.telegram_id, "event_title": event.title, "total_qty": order.total_quantity, "total_amount": order.total_amount})
        await callback.bot.send_message(order.user_id, "✅ پرداخت تأیید و همه بلیت‌ها در یک تراکنش صادر شد.")
        await callback.message.delete()
        await callback.message.answer(f"✅ فاکتور #{order.id} تأیید شد.")
    except Exception as exc:
        logging.exception("approve order failed")
        await callback.answer(str(exc), show_alert=True)

@router.callback_query(F.data.startswith("orderreject_"))
async def reject_order(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        order = await release_order(session, order_id=order_id, new_status=OrderStatus.REJECTED, actor_id=callback.from_user.id)
    if not order:
        return await callback.answer("فاکتور قابل رد نیست.", show_alert=True)
    await callback.bot.send_message(order.user_id, "❌ فیش شما رد شد و ظرفیت و رزرو کد تخفیف آزاد گردید.")
    await callback.message.delete()
    await callback.message.answer(f"❌ فاکتور #{order.id} رد شد.")

# ================= بخش جدید: جستجو در بایگانی =================

@router.message(F.text == "🔍 جستجوی فیش")
async def ask_invoice_id_for_search(message: types.Message, state: FSMContext):
    await state.set_state(AdminSearchInvoice.waiting_for_invoice_id)
    await message.answer("🔍 **جستجوی بایگانی فیش‌ها**\n\nلطفاً **شماره فاکتور (مثلاً 15)** مورد نظر خود را به صورت عدد بفرستید:")

@router.message(AdminSearchInvoice.waiting_for_invoice_id, F.text)
async def process_invoice_search(message: types.Message, state: FSMContext):
    invoice_id_text = message.text.strip()
    if not invoice_id_text.isdigit():
        return await message.answer("❌ لطفاً فقط عدد وارد کنید.")
    
    order_id = int(invoice_id_text)
    
    async with AsyncSessionLocal() as session:
        order = await get_order_by_id(session, order_id)
        
    if not order:
        await state.clear()
        return await message.answer(f"❌ فاکتوری با شماره `#{order_id}` در بایگانی یافت نشد.")
        
    if not order.receipt_file_id:
        await state.clear()
        return await message.answer(f"⚠️ فاکتور `#{order_id}` یافت شد اما هیچ عکسی (فیشی) برای آن ثبت نشده است.\nوضعیت: {order.status}")
    
    await state.clear()
    
    status_map = {
        "AWAITING_PAYMENT": "⏳ منتظر پرداخت",
        "PENDING_APPROVAL": "🔄 در حال بررسی فیش",
        "APPROVED": "✅ تایید شده",
        "REJECTED": "❌ رد شده",
        "EXPIRED": "⌛️ منقضی شده"
    }
    
    caption = (
        f"🧾 **بایگانی فیش فاکتور #{order.id}**\n"
        f"📊 وضعیت کنونی: **{status_map.get(order.status, order.status)}**\n"
        f"💰 مبلغ کل: {order.total_amount:,} تومان\n"
        f"🎫 تعداد بلیت: {order.total_quantity}\n"
        f"👤 آیدی تلگرام خریدار: `{order.user_id}`"
    )
    
    # ارسال مجدد عکس فیش از دیتابیس به ادمین
    await message.answer_photo(photo=order.receipt_file_id, caption=caption, parse_mode="Markdown")