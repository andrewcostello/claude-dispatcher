"""The dispatcher's fallback commit names the Jira ticket.

evenplay-mono's check-jira-keys gate reads
`HasJiraKey(commit.Subject + "\\n" + commit.Body)` over every commit in the PR
range, so a `Jira: SMG-1234` trailer satisfies it. The dispatcher's own
fallback commit did not carry one: `_autocommit_message` has a jira_key
parameter, `_autocommit_worktree` forwards it, and the docstring says the
fallback "has to satisfy the same CI gate the agents' commits do" -- but the
single call site passed nothing, so the default None always won.

Measured 2026-09-04: the four keystone wallet PRs (#1565-#1568) were all red on
that gate with commits reading `[WAL-LEDGER-3] codex implementation`, and 38
dependent rows were waiting behind them.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from claude_dispatcher import spawn as spawn_mod


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True,
                       capture_output=True)
    (repo / "seed.txt").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True,
                   capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True,
                   capture_output=True)
    return repo


def _fake_codex(tmp_path: Path) -> str:
    """A codex that leaves the worktree dirty and writes no summary, which is
    what forces the dispatcher's fallback commit."""
    p = tmp_path / "fake_codex.py"
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import os, sys\n"
        "sys.stdin.read()\n"
        "open(os.path.join(os.getcwd(), 'work.txt'), 'w').write('work\\n')\n"
        "print('fake codex done')\n"
    )
    p.chmod(0o755)
    return f"{sys.executable} {p}"


def _spawn(tmp_path, monkeypatch, env_extra):
    repo = _repo(tmp_path)
    fake = _fake_codex(tmp_path)
    # AGENT_BINS holds a bare name; a two-word command would not exec, so the
    # script is made directly executable and registered by path.
    script = fake.split()[-1]
    monkeypatch.setitem(spawn_mod.AGENT_BINS, "codex", script)
    env = {"SUMMARY_PATH": str(tmp_path / "runs" / "summary.md"),
           "TASK_KEY": "WAL-LEDGER-3", **env_extra}
    spawn_mod.spawn_agent(agent="codex", cwd=repo, env=env, prompt="p")
    return subprocess.run(["git", "log", "-1", "--format=%B"], cwd=repo,
                          capture_output=True, text=True).stdout


def test_the_fallback_commit_carries_the_jira_trailer(tmp_path, monkeypatch):
    """End-to-end through spawn_agent, because the defect was in the WIRING:
    every unit below this already handled jira_key correctly."""
    msg = _spawn(tmp_path, monkeypatch, {"JIRA_KEY": "SMG-4246"})
    assert "WAL-LEDGER-3" in msg, msg
    assert "Jira: SMG-4246" in msg, msg


def test_it_matches_what_the_ci_gate_looks_for(tmp_path, monkeypatch):
    """The gate's own pattern: `(?i)\\b(SMG|...)[-_ ]?(\\d+)\\b` over subject +
    body. Asserting the literal trailer alone would not prove the key is
    findable where the gate looks."""
    msg = _spawn(tmp_path, monkeypatch, {"JIRA_KEY": "SMG-4246"})
    assert re.search(r"(?i)\b(SMG)[-_ ]?(\d+)\b", msg), msg


def test_no_jira_key_leaves_the_message_alone(tmp_path, monkeypatch):
    """Rows without a tracker key must not grow an empty trailer -- a bare
    `Jira:` would satisfy nothing and confuse the gate's hint output."""
    msg = _spawn(tmp_path, monkeypatch, {})
    assert "Jira" not in msg, msg
    assert "WAL-LEDGER-3" in msg, msg


def test_build_env_publishes_the_key_for_the_spawn_to_read(tmp_path):
    env = spawn_mod.build_env(
        base_env={}, task_key="T-1", summary_path=tmp_path / "s.md",
        run_id="r", max_iterations=1, financial_paths="", jira_key="SMG-9")
    assert env["JIRA_KEY"] == "SMG-9"
    blank = spawn_mod.build_env(
        base_env={}, task_key="T-1", summary_path=tmp_path / "s.md",
        run_id="r", max_iterations=1, financial_paths="", jira_key="  ")
    assert "JIRA_KEY" not in blank, "a blank key must not be published"


def test_the_orchestrator_supplies_the_row_s_key() -> None:
    """The last hop. Sealed on source because the alternative is standing up a
    whole task dispatch; safe here only because there is exactly ONE build_env
    call in the module, which the count asserts -- a regex that silently
    matched a second call site is how PR #99's first seal passed while the
    cascade stayed broken."""
    import inspect
    from claude_dispatcher import orchestrator as orch
    calls = re.findall(r"build_env\(\n(.*?)\n    \)", inspect.getsource(orch),
                       re.DOTALL)
    assert len(calls) == 1, f"expected one build_env call, found {len(calls)}"
    assert "jira_key=" in calls[0], calls[0]
