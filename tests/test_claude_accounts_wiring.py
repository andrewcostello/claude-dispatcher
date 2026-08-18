"""Seals for WHERE the account reaches: the two spawn paths and the panel seat.

The pool is inert unless the selected account actually reaches the CLI, and the
mechanism is a single env var — so these rows read the environment a spawn would
really have been given.

The back-compat row is load-bearing. `spawn_agent` omits the kwarg entirely when
no account is drawn, because 22 test doubles across 16 files pin its exact
signature. Widening them to `**kwargs` was the alternative and is worse: a double
that accepts any argument cannot catch a bad call.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

from claude_dispatcher import (
    claude_accounts as ca,
    cross_family_reviewer as cfr,
    orchestrator as orch,
    spawn as spawn_mod,
)

ENV = ca.CONFIG_DIR_ENV


class _Recorder:
    """Stands in for subprocess.run and keeps the environment it was handed."""

    def __init__(self) -> None:
        self.env: dict[str, str] = {}
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        self.env = dict(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout='{"result": "ok"}', stderr="")


def _spawn(tmp_path: Path, monkeypatch, **kw):
    rec = _Recorder()
    monkeypatch.setattr(spawn_mod.subprocess, "run", rec)
    env = {"SUMMARY_PATH": str(tmp_path / "s.md"), "TASK_KEY": "T-1", "PATH": "/usr/bin"}
    spawn_mod.spawn_claude(claude_bin="claude", cwd=tmp_path, env=env,
                           prompt="p", **kw)
    return rec


def test_the_selected_account_reaches_the_CLI(tmp_path: Path, monkeypatch) -> None:
    """The only thing that makes the pool do anything.

    Measured under: drop the assignment in `spawn_claude` and this reddens.
    """
    rec = _spawn(tmp_path, monkeypatch, config_dir="/home/u/.claude-work")
    assert rec.env[ENV] == "/home/u/.claude-work"


def test_no_account_leaves_the_ambient_login(tmp_path: Path, monkeypatch) -> None:
    """No pool must be the world before the pool: the var is ABSENT, not empty.
    An empty CLAUDE_CONFIG_DIR is not "the ambient login" — it is a config dir
    named "", which has no credentials in it.

    Measured under: set the var unconditionally and this reddens.
    """
    rec = _spawn(tmp_path, monkeypatch)
    assert ENV not in rec.env


def test_the_account_does_not_disturb_the_api_key_stripping(
    tmp_path: Path, monkeypatch
) -> None:
    """Subscription billing still depends on the metered keys being removed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-survive")
    rec = _Recorder()
    monkeypatch.setattr(spawn_mod.subprocess, "run", rec)
    spawn_mod.spawn_claude(
        claude_bin="claude", cwd=tmp_path, prompt="p",
        env={"SUMMARY_PATH": str(tmp_path / "s.md"),
             "ANTHROPIC_API_KEY": "sk-should-not-survive"},
        config_dir="/home/u/.claude-work")
    assert "ANTHROPIC_API_KEY" not in rec.env
    assert rec.env[ENV] == "/home/u/.claude-work"


def test_spawn_agent_omits_the_kwarg_when_no_account_is_drawn(
    tmp_path: Path,
) -> None:
    """Back-compat, stated as a property rather than left to luck: with no
    account, `spawn_agent` must call `spawn_claude` WITHOUT `config_dir`, so a
    double pinning the old signature still works.

    Measured under: pass `config_dir=None` unconditionally and this reddens with
    the same TypeError the 127-failure run produced.
    """
    seen = {}

    def strict_double(claude_bin, cwd, env, prompt, extra_args=None,
                      timeout_seconds=3600):
        seen["called"] = True
        return SimpleNamespace(exit_code=0)

    import claude_dispatcher.spawn as s
    original = s.spawn_claude
    try:
        s.spawn_claude = strict_double
        s.spawn_agent(agent="claude", cwd=tmp_path,
                      env={"SUMMARY_PATH": str(tmp_path / "out" / "s.md")},
                      prompt="p")
    finally:
        s.spawn_claude = original
    assert seen.get("called") is True


def test_a_non_claude_agent_is_not_given_a_claude_account(tmp_path: Path) -> None:
    """`CLAUDE_CONFIG_DIR` means nothing to codex or grok, and an endpoint agent
    is billed by the provider key in its env. Only the claude branch forwards it.
    """
    src = inspect.getsource(spawn_mod.spawn_agent)
    claude_branch = src.split('if agent in endpoint_agents_mod')[0]
    assert "config_dir" in claude_branch
    after = src.split('if agent in endpoint_agents_mod')[1]
    assert "config_dir" not in after, (
        "a non-claude spawn is being handed a Claude account")


