# Tikino secure deployment
1. Copy `.env.example` to `.env` and insert a newly rotated bot token and webhook secret.
2. Never commit `.env`, database files, receipts, or virtual environments.
3. Run `docker compose up -d --build`; Alembic runs before the bot starts.
4. Event date input format is `YYYY-MM-DD HH:MM`; refund deadline defaults to 24 hours before start.
5. Admin access is based on `ADMIN_IDS`; all admin-only routers are centrally filtered.
6. PostgreSQL handles atomic capacity and promo reservations; Redis persists FSM state.
7. Review `audit_logs` and `financial_ledger` for administrative and financial operations.
