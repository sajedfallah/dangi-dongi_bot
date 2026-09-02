# dangi-dongi | دنگی - دونگی

ربات مدیریت هزینه‌های مشترک، دونگ و تسویه بین دوستان، هم‌خانه‌ها، سفرها و گروه‌های کوچک.

## وضعیت فعلی
نسخه فعلی در فاز Telegram MVP قرار دارد. هسته مالی، RBAC، Audit Log، Migration دیتابیس، تقسیم حرفه‌ای هزینه، ویرایش هزینه، تسویه دوطرفه و اعلان اعضای مرتبط پیاده‌سازی شده‌اند.

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
- اعلان ثبت/ویرایش هزینه برای اعضای مرتبط دارای Telegram ID
- عضو عادی فقط هزینه ثبت‌شده توسط خودش را مدیریت می‌کند
- Owner/Admin امکان مدیریت همه هزینه‌ها را دارند
- Owner می‌تواند نقش member/admin را تغییر دهد
- Audit Log برای ایجاد/ویرایش/حذف هزینه، درخواست/تأیید/رد تسویه، عضویت و تغییر نقش
- Audit Log فقط برای Owner/Admin قابل مشاهده است
- محاسبه مانده خالص هر عضو
- پیشنهاد برنامه تسویه با کاهش تعداد انتقال‌ها
- تسویه دوطرفه: بدهکار درخواست ثبت می‌کند و طلبکار باید دریافت را تأیید کند
- Settlementهای `pending` و `rejected` هیچ اثری روی Balance ندارند
- فقط Settlement با وضعیت `confirmed` وارد محاسبات مانده می‌شود
- اعلان مستقیم درخواست تسویه به طلبکار با دکمه‌های تأیید/رد
- بخش «تسویه‌های منتظر» داخل Telegram
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
- `app/bot`: Telegram UX، FSM، اعلان‌ها و deep-link
- `app/bot/security.py`: امضای لینک دعوت
- `migrations`: نسخه‌بندی و ارتقای دیتابیس با Alembic

## Migration
برای دیتابیس تازه یا ارتقای schema:
```bash
alembic upgrade head
```

Migration `0004_two_party_settlements` وضعیت `pending/confirmed/rejected` و زمان پاسخ تسویه را اضافه می‌کند. Settlementهای قدیمی هنگام ارتقا `confirmed` باقی می‌مانند تا رفتار مالی قبلی تغییر نکند.

## اجرا
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

برای Bot:
```bash
python -m app.bot.main
```

## تست
```bash
PYTHONPATH=. pytest -q
python -m compileall -q app tests migrations
```

## Docker
```bash
docker compose up --build
```

## کارهای باقی‌مانده برای نسخه عمومی
- Telegram WebApp/API authentication واقعی؛ `actor_user_id` فعلی Authentication محسوب نمی‌شود
- Rate limiting و hardening عمومی API
- صفحه‌بندی تاریخچه و گزارش‌های دسته‌بندی‌شده
- E2E تست واقعی Telegram با چند حساب کاربری
- مدیریت Notification preferences / mute
- Telegram Mini App