# --------------------------------------------------------------------------
# The panel seat
# --------------------------------------------------------------------------

def test_a_claude_SEAT_bills_its_assigned_account(monkeypatch) -> None:
    """Seats are a large share of a run's spend — every task reaching the panel
    pays for one — so a pool that rotated implementers alone spreads half the
    load.

    Measured under: drop `config_dir` from `_seat_env` and this reddens.
    """
    r = cfr.ClaudeReviewer(config_dir="/home/u/.claude-work")
    assert r._seat_env()[ENV] == "/home/u/.claude-work"


def test_a_seat_with_no_account_leaves_the_ambient_login() -> None:
    assert ENV not in cfr.ClaudeReviewer()._seat_env()


def test_a_seat_env_still_strips_metered_credentials(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "should-not-survive")
    env = cfr.ClaudeReviewer(config_dir="/x")._seat_env()
    assert "ANTHROPIC_AUTH_TOKEN" not in env


def test_seats_are_assigned_round_robin_and_only_claude_ones(
    tmp_path: Path,
) -> None:
    """Measured under: assign to every seat regardless of family and this
    reddens — a codex seat would consume a rotation slot it cannot use.
    """
    pool = ca.AccountPool([ca.ClaudeAccount("a", tmp_path / "a"),
                           ca.ClaudeAccount("b", tmp_path / "b")])
    cfg = SimpleNamespace(account_pool=pool)
    seats = [cfr.ClaudeReviewer(), SimpleNamespace(family="codex"),
             cfr.ClaudeReviewer()]
    orch._assign_accounts_to_seats(cfg, seats)
    assert seats[0].config_dir == str((tmp_path / "a"))
    assert seats[2].config_dir == str((tmp_path / "b"))
    assert not hasattr(seats[1], "config_dir")


def test_seat_assignment_is_a_no_op_without_a_pool() -> None:
    seat = cfr.ClaudeReviewer()
    orch._assign_accounts_to_seats(SimpleNamespace(account_pool=None), [seat])
    assert seat.config_dir is None
    orch._assign_accounts_to_seats(
        SimpleNamespace(account_pool=ca.AccountPool()), [seat])
    assert seat.config_dir is None


# --------------------------------------------------------------------------
# Rotation budget
# --------------------------------------------------------------------------

@pytest.mark.parametrize("size, expected", [(0, 0), (1, 0), (2, 1), (3, 2)])
def test_the_rotation_budget_is_the_rest_of_the_pool(
    tmp_path: Path, size: int, expected: int
) -> None:
    """One account cannot rotate anywhere, and N accounts give N-1 alternatives.
    A budget larger than that would re-try accounts already known exhausted.

    Measured under: use `len(pool)` and this reddens at every size.
    """
    pool = ca.AccountPool([ca.ClaudeAccount(str(i), tmp_path / str(i))
                           for i in range(size)])
    assert orch._quota_rotations_available(pool) == expected


def test_no_pool_means_no_rotations() -> None:
    assert orch._quota_rotations_available(None) == 0


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def _profile_with(tmp_path: Path, rows: str) -> Path:
    p = tmp_path / "machine.yaml"
    p.write_text("schema_version: 1\nmanual:\n  claude_accounts:\n" + rows)
    return p


def test_doctor_reports_each_account_without_printing_a_token(
    tmp_path: Path, capsys
) -> None:
    """An operator needs to see WHICH accounts are usable before a run, not
    discover a stale login as a mid-run auth failure that looks like any other.

    This row exercises the reporter directly, so it does NOT prove `execute`
    calls it — the row below does that, and was added because a mutation
    deleting the call fired nothing here.
    """
    import json
    from claude_dispatcher import doctor

    good = tmp_path / "good"
    good.mkdir()
    (good / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "subscriptionType": "max", "rateLimitTier": "t20x",
        "accessToken": "sk-SECRET", "expiresAt": 99999999999999}}))
    profile = _profile_with(tmp_path, f"    - name: personal\n"
                                      f"      config_dir: {good}\n"
                                      f"    - name: work\n"
                                      f"      config_dir: {tmp_path}/absent\n")
    doctor._print_accounts(profile)
    out = capsys.readouterr().out
    assert "personal" in out and "max" in out and "t20x" in out
    assert "work" in out and "no credentials" in out
    assert "SECRET" not in out


def test_doctor_says_nothing_when_no_pool_is_configured(
    tmp_path: Path, capsys
) -> None:
    """The default machine has no pool, and a "0 accounts" line on every box is
    noise. Measured under: print a header unconditionally and this reddens.
    """
    from claude_dispatcher import doctor

    (tmp_path / "machine.yaml").write_text("schema_version: 1\n")
    doctor._print_accounts(tmp_path / "machine.yaml")
    assert capsys.readouterr().out == ""


