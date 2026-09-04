"""Panel iteration escalates when it stops making progress.

Measured on the wallet run (2026-09-04), 49 iterate spawns for 10 tasks and
60% of the run's entire output-token spend. The aggregate blocking counts do
not converge:

    WAL-BALANCE-3   [7, 11, 9, 8, 9] [11, 10, 10, 10]   never beats round 1
    WAL-CHAIN-3     [7, 3, 5, 3, 4] [3, 4, 8, 7, 8] [6]

and the findings are real: 101 HIGH/CRITICAL for WAL-BALANCE-3, 51 in a single
migration, with no location repeating more than 3 times — each round rewrote
the file and the panel found DIFFERENT genuine defects. So the plateau is
evidence that the contract is wrong, not that the reviewer is pedantic.
"""

from __future__ import annotations

from claude_dispatcher import orchestrator as orch

STALLED = orch._panel_convergence_stalled


def test_a_plateau_stalls() -> None:
    """WAL-BALANCE-3's real first rung: never beats its opening round."""
    assert STALLED([7, 11, 9, 8, 9], 2) is True


def test_steady_improvement_does_not_stall() -> None:
    assert STALLED([9, 7, 5, 3], 2) is False


def test_one_bad_round_is_forgiven_at_patience_two() -> None:
    """WAL-HOLD-3 ran [3, 8] and its NEXT round reached ~1 blocking. Patience 1
    escalates that recovery away one round before it lands, which is the whole
    reason the operator chose 2."""
    assert STALLED([3, 8], 2) is False
    assert STALLED([3, 8], 1) is True
    assert STALLED([3, 8, 1], 2) is False


def test_patience_counts_from_the_best_round_not_the_previous_one() -> None:
    """Blocking counts OSCILLATE — WAL-CHAIN-3 ran [7,3,5,3,4]. A
    consecutive-decrease rule is reset by every dip and never fires; measured,
    it would have let all 13 of that task's rounds run."""
    assert STALLED([7, 3, 5, 3, 4], 2) is True
    # strictly-decreasing-vs-previous would see 3<7, 5>3, 3<5, 4>3 and never
    # accumulate two in a row.
    assert STALLED([7, 3, 5, 3], 2) is True


def test_a_new_best_resets_the_patience() -> None:
    assert STALLED([9, 9, 8], 2) is False, "round 3 set a new best"
    assert STALLED([9, 9, 8, 8, 8], 2) is True


def test_zero_patience_disables_the_rule() -> None:
    """Opt-out must exist: this changes review behaviour on critical work."""
    assert STALLED([5, 5, 5, 5, 5], 0) is False


def test_a_single_round_never_stalls() -> None:
    """There is nothing to compare against, and escalating on the first panel
    verdict would remove iteration altogether."""
    assert STALLED([5], 2) is False
    assert STALLED([], 2) is False
    assert STALLED([5], 1) is False


# --- wiring -----------------------------------------------------------------
#
# Sealed on source: reaching the panel loop behaviourally means standing up a
# full cascade dispatch with four reviewer families. Each seal asserts the
# uniqueness of what it matches first — a regex that silently found a second
# site is how #99's first seal passed while the cascade stayed broken.

def _src() -> str:
    import inspect
    return inspect.getsource(orch)


def test_the_loop_consults_the_rule_before_spawning_an_iterate() -> None:
    """Checking it AFTER the corrective spawn would pay for the round it
    exists to avoid."""
    import re
    src = _src()
    calls = re.findall(r"if _panel_convergence_stalled\(\n(.*?)\):", src, re.DOTALL)
    assert len(calls) == 1, f"expected one stall check, found {len(calls)}"
    body = src[src.index("if _panel_convergence_stalled("):]
    spawn_at = body.index("_spawn_panel_iterate(")
    break_at = body.index("break")
    assert break_at < spawn_at, (
        "the stall must break BEFORE the corrective spawn it is avoiding")


def test_every_round_is_recorded_including_the_first() -> None:
    """A history that only records blocked rounds cannot see a plateau."""
    src = _src()
    assert src.count("panel_blocking_history.append(") == 1
    idx = src.index("panel_blocking_history.append(")
    tail = src[idx:idx + 400]
    assert "is_approve or iterations_remaining <= 0" in tail, (
        "the append must precede the approve/budget break, or an approving "
        "round is never recorded")


def test_the_history_resets_per_model_not_per_task() -> None:
    """Operator ruling 2026-09-04: a new model earns a fresh set of rounds.
    Judging its progress against the previous model's plateau would escalate it
    for someone else's churn."""
    src = _src()
    assert src.count("panel_blocking_history = []") == 1, (
        "exactly one per-rung reset expected")
    reset = src.index("panel_blocking_history = []")
    # The reset sits in the rung-reset block, beside the other discarded-rung
    # state — same place `panel_verdict` and `panel_iterations_used` are cleared.
    window = src[reset - 400:reset]
    assert "panel_iterations_used = 0" in window, window[-200:]


def test_the_iterate_budget_is_per_rung() -> None:
    """Same ruling. A per-task budget would deny a fresh model any rounds at
    all once an earlier model had spent them."""
    src = _src()
    assert "cfg.cross_family_panel_iterate - panel_rounds_total" not in src
    assert src.count("iterations_remaining = max(0, cfg.cross_family_panel_iterate)") == 1


def test_the_stall_carries_the_locations_for_adjudication() -> None:
    """What the adjudicator decides is whether the CONTRACT is wrong. A bare
    round count cannot support that; 51 findings in one migration can."""
    src = _src()
    idx = src.index("EventType.panel_convergence_stalled")
    payload = src[idx:idx + 900]
    for field in ("history", "patience", "blocking_locations"):
        assert f'"{field}"' in payload, field
