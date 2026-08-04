from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from models.commerce import ScheduledNotification, WaitlistEntry
from models.enums import NotificationStatus, WaitlistStatus
UTC=lambda: datetime.now(timezone.utc)

async def schedule_event_reminders(session,user_id,event):
    for delta,label in ((timedelta(hours=24),'فردا'),(timedelta(hours=3),'تا سه ساعت دیگر')):
        send_at=event.starts_at-delta
        if send_at>UTC():
            session.add(ScheduledNotification(user_id=user_id,event_id=event.id,send_at=send_at,text=f'⏰ یادآوری Tikino: رویداد «{event.title}» {label} آغاز می‌شود.\nمکان: {event.location}'))

async def notify_waitlist_capacity(bot,session,event_id:int,capacity:int):
    rows=(await session.execute(select(WaitlistEntry).where(WaitlistEntry.event_id==event_id,WaitlistEntry.status==WaitlistStatus.WAITING).order_by(WaitlistEntry.id).limit(max(0,capacity)))).scalars().all()
    for row in rows:
        try:
            await bot.send_message(row.user_id,'🎟 ظرفیت رویدادی که منتظر آن بودید آزاد شد. برای خرید وارد بخش رویدادها شوید.')
            row.status=WaitlistStatus.NOTIFIED; row.notified_at=UTC(); row.expires_at=UTC()+timedelta(minutes=30)
        except Exception: pass
