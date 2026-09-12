from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import AuditLog, Decision, Device, Driver, Incident, NonceRecord, Organization, User, Vehicle
from .schemas import *
from .security import *
from .config import settings

Base.metadata.create_all(engine)
app = FastAPI(title="Interlock Safety API", version="1.0.0")
def audit(db, actor, action, entity, metadata=None):
    db.add(AuditLog(actor_id=getattr(actor, "id", None), action=action, entity=entity, metadata_json=metadata or {}))

@app.get("/health")
def health(): return {"status": "ok"}

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
    return {"access_token": token_for(user), "token_type": "bearer", "user_id": user.id}

@app.post("/auth/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash): raise HTTPException(401, "Invalid credentials")
    audit(db, user, "login", "user"); db.commit()
    return {"access_token": token_for(user), "token_type": "bearer"}

@app.post("/organizations")
def create_org(payload: OrganizationIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    org = Organization(name=payload.name); db.add(org); db.commit(); db.refresh(org); return {"id": org.id, "name": org.name}

@app.post("/vehicles")
def create_vehicle(payload: VehicleIn, db: Session = Depends(get_db), user=Depends(current_user)):
    if not db.get(Organization, payload.organization_id): raise HTTPException(404, "Organization not found")
    v = Vehicle(registration=payload.registration, organization_id=payload.organization_id); db.add(v); db.commit(); db.refresh(v); return {"id": v.id, "status": v.status}

@app.post("/drivers")
def create_driver(payload: DriverIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    if not db.get(Organization, payload.organization_id): raise HTTPException(404, "Organization not found")
    d = Driver(**payload.model_dump()); db.add(d); db.commit(); db.refresh(d); return {"id": d.id}

@app.post("/devices")
def create_device(payload: DeviceIn, db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    if not db.get(Vehicle, payload.vehicle_id): raise HTTPException(404, "Vehicle not found")
    d = Device(serial=payload.serial, vehicle_id=payload.vehicle_id, secret_ciphertext=encrypt_device_secret(payload.secret))
    db.add(d); db.commit(); db.refresh(d); return {"id": d.id, "serial": d.serial}

@app.post("/decisions", response_model=DecisionOut)
def decide(payload: SensorReading, db: Session = Depends(get_db), user=Depends(current_user)):
    device = db.get(Device, payload.device_id)
    reason, outcome = "invalid_attestation", "LOCKED"
    valid = bool(device and device.enabled and device.vehicle_id == payload.vehicle_id)
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
            outcome = "UNLOCKED" if payload.reading < settings.alcohol_threshold else "LOCKED"
            reason = "below_threshold" if outcome == "UNLOCKED" else "above_threshold"
    decision = Decision(vehicle_id=payload.vehicle_id, device_id=getattr(device, "id", None), reading=payload.reading, decision=outcome, reason=reason)
    db.add(decision); db.flush()
    if outcome == "LOCKED": db.add(Incident(decision_id=decision.id))
    audit(db, user, "safety_decision", "decision", {"decision": outcome, "reason": reason}); db.commit(); db.refresh(decision)
    return decision

@app.get("/vehicles/{vehicle_id}/status")
def status(vehicle_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    vehicle = db.get(Vehicle, vehicle_id)
    if not vehicle: raise HTTPException(404, "Vehicle not found")
    latest = db.scalar(select(Decision).where(Decision.vehicle_id == vehicle_id).order_by(Decision.created_at.desc()))
    return {"vehicle_id": vehicle_id, "status": latest.decision if latest else vehicle.status, "last_decision": latest.id if latest else None}

@app.get("/vehicles/{vehicle_id}/decisions", response_model=list[DecisionOut])
def decisions(vehicle_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
    if not db.get(Vehicle, vehicle_id): raise HTTPException(404, "Vehicle not found")
    return db.scalars(select(Decision).where(Decision.vehicle_id == vehicle_id).order_by(Decision.created_at.desc()).limit(100)).all()

@app.get("/audit")
def audit_log(db: Session = Depends(get_db), user=Depends(require_roles("ADMIN","OPERATOR"))):
    return db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)).all()
