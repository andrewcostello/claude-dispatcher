"""Agents build against a shared disk-backed cache, not per-task tmpfs dirs.

Measured 2026-09-04 from the run logs: every Go task invented its own
`GOCACHE` under /tmp -- `cx-luna-go-cache`, `codex-go-cache-WAL-LEDGER-3`,
`wal-settle-3-final-gocache` -- because the sandbox leaves /tmp as the only
obviously writable place. /tmp is tmpfs, so a cold Go build spends INODES: 91%
of 1,048,576 used, and at 94% the symptom was ~1,100 tests failing on OSError,
which reads exactly like a code regression rather than a full filesystem.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import spawn


def _env(tmp_path):
    return spawn.build_env(
        base_env={}, task_key="T-1", summary_path=tmp_path / "s.md",
        run_id="r", max_iterations=1, financial_paths="",
    )


def test_the_go_caches_are_named_and_off_tmpfs(tmp_path) -> None:
    env = _env(tmp_path)
    for var in ("GOCACHE", "GOMODCACHE"):
        assert var in env, f"{var} unset -- the agent picks, and picks /tmp"
        assert not env[var].startswith("/tmp/"), (var, env[var])


def test_the_cache_dirs_exist_before_the_agent_runs(
    tmp_path, monkeypatch,
) -> None:
    """A sandbox permits writing INSIDE a writable root, not creating the root,
    so an exported path that does not exist yet fails like no path at all.

    The cache root is redirected because the real one persists between runs:
    asserting against it passed with the mkdir DELETED, since an earlier call
    had already created the directories. A seal that a previous test satisfies
    is measuring history, not behaviour.
    """
    root = tmp_path / "fresh-cache"
    monkeypatch.setattr(spawn, "AGENT_BUILD_CACHE", root)
    assert not root.exists()
    env = _env(tmp_path)
    assert Path(env["GOCACHE"]).is_dir(), "GOCACHE not created"
    assert Path(env["GOMODCACHE"]).is_dir(), "GOMODCACHE not created"
    assert root in Path(env["GOCACHE"]).parents


def test_the_cache_is_shared_across_tasks(tmp_path) -> None:
    """Per-task caches are what made every task pay for a cold build. Go's
    build and module caches are both concurrency-safe."""
    a, b = _env(tmp_path), _env(tmp_path)
    assert a["GOCACHE"] == b["GOCACHE"]
    assert "T-1" not in a["GOCACHE"]


def test_codex_may_write_to_the_cache(tmp_path) -> None:
    """Exporting GOCACHE without granting the sandbox write access to it is
    worse than not exporting it: the build fails instead of falling back."""
    cmd = spawn._agent_argv(
        "codex", bin_="codex", cwd=tmp_path,
        prompt_file=tmp_path / "p.txt", model=None, prompt_text="x", effort=None,
        summary_dir=str(tmp_path / "runs"),
    )
    roots = [c for c in cmd if "writable_roots" in c]
    assert roots, cmd
    assert str(spawn.AGENT_BUILD_CACHE) in roots[0], roots[0]


def test_codex_still_gets_its_summary_dir(tmp_path) -> None:
    """The root that already had to be there. WAL-APPEND-3 wrote a correct
    DEVIATION and the sandbox destroyed it for want of this."""
    cmd = spawn._agent_argv(
        "codex", bin_="codex", cwd=tmp_path,
        prompt_file=tmp_path / "p.txt", model=None, prompt_text="x", effort=None,
        summary_dir="/some/runs/dir",
    )
    roots = [c for c in cmd if "writable_roots" in c][0]
    assert "/some/runs/dir" in roots, roots
