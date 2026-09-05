"""Adapter-level exceptions for upstream store integrations."""


class AdapterError(Exception):
    """Base exception for all adapter errors."""


class AdapterTimeout(AdapterError):
    """Raised when the upstream store does not respond in time."""


class RateLimited(AdapterError):
    """Raised when the upstream store returns a 429 rate-limit response."""


class AuthError(AdapterError):
    """Raised when the upstream store rejects our credentials."""


class StoreNotFoundError(AdapterError):
    """Raised when the requested store or product does not exist."""
