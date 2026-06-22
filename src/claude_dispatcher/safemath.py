"""Safe arithmetic helpers for dispatcher utilities."""

from __future__ import annotations


def safe_divide(a: float, b: float) -> float:
    """Return ``a / b``.

    Raise ``ValueError("division by zero")`` when ``b`` is zero. A zero
    divisor signals a caller bug; returning a sentinel (``0.0``/``None``/
    ``inf``) would silently corrupt downstream math, so the pipeline must
    halt instead.
    """
    if b == 0:
        raise ValueError("division by zero")
    return a / b