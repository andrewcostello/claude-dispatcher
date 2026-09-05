"""An agent's own escalation reason reaches the row it blocks.

`summary.parse` captures the `## Escalation reason` section, and
`_resolve_summary` returned None for the reason, so a self-declared Blocked
landed with `blocked_reason: None`.

Measured 2026-09-04, WAL-APPEND-3. The agent wrote 574 characters explaining
that no migration creates `wallet.transaction` or `wallet.entry`, so an
attachment migration would fail every fresh deployment — the missing-schema
defect, twelve hours before anyone else found it. The row recorded only
"Blocked". Triage read it as a mystery to retry rather than a finding to act
on, and it sat untouched across two runs.
"""

from __future__ import annotations

from pathlib import Path

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import plan as plan_mod
from claude_dispatcher import summary as summary_mod

REASON = ("Completion requires the v2 ledger DDL plus production "
          "CHAIN/BALANCE/IDEM collaborators.")


def _summary(tmp_path: Path, status: str, reason: str | None) -> object:
    body = f"# T-1\n**Status:** {status}\n\n## What landed\n- nothing\n"
    if reason:
        body += f"\n## Escalation reason\n{reason}\n"
    p = tmp_path / "summary.md"
    p.write_text(body)
    return summary_mod.parse(p)


def _cfg(tmp_path: Path):
    return orch.RunConfig(
        tasks_path=tmp_path / "t.yaml", runs_dir=tmp_path / "runs",
        run_id="r", mode="unattended", max_parallel=1, max_iterations=1,
        reviewer_count=None, skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude", worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None), only_keys=None,
        cross_family_panel="full",
    )


def _resolve(tmp_path, status, reason):
    s = _summary(tmp_path, status, reason)
    snap = orch.TaskSnapshot(key="T-1", summary="s", description="d",
                             type="Task", labels=["size:S"], batch_keys=["T-1"])
    return orch._resolve_summary(_cfg(tmp_path), snap, s, None, tmp_path / "log")


def test_a_self_declared_block_carries_its_reason(tmp_path) -> None:
    """The property. Without it the row says only 'Blocked' and the next
    person pays a full re-dispatch to learn what one line already said."""
    status, _url, reason = _resolve(tmp_path, "Blocked", REASON)
    assert status == plan_mod.BLOCKED
    assert reason and REASON[:40] in reason


def test_an_escalated_row_carries_it_too(tmp_path) -> None:
    status, _url, reason = _resolve(tmp_path, "Escalated", REASON)
    assert status == plan_mod.ESCALATED
    assert reason and REASON[:40] in reason


def test_a_block_with_no_stated_reason_stays_none(tmp_path) -> None:
    """Absence must not become an empty string: 'no reason recorded' is a
    meaningful state and a blank one reads as a reason that says nothing."""
    _status, _url, reason = _resolve(tmp_path, "Blocked", None)
    assert reason is None


def test_a_whitespace_only_section_is_none(tmp_path) -> None:
    """Asserts the OUTCOME, not a redundant guard. `_extract_section` already
    strips, so a whitespace-only section parses to "" upstream — an earlier
    version of this test asserted a caller-side .strip() that a mutation
    removed with no failure, i.e. it was measuring nothing."""
    s = _summary(tmp_path, "Blocked", "   \n  ")
    assert s.escalation_reason == "", "parse should have stripped it"
    _status, _url, reason = _resolve(tmp_path, "Blocked", "   \n  ")
    assert reason is None


def test_a_done_row_gets_no_blocked_reason(tmp_path) -> None:
    """A Done row must never carry a blocked_reason, even if the agent left an
    escalation section behind from an earlier draft."""
    status, _url, reason = _resolve(tmp_path, "Done", REASON)
    assert status == plan_mod.DONE and reason is None


def test_the_real_wal_append_3_summary_yields_its_reason(tmp_path) -> None:
    """The actual artifact, if it is still on disk. This is the case the fix
    exists for, so assert against the real bytes rather than a fixture."""
    real = Path("/home/andrew/Project/dispatcher-runs/"
                "2026-09-04T21-11-28Z-wallet-v2-tasks/WAL-APPEND-3/summary.md")
    if not real.exists():          # artifact pruned; the fixtures above cover it
        return
    s = summary_mod.parse(real)
    snap = orch.TaskSnapshot(key="WAL-APPEND-3", summary="s", description="d",
                             type="Task", labels=["size:M"],
                             batch_keys=["WAL-APPEND-3"])
    status, _url, reason = orch._resolve_summary(
        _cfg(tmp_path), snap, s, None, tmp_path / "log")
    assert status == plan_mod.BLOCKED
    assert reason and "ledger DDL" in reason, reason
