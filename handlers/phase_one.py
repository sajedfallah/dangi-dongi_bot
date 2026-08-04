import io, csv
from openpyxl import Workbook
from reportlab.pdfgen import canvas
from datetime import datetime, timezone, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy import select, func
from filters.admin import AdminFilter
from database.database import AsyncSessionLocal
from models.commerce import Wallet, WalletTransaction, WithdrawalRequest, WaitlistEntry
from models.ticket import Order, Ticket
from models.event import Event
from models.user import User
from models.enums import WithdrawalStatus, WaitlistStatus, OrderStatus, TicketStatus
from states.commerce import WalletStates
from services.wallet_service import create_full_withdrawal, reject_withdrawal, pay_withdrawal
from config import ADMIN_IDS, ADMIN_ID, settings
router=Router()

def money(v:int)->str: return f'{v:,} تومان'

@router.message(F.text=='🧾 کیف پول من')
@router.callback_query(F.data=='wallet_home')
async def wallet_home(update:types.Message|types.CallbackQuery):
    uid=update.from_user.id
    async with AsyncSessionLocal() as s:
        wallet=await s.get(Wallet,uid)
        txs=(await s.execute(select(WalletTransaction).where(WalletTransaction.user_id==uid).order_by(WalletTransaction.id.desc()).limit(5))).scalars().all()
    available=wallet.available_balance if wallet else 0; locked=wallet.locked_balance if wallet else 0
    lines='\n'.join(f'• {x.entry_type.value}: {money(abs(x.amount))}' for x in txs) or 'تراکنشی ثبت نشده است.'
    text=f'💳 **کیف پول Tikino**\n\nموجودی قابل برداشت: **{money(available)}**\nموجودی در انتظار پرداخت: **{money(locked)}**\n\nآخرین تراکنش‌ها:\n{lines}'
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💸 برداشت کامل موجودی',callback_data='withdraw_all')],[InlineKeyboardButton(text='🔄 بروزرسانی',callback_data='wallet_home')]])
    if isinstance(update,types.Message): await update.answer(text,reply_markup=kb,parse_mode='Markdown')
    else: await update.message.edit_text(text,reply_markup=kb,parse_mode='Markdown')

@router.callback_query(F.data=='withdraw_all')
async def withdraw_start(c:types.CallbackQuery,state:FSMContext):
    async with AsyncSessionLocal() as s:
        w=await s.get(Wallet,c.from_user.id)
        if not w or w.available_balance<settings.withdrawal_min_amount: return await c.answer(f'حداقل موجودی برداشت {money(settings.withdrawal_min_amount)} است.',show_alert=True)
    await state.set_state(WalletStates.waiting_for_withdrawal_account)
    await c.message.answer('💳 شماره کارت ۱۶ رقمی یا شبای متعلق به خودتان را ارسال کنید. کل موجودی قابل برداشت قفل و برای تسویه ارسال می‌شود.')

@router.message(WalletStates.waiting_for_withdrawal_account,F.text)
async def withdraw_create(m:types.Message,state:FSMContext):
    try:
        async with AsyncSessionLocal() as s: req=await create_full_withdrawal(s,user_id=m.from_user.id,payout_reference=m.text.strip())
    except ValueError as exc: return await m.answer(f'❌ {exc}')
    await state.clear(); await m.answer(f'✅ درخواست برداشت #{req.id} به مبلغ **{money(req.amount)}** ثبت شد.',parse_mode='Markdown')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='💳 ثبت پرداخت و ارسال رسید',callback_data=f'wdpay_{req.id}')],[InlineKeyboardButton(text='❌ رد درخواست',callback_data=f'wdreject_{req.id}')]])
    await m.bot.send_message(ADMIN_ID,f'💸 درخواست برداشت #{req.id}\nکاربر: `{req.user_id}`\nمبلغ: **{money(req.amount)}**\nحساب پایان‌یافته به: `{req.payout_last4}`',reply_markup=kb,parse_mode='Markdown')

