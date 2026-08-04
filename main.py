import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from sqlalchemy import select

import models.commerce  # noqa: F401
from config import BOT_TOKEN, settings
from database.database import AsyncSessionLocal, engine, init_db
from handlers import (
    admin,
    admin_event,
    my_tickets,
    phase_one,
    public_events,
    registration,
    start,
    user_event,
    user_invoices,
    user_panel,
)
from models.commerce import ScheduledNotification, WaitlistEntry
from models.enums import NotificationStatus, OrderStatus, WaitlistStatus
from models.event import Event
from models.ticket import Order
from services.secure_transactions import release_order

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def expired_order_worker(bot: Bot) -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as session:
                order_ids = (await session.execute(
                    select(Order.id).where(Order.status == OrderStatus.AWAITING_PAYMENT, Order.expires_at <= now)
                )).scalars().all()
            for order_id in order_ids:
                async with AsyncSessionLocal() as session:
                    order = await release_order(session, order_id=order_id, new_status=OrderStatus.EXPIRED, actor_id=0)
                if order:
                    with suppress(Exception):
                        await bot.send_message(order.user_id, f"❌ فاکتور #{order.id} منقضی شد و ظرفیت آزاد گردید.")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("expired-order worker failed")
        await asyncio.sleep(60)


async def notification_worker(bot: Bot) -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(
                    select(ScheduledNotification)
                    .where(ScheduledNotification.status == NotificationStatus.PENDING, ScheduledNotification.send_at <= now)
                    .limit(100)
                )).scalars().all()
                for row in rows:
                    try:
                        await bot.send_message(row.user_id, row.text)
                        row.status = NotificationStatus.SENT
                    except Exception as exc:
                        row.attempts += 1
                        row.last_error = str(exc)[:1000]
                        if row.attempts >= 5:
                            row.status = NotificationStatus.FAILED
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("notification worker failed")
        await asyncio.sleep(60)


async def main() -> None:
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    storage = RedisStorage.from_url(settings.redis_url)
    dispatcher = Dispatcher(storage=storage)

    for module in (
        start,
        registration,
        admin,
        admin_event,
        public_events,
        user_event,
        user_panel,
        my_tickets,
        user_invoices,
        phase_one,
    ):
        dispatcher.include_router(module.router)

    tasks = [
        asyncio.create_task(expired_order_worker(bot)),
        asyncio.create_task(notification_worker(bot)),
    ]
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await storage.close()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
