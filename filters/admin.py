from aiogram.filters import BaseFilter
from config import ADMIN_IDS
class AdminFilter(BaseFilter):
    async def __call__(self, event) -> bool:
        user = getattr(event, 'from_user', None)
        return bool(user and user.id in ADMIN_IDS)
