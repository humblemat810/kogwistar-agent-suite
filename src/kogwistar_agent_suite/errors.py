"""Suite-specific implementation errors."""

from __future__ import annotations


class SuiteImplementationUnavailable(RuntimeError):
    """Raised when an explicitly selected implementation is unavailable."""
