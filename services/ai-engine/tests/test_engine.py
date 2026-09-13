from fastapi.testclient import TestClient

from app.analytics import extract_features
from app.main import app

client = TestClient(app)


def test_feature_extraction_is_deterministic_and_sorted():
    reading = {"z": [3, 1], "a": [2, 4]}
    first = extract_features(reading)
    second = extract_features(reading)
    assert first == second
    assert list(first) == sorted(first)
    assert first["a.mean"] == 3.0
    assert first["z.range"] == 2.0


def test_endpoints_return_metadata_and_never_safety_override():
    response = client.post("/predict", json={"sensors": {"temperature": [1, 2, 3]}})
    assert response.status_code == 200
    body = response.json()
    assert body["model_version"] == "deterministic-baseline-1.0.0"
    assert body["safety_decision"] == "DEFERRED"
    assert body["safety_override"] is False


def test_anomaly_score_is_bounded_and_high_for_extreme_reading():
    response = client.post("/anomaly-score", json={"sensors": {"temperature": [1000]}})
    assert response.status_code == 200
    assert response.json()["score"] == 1.0
    assert response.json()["anomalous"] is True


def test_empty_sensor_series_is_rejected():
    response = client.post("/features", json={"sensors": {"temperature": []}})
    assert response.status_code == 422
