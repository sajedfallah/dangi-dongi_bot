import json
from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.database import AsyncSessionLocal
from services.event_service import (
    get_event_by_id, get_ticket_types_for_event, get_ticket_type_by_id, 
    get_order_by_id, get_promo_by_code
)
from services.secure_transactions import reserve_order, attach_receipt
from config import settings
from services.user_service import get_user
from states.user_event import BuyTicket
from config import ADMIN_ID

router = Router()

def generate_cart_text(event_title, cart):
    if not cart: return f"🎟 **رویداد:** {event_title}\n\n🛒 سبد خرید شما خالی است."
    text = f"🎟 **رویداد:** {event_title}\n\n🛒 **سبد خرید:**\n━━━━━━━━━━━\n"
    total_price = sum(item['qty'] * item['price'] for item in cart.values())
    total_qty = sum(item['qty'] for item in cart.values())
    for tt_id, item in cart.items():
        text += f"🔹 {item['name']} ✖️ {item['qty']} = {item['qty'] * item['price']:,} تومان\n"
    text += f"━━━━━━━━━━━\n💰 **مبلغ کل:** {total_price:,} تومان\n👥 **تعداد بلیت:** {total_qty}\n"
    return text

@router.callback_query(F.data.startswith("buy_"))
async def start_shopping(callback: types.CallbackQuery, state: FSMContext):
    event_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    cart = data.get('cart', {})
    await state.update_data(event_id=event_id, cart=cart, promo_data=None) # Reset promo
    await state.set_state(BuyTicket.shopping)
    
    async with AsyncSessionLocal() as session:
        event = await get_event_by_id(session, event_id)
        ticket_types = await get_ticket_types_for_event(session, event_id)

    text = generate_cart_text(event.title, cart)
    builder = InlineKeyboardBuilder()
    for tt in ticket_types: builder.button(text=f"➕ {tt.name} ({tt.price:,})", callback_data=f"buytype_{tt.id}")
    builder.adjust(1)
    if cart: builder.row(InlineKeyboardButton(text="🛒 ثبت مشخصات", callback_data="start_checkout_names"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="user_events_list"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(BuyTicket.shopping, F.data.startswith("buytype_"))
async def ask_quantity(callback: types.CallbackQuery, state: FSMContext):
    tt_id = int(callback.data.split("_")[1])
    async with AsyncSessionLocal() as session:
        tt = await get_ticket_type_by_id(session, tt_id)
    await state.update_data(current_tt_id=tt_id, current_tt_name=tt.name, current_tt_price=tt.price)
    await state.set_state(BuyTicket.waiting_for_quantity)
    text = f"🔢 **بلیت {tt.name}**\nلطفاً **تعداد** مورد نیاز را به عدد ارسال کنید:"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 لغو", callback_data=f"buy_{tt.event_id}")]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.message(BuyTicket.waiting_for_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    translated_text = "".join({"۰":"0", "۱":"1", "۲":"2", "۳":"3", "۴":"4", "۵":"5", "۶":"6", "۷":"7", "۸":"8", "۹":"9"}.get(c, c) for c in message.text.strip())
    if not translated_text.isdigit() or int(translated_text) <= 0: return await message.answer("❌ عدد معتبر وارد کنید:")
    qty = int(translated_text)
    data = await state.get_data()
    cart = data.get('cart', {})
    tt_id = str(data['current_tt_id'])
    
    if tt_id in cart: cart[tt_id]['qty'] += qty
    else: cart[tt_id] = {'name': data['current_tt_name'], 'price': data['current_tt_price'], 'qty': qty, 'owners': []}
    await state.update_data(cart=cart)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="سبد خرید", callback_data=f"buy_{data['event_id']}")]])
    await message.answer(f"✅ {qty} عدد به سبد خرید اضافه شد.", reply_markup=kb)

