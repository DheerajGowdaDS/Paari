"""Dashboard session authentication (merchant operator)."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from fastapi import Request, Response
from fastapi.responses import RedirectResponse

from paari.config import settings


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_credentials(email: str, password: str) -> bool:
    return email == settings.dashboard_user and _hash(password) == _hash(settings.dashboard_password)


# In-memory session store (demo). Production: signed cookies + DB.
_SESSIONS: dict[str, dict[str, Any]] = {}


def create_session(email: str, merchant_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {"email": email, "merchant_id": merchant_id}
    return token


def get_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    return _SESSIONS.get(token)


def session_cookie_name() -> str:
    return "paari_session"


async def require_dashboard_session(request: Request) -> dict[str, Any]:
    """Dependency: require a valid dashboard session cookie.

    Raises a RedirectResponse to login if the session is missing or invalid.
    FastAPI supports dependencies raising responses, which short-circuits the
    request and sends the redirect to the client.
    """
    token = request.cookies.get(session_cookie_name())
    session = get_session(token)
    if session is None:
        raise RedirectResponse(url="/dashboard/login", status_code=302)
    return session


async def optional_dashboard_session(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(session_cookie_name())
    return get_session(token)


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(session_cookie_name(), token, httponly=True, samesite="lax", max_age=86400)


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(session_cookie_name())
