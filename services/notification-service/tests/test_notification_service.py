from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_enqueue_is_accepted_without_claiming_delivery():
    response = client.post(
        "/notifications",
        json={"channel": "email", "recipient": "person@example.com", "subject": "Alert", "body": "Hello"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert "delivered" not in response.json()


def test_channel_validation():
    response = client.post(
        "/notifications",
        json={"channel": "sms", "recipient": "not-a-number", "body": "hello"},
    )
    assert response.status_code == 422