@router.callback_query(BuyTicket.shopping, F.data == "start_checkout_names")
async def start_naming(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tickets_to_name = [{"tt_id": tt_id, "name": item['name'], "index": i+1} for tt_id, item in data.get('cart', {}).items() for i in range(item['qty'])]
    await state.update_data(tickets_to_name=tickets_to_name, current_naming_index=0)
    await state.set_state(BuyTicket.entering_names)
    await ask_for_next_name(callback.message, state)
    await callback.answer()

async def ask_for_next_name(message_or_callback, state: FSMContext):
    data = await state.get_data()
    idx = data['current_naming_index']
    if idx < len(data['tickets_to_name']):
        ticket = data['tickets_to_name'][idx]
        text = f"👤 لطفاً نام و نام خانوادگی صاحب بلیت **{ticket['name']}** را تایپ کنید:\n\n💡 _راهنما: این نام برای احراز هویت در زمان ورود استفاده می‌شود. لطفاً نام دقیق را وارد کنید._"
        if isinstance(message_or_callback, types.Message): await message_or_callback.answer(text, parse_mode="Markdown")
        else: await message_or_callback.edit_text(text, parse_mode="Markdown")
    else:
        await ask_promo_code(message_or_callback, state)

@router.message(BuyTicket.entering_names, F.text)
async def process_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data['cart'][data['tickets_to_name'][data['current_naming_index']]['tt_id']]['owners'].append(message.text.strip())
    await state.update_data(cart=data['cart'], current_naming_index=data['current_naming_index'] + 1)
    await ask_for_next_name(message, state)

async def ask_promo_code(message_or_callback, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ رد کردن و صدور فاکتور", callback_data="skip_promo")]])
    text = "🎁 **کد تخفیف (اختیاری)**\n\nاگر کد تخفیف دارید، آن را اینجا تایپ کنید. در غیر این صورت دکمه زیر را بزنید:"
    await state.set_state(BuyTicket.asking_promo_code)
    if isinstance(message_or_callback, types.Message): await message_or_callback.answer(text, reply_markup=kb, parse_mode="Markdown")
    else: await message_or_callback.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(BuyTicket.asking_promo_code, F.data == "skip_promo")
async def skip_promo(callback: types.CallbackQuery, state: FSMContext):
    await generate_invoice(callback.message, state)
    await callback.answer()

@router.message(BuyTicket.asking_promo_code, F.text)
async def check_promo_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = message.text.strip()
    async with AsyncSessionLocal() as session:
        promo, msg = await get_promo_by_code(session, code, data['event_id'])
    if not promo:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➡️ رد کردن (بدون تخفیف)", callback_data="skip_promo")]])
        return await message.answer(f"❌ {msg}\nمی‌توانید دوباره تلاش کنید یا رد شوید:", reply_markup=kb)
        
    await state.update_data(promo_data={"id": promo.id, "code": promo.code, "percent": promo.discount_percent})
    await message.answer(f"✅ کد تخفیف `{promo.code}` با موفقیت اعمال شد ({promo.discount_percent}% تخفیف).")
    await generate_invoice(message, state)

async def generate_invoice(message_or_callback, state: FSMContext):
    data = await state.get_data()
    cart = data['cart']
    event_id = data['event_id']
    promo = data.get('promo_data')
    
    total_price = sum(item['qty'] * item['price'] for item in cart.values())
    total_qty = sum(item['qty'] for item in cart.values())
    discount_amount = 0
    final_price = total_price
    
    if promo:
        discount_amount = int(total_price * (promo['percent'] / 100))
        final_price = total_price - discount_amount
    
    await state.update_data(final_price=final_price)
        
    text = "🧾 **پیش فاکتور شما آماده شد!**\n━━━━━━━━━━━━━━━━━━\n📋 **لیست بلیت‌ها:**\n"
    for tt_id, item in cart.items():
        text += f"🔹 **{item['qty']}x {item['name']}**\n"
        for name in item['owners']: text += f"   - {name}\n"
            
    text += "━━━━━━━━━━━━━━━━━━\n"
    if promo: text += f"💵 جمع اولیه: {total_price:,} تومان\n🎁 تخفیف ({promo['percent']}%): -{discount_amount:,} تومان\n"
    text += f"💳 **مبلغ قابل پرداخت:** {final_price:,} تومان\n\n"
    text += "⏳ این پیش فاکتور به مدت **۵ ساعت** اعتبار دارد.\n\n💡 _راهنما: برای قطعی شدن خرید و رزرو صندلی، لطفاً روش پرداخت را در زیر انتخاب کنید:_"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 پرداخت الان (ارسال فیش)", callback_data="pay_now")],
        [InlineKeyboardButton(text="⏳ پرداخت بعداً (رزرو موقت)", callback_data="pay_later")],
        [InlineKeyboardButton(text="❌ لغو", callback_data=f"buy_{event_id}")]
    ])
    await state.set_state(BuyTicket.choosing_payment_method)
    
    if isinstance(message_or_callback, types.Message): await message_or_callback.answer(text, reply_markup=kb, parse_mode="Markdown")
    else: await message_or_callback.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(BuyTicket.choosing_payment_method, F.data.in_(["pay_now", "pay_later"]))
