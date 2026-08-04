# Tikino Phase One

Implemented:
- HMAC-signed anti-tamper ticket QR tokens and atomic check-in.
- Wallet with immutable transaction history.
- Refund-to-wallet workflow.
- Full-balance withdrawal requests, balance locking, admin rejection/release, payment receipt delivery.
- Admin live dashboard and CSV/XLSX/PDF financial exports.
- Waitlist registration and capacity notifications.
- 24-hour and 3-hour event reminders persisted in PostgreSQL.
- PostgreSQL/Alembic and Redis FSM integration retained.

## Important production settings
Set a unique `QR_SIGNING_SECRET` of at least 32 random characters. Never rotate it without a migration plan because existing QR codes will stop validating.

Run migrations before starting:

```bash
alembic upgrade head
```
