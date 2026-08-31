"""`dispatcher init` — prove the machine can actually run a dispatch.

`doctor` answers "what is installed". This answers "what WORKS", which is a
different question and the one that decides whether a first run succeeds.
Measured 2026-08-31: `doctor.probe_binary` runs `shutil.which` and `--version`,
so an installed-but-logged-out CLI and an account over its monthly limit both
report a green tick. Both then fail at dispatch time, after spend.

Three states a tick cannot distinguish, and this module does:

  * NOT INSTALLED — no binary on PATH.
  * INSTALLED BUT UNUSABLE — the binary runs and refuses: not logged in, or the
    account is over its limit. Seen 2026-08-30, when a reviewer seat returned
    UNAVAILABLE in ~4.5s for eleven consecutive cases and read like a broken
    seat rather than a quota wall.
  * USABLE — a real round trip completed.

The probe goes through ``cross_family_reviewer.Reviewer.review``, the same path
a panel seat uses, so a family that passes here is a family that can seat. It
SPENDS a little quota, which is why this is a command an operator runs once and
not a check on every dispatch.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

#: The smallest prompt that still exercises the parse path: the reviewer must
#: return something the verdict parser accepts, or the probe cannot tell a
#: working seat from a broken one.
PROBE_PROMPT = (
    "Reply with exactly these three lines and nothing else:\n"
    "## Verdict\n"
    "APPROVE\n"
)

#: Substrings that identify WHY a working binary refused. Matched against the
#: CLI's own error text, lowercased. Ordered: quota before auth, because a
#: quota message often also mentions the account.
_REFUSAL_MARKERS: tuple[tuple[str, str], ...] = (
    ("spend limit", "over its spend limit"),
    ("usage limit", "over its usage limit"),
    ("rate limit", "rate limited"),
    ("quota", "out of quota"),
    ("429", "rate limited (429)"),
    ("not logged in", "not logged in"),
    ("log in", "not logged in"),
    ("unauthor", "not authorised"),
    ("api key", "no API key configured"),
    ("credential", "no credentials"),
)


@dataclass
class FamilyProbe:
    """What one reviewer family can actually do on this machine."""

    family: str
    binary: str
    installed: bool = False
    usable: bool = False
    reason: str = ""
    seconds: float = 0.0

    @property
    def state(self) -> str:
        if not self.installed:
            return "not installed"
        return "usable" if self.usable else f"unusable — {self.reason}"


@dataclass
class AccountProbe:
    """One Claude config directory, and whether it answers."""

    name: str
    config_dir: Path
    usable: bool = False
    reason: str = ""
    email: str = ""
    plan: str = ""


@dataclass
class FirstRunReport:
    families: list[FamilyProbe] = field(default_factory=list)
    accounts: list[AccountProbe] = field(default_factory=list)
    wrote: list[str] = field(default_factory=list)

    @property
    def usable_families(self) -> list[str]:
        return [f.family for f in self.families if f.usable]

    @property
    def can_seat_a_panel(self) -> bool:
        """Two usable families is the bar `aggregate` sets before it will
        approve; with one it returns "incomplete" and the task blocks."""
        return len(self.usable_families) >= 2


def _classify_refusal(error: str) -> str:
    low = (error or "").lower()
    for marker, reason in _REFUSAL_MARKERS:
        if marker in low:
            return reason
    first = (error or "").strip().splitlines()
    return first[0][:120] if first else "returned no usable verdict"


def probe_families(
    reviewers: Iterable | None = None,
    *,
    timeout_seconds: int = 90,
) -> list[FamilyProbe]:
    """Round-trip each reviewer family. Spends a little quota, by design."""
    from . import cross_family_reviewer as cfr

    out: list[FamilyProbe] = []
    revs = list(reviewers) if reviewers is not None else cfr.default_reviewers()
    for reviewer in revs:
        probe = FamilyProbe(family=reviewer.family, binary=reviewer.cli_bin)
        if shutil.which(reviewer.cli_bin) is None:
            out.append(probe)
            continue
        probe.installed = True
        reviewer.timeout_seconds = timeout_seconds
        verdict = reviewer.review(PROBE_PROMPT)
        probe.seconds = float(verdict.duration_seconds or 0.0)
        if verdict.verdict is cfr.Verdict.UNAVAILABLE:
            probe.reason = _classify_refusal(verdict.error or "")
        elif verdict.verdict is cfr.Verdict.PARSE_FAILED:
            probe.reason = "ran but produced no parseable verdict"
        else:
            probe.usable = True
        out.append(probe)
    return out


#: Config directories that must never be offered for dispatch. These hold a
#: shared bot identity that a cron job spends on its own schedule; pointing a
#: run at one puts the dispatcher and the bot in a race for the same quota.
#: Matched on the directory name, so a rename defeats it — the list is a guard
#: against the obvious mistake, not a security boundary.
EXCLUDED_ACCOUNT_DIRS: frozenset[str] = frozenset({
    ".claude-pr", ".claude-prreview", ".claude-standup",
})


def discover_claude_accounts(home: Path | None = None) -> list[Path]:
    """Candidate `CLAUDE_CONFIG_DIR`s: credentialled `~/.claude*` directories,
    minus the shared-bot ones.

    Discovered rather than hand-listed, because a hand-listed pool is what the
    machine profile already has and nothing reads it. The exclusion exists
    because the first version of this reported three bot directories as
    "usable", which is an invitation to spend an identity a cron job is already
    spending.
    """
    root = home or Path.home()
    try:
        found = sorted(
            p for p in root.glob(".claude*")
            if p.is_dir()
            and (p / ".credentials.json").exists()
            and p.name not in EXCLUDED_ACCOUNT_DIRS
        )
    except OSError:
        return []
    return found


def auth_status(config_dir: Path | None = None, *, run=None) -> dict:
    """`claude auth status --json` — FREE and instant (~300ms, no tokens).

    It is a local credential read, so it answers "is this account logged in,
    and on what plan" without spending anything. It does NOT answer "has this
    account any quota left": an account over its monthly limit still reports
    `loggedIn: true`, verified 2026-08-31. Auth is necessary, not sufficient,
    which is why the round-trip probe still exists behind it.
    """
    import json as _json
    import subprocess

    env = dict(os.environ)
    if config_dir is not None:
        env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    runner = run or (lambda: subprocess.run(
        ["claude", "auth", "status", "--json"],
        capture_output=True, text=True, timeout=30, env=env, check=False,
    ))
    try:
        proc = runner()
        if proc.returncode != 0:
            return {}
        return _json.loads(proc.stdout)
    except Exception:  # noqa: BLE001 - a probe never raises
        return {}


def probe_accounts(
    dirs: Iterable[Path],
    *,
    run: Callable[[Path], tuple[bool, str]] | None = None,
) -> list[AccountProbe]:
    """Round-trip each config dir through the claude seat.

    `run` is injectable so a test never spends anything.
    """
    from . import cross_family_reviewer as cfr

    def _default(cfg: Path) -> tuple[bool, str]:
        previous = os.environ.get("CLAUDE_CONFIG_DIR")
        os.environ["CLAUDE_CONFIG_DIR"] = str(cfg)
        try:
            seat = next(
                (r for r in cfr.default_reviewers() if r.family == "claude"), None
            )
            if seat is None:
                return False, "no claude seat in the roster"
            verdict = seat.review(PROBE_PROMPT)
            if verdict.verdict is cfr.Verdict.UNAVAILABLE:
                return False, _classify_refusal(verdict.error or "")
            return True, ""
        finally:
            if previous is None:
                os.environ.pop("CLAUDE_CONFIG_DIR", None)
            else:
                os.environ["CLAUDE_CONFIG_DIR"] = previous

    probe = run or _default
    out: list[AccountProbe] = []
    for cfg in dirs:
        ok, reason = probe(cfg)
        out.append(AccountProbe(name=cfg.name, config_dir=cfg,
                                usable=ok, reason=reason))
    return out


#: Written only when the repo has none. Deliberately minimal: a gate the
#: operator must complete beats a plausible one they never read.
STARTER_DISPATCHER_YAML = """\
# The mechanical gate: arbitrary shell, run in each task worktree, exit 0 = green.
# This is the single highest-value key — without it a task's only judge is an LLM.
#
# REPLACE THIS with your repo's real test command. It must be self-sufficient in
# a FRESH WORKTREE: gitignored dependencies (node_modules, .venv) do not exist
# there, so install them here if your tests need them.
test: |
  echo "REPLACE ME: no test command configured" >&2
  exit 1

