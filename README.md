# dangi-dongi | دنگی - دونگی

ربات مدیریت هزینه‌های مشترک، دونگ و تسویه بین دوستان، هم‌خانه‌ها، سفرها و گروه‌های کوچک.

## وضعیت فعلی
نسخه فعلی در فاز Telegram MVP قرار دارد. هسته مالی، RBAC، Audit Log، Migration دیتابیس، تقسیم حرفه‌ای هزینه، ویرایش هزینه، تسویه دوطرفه، اعلان اعضا و hardening اولیه API پیاده‌سازی شده‌اند.

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
- چهار مدل تقسیم هزینه: مساوی، درصدی، سهمی/وزنی و مبلغ ثابت
- کنترل جمع دقیق سهم‌ها و مدیریت rounding
- تاریخچه ۲۰ هزینه آخر
- ویرایش مبلغ، عنوان و مدل تقسیم از داخل Telegram
- حذف هزینه با تأیید
- اعلان ثبت/ویرایش هزینه برای اعضای مرتبط
- Owner/Admin و RBAC در سطح Backend
- Audit Log برای عملیات حساس
- محاسبه مانده خالص هر عضو
- پیشنهاد برنامه تسویه با کاهش تعداد انتقال‌ها
- تسویه دوطرفه با وضعیت `pending/confirmed/rejected`
- فقط Settlement تأییدشده وارد Balance می‌شود
- اعلان مستقیم درخواست تسویه به طلبکار با دکمه تأیید/رد
- بخش «تسویه‌های منتظر» داخل Telegram
- FastAPI + SQLAlchemy Async
- SQLite برای Development و PostgreSQL برای Production
- Alembic migrations برای ارتقای schema
- Docker / Docker Compose
- Unit + Integration + authenticated multi-user E2E tests
- GitHub Actions CI برای compile-check و pytest

## امنیت API
- Bot برای ارتباط با Backend از `SERVICE_API_TOKEN` مستقل استفاده می‌کند.
- APIهای `/api/v1/*` بدون احراز هویت در حالت عادی پاسخ `401` می‌دهند.
- Telegram Mini App می‌تواند `X-Telegram-Init-Data` اصلی Telegram را ارسال کند؛ امضای HMAC، `auth_date` و هویت User روی Backend اعتبارسنجی می‌شوند.
- هویت Telegram به User داخلی bind می‌شود؛ جعل `actor_user_id`، `owner_user_id` یا `user_id` کاربر دیگر با `403` رد می‌شود.
- دسترسی به Group برای درخواست‌های Telegram با membership واقعی کنترل می‌شود.
- Rate limiting برای Clientهای غیرسرویسی فعال است و پاسخ `429` همراه `Retry-After` برمی‌گرداند.
- Headerهای `nosniff`, `DENY`, `no-referrer` و `no-store` روی پاسخ‌های API اعمال می‌شوند.
- در Production اجرای برنامه با Secretهای پیش‌فرض متوقف می‌شود.
- Swagger `/docs` در Production غیرفعال است.
- Docker API را فقط روی `127.0.0.1:8000` publish می‌کند و Bot از شبکه داخلی Compose به آن متصل می‌شود.
- `run_bot.py` قبل از import کردن Bot، runtime امن Bot را فعال می‌کند تا Service Token فقط در فرایند واقعی Bot تزریق شود و تست‌ها یا Backend تحت تأثیر قرار نگیرند.

## تنظیمات ضروری
فایل `.env` باید حداقل مقادیر زیر را داشته باشد:
```env
ENV=production
TELEGRAM_BOT_TOKEN=...
APP_SECRET_KEY=...
SERVICE_API_TOKEN=...
POSTGRES_PASSWORD=...
API_AUTH_REQUIRED=true
```

`APP_SECRET_KEY` و `SERVICE_API_TOKEN` باید دو مقدار تصادفی، بلند و متفاوت باشند.

## معماری
- `app/api`: API مشترک برای Telegram Bot / Mini App / Mobile
- `app/services`: منطق مالی و Ledger مستقل از UI
- `app/models`: مدل‌های دیتابیس
- `app/bot`: Telegram UX، FSM، اعلان‌ها و deep-link
- `app/core/api_security.py`: اعتبارسنجی Service Token و Telegram initData
- `app/core/middleware.py`: Identity binding، Rate Limit و Security Headers
- `run_bot.py`: launcher امن فرایند Bot
- `migrations`: نسخه‌بندی و ارتقای دیتابیس با Alembic

## Migration
برای دیتابیس تازه یا ارتقای schema:
```bash
alembic upgrade head
```

Migration `0004_two_party_settlements` وضعیت `pending/confirmed/rejected` و زمان پاسخ تسویه را اضافه می‌کند. Settlementهای قدیمی هنگام ارتقا `confirmed` باقی می‌مانند تا رفتار مالی قبلی تغییر نکند.

## اجرای توسعه
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

برای Bot در یک ترمینال دیگر:
```bash
python run_bot.py
```

## تست
```bash
PYTHONPATH=. pytest -q
python -m compileall -q app tests migrations
```

## Docker Production
پس از تنظیم `.env`:
```bash
docker compose up --build -d
```

API و Bot هر دو توسط Compose اجرا می‌شوند و از `SERVICE_API_TOKEN` یکسان برای ارتباط داخلی استفاده می‌کنند.

## کارهای باقی‌مانده برای نسخه عمومی
- E2E واقعی با دو حساب Telegram و BotFather روی محیط Staging
- صفحه‌بندی تاریخچه و گزارش‌های دسته‌بندی‌شده
- Notification preferences / mute
- Reverse proxy + TLS برای Mini App/API عمومی
- Telegram Mini App
