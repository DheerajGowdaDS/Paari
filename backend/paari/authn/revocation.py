"""JWT revocation list.

For the demo this is an in-memory set of revoked jti values, consulted on
every request. Production replacement: Redis-backed SET with TTL equal to the
token's remaining lifetime, or a database-backed `jwt_revocations` table.
"""

from __future__ import annotations

import time

# In-memory store: jti -> expiry (unix seconds). Checked on every request.
_revoked: dict[str, int] = {}


def revoke(jti: str, expires_at: int | None = None) -> None:
    """Revoke a token immediately."""
    _revoked[jti] = expires_at if expires_at is not None else int(time.time()) + 3600


def is_revoked(jti: str) -> bool:
    """Return True if the token has been revoked (or expired)."""
    expires_at = _revoked.get(jti)
    if expires_at is None:
        return False
    if expires_at < int(time.time()):
        # Auto-purge expired revocations.
        _revoked.pop(jti, None)
        return False
    return True


def revoke_all_for(agent_id: str, token_jtis: list[str]) -> None:
    """Revoke every token issued to an agent (suspension)."""
    for jti in token_jtis:
        revoke(jti)


def purge_expired() -> int:
    """Remove expired revocation entries. Returns count purged."""
    now = int(time.time())
    stale = [jti for jti, exp in _revoked.items() if exp < now]
    for jti in stale:
        _revoked.pop(jti, None)
    return len(stale)