# Where run artifacts go. Point it OUTSIDE the repo: a runs dir inside one is
# gitignored AND lives in a disposable worktree, so the audit trail dies with it.
runs_dir: ../dispatcher-runs
"""

STARTER_RISK_PATHS = """\
{
  "schema_version": 1,
  "_comment": "Which changed paths are risky, and therefore which changes are worth a cross-family panel. WITHOUT this file every path is unmatched, unmatched fails closed to high, and EVERY task pays for a full panel.",
  "unmatched_risk": "high",
  "rules": [
    {
      "id": "example-high",
      "risk": "high",
      "note": "REPLACE: the paths where a defect is silent and expensive.",
      "paths": []
    },
    {
      "id": "docs",
      "risk": "low",
      "note": "Documentation and test helpers.",
      "paths": ["**/*.md", "docs/**"]
    }
  ]
}
"""


def write_starter_config(repo_root: Path) -> list[str]:
    """Create the two files whose absence makes a first run expensive or
    unjudged. Never overwrites: an existing config is the operator's."""
    written: list[str] = []
    cfg = repo_root / ".dispatcher.yaml"
    if not cfg.exists():
        cfg.write_text(STARTER_DISPATCHER_YAML, encoding="utf-8")
        written.append(str(cfg.relative_to(repo_root)))
    risk = repo_root / ".agent" / "risk-paths.json"
    if not risk.exists():
        risk.parent.mkdir(parents=True, exist_ok=True)
        risk.write_text(STARTER_RISK_PATHS, encoding="utf-8")
        written.append(str(risk.relative_to(repo_root)))
    return written


