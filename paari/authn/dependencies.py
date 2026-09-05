"""FastAPI dependency: extract and verify the agent JWT."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from paari.authn.jwt_verifier import Identity, TokenVerificationError, verify_token


def get_identity(authorization: str | None = Header(default=None, description="Bearer <agent JWT>")) -> Identity:
    """Verify the Authorization header and return the agent Identity.

    Raises 401 with a descriptive reason if the token is missing, invalid,
    expired, or revoked.
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_authorization")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="malformed_authorization")
    token = parts[1].strip()
    try:
        return verify_token(token)
    except TokenVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def optional_identity(authorization: str | None = Header(default=None)) -> Identity | None:
    """Like get_identity but returns None instead of raising."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    try:
        return verify_token(parts[1].strip())
    except TokenVerificationError:
        return None
