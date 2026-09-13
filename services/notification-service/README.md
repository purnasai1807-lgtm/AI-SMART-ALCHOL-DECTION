# Notification service

FastAPI service that durably queues notifications in a SQLAlchemy/SQLite
outbox. It does **not** contact providers or claim delivery. A worker can read
pending rows and use an implementation of the provider contracts in
`app.providers` for in-app, email, SMS, or push delivery.

## Run

```bash
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Set `NOTIFICATION_DATABASE_URL` to another SQLAlchemy URL; the default is
`sqlite:///./notification.db`.

`GET /health` reports health. `POST /notifications` accepts `channel`,
`recipient`, `body`, optional email `subject`, and optional `metadata`, and
returns `202 Accepted` with an outbox ID and `"status": "queued"`. Email and
E.164 SMS recipients are validated.
