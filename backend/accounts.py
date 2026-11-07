"""Accounts and logins: students, lecturers and tutors.

Routes
  POST /api/auth/register   {email, name, password, role?, staff_code?} -> {token, user}
  POST /api/auth/login      {email, password}                           -> {token, user}
  POST /api/auth/logout     (Authorization: Bearer <token>)
  GET  /api/auth/me         the logged-in user

Send the token as "Authorization: Bearer <token>" (WebSockets: ?token=...).

Who can do what
  * Staff routes (creating courses and slides, PDF upload, coursework, lecturer
    insights and metrics, the tutor queue, the lecturer side of the live
    lecture) need a lecturer or tutor login: require_staff.
  * Everything a student does keeps working without a login, so the demo and
    the current frontend are unchanged. A logged-in student's user id is their
    student_id.
  * Anyone can register as a student. Registering as a lecturer or tutor needs
    LOSTPOINT_STAFF_CODE; without it, create staff on the server:
        python accounts.py create-staff --email lecturer@uni.ac.uk --name "Dr X" --role lecturer

Passwords are hashed with scrypt (standard library) and a random salt. Only a
hash of each login token is stored, so a copy of the database cannot be used
to log in. Five failed logins for an email within 15 minutes are refused for
the rest of that window.
"""

import argparse
import getpass
import hashlib
import hmac
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config import settings
from db import connect, init_db

router = APIRouter(prefix="/api/auth", tags=["accounts"])

Role = Literal["student", "lecturer", "tutor"]
STAFF = ("lecturer", "tutor")
MAX_FAILED_LOGINS = 5
FAILED_WINDOW_S = 15 * 60
_failed: dict[str, deque] = defaultdict(deque)


class RegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: Role = "student"
    staff_code: str | None = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(check.hex(), digest)
    except ValueError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user_dict(row) -> dict:
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"]}


def create_user(conn, email: str, name: str, password: str, role: str) -> dict:
    email = email.strip().lower()
    if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists")
    user_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, email, name, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, name.strip(), role, hash_password(password), datetime.now(timezone.utc).isoformat()),
    )
    return _user_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())


def _new_session(conn, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO auth_sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (_token_hash(token), user_id, now.isoformat(), (now + timedelta(days=settings().session_days)).isoformat()),
    )
    return token


def user_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    with connect() as conn:
        row = conn.execute(
            """SELECT u.* FROM auth_sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (_token_hash(token), datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    return _user_dict(row) if row else None


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(authorization: str | None = Header(default=None)) -> dict | None:
    """The logged-in user, or None for an anonymous request."""
    return user_for_token(_bearer(authorization))


def require_user(user: dict | None = Depends(current_user)) -> dict:
    if user is None:
        raise HTTPException(401, "Please log in", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_staff(user: dict = Depends(require_user)) -> dict:
    if user["role"] not in STAFF:
        raise HTTPException(403, "Only lecturers and tutors can do this")
    return user


def _too_many_failures(email: str) -> bool:
    attempts, now = _failed[email], time.monotonic()
    while attempts and now - attempts[0] > FAILED_WINDOW_S:
        attempts.popleft()
    return len(attempts) >= MAX_FAILED_LOGINS


@router.post("/register", status_code=201)
def register(body: RegisterIn):
    if body.role in STAFF:
        code = settings().staff_code
        if not code or not body.staff_code or not hmac.compare_digest(body.staff_code, code):
            raise HTTPException(403, "A valid staff code is needed to register as a lecturer or tutor")
    with connect() as conn:
        user = create_user(conn, body.email, body.name, body.password, body.role)
        return {"token": _new_session(conn, user["id"]), "user": user}


@router.post("/login")
def login(body: LoginIn):
    email = body.email.strip().lower()
    if _too_many_failures(email):
        raise HTTPException(429, "Too many failed logins. Try again in 15 minutes.")
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None or not verify_password(body.password, row["password_hash"]):
            _failed[email].append(time.monotonic())
            raise HTTPException(401, "Email or password is wrong")
        _failed.pop(email, None)
        return {"token": _new_session(conn, row["id"]), "user": _user_dict(row)}


@router.post("/logout", status_code=204)
def logout(authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    if token:
        with connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))


@router.get("/me")
def me(user: dict = Depends(require_user)):
    return user


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Create a lecturer or tutor account on the server.")
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create-staff")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", choices=STAFF, default="lecturer")
    c.add_argument("--password", help="omit to be asked (safer: not saved in shell history)")
    args = p.parse_args(argv)
    password = args.password or getpass.getpass("Password (8+ characters): ")
    if len(password) < 8:
        p.error("password must be at least 8 characters")
    init_db()
    with connect() as conn:
        user = create_user(conn, args.email, args.name, password, args.role)
    print(f"Created {user['role']} {user['email']}.")


if __name__ == "__main__":
    main()
