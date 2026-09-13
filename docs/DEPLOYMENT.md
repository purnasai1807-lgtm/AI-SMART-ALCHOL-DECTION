# Deployment

For local development:

```sh
py -3 -m pip install -r services/api/requirements.txt
py -3 -m uvicorn app.main:app --app-dir services/api --reload
```

For the container stack:

```sh
docker compose up --build
```

Production must use managed PostgreSQL and a shared Redis/rate-limit/event
service, HTTPS ingress, a secret manager, structured logs, health/readiness
probes, backups, and a migration tool such as Alembic before schema changes.
The current `create_all` bootstrap is suitable for the local foundation only;
it is not a replacement for reviewed production migrations.

