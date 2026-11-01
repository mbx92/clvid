import hashlib
import secrets
from datetime import timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session as DBSession

from app.api.errors import AppError
from app.api.schemas import LoginInput
from app.config import get_settings
from app.db import get_db
from app.domain.models import LoginAttempt, Session, User, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])
hasher = PasswordHasher()
_dummy_hash = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secure_cookie() -> bool:
    config = get_settings()
    return config.cookie_secure or config.app_origin.startswith("https://")


def set_csrf(response: Response, token: str):
    response.set_cookie("clipper_csrf", token, httponly=False, secure=secure_cookie(), samesite="lax", path="/")


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != get_settings().app_origin.rstrip("/"):
        raise AppError(403, "CSRF_ORIGIN", "Asal permintaan tidak diizinkan. Muat ulang halaman aplikasi.")


def csrf_cookie_check(request: Request):
    check_origin(request)
    supplied = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get("clipper_csrf", "")
    if not supplied or not cookie or not secrets.compare_digest(supplied, cookie):
        raise AppError(403, "CSRF_INVALID", "Sesi keamanan berubah. Muat ulang halaman dan coba lagi.")


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    token = request.cookies.get("clipper_session", "")
    session = db.get(Session, digest(token)) if token else None
    expires = session.expires_at.replace(tzinfo=timezone.utc) if session and session.expires_at.tzinfo is None else (session.expires_at if session else None)
    if not session or session.revoked_at or expires <= utcnow():
        raise AppError(401, "AUTH_REQUIRED", "Silakan masuk untuk melanjutkan.")
    user = db.get(User, session.user_id)
    if not user:
        raise AppError(401, "AUTH_REQUIRED", "Sesi tidak tersedia.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf_cookie_check(request)
        if not secrets.compare_digest(session.csrf_hash, digest(request.headers["x-csrf-token"])):
            raise AppError(403, "CSRF_INVALID", "Token keamanan tidak cocok dengan sesi ini.")
    request.state.session = session
    return user


@router.get("/csrf")
def csrf(response: Response, request: Request, db: DBSession = Depends(get_db)):
    check_origin(request)
    token = request.cookies.get("clipper_csrf", "")
    session_token = request.cookies.get("clipper_session", "")
    session = db.get(Session, digest(session_token)) if session_token else None
    if not token or (session and not secrets.compare_digest(session.csrf_hash, digest(token))):
        token = secrets.token_urlsafe(32)
        if session and not session.revoked_at:
            session.csrf_hash = digest(token)
            db.commit()
    set_csrf(response, token)
    return {"csrf_token": token}


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, db: DBSession = Depends(get_db)):
    csrf_cookie_check(request)
    config = get_settings()
    email = body.email.lower().strip()
    # Gateway must NOT forward arbitrary X-Forwarded-For; trust direct peer only.
    peer = request.client.host if request.client else "unknown"
    account_key, peer_key = digest(f"account:{email}"), digest(f"peer:{peer}")
    cutoff = utcnow() - timedelta(seconds=config.login_window_seconds)
    if db.bind.dialect.name == "postgresql":
        # Serialize concurrent attempts for the same account/peer before verification.
        # Stable signed advisory IDs avoid storing either raw email or network address.
        for lock_id in sorted(int.from_bytes(bytes.fromhex(k[:16]), "big", signed=True) for k in (account_key, peer_key)):
            db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == account_key))
    peer_count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == peer_key))
    if count >= config.login_max_attempts or peer_count >= config.login_max_attempts * 4:
        db.commit()
        raise AppError(429, "LOGIN_RATE_LIMIT", "Terlalu banyak percobaan masuk. Coba lagi dalam beberapa menit.")
    user = db.scalar(select(User).where(User.email == email))
    try:
        valid = hasher.verify(user.password_hash if user else _dummy_hash, body.password)
    except (VerificationError, VerifyMismatchError, InvalidHashError):
        valid = False
    if not user or not valid:
        db.add_all([LoginAttempt(key=account_key), LoginAttempt(key=peer_key)])
        db.commit()
        raise AppError(401, "LOGIN_INVALID", "Email atau kata sandi tidak sesuai.")
    old_token = request.cookies.get("clipper_session")
    old_session = db.get(Session, digest(old_token)) if old_token else None
    if old_session:
        old_session.revoked_at = utcnow()
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(body.password)
    token, csrf_token = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    db.add(Session(id=digest(token), user_id=user.id, csrf_hash=digest(csrf_token), expires_at=utcnow() + timedelta(hours=config.session_hours)))
    db.execute(delete(LoginAttempt).where(LoginAttempt.key == account_key))
    db.commit()
    response.set_cookie("clipper_session", token, max_age=config.session_hours * 3600, httponly=True, secure=secure_cookie(), samesite="lax", path="/")
    set_csrf(response, csrf_token)
    return {"id": user.id, "email": user.email, "csrf_token": csrf_token}


@router.get("/me")
def me(request: Request, user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email, "csrf_token": request.cookies.get("clipper_csrf")}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    request.state.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie("clipper_session", path="/")
    response.delete_cookie("clipper_csrf", path="/")
