import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import get_db
from .models import LoginSession, Role, User

password_hasher = PasswordHasher()
SESSION_COOKIE = "matcha_session"
CART_COOKIE = "matcha_cart"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def issue_session(db: Session, user: User, response: Response, settings: Settings) -> LoginSession:
    token = secrets.token_urlsafe(32)
    login_session = LoginSession(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_token=secrets.token_urlsafe(24),
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
    )
    db.add(login_session)
    db.commit()
    db.refresh(login_session)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_days * 86400,
        path="/",
    )
    return login_session


def optional_session(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> LoginSession | None:
    if not session_token:
        return None
    session = db.scalar(
        select(LoginSession).where(
            LoginSession.token_hash == token_hash(session_token),
            LoginSession.revoked_at.is_(None),
            LoginSession.expires_at > datetime.now(UTC),
        )
    )
    return session


def current_session(session: LoginSession | None = Depends(optional_session)) -> LoginSession:
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return session


def csrf_session(
    session: LoginSession = Depends(current_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> LoginSession:
    if not csrf_token or not secrets.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    return session


def admin_session(session: LoginSession = Depends(current_session)) -> LoginSession:
    if session.user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return session


def admin_csrf_session(session: LoginSession = Depends(csrf_session)) -> LoginSession:
    if session.user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return session


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
