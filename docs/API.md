# API surface

The FastAPI service is the production-oriented API foundation. OpenAPI is
available at `/docs` and `/openapi.json` when it is running.

## Authentication

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh` (rotating, one-use refresh tokens)

Use `Authorization: Bearer <access_token>`. Self-registration cannot select a
privileged role. The first local account is a bootstrap administrator; later
accounts are drivers.

## Safety and devices

- `POST /organizations`, `POST /vehicles`, `POST /drivers`
- `POST /devices`, `POST /devices/{id}/heartbeat`, `GET /devices/{id}/status`
- `POST /devices/{id}/revoke`
- `POST /decisions` for signed device attestations
- `POST /sensor-tests` for validated multi-sample simulator/operator tests
- `GET /vehicles/{id}/status`, `/decisions`, and `/gps`

Unsafe, invalid, stale, replayed, revoked, or unavailable inputs remain
fail-secure and create an auditable blocked/error path.

## Operations

- `GET /incidents`, `POST /incidents/{id}/acknowledge`
- `GET /notifications`, `POST /notifications/{id}/read`
- `POST /notifications`
- `POST /gps`
- `GET /analytics/overview`
- `GET /reports/decisions.csv`
- `GET /audit`
- `GET /health`, `GET /readiness`