@router.callback_query(F.data.startswith('wdreject_'))
async def withdrawal_reject(c:types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('دسترسی غیرمجاز',show_alert=True)
    try:
        async with AsyncSessionLocal() as s: req=await reject_withdrawal(s,request_id=int(c.data.split('_')[1]),admin_id=c.from_user.id)
    except ValueError as exc: return await c.answer(str(exc),show_alert=True)
    await c.bot.send_message(req.user_id,f'❌ درخواست برداشت #{req.id} رد شد و مبلغ به کیف پول شما برگشت.'); await c.message.edit_reply_markup(reply_markup=None)

@router.callback_query(F.data.startswith('wdpay_'))
async def withdrawal_pay_start(c:types.CallbackQuery,state:FSMContext):
    if c.from_user.id not in ADMIN_IDS: return await c.answer('دسترسی غیرمجاز',show_alert=True)
    rid=int(c.data.split('_')[1]); await state.update_data(withdrawal_id=rid); await state.set_state(WalletStates.waiting_for_withdrawal_receipt)
    await c.message.answer(f'🧾 رسید پرداخت درخواست #{rid} را به‌صورت عکس یا فایل ارسال کنید.')

@router.message(WalletStates.waiting_for_withdrawal_receipt,F.photo|F.document)
async def withdrawal_pay_finish(m:types.Message,state:FSMContext):
    if m.from_user.id not in ADMIN_IDS: return
    data=await state.get_data(); rid=data['withdrawal_id']; file_id=m.photo[-1].file_id if m.photo else m.document.file_id
    try:
        async with AsyncSessionLocal() as s: req=await pay_withdrawal(s,request_id=rid,admin_id=m.from_user.id,receipt_file_id=file_id)
    except (ValueError,RuntimeError) as exc: return await m.answer(f'❌ {exc}')
    await state.clear(); caption=f'✅ برداشت #{req.id} پرداخت شد.\nمبلغ: {money(req.amount)}\nاین فایل رسید رسمی پرداخت شماست.'
    if m.photo: await m.bot.send_photo(req.user_id,file_id,caption=caption)
    else: await m.bot.send_document(req.user_id,file_id,caption=caption)
    await m.answer('✅ پرداخت ثبت و رسید برای کاربر ارسال شد.')

@router.message(F.text=='📊 داشبورد لحظه‌ای')
async def admin_dashboard(m:types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    today=datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as s:
        sales=(await s.execute(select(func.coalesce(func.sum(Order.total_amount),0),func.count(Order.id)).where(Order.status==OrderStatus.APPROVED,func.date(Order.approved_at)==today))).one()
        issued=(await s.execute(select(func.count(Ticket.id)).where(Ticket.status==TicketStatus.ISSUED))).scalar_one()
        used=(await s.execute(select(func.count(Ticket.id)).where(Ticket.status==TicketStatus.USED))).scalar_one()
        pending_wd=(await s.execute(select(func.count(WithdrawalRequest.id),func.coalesce(func.sum(WithdrawalRequest.amount),0)).where(WithdrawalRequest.status==WithdrawalStatus.PENDING))).one()
        users=(await s.execute(select(func.count(User.id)))).scalar_one()
    await m.answer(f'📊 **داشبورد لحظه‌ای**\n\n💰 فروش امروز: {money(sales[0])}\n🧾 سفارش تأییدشده امروز: {sales[1]}\n🎫 بلیت فعال: {issued}\n✅ ورود ثبت‌شده: {used}\n👥 کاربران: {users}\n💸 برداشت‌های معلق: {pending_wd[0]} مورد / {money(pending_wd[1])}',parse_mode='Markdown')

@router.message(F.text=='📥 خروجی مالی CSV')
async def financial_csv(m:types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    async with AsyncSessionLocal() as s:
        rows=(await s.execute(select(Order).where(Order.status==OrderStatus.APPROVED).order_by(Order.id))).scalars().all()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['order_id','user_id','event_id','amount','quantity','approved_at'])
    for x in rows: w.writerow([x.id,x.user_id,x.event_id,x.total_amount,x.total_quantity,x.approved_at.isoformat() if x.approved_at else ''])
    await m.answer_document(BufferedInputFile(out.getvalue().encode('utf-8-sig'),filename='tikino-finance.csv'),caption='گزارش مالی قابل بازکردن در Excel')

@router.callback_query(F.data.startswith('waitlist_'))
async def join_waitlist(c:types.CallbackQuery):
    event_id=int(c.data.split('_')[1])
    async with AsyncSessionLocal() as s:
        async with s.begin():
            event=await s.get(Event,event_id)
            if not event: return await c.answer('رویداد یافت نشد.',show_alert=True)
            row=(await s.execute(select(WaitlistEntry).where(WaitlistEntry.event_id==event_id,WaitlistEntry.user_id==c.from_user.id).with_for_update())).scalar_one_or_none()
            if row: row.status=WaitlistStatus.WAITING
            else: s.add(WaitlistEntry(event_id=event_id,user_id=c.from_user.id,quantity=1,status=WaitlistStatus.WAITING))
    await c.answer('در لیست انتظار ثبت شدید.',show_alert=True)

@router.message(F.text=='📊 خروجی مالی Excel')
async def financial_xlsx(m:types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    async with AsyncSessionLocal() as s:
        rows=(await s.execute(select(Order).where(Order.status==OrderStatus.APPROVED).order_by(Order.id))).scalars().all()
    wb=Workbook(); ws=wb.active; ws.title='Finance'
    ws.append(['Order ID','User ID','Event ID','Amount (Toman)','Quantity','Approved At'])
    total=0
    for x in rows:
        total+=x.total_amount; ws.append([x.id,x.user_id,x.event_id,x.total_amount,x.total_quantity,x.approved_at.isoformat() if x.approved_at else ''])
    ws.append([]); ws.append(['TOTAL','','',total])
    bio=io.BytesIO(); wb.save(bio)
    await m.answer_document(BufferedInputFile(bio.getvalue(),filename='tikino-finance.xlsx'),caption='گزارش مالی Excel')

@router.message(F.text=='📄 گزارش مالی PDF')
async def financial_pdf(m:types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    async with AsyncSessionLocal() as s:
        sales=(await s.execute(select(func.coalesce(func.sum(Order.total_amount),0),func.count(Order.id),func.coalesce(func.sum(Order.total_quantity),0)).where(Order.status==OrderStatus.APPROVED))).one()
        refunds=(await s.execute(select(func.coalesce(func.sum(WalletTransaction.amount),0)).where(WalletTransaction.entry_type=='REFUND_CREDIT'))).scalar_one()
        withdrawals=(await s.execute(select(func.coalesce(func.sum(WithdrawalRequest.amount),0)).where(WithdrawalRequest.status==WithdrawalStatus.PAID))).scalar_one()
    bio=io.BytesIO(); pdf=canvas.Canvas(bio)
    pdf.setTitle('Tikino Financial Report'); pdf.setFont('Helvetica-Bold',16); pdf.drawString(72,790,'Tikino Financial Report')
    pdf.setFont('Helvetica',11); y=750
    for label,value in [('Approved orders',sales[1]),('Tickets sold',sales[2]),('Gross sales (Toman)',sales[0]),('Wallet refund credits (Toman)',refunds),('Paid withdrawals (Toman)',withdrawals)]:
        pdf.drawString(72,y,f'{label}: {value:,}'); y-=28
    pdf.drawString(72,y-10,f'Generated UTC: {datetime.now(timezone.utc).isoformat()}'); pdf.save()
    await m.answer_document(BufferedInputFile(bio.getvalue(),filename='tikino-financial-report.pdf'),caption='گزارش مدیریتی PDF')
