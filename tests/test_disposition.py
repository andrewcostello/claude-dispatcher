"""Contract tests for the disposition queue (skipped in the skeleton; the
step-2 body-fill un-skips them). Pure — no subprocess/network/fs."""
import pytest

from claude_dispatcher.disposition import (
    Disposition, DispositionRecord, DispositionLedger, classify_disposition,
    corroboration,
)


def _classify(severity="HIGH", corroboration=2, gate_grounded=False,
              refutable=False, mode="unattended"):
    return classify_disposition(severity=severity, corroboration=corroboration,
                                gate_grounded=gate_grounded, refutable=refutable,
                                mode=mode)[0]


# --- classify_disposition tiers ---
def test_refutable_rejects_regardless_of_severity():
    assert _classify(severity="CRITICAL", refutable=True) == Disposition.REJECT


def test_blocking_corroborated_accepts():
    assert _classify(severity="HIGH", corroboration=2, gate_grounded=False) == Disposition.ACCEPT


def test_blocking_gate_grounded_accepts_even_if_lone():
    assert _classify(severity="CRITICAL", corroboration=1, gate_grounded=True) == Disposition.ACCEPT


def test_blocking_lone_uncorroborated_holds():
    assert _classify(severity="CRITICAL", corroboration=1, gate_grounded=False) == Disposition.HOLD


def test_nit_defers():
    assert _classify(severity="MEDIUM", corroboration=3) == Disposition.DEFER
    assert _classify(severity="LOW", corroboration=1) == Disposition.DEFER


# --- DispositionLedger ---
def _rec(fid="t:loc:HIGH", disp=Disposition.ACCEPT, sev="HIGH"):
    return DispositionRecord(finding_id=fid, severity=sev, corroboration=2,
                             gate_grounded=False, disposition=disp, reason="r")


def test_ledger_records_and_tallies_every_finding():
    led = DispositionLedger()
    led.record(_rec("a", Disposition.ACCEPT))
    led.record(_rec("b", Disposition.DEFER))
    led.record(_rec("c", Disposition.ACCEPT))
    assert led.tally() == {"accept": 2, "defer": 1}
    assert led.accepted_count() == 2
    assert len(led.records) == 3  # no silent drops


def test_ledger_detects_regenerating_finding():
    led = DispositionLedger()
    led.record(_rec("dup", Disposition.ACCEPT))
    assert led.regenerating("dup") is True
    assert led.regenerating("never-seen") is False


def test_ledger_alarm_on_round_cap():
    led = DispositionLedger(max_fix_rounds=3)
    tripped, reason = led.alarm_tripped(rounds_done=3)
    assert tripped is True and reason


def test_ledger_alarm_on_fix_task_cap():
    led = DispositionLedger(max_fix_tasks=2)
    for i in range(3):
        led.record(_rec(f"f{i}", Disposition.ACCEPT))
    tripped, _ = led.alarm_tripped(rounds_done=1)
    assert tripped is True


def test_ledger_no_alarm_under_caps():
    led = DispositionLedger(max_fix_rounds=3, max_fix_tasks=20)
    led.record(_rec("a", Disposition.ACCEPT))
    tripped, _ = led.alarm_tripped(rounds_done=1)
    assert tripped is False


def test_ledger_alarm_on_regenerating_finding():
    # A finding ACCEPTed twice (a fix didn't resolve it) trips the alarm.
    led = DispositionLedger(max_fix_rounds=10, max_fix_tasks=50)
    led.record(_rec("x", Disposition.ACCEPT))
    led.record(_rec("x", Disposition.ACCEPT))
    tripped, reason = led.alarm_tripped(rounds_done=1)
    assert tripped is True and "regen" in reason.lower()


def test_ledger_alarm_on_high_accept_rate():
    # 3 accepts of 4 records (75% > 60%, >=4 records) trips the rate alarm.
    led = DispositionLedger(max_fix_rounds=10, max_fix_tasks=50)
    for i in range(3):
        led.record(_rec(f"a{i}", Disposition.ACCEPT))
    led.record(_rec("d", Disposition.DEFER))
    tripped, reason = led.alarm_tripped(rounds_done=1)
    assert tripped is True and "rate" in reason.lower()


def test_corroboration_counts_distinct_reviewers_by_file_for_blocking():
    # Blocking findings cluster by FILE: reviewers citing the same defect at
    # different lines (a.py:10 / a.py:15) still corroborate.
    from types import SimpleNamespace as NS
    def f(loc, sev="HIGH"):
        return NS(location=loc, severity=sev, description="d")
    verdict = NS(reviewers=[
        NS(family="claude", findings=[f("a.py:10"), f("b.py:2")]),
        NS(family="codex", findings=[f("a.py:15")]),               # diff line, same file
        NS(family="gemini", findings=[f("a.py:99"), f("a.py:1")]),  # same reviewer -> 1
    ])
    c = corroboration(verdict)
    assert c["a.py"] == 3   # claude + codex + gemini, despite different lines
    assert c["b.py"] == 1   # claude only


def test_corroboration_nits_stay_line_level():
    # MEDIUM/LOW nits keep file:line so genuinely distinct nits don't merge.
    from types import SimpleNamespace as NS
    def f(loc, sev):
        return NS(location=loc, severity=sev, description="d")
    verdict = NS(reviewers=[
        NS(family="claude", findings=[f("a.py:1", "MEDIUM"), f("a.py:9", "LOW")]),
        NS(family="codex", findings=[f("a.py:1", "MEDIUM")]),  # corroborates the line
    ])
    c = corroboration(verdict)
    assert c["a.py:1"] == 2   # two reviewers, same line
    assert c["a.py:9"] == 1   # distinct nit, not merged into a.py:1
    assert "a.py" not in c    # nits never collapse to file-level


def test_corroboration_empty_verdict():
    from types import SimpleNamespace as NS
    assert corroboration(NS(reviewers=[])) == {}
    assert corroboration(NS()) == {}
