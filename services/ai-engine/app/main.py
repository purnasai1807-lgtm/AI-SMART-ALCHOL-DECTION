from fastapi import FastAPI

from .analytics import MODEL_VERSION, extract_features, score_anomaly
from .schemas import (
    AnomalyResponse,
    FeaturesResponse,
    PredictionResponse,
    SensorRequest,
)

app = FastAPI(
    title="Interlock AI Engine",
    version=MODEL_VERSION,
    description=(
        "Deterministic sensor analytics. This service is advisory only and never "
        "overrides, makes, or clears a safety decision."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model_version": MODEL_VERSION}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ai-engine", "model_version": MODEL_VERSION}


@app.get("/model", response_model=dict[str, str])
@app.get("/model/version", response_model=dict[str, str], include_in_schema=False)
def model_metadata() -> dict[str, str]:
    return {
        "name": "deterministic-baseline",
        "version": MODEL_VERSION,
        "mode": "deterministic",
        "safety_role": "advisory-only",
    }


@app.post("/features", response_model=FeaturesResponse)
@app.post("/api/v1/features", response_model=FeaturesResponse, include_in_schema=False)
def features(request: SensorRequest) -> FeaturesResponse:
    return FeaturesResponse(model_version=MODEL_VERSION, features=extract_features(request.sensors))


@app.post("/anomaly-score", response_model=AnomalyResponse)
@app.post("/api/v1/anomaly-score", response_model=AnomalyResponse, include_in_schema=False)
def anomaly_score(request: SensorRequest) -> AnomalyResponse:
    score = score_anomaly(extract_features(request.sensors))
    return AnomalyResponse(model_version=MODEL_VERSION, score=score, anomalous=score >= 0.8)


@app.post("/predict", response_model=PredictionResponse)
@app.post("/api/v1/predict", response_model=PredictionResponse, include_in_schema=False)
def predict(request: SensorRequest) -> PredictionResponse:
    score = score_anomaly(extract_features(request.sensors))
    return PredictionResponse(
        model_version=MODEL_VERSION,
        score=score,
        anomalous=score >= 0.8,
        label="ANOMALY" if score >= 0.8 else "NORMAL",
    )
