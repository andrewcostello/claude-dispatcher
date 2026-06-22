"""Safe arithmetic helpers for dispatcher utilities."""

from __future__ import annotations


def safe_divide(a: float, b: float) -> float:
    """Return ``a / b``, or ``0.0`` when ``b`` is zero."""
    if b == 0:
        return 0.0
    return a / b