"""Pure numeric utilities for the dispatcher.

Currently provides :func:`clamp`, a total order bounding function with no
side effects.
"""

from __future__ import annotations


def clamp(value, lo, hi):
    """Return ``value`` bounded to the closed interval ``[lo, hi]``.

    The implementation is exactly ``max(lo, min(value, hi))`` as specified.
    Works for any values supporting ``<`` / ``>`` comparison (ints, floats,
    Decimals, etc.). If ``lo > hi`` the result is ``lo`` (per the formula).
    """
    return max(lo, min(value, hi))
