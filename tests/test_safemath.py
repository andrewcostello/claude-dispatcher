"""Tests for safe_divide: happy-path division and the zero-divisor contract.

The PRD's single BLOCKING acceptance criterion for ``safe_divide`` is that a
zero divisor must be surfaced loudly — it raises ``ValueError`` rather than
returning a sentinel (``0.0``/``None``/``inf``) that would silently corrupt
downstream math. The original suite asserted only the two happy-path cases,
so it passed green against a defective implementation that returned ``0.0``.
These zero-divisor tests close that gap (FIX-2).
"""

from __future__ import annotations

import pytest

from claude_dispatcher.safemath import safe_divide


def test_safe_divide_six_by_two() -> None:
    assert safe_divide(6, 2) == 3.0


def test_safe_divide_nine_by_three() -> None:
    assert safe_divide(9, 3) == 3.0


def test_safe_divide_by_zero_raises_value_error() -> None:
    """FIX-2: a zero divisor MUST halt loudly, not return a sentinel.

    Root cause of the original gap: the suite exercised only happy-path
    division, so the implementation's ``if b == 0: return 0.0`` shortcut went
    untested and the suite stayed green against a defective implementation.
    The contract requires ``ValueError("division by zero")`` instead.
    """
    with pytest.raises(ValueError, match="division by zero"):
        safe_divide(1.0, 0)


@pytest.mark.parametrize("numerator", [0.0, -5.0, 1e9, 7])
def test_safe_divide_by_zero_raises_for_every_numerator(numerator: float) -> None:
    """The zero-divisor contract holds for every ``a`` — including 0/0."""
    with pytest.raises(ValueError, match="division by zero"):
        safe_divide(numerator, 0)


def test_safe_divide_by_negative_zero_raises() -> None:
    """``-0.0 == 0`` in Python, so a negative-zero divisor must also raise."""
    with pytest.raises(ValueError, match="division by zero"):
        safe_divide(3.0, -0.0)
