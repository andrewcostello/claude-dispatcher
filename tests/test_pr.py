"""Unit tests for pr.raise_pr's PR-number parsing (PRF-2)."""

from __future__ import annotations

import pytest

from claude_dispatcher import pr as pr_mod


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/o/r/pull/42", 42),
        ("https://github.com/o/r/pull/42/", 42),  # trailing slash tolerated
        ("https://github.com/o/r/pull/smoke-x", None),  # non-numeric tail
        ("https://example.com/merge_requests", None),
        ("https://github.com/o/r/pull/0", 0),
    ],
)
def test_pr_number_from_url(url: str, expected) -> None:
    assert pr_mod._pr_number_from_url(url) == expected
