"""Safe arithmetic utilities.

Pure functions that never raise on domain errors; callers receive sentinel
values so they can decide how to handle (or propagate) without crashing.
"""

from __future__ import annotations


def safe_divide(a: float | int, b: float | int) -> float:
    """Return a / b, or 0.0 if b is zero (never raises).

    This is a pure function. Zero-divisor returns the float sentinel 0.0
    so that callers never crash on division by zero.
    """
    if b == 0:
        return 0.0
    return a / b
