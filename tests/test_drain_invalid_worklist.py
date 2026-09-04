"""A worklist that stops validating mid-run drains; it does not crash the run.

The dispatcher writes `agent` / `effort` / `model` / `status` back into the
worklist while the run is live, and has written a row it would itself refuse:
WAL-CHAIN-3 ended up carrying `agent: claude` with `model: gpt-5.6-sol` after a
cascade. `_load_tasks_snapshot` re-parses the file on EVERY iteration of the
dispatch loop, so such a row makes `load_tasks` raise from inside the loop.

Unguarded that ends the run from inside the ThreadPoolExecutor's `with`, so
in-flight tasks are abandoned with their rows still In Progress -- the failure
that once collapsed a 19-wave plan to 2, because an orphaned row reads as
permanently running and nothing downstream is ever runnable again.
"""

from __future__ import annotations

from concurrent.futures import Future

import pytest

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import plan as plan_mod


def _cfg(tmp_path, max_parallel=2):
    return orch.RunConfig(
        tasks_path=tmp_path / "tasks.yaml",
        runs_dir=tmp_path / "runs",
        run_id="r", mode="unattended",
        max_parallel=max_parallel, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude",
        worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None),
        only_keys=None,
        cross_family_panel="full",
    )


def _drain(tmp_path, monkeypatch, *, spawns: list[str], invalid_after: int,
           max_parallel: int = 2):
    """Run the real drain loop with a snapshot that goes invalid partway.

    Returns (dispatched_keys, log_text). `_spawn_one_task` is replaced with a
    recorder that completes immediately, so what is under test is the loop's
    reaction to the raise -- not any spawning.
    """
    cfg = _cfg(tmp_path, max_parallel)
    (tmp_path / "runs").mkdir(exist_ok=True)
    cfg.tasks_path.write_text("tasks: []\n")
    log_path = tmp_path / "run.log"
    log_path.write_text("")
    calls = {"n": 0}
    dispatched: list[str] = []

    def fake_snapshot(_cfg):
        calls["n"] += 1
        if calls["n"] > invalid_after:
            raise plan_mod.ValidationError(
                "this worklist was refused (1 error(s)):\n"
                "  - X-1 routes agent 'claude' to model 'gpt-5.6-sol'"
            )
        return [
            plan_mod.Task(
                key=k, summary="s", description="d", type="Task",
                labels=["size:S"], blocked_by=[], status="To Do", raw={},
            )
            for k in (spawns if calls["n"] == 1 else [])
        ]

    def fake_run_task(snap, *a, **kw):
        dispatched.append(snap.key)
        return "Done"

    monkeypatch.setattr(orch, "_load_tasks_snapshot", fake_snapshot)
    monkeypatch.setattr(orch, "_run_task", fake_run_task)
    monkeypatch.setattr(orch, "_emit_event", lambda *a, **kw: None)

    merge_state = orch.merge_mod.MergePassState()
    orch._dispatch_drain(cfg, tmp_path / "runs", log_path, tmp_path, merge_state)
    return dispatched, log_path.read_text()


def test_an_invalid_snapshot_does_not_raise_out_of_the_drain_loop(
    tmp_path, monkeypatch,
) -> None:
    """The property that matters. A raise escaping here abandons every
    in-flight task with its row left In Progress."""
    _dispatched, log = _drain(
        tmp_path, monkeypatch, spawns=["A-1"], invalid_after=0)
    assert "no longer validates" in log, log


def test_the_hold_names_the_defect_and_the_file(tmp_path, monkeypatch) -> None:
    """Held silently, this looks like a run that simply finished. The operator
    has to be able to see WHICH row and WHY without reading the journal."""
    _dispatched, log = _drain(
        tmp_path, monkeypatch, spawns=["A-1"], invalid_after=0)
    assert "tasks.yaml" in log
    assert "routes agent 'claude' to model 'gpt-5.6-sol'" in log, log


