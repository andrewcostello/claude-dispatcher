"""The rotation, driven through the real dispatch loop.

The pool's own seals prove `next_account` spreads and `penalize` sits an account
out; the wiring seals prove a selected account reaches the CLI. NEITHER proves
the thing the feature is for: that a quota 429 causes the retry to land on a
DIFFERENT subscription.

That integration is the seam this repository has repeatedly found vacuous — a
mechanism built, sealed in parts, and never once exercised end to end. So this
runs `orchestrator.execute` with a spawn that returns a real 429 envelope and
watches which config dir each attempt is handed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from claude_dispatcher import orchestrator, spawn as spawn_mod
from claude_dispatcher.cli import build_parser

#: The envelope the CLI really emits on a quota refusal — the same shape as the
#: live 529 recorded in `spawn_failure`'s docstring, with the status changed.
#: An earlier version of this fixture embedded "API Error: 429" in `result`,
#: which `classify` does not read: it returned QUALITY/CASCADE, the rotation
#: never fired, and the cascade's own re-spawn happened to draw the next account
#: — so the headline row below passed for entirely the wrong reason. The row
#: that caught it is `test_the_rotation_is_journaled...`.
QUOTA_ENVELOPE = json.dumps({
    "type": "result", "is_error": True,
    "api_error_status": 429,
    "terminal_reason": "api_error",
    "result": "429 rate_limit_error: quota exceeded",
})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)],
                   check=True, capture_output=True)
    for k, v in (("user.email", "t@t"), ("user.name", "T")):
        subprocess.run(["git", "config", k, v], cwd=tmp_path, check=True,
                       capture_output=True)
    roles = tmp_path / ".claude" / "workflow" / "roles"
    roles.mkdir(parents=True)
    (roles / "tasker.md").write_text("# Tasker stub", encoding="utf-8")
    (tmp_path / "tasks.yaml").write_text(
        "project: TEST\nepic: ROT\ntasks:\n"
        "  - key: ROT-1\n    summary: \"rotation smoke\"\n"
        "    description: \"exercise the quota rotation\"\n"
        "    type: Task\n    estimate: 5m\n"
        "    labels: [size:XS, area:smoke]\n    agent: claude\n",
        encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True,
                   capture_output=True)
    return tmp_path


def _profile(repo: Path, names: list[str],
             weights: dict[str, int] | None = None) -> Path:
    rows = ""
    for n in names:
        d = repo / f"cfg-{n}"
        d.mkdir(exist_ok=True)
        w = (weights or {}).get(n, 1)
        rows += f"    - name: {n}\n      config_dir: {d}\n      weight: {w}\n"
    p = repo / "machine.yaml"
    p.write_text("manual:\n  claude_accounts:\n" + rows)
    return p


def _args(repo: Path, profile: Path, **extra) -> Any:
    argv = [
        "run", str(repo / "tasks.yaml"), "--mode", "unattended",
        "--max-parallel", "1", "--run-id", "rot-test",
        "--runs-dir", str(repo / "_runs"),
        "--worktree-base", str(repo.parent / "wt-rot"),
        "--claude-bin", sys.executable,
        "--cross-family-panel", "never",
        # The verifier re-spawns the implementer; an extra attempt would be
        # indistinguishable from a rotation in `seen`.
        "--skip-verification",
        "--claude-accounts-file", str(profile),
        "--claude-extra-args=--permission-mode bypassPermissions",
    ]
    for k, v in extra.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    return build_parser().parse_args(argv)


def _install_spawn(monkeypatch, outcomes: list[str]) -> list[str | None]:
    """Record the config dir of each attempt; return `outcomes` in order.

    "quota" -> a 429 envelope with a non-zero exit; "ok" -> a Done summary and a
    real commit, so the run can reach a terminal state.
    """
    seen: list[str | None] = []
    calls = {"n": 0}

    def fake(*, agent, claude_bin, cwd, env, prompt, model=None, effort=None,
             extra_args=None, timeout_seconds=3600, **kw):
        seen.append(kw.get("config_dir"))
        i = min(calls["n"], len(outcomes) - 1)
        calls["n"] += 1
        sp = Path(env["SUMMARY_PATH"])
        sp.parent.mkdir(parents=True, exist_ok=True)
        if outcomes[i] == "quota":
            return spawn_mod.SpawnResult(exit_code=1, summary_path=sp,
                                         stdout=QUOTA_ENVELOPE, stderr="")
        sp.write_text("**Status:** Done\n\n## What landed\nwork\n", encoding="utf-8")
        (Path(cwd) / f"out-{calls['n']}.txt").write_text("done\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=cwd, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-q", "-m", f"work {calls['n']}"], cwd=cwd,
                       check=False, capture_output=True)
        return spawn_mod.SpawnResult(exit_code=0, summary_path=sp, stdout="ok",
                                     stderr="")

    monkeypatch.setattr(spawn_mod, "spawn_agent", fake)
    return seen


def test_a_quota_429_retries_on_a_DIFFERENT_subscription(
    repo: Path, monkeypatch
) -> None:
    """The whole feature, end to end.

    Measured under: delete the rotation branch from the spawn loop and this
    reddens with one attempt; keep the branch but skip `penalize` and it reddens
    because both attempts draw the same account.
    """
    profile = _profile(repo, ["a", "b"])
    seen = _install_spawn(monkeypatch, ["quota", "ok"])
    orchestrator.execute(_args(repo, profile))
    assert len(seen) == 2, f"expected a retry after the 429, got {seen}"
    assert seen[0] is not None and seen[1] is not None
    assert seen[0] != seen[1], f"retried on the SAME account: {seen}"


def test_the_rotation_stops_when_every_account_is_exhausted(
    repo: Path, monkeypatch
) -> None:
    """Two accounts give exactly one rotation. A third attempt would be spent
    against a pool already known to be out — the retry budget is len(pool)-1,
    not unbounded.

    Measured under: use `len(pool)` as the budget and this reddens with a third
    attempt.
    """
    profile = _profile(repo, ["a", "b"])
    seen = _install_spawn(monkeypatch, ["quota"])
    orchestrator.execute(_args(repo, profile))
    assert len(seen) == 2, f"expected exactly one rotation, got {len(seen)}: {seen}"
    assert len(set(seen)) == 2, "the one rotation must use the other account"


def test_a_single_account_pool_does_not_rotate(repo: Path, monkeypatch) -> None:
    """One subscription has nowhere to rotate to, so a 429 must fall through to
    the existing park-and-retry-later rather than re-spending on the same
    exhausted account.

    Measured under: allow a rotation when the pool holds one account and this
    reddens.
    """
    profile = _profile(repo, ["only"])
    seen = _install_spawn(monkeypatch, ["quota"])
    orchestrator.execute(_args(repo, profile))
    assert len(seen) == 1, f"a single-account pool rotated: {seen}"


def test_the_rotation_is_journaled_with_the_account_that_ran_out(
    repo: Path, monkeypatch
) -> None:
    """An operator seeing a slow run needs to know WHICH subscription is out.
    Measured under: drop the event payload and this reddens.
    """
    profile = _profile(repo, ["a", "b"])
    _install_spawn(monkeypatch, ["quota", "ok"])
    orchestrator.execute(_args(repo, profile))
    events = [json.loads(l) for l in
              (repo / "_runs" / "rot-test" / "journal.jsonl").read_text().splitlines()
              if l.strip()]
    rotations = [e for e in events
                 if (e.get("payload") or {}).get("quota_rotation")]
    assert rotations, "the rotation was not journaled"
    payload = rotations[0]["payload"]
    assert payload["claude_account"] in ("a", "b")
    assert payload["api_error_status"] == 429


def test_the_account_that_ran_the_task_is_recorded_on_the_row(
    repo: Path, monkeypatch
) -> None:
    """Cost attribution: `cost_usd` across several subscriptions is one number
    nobody can separate afterwards without this.

    Measured under: drop the `claude_account` row stamp and this reddens.
    """
    from claude_dispatcher import yaml_io

    profile = _profile(repo, ["a", "b"])
    _install_spawn(monkeypatch, ["ok"])
    orchestrator.execute(_args(repo, profile))
    row = yaml_io.load(repo / "tasks.yaml")["tasks"][0]
    assert row.get("claude_account") in ("a", "b"), row.get("claude_account")


def test_no_pool_leaves_the_spawn_exactly_as_before(repo: Path, monkeypatch) -> None:
    """The back-compat property, driven through the real loop: with no accounts
    configured the spawn is handed NO config dir at all.
    """
    profile = repo / "empty.yaml"
    profile.write_text("manual:\n")
    seen = _install_spawn(monkeypatch, ["ok"])
    orchestrator.execute(_args(repo, profile))
    assert seen == [None], seen


def test_the_exhausted_account_is_not_handed_straight_back(
    repo: Path, monkeypatch
) -> None:
    """`penalize` is what stops a rotation returning to the account that just
    reported 429 — and with EQUAL weights it is invisible, because round-robin
    advances on its own. It only becomes observable when the weighting would
    otherwise pick the same account again, which is the real pool's shape: a
    20x seat draws four times as often as a 5x one.

    So: a heavily-weighted account fails, and the retry must land on the light
    one anyway.

    Measured under: drop `pool.penalize(...)` and this reddens while every other
    row here stays green — the gap that mutation exposed.
    """
    profile = _profile(repo, ["big", "small"], weights={"big": 10, "small": 1})
    seen = _install_spawn(monkeypatch, ["quota", "ok"])
    orchestrator.execute(_args(repo, profile))
    assert len(seen) == 2, seen
    assert Path(seen[0]).name == "cfg-big", "the heavy account should draw first"
    assert Path(seen[1]).name == "cfg-small", (
        "the retry returned to the account that just ran out of quota")
