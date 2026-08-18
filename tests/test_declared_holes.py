"""Seals for `declares.holes`: the plan says what a scaffold must leave undone.

All three wave-2 scaffolds filled their own holes (32/32, 18/27, 8/9 functions
implemented) with nothing measuring it, which would have left P2 sealing existing
defective code — the circular oracle that produced 24 vacuous seals here.

The declaration is authored by the PLAN, never by the scaffold. That is the whole
security argument: a role able to write its own check could declare zero holes
and pass.
"""

from __future__ import annotations

import pytest

from claude_dispatcher import plan, role_protocol as rp, scaffold_shape as ss


def _row(key, role, blocked=None, **extra):
    r = {"key": key, "role": role, "summary": "s", "description": "d",
         "type": "Task", "labels": ["size:M"], "agent": "claude"}
    if blocked:
        r["blockedBy"] = blocked
    r.update(extra)
    return r


def _unit(holes=None):
    scaffold = _row("U-1", "scaffold",
                    **({"declares": {"holes": list(holes)}} if holes else {}))
    return plan.load_tasks({"tasks": [
        scaffold,
        _row("U-2", "seals", ["U-1"]),
        _row("U-3", "bodies", ["U-2"]),
        _row("U-4", "adjudicate", ["U-3"], disputed_paths=["tests/t.py"]),
    ]})


# ---------------------------------------------------------------- parsing ----

def test_holes_are_refused_on_any_row_but_the_scaffold() -> None:
    """The body's expectation is DERIVED from the scaffold's declaration, so a
    second copy on the body row could disagree and the gate would read whichever
    it happened to load.

    Measured under: drop the role check and this reddens.
    """
    with pytest.raises(rp.RoleProtocolError, match="belongs on the unit's SCAFFOLD"):
        rp.parse_task_role_spec(
            {"role": "bodies", "declares": {"holes": ["a.py::b"]}}, task_key="T",
        )


@pytest.mark.parametrize("block,match", [
    ("nope", "not a mapping"),
    ({"oops": 1}, "unknown declares key"),
    ({"holes": []}, "non-empty list"),
    ({"holes": "a.py::b"}, "non-empty list"),
    ({"holes": ["no-separator"]}, "must be exactly"),
    ({"holes": ["a.py::b::c"]}, "must be exactly"),
    ({"holes": ["a.py::"]}, "blank path or name"),
    ({"holes": ["::b"]}, "blank path or name"),
    ({"holes": [3]}, "must be exactly"),
])
def test_a_malformed_declaration_is_refused_at_plan_time(block, match) -> None:
    """Refused, never ignored: a declaration silently dropped is a check that
    silently does not run — and it would read as "this scaffold has no holes",
    which is exactly the state the check exists to catch.
    """
    with pytest.raises(rp.RoleProtocolError, match=match):
        rp.parse_task_role_spec(
            {"role": "scaffold", "declares": block}, task_key="T",
        )


# ------------------------------------------------------------- resolution ----

def test_the_body_inherits_its_units_scaffold_declaration() -> None:
    """Measured under: return `spec.declared_holes` for BODIES instead of walking
    to the scaffold, and this reddens with `()` — the body would be unchecked.
    """
    tasks = _unit(["src/m.py::decide", "src/m.py::C.run"])
    assert rp.holes_expected_of("U-1", tasks) == ("src/m.py::decide", "src/m.py::C.run")
    assert rp.holes_expected_of("U-3", tasks) == ("src/m.py::decide", "src/m.py::C.run")


def test_seals_and_adjudicate_are_not_hole_checked() -> None:
    """SEALS may not write the implementation at all, and ADJUDICATE rules one
    artifact. Checking either would refuse a task for not doing another role's job.

    Measured under: add either role to HOLE_CHECKED_ROLES and this reddens.
    """
    # Asserted on the MAPPING, not only through the resolver. Mutation testing
    # found the resolver check passes for the wrong reason: the unit walk matches
    # `bodies_keys` only, so adding SEALS to the table still returned () and the
    # behavioural assertion below did not bite. This row is the one that does.
    assert set(rp.HOLE_CHECKED_ROLES) == {rp.Role.SCAFFOLD, rp.Role.BODIES}
    tasks = _unit(["src/m.py::decide"])
    assert rp.holes_expected_of("U-2", tasks) == ()
    assert rp.holes_expected_of("U-4", tasks) == ()


def test_a_unit_that_declared_nothing_is_not_checked() -> None:
    """Every unit written before `declares:` existed. An absent declaration must
    mean "no check", never "no holes are allowed" — the latter would block every
    legacy scaffold on arrival.

    Measured under: treat empty as a failing check and this reddens.
    """
    tasks = _unit(None)
    assert rp.holes_expected_of("U-1", tasks) == ()
    assert rp.holes_expected_of("U-3", tasks) == ()


def test_an_unknown_task_key_resolves_to_no_check() -> None:
    assert rp.holes_expected_of("NOPE", _unit(["a.py::b"])) == ()


# ------------------------------------------------- the check the gate runs ----

def test_the_scaffold_phase_blocks_a_filled_hole() -> None:
    """The wave-2 defect, end to end through the checker the gate calls."""
    src = "def decide():\n    return 1\n"
    report = ss.declared_holes_report(
        ["src/m.py::decide"],
        shapes=[ss.measure("src/m.py", source=src)], phase="scaffold",
    )
    assert not report.passed
    assert "nothing to redden against" in report.detail()


