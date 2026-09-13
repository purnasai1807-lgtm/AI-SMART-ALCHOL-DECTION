# Interlock  demonstrator

This repository includes the original TensorHub event and challenge features plus a secure, end-to-end alcohol-detection vehicle interlock demonstrator. The installable responsive PWA exposes versioned `/api/v1/interlock` APIs, SQL.js persistence, simulator/device HMAC attestation, nonce replay and timestamp freshness checks, authenticated roles, and append-only decisions/audit records.

## Interlock API

Vehicles start `LOCKED`. Authenticated members can create and list their vehicles (`POST/GET /api/v1/interlock/vehicles`). Technical Team or Admin operators pair a simulator (`POST /api/v1/interlock/devices`); the response contains the one-time demonstrator secret, which must be kept by the device. A device signs the canonical string
`deviceId.vehicleId.nonce.timestamp.reading` with HMAC-SHA256 (hex signature) and posts it to `POST /api/v1/interlock/attest` (the `/decision` alias is also supported). Timestamps must be within `ATTESTATION_MAX_AGE_MS` (default five minutes), and each nonce is single-use. Invalid signatures, stale messages, unknown devices, malformed payloads, and replayed nonces always produce a persisted `LOCKED` decision. A valid reading below `ALCOHOL_THRESHOLD` (default `0.02`) produces `UNLOCKED`; all decisions are queryable by the vehicle owner.

Device secrets are encrypted at rest with the session secret. Set a durable `SESSION_SECRET` and unique per-device secrets in production. This is a demonstrator contract, not a certified safety-critical automotive controller; use independent hardware safety validation before any real vehicle integration.

## Run locally

Requires Node.js 20+. Copy `.env.example` to `.env`, install dependencies, and start:

```sh
npm install
npm start
```

The app listens on `0.0.0.0` (not only localhost) and uses `PORT` (default `3000`). The first registered account is a normal `MEMBER`. Provision the Technical Team account through deployment secrets, never source control:

```sh
TECHNICAL_TEAM_EMAIL=team@example.com
TECHNICAL_TEAM_PASSWORD='<unique-password>'
```

On startup these variables create or promote that email to `TECHNICAL_TEAM`. The password is hashed with bcrypt and is never logged. Change it through your secret manager and restart the service. The browser exposes a restricted Technical Team console only after `/api/auth/me` confirms the role; server-side role checks remain authoritative.

## Internet-public production deployment

Use a managed Linux container host (Azure Container Apps, App Service, Fly.io, Render, or equivalent) behind its public HTTPS ingress. Build the image or deploy the Node service with `npm ci --omit=dev && npm start`, set `PORT` from the platform, and configure a custom domain with the platform's managed TLS certificate. Point the domain's DNS `A`/`CNAME` record to the platform ingress; do not expose SQLite files or the container directly to the internet.

Set `NODE_ENV=production`, a random `SESSION_SECRET` of at least 32 characters (retained across restarts), `APP_ORIGIN` to the HTTPS domain, and `TRUST_PROXY=1` only when the platform terminates TLS. Enforce HTTPS redirects at the ingress, restrict CORS to `APP_ORIGIN` if a separate frontend is introduced, configure backups, and use platform health checks against `/api/health`. Mutating API requests are same-origin protected and session cookies are HTTP-only, SameSite, and Secure in production.

SQLite with WAL is suitable for a single instance and modest write volume. For approximately 1,000 concurrent users, keep the stateless web process horizontally scalable but migrate the database to PostgreSQL (including sessions) before running multiple replicas; add a managed Redis cache/rate-limit store, CDN-cache public event GETs briefly, and use a queue-backed isolated worker for submissions. Add database connection pooling, monitoring, autoscaling on CPU/latency, and load-test the chosen SKU. The current repository does not provision cloud resources, DNS, TLS, PostgreSQL, Redis, or the untrusted-code worker, so deployment is not claimed complete.

## Coding worker boundary

`POST /api/challenges/:id/submissions` validates and stores source with `QUEUED` status. A separate worker must claim jobs, run them in disposable network-disabled containers or a sandbox with strict CPU/memory/time limits, write only `PASSED`/`FAILED`/`ERROR` status, and never share the web process or its filesystem. No endpoint in this repository executes submitted code.

## Operations and account modules

The server includes administrator-protected user/role management, moderation reports for events and challenges, append-only audit records for authentication and management actions, in-app notification records, and password-reset token contracts. Password reset requests intentionally return a development-only token when `NODE_ENV` is not `production`; production must connect this endpoint to a transactional email provider and must never expose tokens in HTTP responses. Email verification and MFA require an external identity/email service or an additional approved provider configuration and are not falsely marked as complete.

All mutating API routes require a same-origin `Origin`/`Referer` check, authenticated management routes enforce roles server-side, password-reset tokens are hashed and expire after 30 minutes, and changing a password invalidates existing sessions. The supplied Technical Team password is not present in this repository; rotate it before use.

## Checks

```sh
npm test
npm run lint
```

## FastAPI production foundation

The additive `services/api` package provides a SQLAlchemy-backed FastAPI
service for organizations, vehicles, drivers, devices, authentication, and
fail-secure safety decisions. It defaults to SQLite for the demo flow and
accepts PostgreSQL and Redis URLs in production. Start it with:

```sh
cd services/api
py -3 -m pip install -r requirements.txt
py -3 -m uvicorn app.main:app --reload
```

`docker compose up --build` runs the API with PostgreSQL and Redis without
changing or replacing the existing Node application. See
`shared/api-types.md`, `hardware/esp32/`, and `simulator/` for the device
boundary and signed-reading contract.
