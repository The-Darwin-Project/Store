# @ai-rules:
# 1. [Session store]: In-memory dict, per-pod. Acceptable for low-traffic admin. No Redis.
# 2. [Password]: bcrypt hash stored in admin_settings (singleton row, id=1).
# 3. [Cookie]: HTTP-only, SameSite=Lax, 3-hour max_age. No Secure flag (HTTP internal traffic).
"""Admin authentication endpoints for Darwin Store."""

import logging
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_MAX_AGE = 10800  # 3 hours in seconds
_sessions: dict[str, datetime] = {}


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


def _expire_sessions():
    """Remove sessions older than 3 hours."""
    cutoff = datetime.utcnow() - timedelta(seconds=SESSION_MAX_AGE)
    expired = [t for t, created in _sessions.items() if created < cutoff]
    for t in expired:
        del _sessions[t]


def validate_session(request: Request) -> bool:
    """Check if the request has a valid admin session cookie."""
    _expire_sessions()
    token = request.cookies.get("admin_session")
    if not token or token not in _sessions:
        return False
    return True


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM admin_settings WHERE id = 1"
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Admin not configured")
            stored_hash = row[0]
            if not bcrypt.checkpw(
                body.password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            ):
                raise HTTPException(status_code=401, detail="Invalid password")
    finally:
        pool.putconn(conn)

    token = secrets.token_hex(32)
    _sessions[token] = datetime.utcnow()

    response = JSONResponse(content={"status": "logged_in"})
    response.set_cookie(
        key="admin_session",
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    logger.info("Admin logged in")
    return response


@router.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("admin_session")
    if token and token in _sessions:
        del _sessions[token]

    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(
        key="admin_session",
        httponly=True,
        samesite="lax",
        path="/",
    )
    logger.info("Admin logged out")
    return response


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request):
    if not validate_session(request):
        raise HTTPException(status_code=401, detail="Not authenticated")

    pool = request.app.state.db_pool
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash FROM admin_settings WHERE id = 1"
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="Admin not configured")
            stored_hash = row[0]

            if not bcrypt.checkpw(
                body.current_password.encode("utf-8"),
                stored_hash.encode("utf-8"),
            ):
                raise HTTPException(status_code=401, detail="Current password is incorrect")

            new_hash = bcrypt.hashpw(
                body.new_password.encode("utf-8"),
                bcrypt.gensalt(),
            ).decode("utf-8")
            cur.execute(
                "UPDATE admin_settings SET password_hash = %s WHERE id = 1",
                (new_hash,),
            )
            conn.commit()
    finally:
        pool.putconn(conn)

    logger.info("Admin password changed")
    return {"status": "password_changed"}
