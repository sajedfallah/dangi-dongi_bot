# Dongi — Telegram shared-expense platform

ربات مدیریت هزینه‌های مشترک، دونگ و تسویه بین دوستان، هم‌خانه‌ها، سفرها و گروه‌های کوچک.

## وضعیت فعلی
نسخه فعلی وارد فاز Telegram MVP شده و جریان اصلی استفاده از داخل تلگرام پیاده‌سازی شده است.

## قابلیت‌های فعلی
- ایجاد/بازیابی خودکار کاربر تلگرام
- ساخت حساب مشترک با واحد تومان (IRT)
- نمایش «حساب‌های من»
- ورود به هر حساب از منوی Inline
- لینک دعوت امضاشده برای جلوگیری از دستکاری شناسه حساب
- عضویت مستقیم از Telegram deep-link
- نمایش اعضای حساب
- ثبت هزینه مرحله‌ای با FSM
- پشتیبانی از اعداد فارسی/عربی/لاتین در مبلغ
- انتخاب پرداخت‌کننده از بین اعضا
- انتخاب چندنفره شرکت‌کنندگان در هر هزینه
- تقسیم مساوی با مدیریت دقیق اعشار
- تاریخچه ۲۰ هزینه آخر
- محاسبه مانده خالص هر عضو
- نمایش طلبکار/بدهکار
- پیشنهاد برنامه تسویه با کاهش تعداد انتقال‌ها
- ثبت تسویه توسط خود بدهکار
- کنترل دسترسی بات به حساب‌های عضو
- FastAPI + SQLAlchemy Async
- SQLite برای Development و PostgreSQL برای Production
- Docker / Docker Compose
- تست Unit برای Ledger و لینک دعوت
- GitHub Actions CI برای compile-check و pytest

## معماری
- `app/api`: API مشترک برای Telegram Bot / Mini App / Mobile
- `app/services`: منطق مالی و Ledger مستقل از UI
- `app/models`: مدل‌های دیتابیس
- `app/bot`: Telegram UX، FSM و deep-link
- `app/bot/security.py`: امضای لینک دعوت

## اجرای محلی
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
```

در `.env` حداقل این مقادیر را تنظیم کن:
```env
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN
APP_SECRET_KEY=USE_A_LONG_RANDOM_SECRET
```

Backend:
```bash
uvicorn app.main:app --reload
```

Telegram Bot:
```bash
python -m app.bot.main
```

API docs:
`http://127.0.0.1:8000/docs`

## تست
```bash
PYTHONPATH=. pytest -q
python -m compileall -q app tests
```

## اجرای Docker
```bash
docker compose up --build
```

## کارهای باقی‌مانده برای نسخه عمومی
- ویرایش/حذف هزینه + Audit Log
- نقش‌ها و Permission کامل owner/admin/member
- تقسیم نامساوی: درصدی، سهمی و مبلغ ثابت
- تأیید دوطرفه تسویه
- اعلان هوشمند اعضا پس از ثبت/ویرایش هزینه
- صفحه‌بندی تاریخچه
- دسته‌بندی و گزارش هزینه
- Migration رسمی با Alembic
- API authentication/Telegram WebApp auth
- Rate limiting و hardening عمومی API
- تست Integration و E2E
- Telegram Mini App
