# Interlock API

Run `uvicorn app.main:app --reload` from `services/api`. SQLite is the default demo database; configure `DATABASE_URL`, `REDIS_URL`, a strong `JWT_SECRET`, and a persistent Fernet `DEVICE_ENCRYPTION_KEY` for production. Device secrets are encrypted at rest and are never returned after registration. Self-service registration cannot choose an elevated role; the first local account is the bootstrap admin and subsequent accounts are drivers. Decisions are fail-secure: unknown devices, invalid signatures, stale timestamps, and nonce replays persist `LOCKED` plus an incident and audit record.

Users can enroll TOTP MFA with `POST /auth/mfa/enroll`, confirm it with
`POST /auth/mfa/verify`, and then provide the six-digit `mfa_code` (or `otp`)
to `POST /auth/login`. Organization-scoped live safety events are available
over `/ws/organizations/{organization_id}` using the JWT as a `token` query
parameter (or Bearer authorization header).

Production schema creation is disabled with AUTO_CREATE_SCHEMA=false; run alembic upgrade head before starting the API.
