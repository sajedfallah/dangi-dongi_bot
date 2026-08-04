from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User

async def get_user(session: AsyncSession, telegram_id: int):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()

async def create_user(session: AsyncSession, telegram_id: int, first_name: str, last_name: str, phone: str):
    new_user = User(telegram_id=telegram_id, first_name=first_name, last_name=last_name, phone=phone, status="PENDING_APPROVAL")
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user

async def update_user_status(session: AsyncSession, telegram_id: int, new_status: str):
    user = await get_user(session, telegram_id)
    if user:
        user.status = new_status
        await session.commit()
        return True
    return False