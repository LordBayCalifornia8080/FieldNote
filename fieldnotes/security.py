import hashlib
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete
from sqlalchemy.dialects.sqlite import insert

from .models import Audit, LoginBucket, SessionToken, User

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash("nonexistent-account-timing-padding")
COOKIE = "fn_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def new_secret():
    return secrets.token_urlsafe(32)


def verify_password(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def db_session(request: Request):
    with request.app.state.db.sessions() as session:
        yield session


def audit(db, actor, action, target):
    db.add(Audit(actor=actor, action=action, target=target))


@dataclass
class Principal:
    user: User
    session: SessionToken


def current_principal(request: Request, db=Depends(db_session)):
    raw = request.cookies.get(COOKIE, "")
    session = db.get(SessionToken, digest(raw)) if 0 < len(raw) <= 128 else None
    user = db.get(User, session.user_id) if session and session.expires_at > time.time() else None
    if not user or not user.active:
        raise HTTPException(401, "Sign in to continue")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(supplied.encode(), session.csrf.encode()):
            raise HTTPException(403, "Invalid CSRF token")
    return Principal(user, session)


def require(*roles):
    def dependency(principal=Depends(current_principal)):
        if principal.user.role not in roles:
            raise HTTPException(403, "Insufficient permissions")
        return principal

    return dependency


editor = require("admin", "editor")
admin = require("admin")


def login_budget(db, username, peer, limit):
    now = time.time()
    window = int(now // 900)
    allowed = True
    for category, value, maximum in (
        ("user", username.casefold(), limit),
        ("peer", peer, limit * 5),
    ):
        stmt = insert(LoginBucket).values(
            key=f"{window}:{category}:{digest(value)}", count=1, expires_at=(window + 1) * 900
        )
        count = db.scalar(
            stmt.on_conflict_do_update(
                index_elements=[LoginBucket.key], set_={"count": LoginBucket.count + 1}
            ).returning(LoginBucket.count)
        )
        allowed = allowed and count <= maximum
    # Opportunistic cleanup keeps authentication tables bounded without a background worker.
    db.execute(delete(LoginBucket).where(LoginBucket.expires_at < now))
    db.execute(delete(SessionToken).where(SessionToken.expires_at < now))
    db.commit()
    if not allowed:
        raise HTTPException(
            429,
            "Too many attempts; try again after this 15-minute window",
            headers={"Retry-After": str(int((window + 1) * 900 - now) + 1)},
        )
