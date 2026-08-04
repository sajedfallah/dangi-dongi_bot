import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _ids(value: str) -> frozenset[int]:
    return frozenset(int(x.strip()) for x in value.split(',') if x.strip().isdigit())

@dataclass(frozen=True)
class Settings:
    bot_token: str = os.getenv('BOT_TOKEN', '')
    admin_ids: frozenset[int] = _ids(os.getenv('ADMIN_IDS', os.getenv('ADMIN_ID', '')))
    database_url: str = os.getenv('DATABASE_URL', os.getenv('DB_URL', 'postgresql+asyncpg://tikino:tikino@localhost:5432/tikino'))
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    sheets_webhook_url: str = os.getenv('GOOGLE_SHEETS_WEBHOOK_URL', '')
    sheets_webhook_secret: str = os.getenv('GOOGLE_SHEETS_WEBHOOK_SECRET', '')
    event_timezone: str = os.getenv('EVENT_TIMEZONE', 'Asia/Tehran')
    payment_card_number: str = os.getenv('PAYMENT_CARD_NUMBER', '')
    order_expiry_hours: int = int(os.getenv('ORDER_EXPIRY_HOURS', '5'))
    default_refund_cutoff_hours: int = int(os.getenv('DEFAULT_REFUND_CUTOFF_HOURS', '24'))
    qr_signing_secret: str = os.getenv('QR_SIGNING_SECRET', '')
    withdrawal_min_amount: int = int(os.getenv('WITHDRAWAL_MIN_AMOUNT', '10000'))

settings = Settings()
if not settings.bot_token:
    raise RuntimeError('BOT_TOKEN is required')
if not settings.admin_ids:
    raise RuntimeError('ADMIN_IDS is required')
if len(settings.qr_signing_secret) < 32:
    raise RuntimeError('QR_SIGNING_SECRET must be at least 32 characters')

BOT_TOKEN = settings.bot_token
ADMIN_IDS = settings.admin_ids
ADMIN_ID = min(settings.admin_ids)
DB_URL = settings.database_url
