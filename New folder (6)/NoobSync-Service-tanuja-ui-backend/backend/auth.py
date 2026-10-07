"""
auth.py
Name + phone sign-in, bearer-token sessions and basic abuse protection.

How identity works (and why):
  * The visitor enters a name and phone number. We do NOT verify the phone
    (no OTP), so the phone number is treated as contact info for the
    NoobSync team, never as proof of identity.
  * Each sign-in creates its own profile and a random session token that is
    stored in that browser. Chat history and uploaded documents belong to
    that profile. Because the number is unverified, typing someone else's
    number can never open their history.
  * Only a SHA-256 hash of the token is stored server-side.
"""

import hashlib
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException, Request

from backend import db
from backend.config import REGISTER_LIMIT, REGISTER_WINDOW_SECONDS, SESSION_DAYS

NAME_MIN, NAME_MAX = 2, 60
_PHONE_RE = re.compile(r"^\+?\d{10,15}$")


class RegistrationError(ValueError):
    """Message is safe to show to the visitor."""


def clean_name(raw: str) -> str:
    name = unicodedata.normalize("NFKC", raw or "")
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = re.sub(r"\s+", " ", name).strip()
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        raise RegistrationError(f"Enter your name ({NAME_MIN}-{NAME_MAX} characters).")
    if sum(ch.isalpha() for ch in name) < 2 or any(
        not (ch.isalpha() or ch in " .'-") for ch in name
    ):
        raise RegistrationError("Names can only contain letters, spaces, . ' and -.")
    return name


def clean_phone(raw: str) -> str:
    phone = re.sub(r"[\s\-().]", "", raw or "")
    if not _PHONE_RE.match(phone):
        raise RegistrationError("Enter a valid phone number (10-15 digits, optional + prefix).")
    return phone


# ── Rate limit on sign-ups (in-memory, per client IP) ──────────────────────
_register_hits: dict[str, deque] = defaultdict(deque)


def check_register_rate(ip: str) -> None:
    now = time.time()
    hits = _register_hits[ip]
    while hits and now - hits[0] > REGISTER_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= REGISTER_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait a few minutes and try again.",
        )
    hits.append(now)


# ── Tokens ──────────────────────────────────────────────────────────────────
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db.save_auth_session(_hash(token), user_id, expires.isoformat())
    return token


def revoke_token(token: str) -> None:
    db.delete_auth_session(_hash(token))


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    return authorization[7:].strip()


def current_token(authorization: str | None = Header(default=None)) -> str:
    return _bearer(authorization)


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: resolves the signed-in user or raises 401."""
    user = db.user_for_token_hash(_hash(_bearer(authorization)))
    if not user:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    return user


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
