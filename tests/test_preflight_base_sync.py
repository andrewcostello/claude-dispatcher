"""Seals for the base-branch sync preflight.

The trap: task worktrees fork from the LOCAL base ref and the verifier diffs
against it, so a base behind its remote yields a truncated diff — work the
branch never did reads as work it undid — and a complete task returns
INCOMPLETE. Measured 2026-08-16 at 9 commits behind.

The load-bearing row is `..._not_in_this_clone`: comparing against
`origin/<base>` instead of the remote would report "in sync" in exactly that
case, because the tracking ref is only as fresh as the last fetch.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from claude_dispatcher import preflight


def _run(*args: str, cwd: Path) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run("git", "init", "-q", "-b", "main", cwd=path)
    _run("git", "config", "user.email", "t@t", cwd=path)
    _run("git", "config", "user.name", "t", cwd=path)
    return path


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    _run("git", "add", "-A", cwd=repo)
    _run("git", "commit", "-qm", name, cwd=repo)
    return _run("git", "rev-parse", "HEAD", cwd=repo)


def _pair(tmp_path: Path) -> tuple[Path, Path]:
    """An upstream repo and a clone of it, both on `main`."""
    up = _repo(tmp_path / "upstream")
    _commit(up, "seed")
    clone = tmp_path / "clone"
    _run("git", "clone", "-q", str(up), str(clone), cwd=tmp_path)
    _run("git", "config", "user.email", "t@t", cwd=clone)
    _run("git", "config", "user.name", "t", cwd=clone)
    return up, clone


def _check(repo: Path, base: str = "main"):
    warnings: list[str] = []
    checks: dict = {}
    preflight._check_base_branch_sync(repo, base, warnings, checks)
    return warnings, checks["base_branch_sync"]


def test_a_base_level_with_its_remote_is_silent(tmp_path: Path) -> None:
    _up, clone = _pair(tmp_path)
    warnings, entry = _check(clone)
    assert warnings == []
    assert entry["state"] == "in_sync" and entry["applicable"] is True


def test_a_base_BEHIND_its_remote_warns_with_the_count(tmp_path: Path) -> None:
    """The trap itself. Measured under: report `in_sync` on any difference and
    this reddens.
    """
    up, clone = _pair(tmp_path)
    _commit(up, "one")
    _commit(up, "two")
    _run("git", "fetch", "-q", "origin", cwd=clone)  # remote commits present
    warnings, entry = _check(clone)
    assert entry["state"] == "behind" and entry["behind"] == 2
    assert len(warnings) == 1
    assert "2 commit(s) behind" in warnings[0]
    assert "false INCOMPLETE" in warnings[0]


def test_the_remote_commit_not_in_this_clone_still_warns(tmp_path: Path) -> None:
    """The case a tracking-ref comparison CANNOT see: the clone has never
    fetched, so `origin/main` still points at the old commit and would compare
    equal. Reading the remote directly is the only way to catch it.

    Measured under: compare against `origin/<base>` instead of `ls-remote` and
    this reddens while every other row stays green.
    """
    up, clone = _pair(tmp_path)
    _commit(up, "one")
    assert _run("git", "rev-parse", "origin/main", cwd=clone) == \
        _run("git", "rev-parse", "main", cwd=clone), "tracking ref is stale"
    warnings, entry = _check(clone)
    assert entry["state"] == "behind_unfetched"
    assert len(warnings) == 1
    assert "not in this clone" in warnings[0] and "git fetch" in warnings[0]


def test_a_base_AHEAD_of_its_remote_is_silent(tmp_path: Path) -> None:
    """Unpushed local commits are the normal state of an integration branch and
    nothing the verifier can misread. Measured under: warn on any difference and
    this reddens — a check that fires on every ordinary run gets switched off.
    """
    _up, clone = _pair(tmp_path)
    _commit(clone, "local-only")
    warnings, entry = _check(clone)
    assert entry["state"] == "ahead" and warnings == []


def test_a_diverged_base_is_named_as_diverged(tmp_path: Path) -> None:
    up, clone = _pair(tmp_path)
    _commit(up, "theirs")
    _commit(clone, "mine")
    _run("git", "fetch", "-q", "origin", cwd=clone)
    warnings, entry = _check(clone)
    assert entry["state"] == "diverged"
    assert entry["ahead"] == 1 and entry["behind"] == 1
    assert "diverged" in warnings[0]


def test_a_repo_with_no_remote_is_a_named_skip(tmp_path: Path) -> None:
    """A local integration branch with no remote is the normal case here — it
    must not warn, and it must say WHY it did not compare.
    """
    repo = _repo(tmp_path / "solo")
    _commit(repo, "seed")
    warnings, entry = _check(repo)
    assert warnings == []
    assert entry["applicable"] is False
    assert "no remote" in entry["detail"]


def test_an_unreachable_remote_is_a_skip_not_a_failure(tmp_path: Path) -> None:
    """Offline must not stop a run. Measured under: turn the ls-remote failure
    into a warning or a raise and this reddens.
    """
    _up, clone = _pair(tmp_path)
    _run("git", "remote", "set-url", "origin",
         str(tmp_path / "does-not-exist"), cwd=clone)
    warnings, entry = _check(clone)
    assert warnings == []
    assert entry["applicable"] is False


def test_a_base_that_does_not_resolve_locally_is_a_skip(tmp_path: Path) -> None:
    _up, clone = _pair(tmp_path)
    warnings, entry = _check(clone, base="no-such-branch")
    assert warnings == [] and entry["applicable"] is False
    assert "does not resolve" in entry["detail"]


def test_the_check_is_wired_into_run_preflight() -> None:
    """A check nothing calls is not a check. AST, not a substring: a comment or
    an unused import satisfies a text search.
    """
    import ast

    tree = ast.parse(Path(preflight.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_preflight")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_check_base_branch_sync" in called


def test_a_HUNG_remote_read_is_a_skip_not_a_failure(tmp_path: Path, monkeypatch) -> None:
    """The other offline shape, and a different code path from an unreachable
    URL: `ls-remote` blocks until the timeout and RAISES rather than returning
    non-zero. A preflight that turned that into a warning would fire on every
    run behind a slow or firewalled remote; one that let it propagate would end
    the run outright.

    Measured under: warn from the timeout handler, or drop the handler, and this
    reddens. Added because a mutation on the raising branch fired no row — the
    unreachable-URL row above only ever exercises the returncode branch.
    """
    _up, clone = _pair(tmp_path)
    real = preflight._git

    def _slow(repo_root, *args, **kw):
        if args and args[0] == "ls-remote":
            raise subprocess.TimeoutExpired(cmd="git ls-remote", timeout=15)
        return real(repo_root, *args, **kw)

    monkeypatch.setattr(preflight, "_git", _slow)
    warnings, entry = _check(clone)
    assert warnings == []
    assert entry["applicable"] is False
    assert "could not read" in entry["detail"]
