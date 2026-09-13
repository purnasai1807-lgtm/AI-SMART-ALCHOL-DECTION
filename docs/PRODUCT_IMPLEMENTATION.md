# AI Smart Alcohol Detection Product

This repository contains a complete **software product and bench-hardware
reference product** for an alcohol-detection vehicle interlock workflow.
The system is fail-secure: only a fresh, authenticated, valid negative test can
produce an allow decision. Missing, stale, replayed, tampered, inconsistent,
positive, or unavailable readings remain blocked or error states.

## Product modules

| Module | Location | Product responsibility |
|---|---|---|
| Operator PWA | `public/`, `server.js` | Browser fleet/interlock workflows and legacy API |
| Safety API | `services/api/` | Auth, RBAC, tenancy, devices, decisions, incidents, GPS, reports |
| AI engine | `services/ai-engine/` | Advisory features and anomaly metadata; never controls safety |
| Notification service | `services/notification-service/` | Durable outbox and retrying provider worker |
| Device simulator | `simulator/` | Signed end-to-end device contract testing |
| ESP32 firmware | `hardware/esp32/` | Bench sensor state machine and isolated output reference |
| Database migrations | `services/api/alembic/` | Reviewed production schema lifecycle |
| Deployment | `docker-compose.yml`, `Dockerfile` | Local multi-service runtime foundation |

## Start the complete local product

### Node/PWA

```sh
npm ci
npm start
```

Open `http://localhost:3000`.

### FastAPI safety platform

```sh
cd services/api
py -3 -m pip install -r requirements.txt
py -3 -m uvicorn app.main:app --reload --port 8000
```

For production-like startup, configure `DATABASE_URL`, `JWT_SECRET`,
`DEVICE_ENCRYPTION_KEY`, `CORS_ORIGINS`, and `AUTO_CREATE_SCHEMA=false`, then
run:

```sh
alembic upgrade head
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### All containerized services

```sh
docker compose up --build
```

This starts PostgreSQL, Redis, the safety API, advisory AI service, and
notification API. Run the notification worker separately in its service
environment:

```sh
cd services/notification-service
py -3 -m app.worker
```

Email, SMS, and push delivery require an approved provider adapter and explicit
provider configuration. The worker never reports delivery success when a
provider is not configured.

## End-to-end acceptance flow

1. Register the first local account; it becomes the bootstrap administrator.
2. Create an organization, vehicle, and device through the API.
3. Keep the generated device secret in a secret manager.
4. Generate a signed simulator reading:

   ```sh
   py -3 simulator/device_simulator.py `
     --device-id DEVICE_ID `
     --vehicle-id VEHICLE_ID `
     --secret PROVISIONED_SECRET `
     --reading 0.01
   ```

5. Submit the signed payload to `/decisions`.
6. Verify that a valid negative reading produces `UNLOCKED`.
7. Submit a positive reading and verify `LOCKED`, incident, notification, and
   vehicle status update.
8. Replay the same nonce and verify another `LOCKED` decision.
9. Send a stale, malformed, or invalid-signature payload and verify it remains
   fail-secure.
10. Subscribe to `/ws/organizations/{organization_id}` and verify live
    decision events are delivered only to users in that organization.

## Hardware product workflow

Follow `docs/HARDWARE_CONFIGURATION.md` for the bill of materials, wiring,
device identity configuration, PlatformIO build, flashing, serial checks, and
bench acceptance tests. The firmware provides:

- Sensor warm-up and self-test
- Five-sample consistency validation
- `BOOTING`, `SELF_TEST`, `READY`, `TESTING`, `ANALYZING`, `SAFE`, `BLOCKED`,
  and `ERROR` states
- Watchdog recovery
- JSON heartbeat and sensor events
- A momentary local test button
- Fail-closed isolated dummy-load output

## Security and operations

Implemented controls include encrypted device secrets, HMAC device
attestation, nonce replay protection, timestamp freshness, PBKDF2 password
hashing, short-lived JWT access tokens, rotating refresh tokens, TOTP MFA,
role-based authorization, organization isolation, audit records, request
hardening, durable notification retries, and migration-controlled schemas.

Review `docs/SECURITY.md`, `docs/OPERATIONS.md`, `docs/DEPLOYMENT.md`, and
`docs/PRIVACY.md` before deployment.

## Product completion boundary

The application and bench product are implemented and buildable. A real
vehicle/government deployment additionally requires work that cannot be
completed safely by source code alone:

- Certified breathalyzer hardware and traceable calibration
- Automotive-rated power, isolation, enclosure, and connectors
- Certified ECU/gateway integration and a reviewed recovery policy
- Secure boot/eFuse provisioning, signed OTA, and tamper evidence
- Hardware-in-the-loop, environmental, EMC, and electrical safety testing
- Regulatory, legal, privacy, accessibility, and procurement approval
- Independent penetration testing and functional-safety certification

Until those gates pass, GPIO26 must remain connected only to the isolated
bench dummy load and the prototype sensor must not be treated as a legal BAC
instrument.
