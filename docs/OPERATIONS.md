# Operations runbook

## Start locally

```sh
docker compose up --build
py -3 -m uvicorn app.main:app --app-dir services/api --reload
py -3 -m uvicorn app.main:app --app-dir services/ai-engine --port 8001
py -3 -m uvicorn app.main:app --app-dir services/notification-service --port 8002
npm.cmd start
```

Run the signed simulator payload with:

```sh
py -3 simulator/device_simulator.py --device-id 1 --vehicle-id 1 --secret "<provisioned-secret>" --reading 0.01
```

## Safety incident response

1. Treat `BLOCK`, `LOCKED`, `ERROR`, stale, replayed, revoked, and offline
   readings as immobilized until an authorized human and certified device
   workflow completes a new test.
2. Revoke a suspected device immediately with `POST /devices/{id}/revoke`.
3. Acknowledge and investigate incidents; do not clear them by editing the
   database.
4. Rotate JWT/device encryption secrets after suspected exposure.
5. Preserve audit logs and export the decision report before retention deletion.

## Production gates

Before real deployment, complete independent security testing, privacy/legal
review, hardware calibration and certification, secure boot/OTA validation,
PostgreSQL migrations, centralized monitoring, backups/restore drills, MFA or
SSO, and a separately validated vehicle gateway. Prototype services must never
be wired directly to a starter relay.
