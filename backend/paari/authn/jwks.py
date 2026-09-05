"""RS256 JWT keypair management (JWKS-compatible)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_KEYS_DIR = Path(__file__).resolve().parent / "keys"
_PRIVATE_PATH = _KEYS_DIR / "paari_private.pem"
_PUBLIC_PATH = _KEYS_DIR / "paari_public.pem"


def _ensure_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Load the keypair, generating it on first use if absent."""
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)
    if not (_PRIVATE_PATH.exists() and _PUBLIC_PATH.exists()):
        from paari.seed import _generate_keypair

        _generate_keypair()
    private_pem = _PRIVATE_PATH.read_bytes()
    public_pem = _PUBLIC_PATH.read_bytes()
    private_key = serialization.load_pem_private_key(private_pem, password=None)
    public_key = serialization.load_pem_public_key(public_pem)
    if not isinstance(private_key, rsa.RSAPrivateKey) or not isinstance(public_key, rsa.RSAPublicKey):
        raise RuntimeError("Paari keypair is not an RSA keypair")
    return private_key, public_key


def get_private_key() -> rsa.RSAPrivateKey:
    return _ensure_keypair()[0]


def get_public_key() -> rsa.RSAPublicKey:
    return _ensure_keypair()[1]


def jwks() -> dict[str, Any]:
    """Return the public key as a JWKS document."""
    public_key = get_public_key()
    numbers = public_key.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "paari-key-1",
                "n": _int_to_base64url(numbers.n),
                "e": _int_to_base64url(numbers.e),
            }
        ]
    }


def get_public_key_pem() -> bytes:
    """Return the public key in PEM (SubjectPublicKeyInfo) form."""
    return get_public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _int_to_base64url(value: int) -> str:
    """Encode an integer as base64url without padding (JWKS standard)."""
    import base64

    byte_length = (value.bit_length() + 7) // 8
    raw = value.to_bytes(byte_length, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
