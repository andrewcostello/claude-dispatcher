"""Contract tests for the disposition queue (skipped in the skeleton; the
step-2 body-fill un-skips them). Pure — no subprocess/network/fs."""
import pytest

from claude_dispatcher.disposition import (
    Disposition, DispositionRecord, DispositionLedger, classify_disposition,
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


@pytest.mark.skip(reason="step-2 body-fill: DispositionLedger")
def test_ledger_records_and_tallies_every_finding():
    led = DispositionLedger()
    led.record(_rec("a", Disposition.ACCEPT))
    led.record(_rec("b", Disposition.DEFER))
    led.record(_rec("c", Disposition.ACCEPT))
    assert led.tally() == {"accept": 2, "defer": 1}
    assert led.accepted_count() == 2
    assert len(led.records) == 3  # no silent drops


@pytest.mark.skip(reason="step-2 body-fill: DispositionLedger")
def test_ledger_detects_regenerating_finding():
    led = DispositionLedger()
    led.record(_rec("dup", Disposition.ACCEPT))
    assert led.regenerating("dup") is True
    assert led.regenerating("never-seen") is False


@pytest.mark.skip(reason="step-2 body-fill: DispositionLedger")
def test_ledger_alarm_on_round_cap():
    led = DispositionLedger(max_fix_rounds=3)
    tripped, reason = led.alarm_tripped(rounds_done=3)
    assert tripped is True and reason


@pytest.mark.skip(reason="step-2 body-fill: DispositionLedger")
def test_ledger_alarm_on_fix_task_cap():
    led = DispositionLedger(max_fix_tasks=2)
    for i in range(3):
        led.record(_rec(f"f{i}", Disposition.ACCEPT))
    tripped, _ = led.alarm_tripped(rounds_done=1)
    assert tripped is True


@pytest.mark.skip(reason="step-2 body-fill: DispositionLedger")
def test_ledger_no_alarm_under_caps():
    led = DispositionLedger(max_fix_rounds=3, max_fix_tasks=20)
    led.record(_rec("a", Disposition.ACCEPT))
    tripped, _ = led.alarm_tripped(rounds_done=1)
    assert tripped is False
