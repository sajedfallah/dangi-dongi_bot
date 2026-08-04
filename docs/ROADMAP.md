# Roadmap

## v0.1.0 — stabilized baseline
- repair event administration and public event routing;
- Docker/PostgreSQL/Redis/Alembic boot path;
- security and transaction baseline.

## v0.2.0 — test coverage
- repository/service unit tests;
- integration tests with PostgreSQL and Redis;
- purchase, refund, wallet and withdrawal scenario tests.

## v0.3.0 — payments and operations
- payment gateway adapter interface;
- idempotent webhook processing;
- retry/outbox worker;
- backup and monitoring documentation.

## v0.4.0 — multi-admin RBAC
- owner, finance, support and checker roles;
- permission matrix and audit viewer.

## v0.5.0 — commercial readiness
- organizer tenancy;
- plans, quotas and commission accounting;
- referral/affiliate tracking.

## v1.0.0 — production release
- complete automated test suite;
- documented deployment and rollback;
- security review;
- stable database migrations;
- versioned API contract and release notes.