def test_it_starts_no_new_work_after_going_invalid(
    tmp_path, monkeypatch,
) -> None:
    """Draining means finishing what is running, not picking up more. A loop
    that kept dispatching from a stale in-memory list would spend real money
    against a worklist the dispatcher can no longer read."""
    dispatched, _log = _drain(
        tmp_path, monkeypatch, spawns=["A-1", "A-2"], invalid_after=0)
    assert dispatched == [], dispatched


def test_a_valid_snapshot_still_dispatches(tmp_path, monkeypatch) -> None:
    """The guard must not turn every run into a hold."""
    dispatched, log = _drain(
        tmp_path, monkeypatch, spawns=["A-1"], invalid_after=50)
    assert dispatched, "a valid worklist must still dispatch"
    assert "no longer validates" not in log


def test_work_queued_before_the_defect_is_not_dispatched_after_it(
    tmp_path, monkeypatch,
) -> None:
    """The PRODUCTION shape: the worklist validated at startup and went invalid
    later, mid-run, because the dispatcher wrote to it.

    Sealed separately because "invalid on the very first snapshot" never
    exercises the interesting path -- there is no earlier runnable list to
    carry forward. A loop that fell back to the last good list would keep
    spending against a worklist it can no longer read, and would dispatch rows
    whose real status it does not know.

    One slot, three runnable rows: A-1 goes out from the valid snapshot, then
    the file stops validating. A-2 and A-3 must never start.
    """
    dispatched, log = _drain(
        tmp_path, monkeypatch, spawns=["A-1", "A-2", "A-3"],
        invalid_after=1, max_parallel=1)
    assert dispatched == ["A-1"], dispatched
    assert "no longer validates" in log


def test_free_slots_do_not_get_filled_from_a_stale_runnable_list(
    tmp_path, monkeypatch,
) -> None:
    """The case where clearing `runnable` is the ONLY thing that stops a
    dispatch.

    Found by a mutation that survived. Deleting the clear looked harmless
    because `if not in_flight: break` already covers the one-slot case -- so a
    seal built with max_parallel=1 passes whatever the guard does. The clear
    only matters when in-flight work leaves FREE SLOTS: three slots, one task
    still running, and a list of runnable rows left over from the last good
    snapshot. Without the clear the loop fills those slots against a worklist
    it can no longer parse, dispatching rows whose real status it cannot read.
    """
    import time

    slow = "A-1"

    def _drain_with_slow(spawns):
        cfg = _cfg(tmp_path, 3)
        cfg.tasks_path.write_text("tasks: []\n")
        (tmp_path / "runs").mkdir(exist_ok=True)
        log_path = tmp_path / "run.log"
        log_path.write_text("")
        calls = {"n": 0}
        dispatched: list[str] = []

        def fake_snapshot(_cfg):
            calls["n"] += 1
            if calls["n"] > 1:
                raise plan_mod.ValidationError("  - A-9 routes agent 'claude'")
            return [
                plan_mod.Task(
                    key=k, summary="s", description="d", type="Task",
                    labels=["size:S"], blocked_by=[], status="To Do", raw={},
                )
                for k in spawns
            ]

        def fake_run_task(snap, *a, **kw):
            dispatched.append(snap.key)
            if snap.key == slow:
                # Outlive the invalid iteration so its slots are genuinely free
                # while the loop is holding.
                time.sleep(0.3)
            return "Done"

        monkeypatch.setattr(orch, "_load_tasks_snapshot", fake_snapshot)
        monkeypatch.setattr(orch, "_run_task", fake_run_task)
        monkeypatch.setattr(orch, "_emit_event", lambda *a, **kw: None)
        orch._dispatch_drain(cfg, tmp_path / "runs", log_path, tmp_path,
                             orch.merge_mod.MergePassState())
        return dispatched

    dispatched = _drain_with_slow(["A-1", "A-2", "A-3", "A-4"])
    # Three slots -> A-1..A-3 go out from the VALID snapshot. A-4 was runnable
    # but unstarted when the worklist broke, and must stay unstarted.
    assert "A-4" not in dispatched, dispatched
    assert dispatched[:3] == ["A-1", "A-2", "A-3"], dispatched
