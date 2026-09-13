# Smart Vehicle Safety Architecture

The repository contains two compatible surfaces:

```text
ESP32/device adapter or simulator
        | signed readings, heartbeat, GPS
        v
FastAPI safety service ---> PostgreSQL
        |                  Redis-ready event boundary
        +--> decisions, incidents, notifications, audit, analytics
        v
Web/PWA and future Flutter clients
```

The deterministic safety rule is authoritative. AI/ML may provide anomaly or
confidence signals later, but it must never override an unsafe sensor result,
missing attestation, stale data, revoked device, or offline fail-safe policy.
The web service does not directly energize an immobilizer; certified in-vehicle
hardware must enforce that boundary.

## Local services

- Existing Node/PWA: `npm.cmd start`
- FastAPI: `cd services/api; py -3 -m pip install -r requirements.txt; py -3 -m uvicorn app.main:app`
- PostgreSQL and Redis: `docker compose up --build`
- Simulator contract: `simulator/README.md`

