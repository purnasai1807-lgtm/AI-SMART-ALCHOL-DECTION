# API database migrations

Production deployments set `AUTO_CREATE_SCHEMA=false` and run:

```sh
cd services/api
alembic upgrade head
```

Future schema changes must be generated as reviewed revisions with
`alembic revision --autogenerate -m "describe change"` and applied by the
deployment pipeline.