def render(report: FirstRunReport, *, repo_root: Path) -> str:
    """The operator-facing report. Says what works, what does not, and what to
    do about it — a probe that only prints state leaves the reader to guess."""
    lines = ["", "reviewer families (a real round trip, not --version):"]
    for f in report.families:
        mark = "OK " if f.usable else "!! "
        timing = f" ({f.seconds:.1f}s)" if f.usable and f.seconds else ""
        lines.append(f"  {mark} {f.family:8} {f.state}{timing}")

    if report.accounts:
        lines += ["", "claude config directories:"]
        for a in report.accounts:
            mark = "OK " if a.usable else "!! "
            lines.append(
                f"  {mark} {a.name:24} {'usable' if a.usable else a.reason}")

    usable = report.usable_families
    lines += ["", "verdict:"]
    if report.can_seat_a_panel:
        lines.append(
            f"  {len(usable)} usable reviewer families ({', '.join(usable)}) — "
            "the panel can reach a verdict.")
    elif usable:
        lines += [
            f"  ONLY ONE usable reviewer family ({usable[0]}).",
            "  A multi-seat panel needs two: with one it returns 'incomplete',",
            "  which blocks the task, so every task would block AFTER paying for",
            "  its implementer. Either install another reviewer CLI, or run with",
            "  --reviewer-count 1 for a deliberate single seat.",
        ]
    else:
        lines += [
            "  NO usable reviewer family. Nothing can be reviewed.",
            "  Install and authenticate at least one agent CLI.",
        ]

    if len(report.accounts) > 1:
        lines += [
            "",
            "  Note: the dispatcher does NOT rotate between config directories.",
            "  Every spawn spends the ambient ~/.claude, so one account is the",
            "  whole ceiling for a run. Set CLAUDE_CONFIG_DIR on the run to use",
            "  a different one.",
        ]

    if report.wrote:
        lines += ["", "wrote:"] + [f"  {w}" for w in report.wrote]
        lines.append("  Edit the `test:` command before dispatching — the")
        lines.append("  starter gate deliberately fails until you do.")
    return "\n".join(lines) + "\n"
