"""Seals for `dispatcher init` — what WORKS, not what is installed.

`doctor.probe_binary` runs `shutil.which` and `--version`, so an
installed-but-logged-out CLI and an account over its monthly limit both report
a green tick and then fail at dispatch time, after spend. Measured 2026-08-30:
a reviewer seat returned UNAVAILABLE in ~4.5s for eleven consecutive cases and
read like a broken seat rather than the quota wall it was.

Every row here stubs the round trip. A test that spent real quota would be a
test nobody runs.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from claude_dispatcher import cross_family_reviewer as cfr
from claude_dispatcher import first_run


class _Seat(cfr.Reviewer):
    """A reviewer whose round trip is decided by the test."""

    def __init__(self, family: str, body: str | None = None,
                 error: str | None = None):
        super().__init__()
        self.family = family
        self.cli_bin = family
        self._body = body
        self._error = error

    def _invoke_cli(self, prompt: str) -> str:  # noqa: ARG002
        if self._error is not None:
            raise cfr.ReviewerUnavailable(self._error)
        return self._body or "## Verdict\nAPPROVE\n"


def _with_binaries(present: list[str]):
    return mock.patch(
        "claude_dispatcher.first_run.shutil.which",
        side_effect=lambda b: f"/usr/bin/{b}" if b in present else None,
    )


# --- the three states a tick cannot distinguish ------------------------------


def test_a_missing_binary_is_not_installed() -> None:
    with _with_binaries([]):
        probes = first_run.probe_families([_Seat("claude")])
    assert probes[0].installed is False
    assert probes[0].usable is False
    assert probes[0].state == "not installed"


def test_a_working_round_trip_is_usable() -> None:
    with _with_binaries(["claude"]):
        probes = first_run.probe_families([_Seat("claude")])
    assert probes[0].installed and probes[0].usable
    assert probes[0].state == "usable"


def test_an_installed_binary_over_its_limit_is_not_usable() -> None:
    """The exact failure of 2026-08-30. A tick said this was fine."""
    with _with_binaries(["claude"]):
        probes = first_run.probe_families([
            _Seat("claude", error="You've hit your monthly spend limit."),
        ])
    assert probes[0].installed is True, "the binary IS there"
    assert probes[0].usable is False
    assert "spend limit" in probes[0].reason


def test_an_installed_binary_not_logged_in_is_not_usable() -> None:
    with _with_binaries(["codex"]):
        probes = first_run.probe_families([
            _Seat("codex", error="Error: you are not logged in"),
        ])
    assert probes[0].installed and not probes[0].usable
    assert probes[0].reason == "not logged in"


def test_an_unrecognised_refusal_reports_its_first_line() -> None:
    """A marker list cannot be exhaustive, so an unknown refusal must still say
    something an operator can act on rather than a shrug."""
    with _with_binaries(["grok"]):
        probes = first_run.probe_families([
            _Seat("grok", error="socket hang up while contacting the API"),
        ])
    assert "socket hang up" in probes[0].reason


def test_a_binary_that_runs_but_says_nothing_parseable_is_not_usable() -> None:
    """Running is not the same as answering. A seat that cannot produce a
    verdict cannot seat a panel."""
    with _with_binaries(["claude"]):
        probes = first_run.probe_families([_Seat("claude", body="hello there")])
    assert probes[0].installed and not probes[0].usable
    assert "parseable" in probes[0].reason


# --- the verdict that matters ------------------------------------------------


def test_two_usable_families_can_seat_a_panel() -> None:
    r = first_run.FirstRunReport(families=[
        first_run.FamilyProbe("claude", "claude", installed=True, usable=True),
        first_run.FamilyProbe("codex", "codex", installed=True, usable=True),
    ])
    assert r.can_seat_a_panel is True


def test_one_usable_family_cannot() -> None:
    """Two is the bar `aggregate` sets: with one valid seat it returns
    'incomplete', which the orchestrator treats as a block."""
    r = first_run.FirstRunReport(families=[
        first_run.FamilyProbe("claude", "claude", installed=True, usable=True),
        first_run.FamilyProbe("codex", "codex", installed=True, usable=False,
                              reason="not logged in"),
    ])
    assert r.can_seat_a_panel is False
    assert r.usable_families == ["claude"]


def test_the_report_names_the_escape_when_only_one_family_works(tmp_path) -> None:
    r = first_run.FirstRunReport(families=[
        first_run.FamilyProbe("claude", "claude", installed=True, usable=True),
        first_run.FamilyProbe("codex", "codex", installed=True, usable=False,
                              reason="not logged in"),
    ])
    out = first_run.render(r, repo_root=tmp_path)
    assert "ONLY ONE usable reviewer family" in out
    assert "--reviewer-count 1" in out
    assert "every task would block" in out


def test_the_report_warns_that_accounts_do_not_rotate(tmp_path) -> None:
    """A machine with several config dirs invites the assumption that the
    dispatcher uses them. It does not — every spawn spends the ambient one."""
    r = first_run.FirstRunReport(
        families=[first_run.FamilyProbe("claude", "claude", True, True),
                  first_run.FamilyProbe("codex", "codex", True, True)],
        accounts=[first_run.AccountProbe("a", Path("/a"), usable=True),
                  first_run.AccountProbe("b", Path("/b"), usable=True)],
    )
    out = first_run.render(r, repo_root=tmp_path)
    assert "does NOT rotate" in out
    assert "CLAUDE_CONFIG_DIR" in out


# --- account discovery -------------------------------------------------------


def test_discovery_finds_credentialled_config_dirs_only(tmp_path) -> None:
    """A `.claude*` directory without credentials is not an account; probing it
    would spend a round trip to learn nothing."""
    for name in (".claude", ".claude-work"):
        d = tmp_path / name
        d.mkdir()
        (d / ".credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".claude-empty").mkdir()
    (tmp_path / ".claudefile").write_text("not a dir", encoding="utf-8")

    found = [p.name for p in first_run.discover_claude_accounts(tmp_path)]
    assert found == [".claude", ".claude-work"]


def test_account_probing_restores_the_ambient_config_dir(monkeypatch) -> None:
    """The probe sets CLAUDE_CONFIG_DIR per candidate. Leaking it would silently
    repoint every later command in the process at the last one tried."""
    import os

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/original")
    seen: list[str | None] = []

    def fake(cfg: Path) -> tuple[bool, str]:
        seen.append(os.environ.get("CLAUDE_CONFIG_DIR"))
        return True, ""

    first_run.probe_accounts([Path("/a"), Path("/b")], run=fake)
    assert os.environ["CLAUDE_CONFIG_DIR"] == "/original"


# --- starter config ----------------------------------------------------------


def test_the_starter_gate_fails_until_it_is_replaced(tmp_path) -> None:
    """A plausible-looking gate nobody edited is worse than an obviously broken
    one: it would report green while judging nothing."""
    first_run.write_starter_config(tmp_path)
    cfg = (tmp_path / ".dispatcher.yaml").read_text(encoding="utf-8")
    assert "REPLACE" in cfg
    assert "exit 1" in cfg


def test_a_starter_risk_table_is_written_so_the_first_run_is_not_all_high(
    tmp_path,
) -> None:
    first_run.write_starter_config(tmp_path)
    risk = (tmp_path / ".agent" / "risk-paths.json").read_text(encoding="utf-8")
    assert '"unmatched_risk": "high"' in risk


def test_existing_config_is_never_overwritten(tmp_path) -> None:
    """An existing config is the operator's, and a first-run helper that
    clobbers it is worse than one that does nothing."""
    (tmp_path / ".dispatcher.yaml").write_text("test: make check\n",
                                               encoding="utf-8")
    written = first_run.write_starter_config(tmp_path)
    assert ".dispatcher.yaml" not in written
    assert (tmp_path / ".dispatcher.yaml").read_text() == "test: make check\n"


# --- the shared-bot accounts must never be offered ---------------------------
# The first version of this reported .claude-pr, .claude-prreview and
# .claude-standup as "usable". They hold one bot identity that a cron job
# spends every 20 minutes, so pointing a run at one puts the dispatcher and the
# bot in a race for the same quota.


def test_bot_config_dirs_are_never_offered(tmp_path) -> None:
    for name in (".claude", ".claude-work", ".claude-pr", ".claude-prreview",
                 ".claude-standup"):
        d = tmp_path / name
        d.mkdir()
        (d / ".credentials.json").write_text("{}", encoding="utf-8")

    found = [p.name for p in first_run.discover_claude_accounts(tmp_path)]
    assert found == [".claude", ".claude-work"]
    for excluded in (".claude-pr", ".claude-prreview", ".claude-standup"):
        assert excluded not in found


def test_the_exclusion_list_is_not_empty() -> None:
    """A guard that silently became empty would offer the bot dirs again."""
    assert first_run.EXCLUDED_ACCOUNT_DIRS


# --- auth is free; quota is not knowable -------------------------------------


def test_auth_status_parses_the_json_the_cli_returns() -> None:
    """`claude auth status --json` is a local credential read: ~300ms and no
    tokens. It is the cheap first filter before spending a round trip."""
    import subprocess

    payload = ('{"loggedIn": true, "subscriptionType": "max", '
               '"email": "a@b.c"}')
    fake = subprocess.CompletedProcess([], 0, stdout=payload, stderr="")
    got = first_run.auth_status(run=lambda: fake)
    assert got["loggedIn"] is True
    assert got["subscriptionType"] == "max"


def test_auth_status_never_raises_on_a_broken_cli() -> None:
    """A probe that raises turns a diagnostic command into a crash."""
    def boom():
        raise OSError("no such binary")

    assert first_run.auth_status(run=boom) == {}


def test_auth_status_is_not_evidence_of_quota() -> None:
    """Verified 2026-08-31: an account over its MONTHLY limit still reports
    loggedIn: true. Auth is necessary and not sufficient, which is the whole
    reason the round-trip probe still exists behind it. This row exists to stop
    a later change replacing the round trip with the cheap call.
    """
    import inspect

    src = inspect.getsource(first_run.probe_families)
    assert ".review(" in src, (
        "probe_families must still perform a real round trip; auth status "
        "cannot tell a working account from an exhausted one"
    )
