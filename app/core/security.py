import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.db import get_db
from app.models.database import AuditLog, User


PBKDF2_ROUNDS = 160_000
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
settings = get_settings()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _client_key(request: Request, identifier: str = "") -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{identifier.strip().lower()}"


def check_login_rate_limit(request: Request, identifier: str) -> None:
    key = _client_key(request, identifier)
    now = time.time()
    window = settings.login_rate_limit_window_seconds
    attempts = [ts for ts in _LOGIN_ATTEMPTS.get(key, []) if now - ts < window]
    _LOGIN_ATTEMPTS[key] = attempts
    if len(attempts) >= settings.login_rate_limit_attempts:
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait a few minutes and try again.")


def record_failed_login(request: Request, identifier: str) -> None:
    key = _client_key(request, identifier)
    _LOGIN_ATTEMPTS.setdefault(key, []).append(time.time())


def clear_failed_login(request: Request, identifier: str) -> None:
    _LOGIN_ATTEMPTS.pop(_client_key(request, identifier), None)


def authenticate(db: Session, identifier: str, password: str) -> Optional[User]:
    user = db.query(User).filter(User.identifier == identifier.strip()).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    user = db.get(User, int(user_id))
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_role(role: str):
    def _dependency(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return user
    return _dependency


def csrf_token(request: Request) -> str:
    if "session" not in request.scope:
        return ""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def validate_csrf(request: Request, token: str | None) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not token or not hmac.compare_digest(str(expected), str(token)):
        raise HTTPException(status_code=403, detail="Invalid or expired form token. Please refresh and try again.")


def validate_csrf_header(request: Request) -> None:
    validate_csrf(request, request.headers.get("x-csrf-token"))


def audit_log(db: Session, request: Request | None, actor_id: int | None, action: str, details: str = "") -> None:
    try:
        db.add(AuditLog(
            actor_id=actor_id,
            action=action[:120],
            details=details[:4000],
            ip_address=(request.client.host if request and request.client else "")[:80],
            user_agent=(request.headers.get("user-agent", "") if request else "")[:300],
        ))
        db.flush()
    except Exception:
        db.rollback()
