# Tikino Telegram Bot

Tikino is an event ticketing Telegram bot built with Aiogram 3, PostgreSQL, Redis, SQLAlchemy 2 and Alembic.

## Current status

This repository is the stabilized development baseline toward **v1.0.0**. The current milestone is **v0.1.0** and includes:

- user registration and admin approval;
- event creation and public event listing;
- ticket types, promo codes and capacity management;
- atomic order reservation, receipt review and ticket issuing;
- signed QR tickets and check-in;
- refunds to wallet and full-balance withdrawal requests;
- waitlist and scheduled notifications;
- PostgreSQL migrations and Redis FSM storage;
- Docker Compose development deployment.

## Quick start

```bash
cp .env.example .env
# Fill BOT_TOKEN, ADMIN_IDS, POSTGRES_PASSWORD and QR_SIGNING_SECRET
docker compose up -d --build
docker compose logs -f bot
```

## Important commands

```bash
docker compose ps
docker compose exec bot alembic current
docker compose exec bot alembic upgrade head
docker compose exec redis redis-cli FLUSHDB
docker compose down
docker compose down -v  # destroys local database data
```

## Security

Never commit `.env`, bot tokens, database dumps, payment receipts or production secrets. Rotate any token that has previously been shared.

## Roadmap to v1.0.0

See [docs/ROADMAP.md](docs/ROADMAP.md).
