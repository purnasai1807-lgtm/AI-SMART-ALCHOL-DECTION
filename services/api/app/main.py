from datetime import datetime, timezone
import csv, io
from datetime import timedelta
import hashlib, secrets
import asyncio
import pyotp
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import *
from .schemas import *
from .security import *
from .security import _login_attempts, jwt
from .config import settings

if settings.auto_create_schema:
    Base.metadata.create_all(engine)
app = FastAPI(title="Interlock Safety API", version="1.0.0")

class OrganizationUpdates:
    def __init__(self):
        self._subscribers: dict[int, dict[asyncio.Queue, asyncio.AbstractEventLoop]] = {}

    async def subscribe(self, organization_id: int):
        queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(organization_id, {})[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, organization_id: int, queue):
        self._subscribers.get(organization_id, {}).pop(queue, None)

    def publish(self, organization_id: int, event: dict):
        for queue, loop in tuple(self._subscribers.get(organization_id, {}).items()):
            loop.call_soon_threadsafe(self._publish_to_queue, queue, event)

    @staticmethod
    def _publish_to_queue(queue: asyncio.Queue, event: dict):
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # A slow client must not block safety writes.
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

updates = OrganizationUpdates()
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    import uuid
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
def audit(db, actor, action, entity, metadata=None):
    db.add(AuditLog(actor_id=getattr(actor, "id", None), action=action, entity=entity, metadata_json=metadata or {}))

def check_vehicle_access(vehicle, user):
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    if user.role != "ADMIN" and user.organization_id != vehicle.organization_id: raise HTTPException(403, "Forbidden")

@app.get("/health")
def health(): return {"status": "ok"}
@app.get("/readiness")
def readiness(db: Session = Depends(get_db)):
    try: db.execute(select(1))
    except Exception: raise HTTPException(503, "Service unavailable")
    return {"status": "ready"}

@app.post("/auth/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == payload.email)): raise HTTPException(409, "Email already registered")
    # Keep self-service registration least-privilege. A fresh local database
    # gets one bootstrap administrator so the demo can be provisioned; later
    # accounts cannot elevate themselves through request data.
    is_bootstrap = db.scalar(select(User.id).limit(1)) is None
    role = "ADMIN" if is_bootstrap else "DRIVER"
    user = User(email=payload.email, password_hash=hash_password(payload.password), role=role)
    db.add(user); db.commit(); db.refresh(user); audit(db, user, "register", "user"); db.commit()
    refresh_token = refresh_for(user, db); db.commit()
    return {"access_token": token_for(user), "refresh_token": refresh_token, "token_type": "bearer", "user_id": user.id}

@app.post("/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts[payload.email.lower()]
    while attempts and now - attempts[0] > settings.login_rate_window_seconds: attempts.popleft()
    if len(attempts) >= settings.login_rate_limit: raise HTTPException(429, "Too many requests")
    attempts.append(now)
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "Authentication failed")
    if user.mfa_enabled and not verify_mfa_code(user, payload.mfa_code or payload.otp):
        raise HTTPException(401, "MFA verification required")
    audit(db, user, "login", "user"); db.commit()
    refresh_token = refresh_for(user, db); db.commit()
    return {"access_token": token_for(user), "refresh_token": refresh_token, "token_type": "bearer"}

@app.post("/auth/mfa/enroll")
def mfa_enroll(db: Session = Depends(get_db), user=Depends(current_user)):
    secret = pyotp.random_base32()
    user.mfa_secret_ciphertext = encrypt_mfa_secret(secret)
    user.mfa_enabled = False
    user.mfa_enrolled_at = None
    db.commit()
    return {"secret": secret, "otpauth_url": pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="Interlock")}

