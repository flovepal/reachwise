"""Session tokens and encryption of stored app passwords."""
from datetime import timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .db import get_db, oid, utcnow

_bearer = HTTPBearer(auto_error=False)


def _jwt_secret() -> str:
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set (run: python -m app.keys)")
    return settings.jwt_secret


def make_token(user_id: str, purpose: str = "session", minutes: int | None = None, **extra) -> str:
    exp = utcnow() + (timedelta(minutes=minutes) if minutes else timedelta(days=settings.jwt_days))
    payload = {"sub": user_id, "purpose": purpose, "exp": exp, **extra}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def read_token(token: str, purpose: str = "session") -> dict:
    try:
        data = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    if data.get("purpose") != purpose:
        raise HTTPException(401, "Invalid token")
    return data


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if creds is None:
        raise HTTPException(401, "Please sign in")
    data = read_token(creds.credentials)
    user = get_db().users.find_one({"_id": oid(data["sub"])})
    if user is None or user.get("deleted"):
        raise HTTPException(401, "Account not found")
    return user


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is not set (run: python -m app.keys)")
    return Fernet(settings.encryption_key.encode())


def encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Stored app password can't be decrypted (was ENCRYPTION_KEY changed?)")
