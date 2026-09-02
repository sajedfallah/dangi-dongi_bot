# Dongi — Telegram shared-expense platform

ربات مدیریت هزینه‌های مشترک، دونگ و تسویه بین دوستان، هم‌خانه‌ها، سفرها و گروه‌های کوچک.

## وضعیت فعلی
نسخه فعلی در فاز Telegram MVP قرار دارد و جریان اصلی استفاده از داخل تلگرام پیاده‌سازی شده است. لایه RBAC، Audit Log، حذف کنترل‌شده هزینه و Migration رسمی دیتابیس نیز اضافه شده‌اند.

## قابلیت‌های فعلی
- ایجاد/بازیابی خودکار کاربر تلگرام
- ساخت حساب مشترک با واحد تومان (IRT)
- نمایش «حساب‌های من» و ورود به حساب
- لینک دعوت امضاشده و عضویت با Telegram deep-link
- نمایش اعضا و نقش‌های owner/admin/member
- ثبت هزینه مرحله‌ای با FSM
- ثبت مالک واقعی رکورد هزینه (`created_by_user_id`)
- پشتیبانی از اعداد فارسی/عربی/لاتین
- انتخاب پرداخت‌کننده و شرکت‌کنندگان هزینه
- تقسیم مساوی با مدیریت دقیق اعشار
- تاریخچه ۲۰ هزینه آخر
- حذف هزینه با تأیید از داخل Telegram
- عضو عادی فقط هزینه ثبت‌شده توسط خودش را مدیریت می‌کند
- Owner/Admin امکان مدیریت همه هزینه‌ها را دارند
- API ویرایش کامل هزینه با محاسبه مجدد سهم‌ها
- Owner می‌تواند نقش member/admin را تغییر دهد
- Audit Log برای ایجاد/ویرایش/حذف هزینه، تسویه، عضویت و تغییر نقش
- Audit Log فقط برای Owner/Admin قابل مشاهده است
- محاسبه مانده خالص هر عضو
- پیشنهاد برنامه تسویه با کاهش تعداد انتقال‌ها
- ثبت تسویه فقط توسط خود بدهکار
- FastAPI + SQLAlchemy Async
- SQLite برای Development و PostgreSQL برای Production
- Alembic migrations برای ارتقای schema
- Docker / Docker Compose
- Unit + Integration tests
- GitHub Actions CI برای compile-check و pytest

## معماری
- `app/api`: API مشترک برای Telegram Bot / Mini App / Mobile
- `app/services`: منطق مالی و Ledger مستقل از UI
- `app/models`: مدل‌های دیتابیس
- `app/bot`: Telegram UX، FSM و deep-link
- `app/bot/security.py`: امضای لینک دعوت
- `migrations`: نسخه‌بندی و ارتقای دیتابیس با Alembic

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

برای دیتابیس تازه:
```bash
alembic upgrade head
```

اگر یک دیتابیس قدیمی v0.1 داری که قبل از Alembic ساخته شده، ابتدا از آن Backup بگیر، سپس وضعیت آن را روی migration اولیه stamp کن و ارتقا بده:
```bash
alembic stamp 0001_initial
alembic upgrade head
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
python -m compileall -q app tests migrations
```

## اجرای Docker
Docker قبل از اجرای API به‌صورت خودکار `alembic upgrade head` را اجرا می‌کند.

```bash
docker compose up --build
```

## کارهای باقی‌مانده برای نسخه عمومی
- UI ویرایش هزینه داخل خود Telegram Bot
- تقسیم نامساوی: درصدی، سهمی و مبلغ ثابت
- تأیید دوطرفه تسویه
- اعلان هوشمند اعضا پس از ثبت/ویرایش هزینه
- صفحه‌بندی تاریخچه
- دسته‌بندی و گزارش هزینه
- Telegram WebApp/API authentication واقعی؛ `actor_user_id` فعلی جای Authentication را نمی‌گیرد
- Rate limiting و hardening عمومی API
- E2E تست واقعی Telegram
- Telegram Mini App
