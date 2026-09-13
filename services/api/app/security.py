import base64, hashlib, hmac, os, time, secrets
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet
import jwt
import pyotp
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User, RefreshToken

oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")
_login_attempts = defaultdict(deque)
_test_fernet = Fernet.generate_key()

def hash_password(value):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", value.encode(), salt, 310000)
    return "pbkdf2$310000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

def verify_password(value, hashed):
    try:
        scheme, rounds, salt, digest = hashed.split("$")
        candidate = hashlib.pbkdf2_hmac("sha256", value.encode(), base64.urlsafe_b64decode(salt), int(rounds))
        return scheme == "pbkdf2" and hmac.compare_digest(base64.urlsafe_b64encode(candidate).decode(), digest)
    except (ValueError, TypeError):
        return False
def token_for(user):
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": int(time.time()) + 3600}, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def refresh_for(user, db):
    raw = secrets.token_urlsafe(48)
    db.add(RefreshToken(
        user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    return raw

def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)):
    try: uid = int(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["sub"])
    except Exception as exc: raise HTTPException(status_code=401, detail="Authentication failed") from exc
    user = db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail="Authentication failed")
    return user

def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user.role not in roles: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return dependency

def signature(reading, device_secret):
    return hmac.new(device_secret.encode(), reading.encode(), hashlib.sha256).hexdigest()

def _fernet():
    if not settings.device_encryption_key and settings.environment.lower() not in ("test", "testing"):
        raise RuntimeError("DEVICE_ENCRYPTION_KEY must be configured")
    if not settings.device_encryption_key:
        return Fernet(_test_fernet)
    return Fernet(settings.device_encryption_key.encode())

def encrypt_device_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()

def decrypt_device_secret(ciphertext):
    return _fernet().decrypt(ciphertext.encode()).decode()

def encrypt_mfa_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()

def decrypt_mfa_secret(ciphertext):
    return _fernet().decrypt(ciphertext.encode()).decode()

def verify_mfa_code(user, code):
    if not user.mfa_enabled or not user.mfa_secret_ciphertext or not code:
        return False
    try:
        return verify_mfa_secret(decrypt_mfa_secret(user.mfa_secret_ciphertext), code)
    except Exception:
        return False

def verify_mfa_secret(secret, code):
    return bool(code) and pyotp.TOTP(secret).verify(code, valid_window=1)
