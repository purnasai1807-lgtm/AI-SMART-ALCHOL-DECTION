import uuid

import pyotp
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app, updates
from app.models import Organization, User


client = TestClient(app)


def register():
    email = f"mfa-{uuid.uuid4().hex}@example.com"
    password = "a-strong-mfa-password"
    response = client.post("/auth/register", json={"email": email, "password": password})
    assert response.status_code == 200
    return email, password, response.json()["access_token"]


def test_mfa_enrollment_is_required_for_login():
    email, password, token = register()
    headers = {"Authorization": f"Bearer {token}"}

    enrollment = client.post("/auth/mfa/enroll", headers=headers)
    assert enrollment.status_code == 200
    secret = enrollment.json()["secret"]
    assert pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Interlock") == enrollment.json()["otpauth_url"]

    code = pyotp.TOTP(secret).now()
    assert client.post("/auth/mfa/verify", json={"code": code}, headers=headers).json() == {"enabled": True}
    assert client.post("/auth/login", json={"email": email, "password": password}).status_code == 401

    logged_in = client.post(
        "/auth/login", json={"email": email, "password": password, "mfa_code": pyotp.TOTP(secret).now()}
    )
    assert logged_in.status_code == 200


def test_organization_websocket_rejects_missing_or_invalid_tokens():
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/organizations/999999"):
            pass


def test_organization_websocket_delivers_scoped_updates():
    email, _, token = register()
    db = SessionLocal()
    try:
        organization = Organization(name=f"Live Org {uuid.uuid4().hex}")
        db.add(organization)
        db.flush()
        db.scalar(select(User).where(User.email == email)).organization_id = organization.id
        db.commit()
        organization_id = organization.id
    finally:
        db.close()

    with client.websocket_connect(f"/ws/organizations/{organization_id}?token={token}") as websocket:
        updates.publish(organization_id, {"type": "vehicle", "vehicle_id": 42, "status": "LOCKED"})
        assert websocket.receive_json() == {"type": "vehicle", "vehicle_id": 42, "status": "LOCKED"}
