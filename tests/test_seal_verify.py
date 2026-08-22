"""Seal-inversion gate: partition, applicability, inversion + restore."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import seal_verify as sv


def _git(d: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Base: code.txt says 'broken', tests/run.sh is a trivial green suite.
    The suite command for all tests is `sh tests/run.sh`."""
    d = tmp_path / "seal-repo"
    (d / "tests").mkdir(parents=True)
    _git(d, "init", "-q", "-b", "main")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "T")
    (d / "code.txt").write_text("broken\n", encoding="utf-8")
    (d / "tests" / "run.sh").write_text("exit 0\n", encoding="utf-8")
    _git(d, "add", ".")
    _git(d, "commit", "-q", "-m", "base")
    _git(d, "checkout", "-q", "-b", "fix/seal")
    return d


def _commit_fix(d: Path, *, seal: str) -> None:
    """Branch commit: the fix (code.txt -> fixed) + a new suite body."""
    (d / "code.txt").write_text("fixed\n", encoding="utf-8")
    (d / "tests" / "run.sh").write_text(seal, encoding="utf-8")
    _git(d, "add", ".")
    _git(d, "commit", "-q", "-m", "fix + seal")


# --- applies -------------------------------------------------------------


def test_applies_to_fix_keys_and_labels() -> None:
    assert sv.applies("FIX-3", [])
    assert sv.applies("fix-12", None)
    assert sv.applies("SMG-1", ["size:S", "type:fix"])
    assert sv.applies("SMG-1", ["seal-check"])
    assert not sv.applies("SMG-1", ["size:S", "type:component"])
    assert not sv.applies("FEAT-2", [])


# --- partition -------------------------------------------------------------


def test_partition_splits_test_and_non_test(repo: Path) -> None:
    _commit_fix(repo, seal="grep -q fixed code.txt\n")
    tests, non_tests = sv.partition_changed(repo, "main")
    assert [p for _s, p in tests] == ["tests/run.sh"]
    assert [p for _s, p in non_tests] == ["code.txt"]


def test_partition_does_not_fail_open_on_bad_base(repo: Path) -> None:
    """RED — AMENDED BY P4, 2026-08-09 (was `test_partition_fails_open_on_
    bad_base`, which asserted `== ([], [])`).

    This row was the live seal that pinned the git-failure fail-open as
    intended, and closing that fail-open therefore required amending it. The
    ruling and its reasoning are in
    `tests/test_seal_verify_failopen.py`, RULINGS 1: an undecodable path
    blocks because "we learned that the change contains a file we cannot
    classify", while a git failure fails open because it "means we learned
    nothing" — and learned nothing is the weaker position, so the asymmetry
    runs the wrong way.

    `([], [])` is indistinguishable from a real, empty answer, and the caller
    reads it as one: `run_seal_inversion` turns it into "no test files
    changed — nothing claims to seal". A function that cannot say "git would
    not tell me" must not return a partition it does not have.

    The row does not name an exception class — the mechanism is the body
    author's — only that a bad base is signalled rather than answered, and
    that the signal names the ref, so an incidental `AttributeError` cannot
    satisfy it. The end-to-end consequence is sealed separately by
    `test_a_git_failure_is_not_a_change_with_no_tests_in_it`.

    Green when: a git failure is signalled. SEPARATE body change.
    Falsify: the good-base control below is a real partition in the same row.
    """
    try:
        answered = sv.partition_changed(repo, "no-such-ref")
    except Exception as exc:      # noqa: BLE001 — the class is not the policy
        assert "no-such-ref" in str(exc), (
            "a bad base was signalled by something that does not name it, so "
            f"this row cannot tell a refusal from a bug: {exc!r}"
        )
    else:
        pytest.fail(
            "git refused to say what the change contains and `partition_"
            f"changed` returned {answered!r} — the same value a change with "
            "no test files in it produces, which the caller reports as "
            "'nothing claims to seal'"
        )

    _commit_fix(repo, seal="grep -q fixed code.txt\n")
    tests, non_tests = sv.partition_changed(repo, "main")
    assert ([p for _s, p in tests], [p for _s, p in non_tests]) == (
        ["tests/run.sh"], ["code.txt"]), (
        "control: a base that exists must still be partitioned, or the "
        "assertion above would pass by the function refusing everything"
    )


# --- inversion -------------------------------------------------------------


def test_real_seal_passes_and_tree_restored(repo: Path) -> None:
    _commit_fix(repo, seal="grep -q fixed code.txt\n")
    res = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=30,
    )
    assert res.outcome == "passed"
    # Restore: the fix is back and the tree is clean.
    assert (repo / "code.txt").read_text() == "fixed\n"
    st = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                        capture_output=True, text=True)
    assert st.stdout.strip() == ""


def test_false_seal_fails(repo: Path) -> None:
    """The audit's false-passing-seal class: suite green with or without
    the fix. The gate must catch it."""
    _commit_fix(repo, seal="echo vacuous seal\nexit 0\n")
    res = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=30,
    )
    assert res.outcome == "failed"
    assert "do not pin the change" in res.detail
    assert (repo / "code.txt").read_text() == "fixed\n"  # still restored


def test_added_non_test_file_is_removed_during_inversion(repo: Path) -> None:
    (repo / "code.txt").write_text("fixed\n", encoding="utf-8")
    (repo / "helper.txt").write_text("new helper\n", encoding="utf-8")
    (repo / "tests" / "run.sh").write_text(
        "grep -q fixed code.txt && test -f helper.txt\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fix + helper + seal")

    res = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=30,
    )
    assert res.outcome == "passed"          # inverted run went red
    assert (repo / "helper.txt").exists()   # and the helper came back


def test_test_only_change_skips(repo: Path) -> None:
    (repo / "tests" / "run.sh").write_text("exit 0 # more\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "test-only")
    res = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=30,
    )
    assert res.outcome == "skipped"
    assert "no fix to invert" in res.detail


def test_no_test_change_skips(repo: Path) -> None:
    (repo / "code.txt").write_text("fixed\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "code only")
    res = sv.run_seal_inversion(
        worktree=repo, base="main", test_command="sh tests/run.sh",
        timeout_seconds=30,
    )
    assert res.outcome == "skipped"
    assert "nothing claims to seal" in res.detail
