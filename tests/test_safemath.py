"""Tests for safe_divide happy-path division."""

from __future__ import annotations

from claude_dispatcher.safemath import safe_divide


def test_safe_divide_six_by_two() -> None:
    assert safe_divide(6, 2) == 3.0


def test_safe_divide_nine_by_three() -> None:
    assert safe_divide(9, 3) == 3.0