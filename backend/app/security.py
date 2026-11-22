import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import func, select

from .config import settings
from .db import ApiKey, ResearchJob, SessionLocal, User


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode()[:72], h.encode())


def make_token(user_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": user_id, "exp": exp}, settings.jwt_secret, algorithm="HS256")


def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


def new_api_key() -> str:
    return "oi_" + secrets.token_urlsafe(32)


def client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(ip: str) -> str:
    return hashlib.sha256((settings.ip_hash_salt + ip).encode()).hexdigest()


def current_user_optional(authorization: str | None = Header(None),
                          x_api_key: str | None = Header(None)) -> User | None:
    with SessionLocal() as db:
        if x_api_key:
            key = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_key(x_api_key),
                                                 ApiKey.revoked == False))  # noqa: E712
            if not key:
                raise HTTPException(401, "Invalid API key")
            user = db.get(User, key.user_id)
            return user
        if authorization and authorization.startswith("Bearer "):
            try:
                data = jwt.decode(authorization[7:], settings.jwt_secret, algorithms=["HS256"])
            except jwt.PyJWTError:
                raise HTTPException(401, "Invalid token")
            return db.get(User, data["sub"])
    return None


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(401, "Login required")
    return user


def quota_for(user: User | None) -> int:
    """Searches allowed per window; 0 means unlimited."""
    return settings.guest_limit if user is None else settings.user_limit


def used_in_window(db, user: User | None, iph: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=settings.quota_window_days)
    q = select(func.count()).select_from(ResearchJob).where(ResearchJob.created_at >= since)
    q = q.where(ResearchJob.owner_id == user.id) if user else q.where(
        ResearchJob.ip_hash == iph, ResearchJob.owner_id.is_(None))
    return db.scalar(q) or 0