@app.post("/auth/mfa/verify")
def mfa_verify(payload: MFAVerifyIn, db: Session = Depends(get_db), user=Depends(current_user)):
    try:
        valid = bool(user.mfa_secret_ciphertext) and verify_mfa_secret(
            decrypt_mfa_secret(user.mfa_secret_ciphertext), payload.code)
    except Exception:
        valid = False
    if not valid:
        raise HTTPException(400, "Invalid MFA code")
    user.mfa_enabled = True
    user.mfa_enrolled_at = datetime.now(timezone.utc)
    audit(db, user, "mfa_enabled", "user")
    db.commit()
    return {"enabled": True}

@app.post("/auth/mfa/disable")
def mfa_disable(db: Session = Depends(get_db), user=Depends(current_user)):
    user.mfa_enabled = False
    user.mfa_secret_ciphertext = None
    user.mfa_enrolled_at = None
    audit(db, user, "mfa_disabled", "user")
    db.commit()
    return {"enabled": False}

@app.post("/auth/refresh")
def refresh(payload: RefreshIn, db: Session = Depends(get_db)):
    raw = payload.refresh_token
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hashlib.sha256(raw.encode()).hexdigest(), RefreshToken.revoked_at.is_(None)))
    if not row or (row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at.tzinfo is None else row.expires_at) < datetime.now(timezone.utc): raise HTTPException(401, "Authentication failed")
    user = db.get(User, row.user_id)
    if not user: raise HTTPException(401, "Authentication failed")
    row.revoked_at = datetime.now(timezone.utc)
    new_raw = refresh_for(user, db)
    db.commit()
    return {"access_token": token_for(user), "refresh_token": new_raw, "token_type": "bearer"}

@app.post("/auth/logout")
def logout(payload: RefreshIn, db: Session = Depends(get_db), user=Depends(current_user)):
    row = db.scalar(select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.token_hash == hashlib.sha256(payload.refresh_token.encode()).hexdigest(),
        RefreshToken.revoked_at.is_(None)))
    if row:
        row.revoked_at = datetime.now(timezone.utc)
        audit(db, user, "logout", "session")
        db.commit()
    return {"ok": True}

