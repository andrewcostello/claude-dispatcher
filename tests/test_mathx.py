"""Tests for the pure clamp utility in claude_dispatcher.mathx.

Covers the four required cases: below, within, above, and lo == hi.
"""

from claude_dispatcher.mathx import clamp


def test_clamp_below_lo():
    assert clamp(5, 10, 20) == 10
    assert clamp(-3, 0, 100) == 0


def test_clamp_within_range():
    assert clamp(15, 10, 20) == 15
    assert clamp(10, 10, 20) == 10  # boundary
    assert clamp(20, 10, 20) == 20  # boundary
    assert clamp(0.5, 0.0, 1.0) == 0.5


def test_clamp_above_hi():
    assert clamp(25, 10, 20) == 20
    assert clamp(101, 0, 100) == 100


def test_clamp_lo_equals_hi():
    assert clamp(10, 10, 10) == 10
    assert clamp(5, 10, 10) == 10
    assert clamp(15, 10, 10) == 10
    assert clamp(10.0, 10, 10) == 10
