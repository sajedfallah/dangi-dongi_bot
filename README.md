# Dongi — Telegram shared-expense platform (MVP)

نسخه اولیه یک هسته قابل توسعه برای مدیریت هزینه‌های مشترک است.

## قابلیت‌های فعلی
- ایجاد/بازیابی کاربر تلگرام
- ایجاد حساب/گروه
- افزودن عضو
- ثبت هزینه
- تقسیم مساوی هزینه بین اعضای انتخاب‌شده
- محاسبه مانده هر عضو
- پیشنهاد برنامه تسویه با انتقال‌های حداقلی
- ثبت تسویه
- اسکلت Telegram Bot با aiogram
- FastAPI و دیتابیس async
- SQLite برای توسعه و PostgreSQL برای استقرار

## اجرا در حالت توسعه
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs:
`http://127.0.0.1:8000/docs`

## اجرای بات
توکن BotFather را در `.env` قرار بده:
```env
TELEGRAM_BOT_TOKEN=...
```
سپس:
```bash
python -m app.bot.main
```

## اجرای تست
```bash
PYTHONPATH=. pytest -q
```

## معماری
- `app/api`: API مشترک برای Bot/Mini App/Mobile
- `app/services`: منطق محاسبات مالی مستقل از UI
- `app/models`: مدل دیتابیس
- `app/bot`: رابط Telegram

## برنامه نسخه 0.2
- لیست حساب‌های کاربر
- دعوت عضو با لینک امن
- ثبت کامل هزینه از داخل Bot با FSM و inline keyboard
- ویرایش/حذف هزینه و Audit Log
- تقسیم درصدی، سهمی و مبلغ ثابت
- واحد پول و گردکردن قابل تنظیم
- گزارش و تاریخچه
- تسویه با تأیید دوطرفه
- RBAC مدیر/عضو