def test_the_scaffold_phase_passes_a_left_hole() -> None:
    src = 'def decide():\n    """Doc."""\n    raise NotImplementedError\n'
    report = ss.declared_holes_report(
        ["src/m.py::decide"],
        shapes=[ss.measure("src/m.py", source=src)], phase="scaffold",
    )
    assert report.passed


def test_the_bodies_phase_blocks_an_unfilled_hole() -> None:
    src = "def decide():\n    raise NotImplementedError\n"
    report = ss.declared_holes_report(
        ["src/m.py::decide"],
        shapes=[ss.measure("src/m.py", source=src)], phase="bodies",
    )
    assert not report.passed
    assert "still stubs" in report.detail()


def test_a_hole_in_a_file_the_branch_never_created_is_a_failure() -> None:
    """The gate measures only files that EXIST in the worktree, so a hole whose
    file is absent must surface as `missing` rather than vanish.

    Measured under: report an absent file as ok and this reddens — a scaffold
    could then satisfy its declaration by writing nothing at all.
    """
    report = ss.declared_holes_report(
        ["src/never_written.py::decide"], shapes=[], phase="scaffold",
    )
    assert not report.passed
    assert report.missing == ("src/never_written.py::decide",)


def test_the_checker_is_on_the_floor_because_the_gate_calls_it() -> None:
    """A check a role can edit is not a check. Measured under: remove the glob
    and this reddens (and `test_role_protocol_floor` reddens too).
    """
    assert "**/src/claude_dispatcher/scaffold_shape.py" in rp.FLOOR_GLOBS


def test_the_orchestrator_blocks_on_the_check_before_the_suite_runs() -> None:
    """Order matters for cost: a scaffold that over-built has not produced a
    sealable contract, so paying for a full suite run over it is wasted.

    Measured under: move the call after `_verify_mechanical_and_maybe_retry` and
    this reddens.
    """
    from pathlib import Path
    from claude_dispatcher import orchestrator
    src = Path(orchestrator.__file__).read_text()
    holes_at = src.index("_check_declared_holes(cfg, snap, wt, log_path)")
    mech_at = src.index("mech_outcome, mech_detail = _verify_mechanical_and_maybe_retry(")
    assert holes_at < mech_at


# ------------------------------------------------------- the gate's wiring ----

def _snap(key, role):
    from claude_dispatcher.orchestrator import TaskSnapshot
    return TaskSnapshot(
        key=key, summary="s", description="d", type="Task", labels=["size:M"],
        role_specs=[rp.TaskRoleSpec(task_key=key, role=role)],
    )


def _cfg(tmp_path, rows):
    """A minimal RunConfig whose tasks file holds `rows`. Field list mirrors
    tests/test_feature_review.py's helper; journal defaults make events a no-op."""
    import json
    from claude_dispatcher.orchestrator import RunConfig
    tasks = tmp_path / "t.yaml"
    tasks.write_text(json.dumps({"tasks": rows}))   # JSON is valid YAML
    return RunConfig(
        tasks_path=tasks, runs_dir=tmp_path / "runs", run_id="R",
        mode="unattended", max_parallel=1, max_iterations=1, reviewer_count=None,
        skip_design=False, skip_security_linter=False, financial_paths="",
        claude_bin="claude", worktree_base=None, label_filter=[], only_keys=None,
        base_branch="main",
    )


def test_the_gate_returns_a_blocked_reason_when_a_hole_is_filled(
    tmp_path, monkeypatch,
) -> None:
    """The WIRING, not just the checker: `_check_declared_holes` must hand back a
    reason, because that return value is what sets the row to Blocked.

    Measured under: `return None` on failure and this reddens — the checker would
    keep reporting correctly into the journal while the task sailed through, which
    is the worst shape (a check that runs, logs, and decides nothing).
    """
    from claude_dispatcher import orchestrator, worktree as wt_mod

    monkeypatch.setattr(orchestrator, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_log", lambda *a, **k: None)

    wt_path = tmp_path / "wt"
    (wt_path / "src").mkdir(parents=True)
    (wt_path / "src" / "m.py").write_text("def decide():\n    return 1\n")
    wt = wt_mod.Worktree(path=wt_path, branch="feat/x")

    rows = [_row("U-1", "scaffold", declares={"holes": ["src/m.py::decide"]})]
    cfg = _cfg(tmp_path, rows)

    reason = orchestrator._check_declared_holes(
        cfg, _snap("U-1", rp.Role.SCAFFOLD), wt, tmp_path / "log",
    )
    assert reason is not None
    assert reason.startswith("declared_holes_scaffold:")


def test_the_gate_is_silent_when_the_unit_declared_nothing(
    tmp_path, monkeypatch,
) -> None:
    """Measured under: block on an empty declaration and every legacy scaffold
    fails on arrival.
    """
    from claude_dispatcher import orchestrator, worktree as wt_mod
    monkeypatch.setattr(orchestrator, "_emit_event", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator, "_log", lambda *a, **k: None)
    wt_path = tmp_path / "wt"
    wt_path.mkdir()
    wt = wt_mod.Worktree(path=wt_path, branch="feat/x")
    cfg = _cfg(tmp_path, [_row("U-1", "scaffold")])
    assert orchestrator._check_declared_holes(
        cfg, _snap("U-1", rp.Role.SCAFFOLD), wt, tmp_path / "log",
    ) is None
