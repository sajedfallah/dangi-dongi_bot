# dangi-dongi | دنگی - دونگی

ربات مدیریت هزینه‌های مشترک، دونگ، بدهی و تسویه بین دوستان، سفرها، هم‌خانه‌ها و گروه‌های کوچک.

## نسخه فعلی
`v0.4.0` — Telegram MVP نهایی برای تست لوکال.

## قابلیت‌های اصلی
- داشبورد شخصی مستقل برای هر کاربر
- ساخت چند حساب و عضویت هم‌زمان در حساب‌های دیگر
- نقش‌های owner / admin / member
- لینک دعوت امن و Deep Link تلگرام
- آرشیو و بازگردانی حساب بدون حذف داده
- ثبت هزینه با اعداد فارسی/عربی/لاتین
- دسته‌بندی هزینه: خورد و خوراک، رفت‌وآمد، اقامت، خرید، تفریح، سوخت و سایر
- چهار مدل تقسیم: مساوی، درصدی، سهمی/وزنی و مبلغ ثابت
- تاریخچه، ویرایش مبلغ/عنوان و حذف هزینه با کنترل دسترسی
- گزارش بدهکاران / بستانکاران
- گزارش کلی هزینه‌ها و تفکیک بر اساس دسته‌بندی
- موتور Simplify Debt برای کاهش تعداد انتقال‌ها
- اطلاعات پرداخت شخصی: بانک، صاحب حساب، شماره کارت، شبا و شماره حساب
- نمایش اطلاعات پرداخت به‌صورت قابل کپی داخل Telegram
- تسویه دوطرفه با pending / confirmed / rejected
- ارسال رسید پرداخت به‌صورت اختیاری (عکس یا فایل)
- تغییر Balance فقط بعد از تأیید بستانکار
- اعلان خودکار تأیید/رد برای بدهکار
- تشخیص صفر شدن کامل حساب و «یک تسویه تا پایان»
- Reminder خودکار بدهی با فاصله حداقل 24 ساعت
- Reminder دستی از پنل حساب
- امکان روشن/خاموش کردن Reminder در تنظیمات شخصی
- اعلان‌های داخل داشبورد
- RBAC + Audit Log
- FastAPI + SQLAlchemy Async
- SQLite برای Development و PostgreSQL برای Production
- Alembic migrations
- Docker / Docker Compose
- API Authentication، Telegram initData validation و Rate Limiting
- GitHub Actions CI برای compile-check و pytest

## Migration جدید v0.4
Migration زیر اطلاعات پرداخت، رسید تسویه و وضعیت Reminder را اضافه می‌کند:

```text
0006_payments_receipts_reminders
```

قبل از اجرای Bot بعد از Pull حتماً اجرا کن:

```bash
alembic upgrade head
```

## تنظیمات لوکال ویندوز
فایل `.env` در ریشه پروژه باید حداقل شامل موارد زیر باشد:

```env
APP_NAME=dangi-dongi
ENV=development
DATABASE_URL=sqlite+aiosqlite:///./dongi.db
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN
API_BASE_URL=http://127.0.0.1:8000
APP_SECRET_KEY=YOUR_RANDOM_SECRET
SERVICE_API_TOKEN=YOUR_OTHER_RANDOM_SECRET
API_AUTH_REQUIRED=true
TELEGRAM_INIT_DATA_MAX_AGE_SECONDS=86400
RATE_LIMIT_REQUESTS=120
RATE_LIMIT_WINDOW_SECONDS=60
```

`APP_SECRET_KEY` و `SERVICE_API_TOKEN` باید بلند، تصادفی و متفاوت باشند. `.env` را Commit نکن.

## اجرای لوکال روی Windows
CMD اول — Backend:

```bat
cd /d "C:\Users\STOCK LAND\tikino-telegram-bot"
.venv\Scripts\activate
git pull
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health Check:

```bat
curl http://127.0.0.1:8000/health
```

خروجی مورد انتظار:

```json
{"status":"ok","service":"dangi-dongi","version":"0.4.0"}
```

CMD دوم — Telegram Bot:

```bat
cd /d "C:\Users\STOCK LAND\tikino-telegram-bot"
.venv\Scripts\activate
python run_bot.py
```

سپس در Telegram دستور `/start` را اجرا کن.

## منوی اصلی v0.4
- ➕ حساب جدید
- 📂 حساب‌های من
- 🔔 اعلان‌ها
- ⚙️ تنظیمات من
- 🗄 آرشیو
- ❓ راهنما

## منوی هر حساب
- 💸 ثبت هزینه
- 📊 گزارش‌ها
- 💳 تسویه
- ⏳ منتظر تأیید
- 🔔 یادآوری بدهی
- 📜 تاریخچه
- 👥 اعضا
- 🔗 دعوت عضو
- 🗄 آرشیو حساب

## منطق تسویه
1. بدهکار وارد «💳 تسویه» می‌شود.
2. اطلاعات پرداخت بستانکار را می‌بیند.
3. «پرداخت کردم» را می‌زند.
4. می‌تواند رسید را اختیاری ارسال کند یا بدون رسید ادامه دهد.
5. بستانکار پیام تأیید/رد دریافت می‌کند.
6. تا قبل از تأیید، Balance تغییر نمی‌کند.
7. بعد از تأیید، Settlement وارد Ledger می‌شود و بدهکار پیام تأیید دریافت می‌کند.

## Reminder خودکار
Bot یک Task داخلی دارد که وضعیت بدهی‌ها را بررسی می‌کند. برای هر رابطه بدهکار/بستانکار، Reminder خودکار حداکثر یک بار در 24 ساعت ارسال می‌شود. کاربر می‌تواند Reminder شخصی را از «⚙️ تنظیمات من» خاموش کند. مدیر/عضو حساب نیز می‌تواند از دکمه «🔔 یادآوری بدهی» Reminder دستی ارسال کند.

## تست

```bat
python -m compileall -q app tests migrations
pytest -q
```

## معماری
- `app/api/routes.py`: هسته حساب، هزینه، Ledger و Settlement
- `app/api/dashboard.py`: داشبورد شخصی، نقش‌ها و آرشیو
- `app/api/product.py`: گزارش‌ها، اطلاعات پرداخت، رسید و Reminder
- `app/bot/final_main.py`: رابط نهایی Telegram v0.4
- `app/services/ledger.py`: موتور مالی مستقل از UI
- `app/core`: Security / Auth / Rate Limit
- `migrations`: نسخه‌بندی دیتابیس
- `run_bot.py`: Launcher نسخه نهایی Bot

## Production
پس از تنظیم Secretهای Production و PostgreSQL:

```bash
docker compose up --build -d
```

قبل از انتشار عمومی، تست واقعی چندکاربره و بررسی UX در Staging الزامی است.