def test_doctor_reports_a_malformed_pool_instead_of_crashing(
    tmp_path: Path, capsys
) -> None:
    """`load_accounts` raises on a bad entry by design. `doctor` is the command
    an operator runs to FIND that, so it must print it rather than traceback.
    """
    from claude_dispatcher import doctor

    doctor._print_accounts(_profile_with(tmp_path, "    - name: broken\n"))
    out = capsys.readouterr().out
    assert "✗" in out and "config_dir" in out


def test_doctor_flags_an_expired_login(tmp_path: Path, capsys) -> None:
    """Measured under: report `expired` without acting on it and this reddens —
    an expired account reads as healthy and the run blocks on it instead.
    """
    import json
    from claude_dispatcher import doctor

    d = tmp_path / "stale"
    d.mkdir()
    (d / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
        "subscriptionType": "max", "rateLimitTier": "t", "expiresAt": 1}}))
    doctor._print_accounts(
        _profile_with(tmp_path, f"    - name: stale\n      config_dir: {d}\n"))
    assert "EXPIRED" in capsys.readouterr().out


def test_doctor_actually_calls_the_account_report() -> None:
    """The reporter is worthless if `dispatcher doctor` never runs it, and the
    rows above call it directly so they cannot tell.

    AST, not a substring: a comment or an unused import satisfies a text search,
    which is the vacuity this repository's own seals were blocked for on
    2026-08-18.

    Measured under: delete the call from `execute` and this reddens.
    """
    import ast
    from claude_dispatcher import doctor

    tree = ast.parse(Path(doctor.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "execute")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_print_accounts" in called


def test_the_accounts_file_flag_reaches_the_pool(tmp_path: Path) -> None:
    """`_build_account_pool` reads `args.claude_accounts_file`. Without a flag
    setting it, that read is dead indirection that no run can exercise.

    Measured under: remove the CLI flag and this reddens at parse time; remove
    the getattr and it reddens on the pool contents.
    """
    from claude_dispatcher.cli import build_parser

    d = tmp_path / "acct"
    d.mkdir()
    profile = tmp_path / "alt.yaml"
    profile.write_text(
        f"manual:\n  claude_accounts:\n    - name: alt\n      config_dir: {d}\n")
    args = build_parser().parse_args(
        ["run", str(tmp_path / "tasks.yaml"),
         "--claude-accounts-file", str(profile)])
    assert args.claude_accounts_file == str(profile)
    pool = orch._build_account_pool(args)
    assert pool.names == ["alt"]


def test_the_selection_flag_restricts_the_pool(tmp_path: Path) -> None:
    """End to end: the flag parses, the profile loads, and the pool holds only
    the named accounts.

    Measured under: drop the `select` call from `_build_account_pool` and this
    reddens — the run would spend every account on the machine.
    """
    from claude_dispatcher.cli import build_parser

    for n in ("personal", "work"):
        (tmp_path / n).mkdir()
    profile = tmp_path / "machine.yaml"
    profile.write_text(
        "manual:\n  claude_accounts:\n"
        f"    - name: personal\n      config_dir: {tmp_path}/personal\n"
        f"    - name: work\n      config_dir: {tmp_path}/work\n")

    args = build_parser().parse_args(
        ["run", str(tmp_path / "tasks.yaml"),
         "--claude-accounts-file", str(profile),
         "--claude-accounts", "personal"])
    assert orch._build_account_pool(args).names == ["personal"]

    all_args = build_parser().parse_args(
        ["run", str(tmp_path / "tasks.yaml"),
         "--claude-accounts-file", str(profile)])
    assert orch._build_account_pool(all_args).names == ["personal", "work"]


def test_an_unknown_selected_account_stops_the_run(tmp_path: Path) -> None:
    """Fatal at config time, before any spend. Measured under: swallow the
    ValueError and the run proceeds on accounts the operator did not choose.
    """
    from claude_dispatcher.cli import build_parser

    (tmp_path / "personal").mkdir()
    profile = tmp_path / "machine.yaml"
    profile.write_text(
        "manual:\n  claude_accounts:\n"
        f"    - name: personal\n      config_dir: {tmp_path}/personal\n")
    args = build_parser().parse_args(
        ["run", str(tmp_path / "tasks.yaml"),
         "--claude-accounts-file", str(profile),
         "--claude-accounts", "personl"])
    with pytest.raises(ValueError, match="unknown claude account"):
        orch._build_account_pool(args)
