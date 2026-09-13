from datetime import datetime, timezone
import hashlib, hmac
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
admin_token = None

def test_health_and_fail_secure():
    global admin_token
    suffix = uuid.uuid4().hex[:8]
    assert client.get("/health").json()["status"] == "ok"
    reg = client.post("/auth/register", json={"email": f"demo-{suffix}@example.com", "password": "a-strong-demo-password"})
    assert reg.status_code in (200, 409)
    token = reg.json().get("access_token") or client.post("/auth/login", json={"email": f"demo-{suffix}@example.com", "password": "a-strong-demo-password"}).json()["access_token"]
    admin_token = token
    headers = {"Authorization": f"Bearer {token}"}
    org = client.post("/organizations", json={"name": f"Demo Org {suffix}"}, headers=headers)
    oid = org.json()["id"] if org.status_code == 200 else 1
    vehicle = client.post("/vehicles", json={"registration": f"DEMO-{suffix}", "organization_id": oid}, headers=headers)
    vid = vehicle.json()["id"] if vehicle.status_code == 200 else 1
    device = client.post("/devices", json={"serial": f"sim-{suffix}", "vehicle_id": vid, "secret": "sixteen-character-secret"}, headers=headers)
    did = device.json()["id"] if device.status_code == 200 else 1
    payload = {"device_id": did, "vehicle_id": vid, "reading": 0.0, "timestamp": datetime.now(timezone.utc).isoformat(), "nonce": "bad-nonce-123", "signature": "invalid-signature-000"}
    result = client.post("/decisions", json=payload, headers=headers)
    assert result.status_code == 200 and result.json()["decision"] == "LOCKED"
    driver = client.post("/drivers", json={"name": "Demo Driver", "license_number": f"LIC-{suffix}", "organization_id": oid}, headers=headers)
    assert driver.status_code == 200

    timestamp = datetime.now(timezone.utc).isoformat()
    nonce = f"good-{suffix}"
    canonical = f"{did}.{vid}.{nonce}.{timestamp}.0.0"
    signature = hmac.new(b"sixteen-character-secret", canonical.encode(), hashlib.sha256).hexdigest()
    signed = {"device_id": did, "vehicle_id": vid, "reading": 0.0, "timestamp": timestamp, "nonce": nonce, "signature": signature}
    unlocked = client.post("/decisions", json=signed, headers=headers)
    assert unlocked.status_code == 200 and unlocked.json()["decision"] == "UNLOCKED"
    replay = client.post("/decisions", json=signed, headers=headers)
    assert replay.status_code == 200 and replay.json()["decision"] == "LOCKED"
    assert client.get(f"/vehicles/{vid}/status", headers=headers).json()["status"] == "LOCKED"
    assert client.get("/audit", headers=headers).status_code == 200

def test_rbac_and_safety_modules():
    assert admin_token
    headers = {"Authorization": f"Bearer {admin_token}"}
    suffix = uuid.uuid4().hex[:8]
    org = client.post("/organizations", json={"name": f"Module Org {suffix}"}, headers=headers)
    assert org.status_code == 200
    oid = org.json()["id"]
    vehicle = client.post("/vehicles", json={"registration": f"MOD-{suffix}", "organization_id": oid}, headers=headers)
    assert vehicle.status_code == 200
    vid = vehicle.json()["id"]
    test = client.post("/sensor-tests", json={"vehicle_id": vid, "samples": [0.01, 0.011, 0.009]}, headers=headers)
    assert test.status_code == 200 and test.json()["decision"] == "ALLOW"
    blocked = client.post("/sensor-tests", json={"vehicle_id": vid, "samples": [0.08, 0.081, 0.079]}, headers=headers)
    assert blocked.status_code == 200 and blocked.json()["decision"] == "BLOCK"
    assert client.get("/analytics/overview", headers=headers).json()["blocked"] >= 1
    assert client.get("/incidents", headers=headers).status_code == 200
    assert client.get("/reports/decisions.csv", headers=headers).status_code == 200
    assert client.post("/notifications/999999/read", headers=headers).status_code == 404