async def process_payment_method(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    total_qty = sum(item['qty'] for item in data['cart'].values())
    promo_id = data['promo_data']['id'] if data.get('promo_data') else None
    final_price = data.get('final_price')
    
    async with AsyncSessionLocal() as session:
        event = await get_event_by_id(session, data['event_id'])
        user = await get_user(session, user_id)
        try:
            order = await reserve_order(session, user_id=user.telegram_id, event_id=event.id, total_amount=final_price, total_quantity=total_qty, cart_data=data['cart'], promo_id=promo_id, expires_hours=settings.order_expiry_hours)
        except ValueError as exc:
            await state.clear()
            kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔔 عضویت در لیست انتظار",callback_data=f"waitlist_{data['event_id']}")],[InlineKeyboardButton(text="🔙 بازگشت",callback_data="user_events_list")]])
            return await callback.message.edit_text(f"❌ {exc}\n\nدر صورت آزادشدن ظرفیت به شما اطلاع می‌دهیم.",reply_markup=kb)
        
    if callback.data == "pay_later":
        await state.clear()
        text = f"✅ **رزرو شد.**\n⏳ فاکتور `#{order.id}` تا ۵ ساعت اعتبار دارد. برای پرداخت از کیف پول اقدام کنید."
        await callback.message.edit_text(text, parse_mode="Markdown")
    else:
        await state.update_data(order_id=order.id)
        await state.set_state(BuyTicket.waiting_for_receipt)
        text = f"💳 **شماره کارت جهت واریز {final_price:,} تومان:**\n`{settings.payment_card_number}`\n\n📸 **عکس فیش واریزی را ارسال کنید:**"
        await callback.message.edit_text(text, parse_mode="Markdown")

@router.message(BuyTicket.waiting_for_receipt, F.photo)
async def process_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id 
    wait_msg = await message.answer("⏳ پردازش...")
    
    async with AsyncSessionLocal() as session:
        try:
            order = await attach_receipt(session, order_id=data['order_id'], user_id=message.from_user.id, file_id=file_id)
        except (ValueError, PermissionError) as exc:
            await state.clear()
            await wait_msg.delete()
            return await message.answer(f"❌ {exc}")
        user = await get_user(session, message.from_user.id)
        
    await state.clear()
    await wait_msg.delete()
    await message.answer("✅ رسید دریافت شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="بازگشت", callback_data="user_events_list")]]))
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ تایید", callback_data=f"orderapprove_{order.id}"), InlineKeyboardButton(text="❌ رد", callback_data=f"orderreject_{order.id}")]])
    await message.bot.send_photo(chat_id=ADMIN_ID, photo=file_id, caption=f"🔔 **فیش جدید #{order.id}**\n💰 {order.total_amount:,} تومان\n🎫 {order.total_quantity} بلیت", reply_markup=kb)