from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.commerce import Wallet, WalletTransaction, WithdrawalRequest
from models.enums import WalletEntryType, WithdrawalStatus
from services.secure_transactions import audit
UTC=lambda: datetime.now(timezone.utc)

async def _wallet_locked(session:AsyncSession,user_id:int)->Wallet:
    wallet=(await session.execute(select(Wallet).where(Wallet.user_id==user_id).with_for_update())).scalar_one_or_none()
    if not wallet:
        wallet=Wallet(user_id=user_id,available_balance=0,locked_balance=0); session.add(wallet); await session.flush()
    return wallet

async def credit_refund(session:AsyncSession,*,user_id:int,amount:int,refund_id:int,actor_id:int):
    if amount<=0: raise ValueError('مبلغ استرداد نامعتبر است.')
    wallet=await _wallet_locked(session,user_id); wallet.available_balance+=amount
    session.add(WalletTransaction(user_id=user_id,entry_type=WalletEntryType.REFUND_CREDIT,amount=amount,balance_after=wallet.available_balance,reference_type='refund',reference_id=str(refund_id),actor_id=actor_id,note='واریز استرداد بلیت به کیف پول'))
    audit(session,actor_id,'WALLET_REFUND_CREDIT','wallet',user_id,after={'amount':amount,'balance':wallet.available_balance})
    return wallet

async def create_full_withdrawal(session:AsyncSession,*,user_id:int,payout_reference:str):
    digits=''.join(c for c in payout_reference if c.isdigit())
    if len(digits)<4: raise ValueError('شماره کارت یا شبا معتبر نیست.')
    async with session.begin():
        pending=(await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.user_id==user_id,WithdrawalRequest.status==WithdrawalStatus.PENDING))).scalar_one_or_none()
        if pending: raise ValueError('یک درخواست برداشت در حال بررسی دارید.')
        wallet=await _wallet_locked(session,user_id)
        if wallet.available_balance<=0: raise ValueError('موجودی قابل برداشت ندارید.')
        amount=wallet.available_balance; wallet.available_balance=0; wallet.locked_balance+=amount
        req=WithdrawalRequest(user_id=user_id,amount=amount,payout_reference=payout_reference,payout_last4=digits[-4:],status=WithdrawalStatus.PENDING); session.add(req); await session.flush()
        session.add(WalletTransaction(user_id=user_id,entry_type=WalletEntryType.WITHDRAWAL_LOCK,amount=-amount,balance_after=wallet.available_balance,reference_type='withdrawal',reference_id=str(req.id),actor_id=user_id,note='قفل موجودی برای برداشت کامل'))
        audit(session,user_id,'WITHDRAWAL_REQUESTED','withdrawal',req.id,after={'amount':amount})
    await session.refresh(req); return req

async def reject_withdrawal(session:AsyncSession,*,request_id:int,admin_id:int,note:str|None=None):
    async with session.begin():
        req=(await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id==request_id).with_for_update())).scalar_one_or_none()
        if not req or req.status!=WithdrawalStatus.PENDING: raise ValueError('درخواست قابل رد نیست.')
        wallet=await _wallet_locked(session,req.user_id); wallet.locked_balance-=req.amount; wallet.available_balance+=req.amount
        req.status=WithdrawalStatus.REJECTED; req.reviewed_by=admin_id; req.reviewed_at=UTC(); req.admin_note=note
        session.add(WalletTransaction(user_id=req.user_id,entry_type=WalletEntryType.WITHDRAWAL_RELEASE,amount=req.amount,balance_after=wallet.available_balance,reference_type='withdrawal',reference_id=str(req.id),actor_id=admin_id,note='آزادسازی موجودی برداشت ردشده'))
        audit(session,admin_id,'WITHDRAWAL_REJECTED','withdrawal',req.id)
    return req

async def pay_withdrawal(session:AsyncSession,*,request_id:int,admin_id:int,receipt_file_id:str):
    async with session.begin():
        req=(await session.execute(select(WithdrawalRequest).where(WithdrawalRequest.id==request_id).with_for_update())).scalar_one_or_none()
        if not req or req.status!=WithdrawalStatus.PENDING: raise ValueError('درخواست قابل پرداخت نیست.')
        wallet=await _wallet_locked(session,req.user_id)
        if wallet.locked_balance<req.amount: raise RuntimeError('مانده قفل‌شده کیف پول ناسازگار است.')
        wallet.locked_balance-=req.amount; req.status=WithdrawalStatus.PAID; req.receipt_file_id=receipt_file_id; req.reviewed_by=admin_id; req.reviewed_at=UTC()
        session.add(WalletTransaction(user_id=req.user_id,entry_type=WalletEntryType.WITHDRAWAL_PAID,amount=-req.amount,balance_after=wallet.available_balance,reference_type='withdrawal',reference_id=str(req.id),actor_id=admin_id,note='برداشت پرداخت‌شده'))
        audit(session,admin_id,'WITHDRAWAL_PAID','withdrawal',req.id,after={'amount':req.amount})
    return req
