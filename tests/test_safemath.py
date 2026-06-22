"""Tests for safe_divide division and the zero-divisor contract."""

from __future__ import annotations

import pytest

from claude_dispatcher.safemath import safe_divide


def test_safe_divide_six_by_two() -> None:
    assert safe_divide(6, 2) == 3.0


def test_safe_divide_nine_by_three() -> None:
    assert safe_divide(9, 3) == 3.0


def test_safe_divide_by_zero_raises_value_error() -> None:
    """FIX-1: a zero divisor MUST halt the pipeline, not return a sentinel.

    Root cause: the implementation did ``if b == 0: return 0.0``, which
    silently fabricates a result for a caller bug and lets it flow downstream
    into money math. The PRD's single hard contract requires
    ``ValueError("division by zero")`` instead.
    """
    with pytest.raises(ValueError, match="division by zero"):
        safe_divide(1.0, 0)


@pytest.mark.parametrize("numerator", [0.0, -5.0, 1e9])
def test_safe_divide_by_zero_raises_for_every_numerator(numerator: float) -> None:
    """The contract holds for every ``a`` — including ``a == 0`` (0/0)."""
    with pytest.raises(ValueError, match="division by zero"):
        safe_divide(numerator, 0)