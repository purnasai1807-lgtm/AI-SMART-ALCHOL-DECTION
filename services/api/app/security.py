import base64, hashlib, hmac, os, time
from cryptography.fernet import Fernet
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import User

oauth = OAuth2PasswordBearer(tokenUrl="/auth/login")

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

def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)):
    try: uid = int(jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])["sub"])
    except Exception as exc: raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = db.get(User, uid)
    if not user: raise HTTPException(status_code=401, detail="Unknown user")
    return user

def require_roles(*roles):
    def dependency(user=Depends(current_user)):
        if user.role not in roles: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return dependency

def signature(reading, device_secret):
    return hmac.new(device_secret.encode(), reading.encode(), hashlib.sha256).hexdigest()

def _fernet():
    if not settings.device_encryption_key:
        raise RuntimeError("DEVICE_ENCRYPTION_KEY must be configured")
    return Fernet(settings.device_encryption_key.encode())

def encrypt_device_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()

def decrypt_device_secret(ciphertext):
    return _fernet().decrypt(ciphertext.encode()).decode()
