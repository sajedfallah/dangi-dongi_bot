import io
import qrcode
from PIL import Image
from aiogram import Router, types, F
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.database import AsyncSessionLocal
from sqlalchemy import select
from models.ticket import Ticket
from services.event_service import get_event_by_id
from services.qr_service import create_ticket_token

router = Router()

def create_ticket_image(ticket_data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(ticket_data['tracking_code'])
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    ticket_img = Image.new('RGB', (800, 400), color=(255, 255, 255))
    qr_img = qr_img.resize((300, 300))
    ticket_img.paste(qr_img, (250, 50)) 
    bio = io.BytesIO()
    ticket_img.save(bio, format='PNG')
    bio.seek(0)
    return bio

@router.message(F.text == "🎫 بلیت‌های من")
@router.callback_query(F.data == "show_my_tickets")
async def show_my_events_callback(update: types.Message | types.CallbackQuery):
    user_id = update.from_user.id
    
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Ticket.event_id).where(Ticket.user_id == user_id).distinct()
        )
        event_ids = result.scalars().all()
        
    builder = InlineKeyboardBuilder()
    
    if not event_ids:
        text = "🎫 **بلیت‌های شما**\n\nشما در حال حاضر هیچ بلیتی در سیستم ندارید.\n💡 _راهنما: اگر منتظر تایید فیش هستید، به بخش «کیف پول من» مراجعه کنید._"
    else:
        text = "🎫 **تاریخچه بلیت‌های شما**\n\n💡 _راهنما: رویداد مورد نظر را انتخاب کنید تا بلیت‌های (فعال و غیرفعال) آن نمایش داده شود:_"
        for e_id in event_ids:
            async with AsyncSessionLocal() as session:
                event = await get_event_by_id(session, e_id)
            if event:
                builder.button(text=f"🔹 {event.title}", callback_data=f"mytickets_{event.id}")
                
    builder.adjust(1)
    
    if isinstance(update, types.Message):
        await update.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    else:
        await update.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(F.data.startswith("mytickets_"))
async def show_first_ticket(callback: types.CallbackQuery):
    event_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id # باگ تایپی در اینجا برطرف شد
    await paginate_tickets_logic(callback, event_id, user_id, 0)

@router.callback_query(F.data.startswith("showt_"))
async def paginate_tickets(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    event_id = int(parts[1])
    idx = int(parts[2])
    user_id = callback.from_user.id
    await paginate_tickets_logic(callback, event_id, user_id, idx)

async def paginate_tickets_logic(callback: types.CallbackQuery, event_id: int, user_id: int, idx: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Ticket).where(Ticket.user_id == user_id, Ticket.event_id == event_id)
        )
        tickets = result.scalars().all()
        
    if not tickets:
        await callback.answer("بلیتی یافت نشد.", show_alert=True)
        return
        
    if idx < 0 or idx >= len(tickets): idx = 0
        
    ticket = tickets[idx]
    
    status_dict = {
        "ISSUED": "🟢 فعال (آماده ورود)", 
        "USED": "🔴 استفاده شده (باطل)", 
        "CANCELED": "⚫️ باطل / لغو شده", 
        "REFUND_PENDING": "⏳ در حال بررسی عودت وجه"
    }
    
    caption = (
        f"🎟 **بلیت {idx + 1} از {len(tickets)}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **صاحب بلیت:** {ticket.owner_name}\n"
        f"🔢 **کد پیگیری:** `{ticket.tracking_code}`\n"
        f"📊 **وضعیت بلیت:** {status_dict.get(ticket.status, ticket.status)}\n\n"
    )
    if ticket.status == "ISSUED":
        caption += f"📱 لطفاً در زمان برگزاری، این بارکد را به متصدی گیت نشان دهید.\n\n💡 _در صورت انصراف، دکمه درخواست استرداد را در زیر فشار دهید._"
    
    kb = InlineKeyboardBuilder()
    
    # نمایش دکمه استرداد فقط برای بلیت‌های فعال
    if ticket.status == "ISSUED":
        kb.button(text="❌ درخواست لغو و عودت وجه", callback_data=f"refundreq_{ticket.id}")
        
    # دکمه‌های صفحه‌بندی
    if idx > 0: kb.button(text="⬅️ قبلی", callback_data=f"showt_{event_id}_{idx-1}")
    if idx < len(tickets) - 1: kb.button(text="بعدی ➡️", callback_data=f"showt_{event_id}_{idx+1}")
        
    kb.button(text="🔙 بازگشت به لیست", callback_data="show_my_tickets")
    
    # تنظیم چیدمان دکمه‌ها
    if ticket.status == "ISSUED":
        if idx > 0 and idx < len(tickets) - 1: kb.adjust(1, 2, 1)
        else: kb.adjust(1)
    else:
        if idx > 0 and idx < len(tickets) - 1: kb.adjust(2, 1)
        else: kb.adjust(1)

    bio = create_ticket_image({'tracking_code': create_ticket_token(ticket.id,ticket.tracking_code,ticket.event_id)})
    
    if not callback.message.photo:
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=BufferedInputFile(bio.read(), filename="ticket.png"),
            caption=caption, reply_markup=kb.as_markup(), parse_mode="Markdown"
        )
    else:
        await callback.message.edit_media(
            media=types.InputMediaPhoto(media=BufferedInputFile(bio.read(), filename="ticket.png"), caption=caption, parse_mode="Markdown"),
            reply_markup=kb.as_markup()
        )
    await callback.answer()