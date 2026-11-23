"""Passwords and login tokens, with nothing beyond the standard library.

Enough for a demonstration with seeded accounts, not a production identity
system: scrypt password hashes, and a token that is the account key and an
expiry signed with HMAC-SHA256. There is no server-side session to revoke;
a token simply expires.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

TOKEN_TTL = 12 * 3600  # seconds: a working day, so a demo never logs out mid-talk

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=_N, r=_R, p=_P)
    return hmac.compare_digest(got.hex(), digest)


def _sign(payload: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def make_token(account_key: str, secret: str, *, now: float | None = None, ttl: int = TOKEN_TTL) -> str:
    expires = int((time.time() if now is None else now) + ttl)
    payload = base64.urlsafe_b64encode(f"{account_key}:{expires}".encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload, secret)}"


def read_token(token: str, secret: str, *, now: float | None = None) -> str | None:
    """The account key, or None for a forged, malformed or expired token."""
    payload, _, sig = token.partition(".")
    if not payload or not hmac.compare_digest(sig, _sign(payload, secret)):
        return None
    try:
        key, expires = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode().rsplit(":", 1)
        expires = int(expires)
    except (ValueError, UnicodeDecodeError):
        return None
    if (time.time() if now is None else now) > expires:
        return None
    return key
