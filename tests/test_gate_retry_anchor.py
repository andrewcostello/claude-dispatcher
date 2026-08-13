"""D-54 — the role loop gate must be clearable by complying with it.

Found by dogfooding: DF-4-1 (SCAFFOLD) wrote `tests/test_scratch_clone.py`,
was blocked, was unblocked with an adjudication telling it to remove the file,
removed it, and was blocked AGAIN — because the gate's base is `pre_spawn_sha`
and on a retry that is the VIOLATING tip, so the deletion is itself a changed
path under `**/tests/**`. The remedy scored identically to the breach.

Every row here is written to redden against the pre-D-54 orchestrator, and the
fixture is a real repository rather than a stubbed `run` seam: the defect was
never in the diff parser (`changed_paths_between` is three-dot and correct) but
in WHICH REF the orchestrator handed it, and a fake that returns paths cannot
tell one ref from another. That is the "recording that measures a frozen
artifact" shape from the vacuous-seal taxonomy, and it is the shape this defect
would hide in.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import loop_gate as lg
from claude_dispatcher import orchestrator as orch
from claude_dispatcher import unblock as ub


def _git(repo: Path, *argv: str) -> str:
    proc = subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True,
        check=True, timeout=30,
    )
    return proc.stdout.strip()


@pytest.fixture()
def df41(tmp_path: Path) -> dict:
    """The DF-4-1 history, rebuilt: base, a violating commit, a remedy commit.

    base      src/mod.py                       <- the scaffold, allowed
    violate   + tests/test_mod.py              <- the breach
    remedy    - tests/test_mod.py, M src/mod.py <- what the unblock asked for
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "seal@example.invalid")
    _git(repo, "config", "user.name", "Seal")

    (repo / "src").mkdir()
    (repo / "src" / "mod.py").write_text("def f():\n    raise NotImplementedError\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "feat/x")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_mod.py").write_text("def test_f():\n    assert True\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "violate: scaffold wrote its own seals")
    violating_tip = _git(repo, "rev-parse", "HEAD")

    (repo / "tests" / "test_mod.py").unlink()
    (repo / "src" / "mod.py").write_text(
        "def f():\n    raise NotImplementedError  # DF-4-2 supplies the seals\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "remedy: the seals are not this role's to write")

    return {"repo": repo, "base": base, "violating_tip": violating_tip,
            "branch": "feat/x"}


def _snap(key: str = "DF-4-1", anchor: str | None = None) -> orch.TaskSnapshot:
    return orch.TaskSnapshot(
        key=key, summary="s", description="d", type="Task", labels=[],
        gate_base_sha=anchor,
    )


# --- the defect itself -----------------------------------------------------

def test_seal_D54_the_remedy_is_a_forbidden_path_when_judged_from_the_violating_tip(df41):
    """The measurement the defect is made of. Judged from the violating tip,
    DELETING the forbidden file reports as touching it — so no branch state
    reachable from that tip is clean, and the task is stranded."""
    from claude_dispatcher.role_protocol import changed_paths_between

    paths = changed_paths_between(
        df41["repo"], df41["violating_tip"], df41["branch"],
    )
    assert "tests/test_mod.py" in paths, (
        "the remedy commit's deletion must show up as a changed path — if it "
        "does not, this fixture no longer reproduces D-54"
    )


def test_seal_D54_judged_from_the_attempts_own_base_the_remedied_branch_is_clean(df41):
    """The same tree, judged from where the attempt actually started, touches
    nothing forbidden. The two refs disagree, and that disagreement IS D-54."""
    from claude_dispatcher.role_protocol import changed_paths_between

    paths = changed_paths_between(df41["repo"], df41["base"], df41["branch"])
    assert "tests/test_mod.py" not in paths
    assert "src/mod.py" in paths


# --- _resolve_gate_base ----------------------------------------------------

def test_seal_anchor_wins_over_pre_spawn_sha_on_an_adjudicated_retry(df41, tmp_path):
    ref, reason = orch._resolve_gate_base(
        df41["repo"], _snap(anchor=df41["base"]), df41["branch"],
        pre_spawn_sha=df41["violating_tip"],
        log_path=tmp_path / "log",
    )
    assert ref == df41["base"], reason
    assert "retry anchor" in reason


def test_seal_no_anchor_is_unchanged_first_attempt_behaviour(df41, tmp_path):
    """The pre-D-54 semantics must survive for every un-adjudicated run: a
    breach is still a fact about the agent, not about the surviving diff."""
    ref, reason = orch._resolve_gate_base(
        df41["repo"], _snap(anchor=None), df41["branch"],
        pre_spawn_sha=df41["violating_tip"],
        log_path=tmp_path / "log",
    )
    assert ref == df41["violating_tip"]
    assert "no retry anchor" in reason


def test_seal_an_anchor_off_this_branch_is_declined_not_used(df41, tmp_path):
    """A branch that was reset or recreated leaves an anchor naming a ref the
    diff cannot be taken from. Falling back narrows the window (over-report),
    never widens it (under-report)."""
    orphan = _git(df41["repo"], "commit-tree", "-m", "orphan",
                  _git(df41["repo"], "rev-parse", "HEAD^{tree}"))
    ref, reason = orch._resolve_gate_base(
        df41["repo"], _snap(anchor=orphan), df41["branch"],
        pre_spawn_sha=df41["violating_tip"],
        log_path=tmp_path / "log",
    )
    assert ref == df41["violating_tip"]
    assert "not an ancestor" in reason


def test_seal_a_garbage_anchor_is_declined_not_passed_to_git(df41, tmp_path):
    """`git merge-base --is-ancestor` exits 128 on an unknown object. Only
    exit 0 is a yes — a non-1 failure must not read as one."""
    ref, _ = orch._resolve_gate_base(
        df41["repo"], _snap(anchor="not-a-sha"), df41["branch"],
        pre_spawn_sha=df41["violating_tip"],
        log_path=tmp_path / "log",
    )
    assert ref == df41["violating_tip"]


def test_seal_an_unreadable_pre_spawn_sha_is_not_papered_over_by_the_anchor(df41, tmp_path):
    """A run that could not read its own branch tip must not then be handed a
    base ref out of the YAML."""
    ref, reason = orch._resolve_gate_base(
        df41["repo"], _snap(anchor=df41["base"]), df41["branch"],
        pre_spawn_sha=None, log_path=tmp_path / "log",
    )
    assert ref is None
    assert "NOT substituted" in reason


# --- _is_ancestor ----------------------------------------------------------

def test_seal_is_ancestor_only_exit_zero_is_yes(df41, tmp_path):
    log = tmp_path / "log"
    assert orch._is_ancestor(df41["repo"], df41["base"], df41["branch"], log, "K")
    assert not orch._is_ancestor(df41["repo"], "0" * 40, df41["branch"], log, "K")
    assert not orch._is_ancestor(df41["repo"], "nope", df41["branch"], log, "K")


# --- the row contract ------------------------------------------------------

def test_seal_the_anchor_survives_unblock(df41):
    """`unblock` clears the previous attempt's VERDICTS. The anchor is not a
    verdict — it is the coordinate the next verdict is taken from — so a fix
    that put it in ROW_STAMPS would delete it exactly when it is needed."""
    assert lg.RETRY_ANCHOR_STAMP not in lg.ROW_STAMPS
    assert lg.RETRY_ANCHOR_STAMP not in ub._STALE_STAMPS


def test_seal_the_anchor_is_read_from_one_constant_by_both_halves():
    """Two spellings of one key is the failure where a rename clears one and
    writes the other, both halves internally consistent."""
    assert orch._RETRY_ANCHOR_STAMP is lg.RETRY_ANCHOR_STAMP


def test_seal_the_anchor_names_the_FIRST_blocked_attempts_base_not_the_last():
    """Re-stamping on every retry walks the anchor forward one attempt at a
    time — attempt 3 judged from attempt 2's tip, which already contains the
    violation. That is D-54 with extra steps, and it is why the write is a
    `setdefault`."""
    row = {"gate_base_sha": "first_attempt_base"}
    orch._record_retry_anchor(row, orch.plan_mod.BLOCKED, "second_attempt_tip")
    assert row["gate_base_sha"] == "first_attempt_base"


def test_seal_a_first_block_records_the_base_it_was_judged_from():
    row: dict = {}
    orch._record_retry_anchor(row, orch.plan_mod.BLOCKED, "base_sha")
    assert row["gate_base_sha"] == "base_sha"


def test_seal_done_clears_the_anchor_so_the_next_dispatch_is_a_first_attempt():
    """A stale anchor on a Done row would widen the NEXT task's gate window to
    a base it never ran from."""
    row = {"gate_base_sha": "stale"}
    orch._record_retry_anchor(row, orch.plan_mod.DONE, None)
    assert "gate_base_sha" not in row


def test_seal_a_block_with_no_resolvable_base_writes_nothing(df41):
    """The gate never resolved a base (git failed). There is nothing honest to
    record, and a guess would be a base ref invented by the failure path."""
    row: dict = {}
    orch._record_retry_anchor(row, orch.plan_mod.BLOCKED, None)
    assert row == {}


def test_seal_the_resolved_base_actually_reaches_the_gate():
    """The call site, not just the resolver.

    Every row above passes if `_resolve_gate_base` is correct and its answer is
    then thrown away — which is the protocol gap this project has now hit
    twice: a seal proves a function behaves, never that it runs. Measured: a
    mutant leaving `pre_spawn_sha=pre_spawn_sha` at the gate call reddens NO
    other row in this file.

    This is a STRUCTURAL check and stated as one. Exercising the real call site
    needs a spawned implementer, a worktree and a live git branch, so an AST
    walk over `_run_task`'s `check_after_implementer(...)` keyword is what is
    affordable here. It is weaker than an execution seal and stronger than the
    nothing that covers the wiring otherwise.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(orch._run_task))
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "check_after_implementer"
    ]
    assert len(calls) == 1, (
        f"expected exactly one gate call in _run_task, found {len(calls)} — a "
        "second call site is a second base ref nobody is checking"
    )
    kw = {k.arg: k.value for k in calls[0].keywords}
    assert "pre_spawn_sha" in kw, "the gate call no longer names its base ref"
    passed = kw["pre_spawn_sha"]
    assert isinstance(passed, ast.Name) and passed.id == "gate_base_sha", (
        "the gate must be handed the RESOLVED base, not the raw pre_spawn_sha; "
        f"it is being handed {ast.dump(passed)}"
    )


def test_seal_the_snapshot_freezes_the_anchor_before_the_implementer_runs():
    """Read at dispatch, like `role_specs`: a branch must not be able to move
    the ref it is judged from by editing its own row mid-session."""
    assert "gate_base_sha" in orch.TaskSnapshot.__dataclass_fields__
    assert orch.TaskSnapshot.__dataclass_fields__["gate_base_sha"].default is None
