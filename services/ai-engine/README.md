# Interlock AI engine

Small, runnable FastAPI service for deterministic sensor feature extraction,
anomaly scoring, model metadata, and prediction:

```sh
cd services/ai-engine
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

It exposes `GET /health`, `GET /model`, and `POST /features`,
`POST /anomaly-score`, and `POST /predict`. POST bodies use this shape:

```json
{"sensors": {"temperature": [20.0, 21.5], "pressure": [1.0, 1.1]}}
```

The calculations use only Python's standard library and stable sorted
iteration; the same input always produces the same output. The model version
is returned by every endpoint.

## Safety boundary

This engine is **advisory only**. It never makes, clears, or overrides an
interlock or other safety decision, and it has no actuator or decision-store
integration. A caller must treat `label`, `score`, and `anomalous` as telemetry
for an independently implemented safety controller. A safety controller must
fail safe if this service is unavailable, malformed, or disagrees with its
own sensors and policy. This demonstrator is not certified safety-critical
software.

Run tests with `pytest`.
