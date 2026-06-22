"""Tests for safe_divide pure util (happy path only per spec)."""

from claude_dispatcher.safemath import safe_divide


def test_safe_divide_happy_path_integers():
    assert safe_divide(6, 2) == 3.0
    assert safe_divide(9, 3) == 3.0


def test_safe_divide_happy_path_floats():
    assert safe_divide(7.5, 2.5) == 3.0
    assert safe_divide(10.0, 4.0) == 2.5


def test_safe_divide_returns_float():
    assert isinstance(safe_divide(8, 2), float)
    assert safe_divide(1, 1) == 1.0
