"""JWKS endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from paari.authn.jwks import jwks

router = APIRouter(tags=["jwks"])


@router.get("/.well-known/jwks.json")
async def jwks_endpoint() -> dict:
    return jwks()
