# dangi-dongi | دنگی - دونگی

ربات مدیریت هزینه‌های مشترک، دونگ و تسویه بین دوستان، هم‌خانه‌ها، سفرها و گروه‌های کوچک.

## وضعیت فعلی
نسخه فعلی در فاز Telegram MVP قرار دارد. هسته مالی، RBAC، Audit Log، Migration دیتابیس، تقسیم حرفه‌ای هزینه و ویرایش هزینه داخل تلگرام پیاده‌سازی شده‌اند.

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
- عضو عادی فقط هزینه ثبت‌شده توسط خودش را مدیریت می‌کند
- Owner/Admin امکان مدیریت همه هزینه‌ها را دارند
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

## Migration
برای دیتابیس تازه یا ارتقای schema:
```bash
alembic upgrade head
```

اگر دیتابیس قدیمی قبل از Alembic داری، ابتدا Backup بگیر و مطابق نسخه موجود stamp/upgrade کن.

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
- تأیید دوطرفه تسویه
- اعلان هوشمند اعضا بعد از ثبت/ویرایش هزینه
- صفحه‌بندی تاریخچه و گزارش‌ها
- Telegram WebApp/API authentication واقعی
- Rate limiting و hardening عمومی API
- E2E تست واقعی Telegram
- Telegram Mini App