@app.get("/auth/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "email": user.email, "role": user.role, "organization_id": user.organization_id}

@app.post("/auth/password")
def change_password(payload: PasswordChangeIn, db: Session = Depends(get_db), user=Depends(current_user)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(400, "Current password is invalid")
    user.password_hash = hash_password(payload.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).update(
        {RefreshToken.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False)
    audit(db, user, "password_changed", "user")
    db.commit()
    return {"ok": True}

@app.post("/organizations")
def create_org(payload: OrganizationIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    org = Organization(name=payload.name); db.add(org); db.commit(); db.refresh(org); return {"id": org.id, "name": org.name}

@app.get("/organizations")
def list_orgs(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    query = select(Organization)
    if user.role != "ADMIN":
        query = query.where(Organization.id == user.organization_id)
    return db.scalars(query.order_by(Organization.name)).all()

@app.post("/vehicles")
def create_vehicle(payload: VehicleIn, db: Session = Depends(get_db), user=Depends(current_user)):
    if user.role != "ADMIN" and user.organization_id != payload.organization_id: raise HTTPException(403, "Forbidden")
    if not db.get(Organization, payload.organization_id): raise HTTPException(404, "Organization not found")
    v = Vehicle(registration=payload.registration, organization_id=payload.organization_id); db.add(v); db.commit(); db.refresh(v); return {"id": v.id, "status": v.status}

@app.get("/vehicles")
def list_vehicles(db: Session = Depends(get_db), user=Depends(current_user)):
    query = select(Vehicle)
    if user.role != "ADMIN":
        query = query.where(Vehicle.organization_id == user.organization_id)
    return db.scalars(query.order_by(Vehicle.registration)).all()

@app.post("/drivers")
def create_driver(payload: DriverIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    if user.role != "ADMIN" and user.organization_id != payload.organization_id: raise HTTPException(403, "Forbidden")
    if not db.get(Organization, payload.organization_id): raise HTTPException(404, "Organization not found")
    d = Driver(**payload.model_dump()); db.add(d); db.commit(); db.refresh(d); return {"id": d.id}

@app.get("/drivers")
def list_drivers(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    query = select(Driver)
    if user.role != "ADMIN":
        query = query.where(Driver.organization_id == user.organization_id)
    return db.scalars(query.order_by(Driver.name)).all()

@app.post("/devices")
def create_device(payload: DeviceIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    vehicle = db.get(Vehicle, payload.vehicle_id)
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    if user.role != "ADMIN" and user.organization_id != vehicle.organization_id: raise HTTPException(403, "Forbidden")
    d = Device(serial=payload.serial, vehicle_id=payload.vehicle_id, secret_ciphertext=encrypt_device_secret(payload.secret))
    db.add(d); db.commit(); db.refresh(d); return {"id": d.id, "serial": d.serial}

@app.get("/devices")
def list_devices(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    query = select(Device).join(Vehicle, Device.vehicle_id == Vehicle.id)
    if user.role != "ADMIN":
        query = query.where(Vehicle.organization_id == user.organization_id)
    return db.scalars(query.order_by(Device.serial)).all()

@app.post("/decisions", response_model=DecisionOut)
def decide(payload: SensorReading, db: Session = Depends(get_db), user=Depends(current_user)):
    device = db.get(Device, payload.device_id)
    reason, outcome = "invalid_attestation", "LOCKED"
    valid = bool(device and device.enabled and not device.revoked_at and device.vehicle_id == payload.vehicle_id)
    check_vehicle_access(db.get(Vehicle, payload.vehicle_id), user)
    if valid:
        canonical = f"{payload.device_id}.{payload.vehicle_id}.{payload.nonce}.{payload.timestamp.isoformat()}.{payload.reading}"
        try:
            device_secret = decrypt_device_secret(device.secret_ciphertext)
        except Exception:
            device_secret = ""
        valid = bool(device_secret) and hmac.compare_digest(payload.signature, signature(canonical, device_secret)) and db.get(NonceRecord, payload.nonce) is None
        valid = valid and abs((datetime.now(timezone.utc) - payload.timestamp).total_seconds()) <= settings.attestation_max_age_seconds
        if valid:
            db.add(NonceRecord(nonce=payload.nonce))
            # Keep the original /decisions contract; /sensor-tests exposes
            # the newer ALLOW/BLOCK vocabulary.
            outcome = "UNLOCKED" if payload.reading < settings.alcohol_threshold else "LOCKED"
            reason = "below_threshold" if outcome == "UNLOCKED" else "above_threshold"
    decision = Decision(vehicle_id=payload.vehicle_id, device_id=getattr(device, "id", None), reading=payload.reading, decision=outcome, reason=reason)
    db.add(decision); db.flush()
    if outcome in ("BLOCK", "ERROR", "LOCKED"): db.add(Incident(decision_id=decision.id))
    vehicle = db.get(Vehicle, payload.vehicle_id)
    vehicle.status = outcome
    if outcome in ("LOCKED", "ERROR"):
        db.add(Notification(organization_id=vehicle.organization_id,
                             title="Vehicle start blocked", message=f"Attested decision blocked vehicle start: {reason}."))
    audit(db, user, "safety_decision", "decision", {"decision": outcome, "reason": reason}); db.commit(); db.refresh(decision)
    updates.publish(vehicle.organization_id, {"type": "decision", "vehicle_id": vehicle.id, "decision": decision.decision,
                                               "reason": decision.reason, "id": decision.id, "created_at": decision.created_at.isoformat()})
    return decision

@app.post("/drivers/assign")
@app.post("/assignments")
@app.post("/vehicles/{vehicle_id}/assign-driver")
def assign_driver(payload: AssignmentIn, vehicle_id: int | None = None, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    if vehicle_id is not None: payload.vehicle_id = vehicle_id
    d, v = db.get(Driver, payload.driver_id), db.get(Vehicle, payload.vehicle_id)
    if not d or not v: raise HTTPException(404, "Resource not found")
    if user.role != "ADMIN" and user.organization_id not in (d.organization_id, v.organization_id): raise HTTPException(403, "Forbidden")
    row = DriverAssignment(driver_id=d.id, vehicle_id=v.id); db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "driver_id": d.id, "vehicle_id": v.id}

@app.post("/devices/{device_id}/heartbeat")
def heartbeat(device_id: int, payload: HeartbeatIn, request: Request, db: Session = Depends(get_db), user=Depends(current_user)):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "Device not found")
    check_vehicle_access(db.get(Vehicle, d.vehicle_id), user)
    d.last_seen_at = datetime.now(timezone.utc); d.last_ip = request.client.host if request.client else None
    db.commit()
    return {"device_id": d.id, "status": payload.status, "enabled": d.enabled, "revoked": bool(d.revoked_at), "last_seen_at": d.last_seen_at}

@app.get("/devices/{device_id}/status")
def device_status(device_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "Device not found")
    check_vehicle_access(db.get(Vehicle, d.vehicle_id), user)
    return {"device_id": d.id, "enabled": d.enabled, "revoked": bool(d.revoked_at), "last_seen_at": d.last_seen_at}

@app.post("/devices/{device_id}/revoke")
def revoke_device(device_id: int, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    d = db.get(Device, device_id)
    if not d: raise HTTPException(404, "Device not found")
    check_vehicle_access(db.get(Vehicle, d.vehicle_id), user)
    d.enabled = False; d.revoked_at = datetime.now(timezone.utc); db.commit()
    return {"device_id": d.id, "revoked": True}

@app.post("/sensor-tests")
def sensor_test(payload: SensorTestIn, db: Session = Depends(get_db), user=Depends(current_user)):
    samples = payload.samples
    decision, reason = "ERROR", "invalid_samples"
    check_vehicle_access(db.get(Vehicle, payload.vehicle_id), user)
    device = db.get(Device, payload.device_id) if payload.device_id else None
    if device and device.vehicle_id != payload.vehicle_id:
        raise HTTPException(400, "Device is not paired with this vehicle")
    if payload.device_id and (not device or not device.enabled or device.revoked_at):
        reason = "device_offline"
        row = SensorTest(vehicle_id=payload.vehicle_id, device_id=payload.device_id, samples=samples, decision=decision, reason=reason)
        db.add(row)
        db.get(Vehicle, payload.vehicle_id).status = decision
        if decision in ("BLOCK", "ERROR"):
            linked_decision = Decision(vehicle_id=payload.vehicle_id, device_id=payload.device_id,
                                       reading=sum(samples) / len(samples), decision=decision, reason=reason)
            db.add(linked_decision)
            db.flush()
            db.add(Incident(decision_id=linked_decision.id, severity="HIGH"))
            db.add(Notification(organization_id=db.get(Vehicle, payload.vehicle_id).organization_id,
                                 title="Vehicle start blocked", message=f"Safety test blocked vehicle start: {reason}."))
        db.commit(); db.refresh(row)
        updates.publish(db.get(Vehicle, payload.vehicle_id).organization_id, {
            "type": "decision", "vehicle_id": payload.vehicle_id, "decision": row.decision,
            "reason": row.reason, "id": row.id, "created_at": row.created_at.isoformat()})
        return {"id": row.id, "decision": decision, "reason": reason, "samples": samples}
    if all(0 <= x <= 10 for x in samples) and len(samples) >= 3:
        if max(samples)-min(samples) > 0.05: decision, reason = "RETEST", "inconsistent_samples"
        elif sum(samples)/len(samples) < settings.alcohol_threshold: decision, reason = "ALLOW", "below_threshold"
        else: decision, reason = "BLOCK", "above_threshold"
    row = SensorTest(vehicle_id=payload.vehicle_id, device_id=payload.device_id, samples=samples, decision=decision, reason=reason)
    db.add(row)
    vehicle = db.get(Vehicle, payload.vehicle_id)
    vehicle.status = decision
    linked_decision = Decision(
        vehicle_id=payload.vehicle_id,
        device_id=payload.device_id,
        reading=sum(samples) / len(samples) if samples else None,
        decision=decision,
        reason=reason,
    )
    db.add(linked_decision)
    db.flush()
    if decision in ("BLOCK", "ERROR"):
        db.add(Incident(decision_id=linked_decision.id, severity="HIGH"))
        db.add(Notification(
            organization_id=vehicle.organization_id,
            title="Vehicle start blocked",
            message=f"Safety test blocked vehicle start: {reason}.",
        ))
    db.commit(); db.refresh(row)
    updates.publish(vehicle.organization_id, {
        "type": "decision", "vehicle_id": vehicle.id, "decision": linked_decision.decision,
        "reason": linked_decision.reason, "id": linked_decision.id,
        "created_at": linked_decision.created_at.isoformat()})
    return {"id": row.id, "decision": decision, "reason": reason, "samples": samples}

@app.get("/incidents")
def incidents(db: Session = Depends(get_db), user=Depends(current_user)):
    query = select(Incident).join(Decision, Incident.decision_id == Decision.id).join(Vehicle, Decision.vehicle_id == Vehicle.id)
    if user.role != "ADMIN": query = query.where(Vehicle.organization_id == user.organization_id)
    return db.scalars(query.order_by(Incident.created_at.desc()).limit(100)).all()

@app.post("/incidents/{incident_id}/acknowledge")
@app.post("/incidents/{incident_id}/ack")
def acknowledge(incident_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    row = db.get(Incident, incident_id)
    if not row: raise HTTPException(404, "Incident not found")
    decision = db.get(Decision, row.decision_id)
    check_vehicle_access(db.get(Vehicle, decision.vehicle_id), user)
    row.acknowledged_at = datetime.now(timezone.utc); row.acknowledged_by = user.id; db.commit()
    return {"id": row.id, "acknowledged": True}

@app.get("/notifications")
def notifications(db: Session = Depends(get_db), user=Depends(current_user)):
    query = select(Notification).where(
        ((Notification.user_id == user.id) | (Notification.user_id.is_(None)))
    )
    if user.role != "ADMIN":
        query = query.where(
            (Notification.organization_id == user.organization_id)
            | (Notification.organization_id.is_(None))
        )
    return db.scalars(query.order_by(Notification.created_at.desc()).limit(100)).all()

@app.post("/notifications")
def create_notification(payload: NotificationIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    target = db.get(User, payload.user_id) if payload.user_id else None
    if target and user.role != "ADMIN" and target.organization_id != user.organization_id:
        raise HTTPException(403, "Forbidden")
    row = Notification(**payload.model_dump(), organization_id=target.organization_id if target else user.organization_id)
    db.add(row); audit(db, user, "notification_created", "notification", {"target_user_id": payload.user_id}); db.commit(); db.refresh(row); return row

@app.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    row = db.get(Notification, notification_id)
    if not row or (row.user_id not in (None, user.id) and row.organization_id != user.organization_id):
        raise HTTPException(404, "Notification not found")
    row.read = True
    db.commit()
    return {"id": row.id, "read": True}

@app.post("/gps")
def gps(payload: GPSIn, db: Session = Depends(get_db), user=Depends(current_user)):
    check_vehicle_access(db.get(Vehicle, payload.vehicle_id), user)
    row = GPSPoint(vehicle_id=payload.vehicle_id, latitude=payload.latitude, longitude=payload.longitude, recorded_at=payload.recorded_at or datetime.now(timezone.utc)); db.add(row); db.commit(); db.refresh(row); return row

@app.get("/vehicles/{vehicle_id}/gps")
def gps_history(vehicle_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    check_vehicle_access(db.get(Vehicle, vehicle_id), user)
    return db.scalars(select(GPSPoint).where(GPSPoint.vehicle_id == vehicle_id).order_by(GPSPoint.recorded_at.desc()).limit(100)).all()

@app.get("/analytics/overview")
def analytics(db: Session = Depends(get_db), user=Depends(current_user)):
    query = select(Decision).join(Vehicle, Decision.vehicle_id == Vehicle.id)
    if user.role != "ADMIN": query = query.where(Vehicle.organization_id == user.organization_id)
    rows = db.scalars(query).all()
    incident_query = select(Incident).join(Decision, Incident.decision_id == Decision.id).join(Vehicle, Decision.vehicle_id == Vehicle.id)
    if user.role != "ADMIN": incident_query = incident_query.where(Vehicle.organization_id == user.organization_id)
    tests_query = select(SensorTest).join(Vehicle, SensorTest.vehicle_id == Vehicle.id)
    if user.role != "ADMIN": tests_query = tests_query.where(Vehicle.organization_id == user.organization_id)
    tests = db.scalars(tests_query).all()
    return {"total_decisions": len(rows), "allowed": sum(x.decision in ("ALLOW","UNLOCKED") for x in rows), "blocked": sum(x.decision in ("BLOCK","LOCKED") for x in rows), "errors": sum(x.decision == "ERROR" for x in rows), "incidents": len(db.scalars(incident_query).all()), "sensor_tests": len(tests), "retests": sum(x.decision == "RETEST" for x in tests)}

@app.get("/reports/decisions.csv")
def report(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    out = io.StringIO(); writer = csv.writer(out); writer.writerow(["id","vehicle_id","decision","reason","reading","created_at"])
    query = select(Decision).join(Vehicle, Decision.vehicle_id == Vehicle.id)
    if user.role != "ADMIN": query = query.where(Vehicle.organization_id == user.organization_id)
    for d in db.scalars(query.order_by(Decision.created_at.desc())).all(): writer.writerow([d.id,d.vehicle_id,d.decision,d.reason,d.reading,d.created_at.isoformat()])
    return StreamingResponse(iter([out.getvalue()]), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=decisions.csv"})

@app.get("/vehicles/{vehicle_id}/status")
def status(vehicle_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    vehicle = db.get(Vehicle, vehicle_id)
    check_vehicle_access(vehicle, user)
    latest = db.scalar(select(Decision).where(Decision.vehicle_id == vehicle_id).order_by(Decision.created_at.desc()))
    return {"vehicle_id": vehicle_id, "status": latest.decision if latest else vehicle.status, "last_decision": latest.id if latest else None}

@app.get("/vehicles/{vehicle_id}/decisions", response_model=list[DecisionOut])
def decisions(vehicle_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    check_vehicle_access(db.get(Vehicle, vehicle_id), user)
    return db.scalars(select(Decision).where(Decision.vehicle_id == vehicle_id).order_by(Decision.created_at.desc()).limit(100)).all()

@app.websocket("/ws/organizations/{organization_id}")
@app.websocket("/ws/organizations/{organization_id}/updates")
async def organization_updates(websocket: WebSocket, organization_id: int):
    token = websocket.query_params.get("token")
    if not token:
        authorization = websocket.headers.get("authorization", "")
        token = authorization.removeprefix("Bearer ").strip() if authorization else None
    if not token:
        await websocket.close(code=1008)
        return
    try:
        uid = int(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["sub"])
        db = next(get_db())
        try:
            user = db.get(User, uid)
            if not user or (user.role != "ADMIN" and user.organization_id != organization_id):
                await websocket.close(code=1008)
                return
        finally:
            db.close()
    except Exception:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    queue = await updates.subscribe(organization_id)
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        updates.unsubscribe(organization_id, queue)

@app.get("/audit")
def audit_log(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
