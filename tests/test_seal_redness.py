"""D-58 — a SEALS task's red seals are its deliverable, not its failure.

Found by dogfooding DF-1-2. The dispatcher was built around FIX-SHAPED tasks
(one task writes fix + test, suite ends green, `seal_verify` then reverts the
fix and demands red). The scaffold-first protocol inverts that: a SEALS task
writes ONLY tests, by a different author, and they must end RED.

Measured on DF-1-2: the mechanical gate read its six own red seals as failure,
spawned a fix-the-tests agent, then cascaded to a higher-effort rung which
RESET the seals away. `seal_verify.applies()` skipped the same branch
("test-only change — no fix to invert"), so the task was accused by one gate
and unexamined by the other.

The fixture is a REAL repository running a REAL test command. A stubbed runner
returning canned exit codes could not tell the two runs apart, and "which of
the two runs produced this code" is the entire mechanism.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import role_protocol as rp
from claude_dispatcher import seal_verify as sv

# A test command with no pytest dependency and no shared temp dir: the suite
# under test here is three files in the fixture repo, run by python directly.
TEST_CMD = (
    f"{sys.executable} - <<'EOF'\n"
    "import pathlib, sys\n"
    "fail = 0\n"
    "for p in sorted(pathlib.Path('tests').glob('*.py')):\n"
    "    src = p.read_text()\n"
    "    try:\n"
    "        exec(compile(src, str(p), 'exec'), {'__name__': '__main__'})\n"
    "    except Exception as e:\n"
    "        print(f'FAILED {p}: {e}')\n"
    "        fail += 1\n"
    "sys.exit(1 if fail else 0)\n"
    "EOF\n"
)


def _git(repo: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True,
        check=True, timeout=30,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "src").mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "seal@example.invalid")
    _git(repo, "config", "user.name", "Seal")
    # A base whose suite is green: one passing row, and a stub that raises.
    (repo / "tests" / "test_base.py").write_text("assert 1 + 1 == 2\n")
    (repo / "src" / "mod.py").write_text(
        "def f():\n    raise NotImplementedError('DF body supplies this')\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


@pytest.fixture()
def base_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = _repo(tmp_path)
    return repo, _git(repo, "rev-parse", "HEAD")


def _commit_seals(repo: Path, body: str, name: str = "test_seal.py") -> None:
    (repo / "tests" / name).write_text(body)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"seals: {name}")


def _run(repo: Path, base: str) -> sv.SealVerifyResult:
    return sv.run_seal_redness(
        worktree=repo, base=base, test_command=TEST_CMD, timeout_seconds=120,
    )


# --- the shape the protocol wants ------------------------------------------

def test_seal_D58_red_as_committed_and_green_without_its_rows_passes(base_repo):
    """The correct P2 deliverable: a row that fails because the body does not
    exist yet. This is what DF-1-2 produced and was accused for."""
    repo, base = base_repo
    _commit_seals(repo, "import sys; sys.path.insert(0, 'src')\n"
                        "from mod import f\n"
                        "f()  # raises NotImplementedError until the body lands\n")
    res = _run(repo, base)
    assert res.outcome == "passed", res.detail
    assert "red as committed" in res.detail


# --- the two ways it fails, which are the two things worth catching --------

def test_seal_D58_seals_that_are_already_green_pin_nothing(base_repo):
    """The false-passing seal — the highest-frequency defect in the 2026-07
    escape audit, and the shape that let a Critical money bug through in
    SMG-3966. A green P2 seal passes without the body it claims to pin."""
    repo, base = base_repo
    _commit_seals(repo, "assert True  # pins nothing\n")
    res = _run(repo, base)
    assert res.outcome == "failed", res.detail
    assert "GREEN as committed" in res.detail


def test_seal_D58_inherited_redness_cannot_certify_the_seals(base_repo, tmp_path):
    """Redness the branch did NOT cause — an already-red base, or a dependency
    merge that broke something. Without run 2 this is indistinguishable from a
    correct seal: both are red as committed.

    NOT "the branch broke a row it did not write": SEALS is allow_only over
    test files, so MODIFYING an existing row is its own row and reverts with
    the rest. That distinction is why this test exists in this shape — the
    first version of it asserted the wrong thing and passed a correct
    implementation as a failure."""
    repo, base = base_repo
    # The base the branch is judged from is green; the branch INHERITS a red
    # row from somewhere else (modelled as a commit it did not author, the
    # shape a dependency merge produces).
    _git(repo, "checkout", "-q", "-b", "feat/seals")
    (repo / "tests" / "test_inherited.py").write_text("assert 1 + 1 == 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "merged dependency: a row that was already broken")
    inherited_base = _git(repo, "rev-parse", "HEAD")
    _commit_seals(repo, "raise AssertionError('the seal')\n")
    res = sv.run_seal_redness(
        worktree=repo, base=inherited_base, test_command=TEST_CMD,
        timeout_seconds=120,
    )
    assert res.outcome == "failed", res.detail
    assert "STILL RED" in res.detail
    assert "INHERITED" in res.detail


# --- refusals: no verdict is not a verdict ---------------------------------

def test_seal_D58_a_seals_branch_that_wrote_no_test_is_an_accusation(base_repo):
    """Not "skipped". The role's entire deliverable is the rows it did not
    write, so silence here is the gate's own finding."""
    repo, base = base_repo
    (repo / "docs").mkdir()
    (repo / "docs" / "note.md").write_text("no seals here\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "docs only")
    res = _run(repo, base)
    assert res.outcome == "failed"
    assert "pins nothing" in res.detail


def test_seal_D58_a_non_test_change_on_a_seals_branch_is_unjudgeable(base_repo):
    """SEALS is allow_only_globs over test files and docs. A non-test change
    means the row is mislabelled or something reached the tree the role gate
    did not judge — either way the reversion would not be its own rows."""
    repo, base = base_repo
    (repo / "tests" / "test_seal.py").write_text("raise AssertionError('x')\n")
    (repo / "src" / "mod.py").write_text("def f():\n    return 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seals + a body edit")
    res = _run(repo, base)
    assert res.outcome == "error", res.detail
    assert "non-test file" in res.detail


def test_seal_D58_the_worktree_is_restored_after_every_outcome(base_repo):
    """Every later gate reads this tree. The revert must not survive the run."""
    repo, base = base_repo
    _commit_seals(repo, "raise AssertionError('seal')\n")
    before = _git(repo, "rev-parse", "HEAD")
    _run(repo, base)
    assert _git(repo, "rev-parse", "HEAD") == before
    assert _git(repo, "status", "--porcelain") == ""
    assert (repo / "tests" / "test_seal.py").exists()


# --- the expectation table --------------------------------------------------

def test_seal_D58_seals_is_parked_at_unjudged_and_the_rest_stay_green():
    """Operator ruling 2026-08-14. SEALS is NOT judged by the RED rule yet:
    DF-4-2's conditional `xfail(strict=True, raises=...)` seals EXIT ZERO, so
    run 1 and run 2 are indistinguishable by exit code, and judging SEALS as
    RED would fail a branch that already passed its panel and merged.

    The other four are GREEN because that is what they already did. Ruling
    BODIES explicitly is NOT safe yet either: D6 has three body(...) commits
    and D5 has two, so a unit's seals are turned green incrementally and an
    intermediate body task legitimately ends RED."""
    assert rp.suite_expectation(rp.Role.SEALS) is rp.SuiteExpectation.UNJUDGED
    for role in (rp.Role.SCAFFOLD, rp.Role.BODIES, rp.Role.ADJUDICATE, rp.Role.LEGACY):
        assert rp.suite_expectation(role) is rp.SuiteExpectation.GREEN


def test_seal_D58_an_unjudged_role_never_runs_the_suite_or_the_respawn(tmp_path):
    """EXECUTION, not structure. An earlier version of this row walked the AST
    and asserted the UNJUDGED branch appeared before the retry call — and a
    mutant that neutered the guard to `if False and ...` left the statement
    ORDER intact and passed. A row satisfiable by typing is the refusal this
    project inherits, so this one runs the gate.

    The fixture's test command is `exit 7`. If the suite is ever executed the
    outcome cannot be "skipped", so a green result here is proof the gate
    returned before running anything — which is also what makes the
    fix-the-tests re-spawn (whose only route to green is weakening the seals)
    unreachable for this role."""
    from claude_dispatcher import journal as journal_mod
    from claude_dispatcher import orchestrator as orch
    from claude_dispatcher import plan as plan_mod
    from claude_dispatcher import role_protocol as rpm
    from claude_dispatcher import worktree as wt_mod

    repo = tmp_path / "wt"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "s@e.invalid")
    _git(repo, "config", "user.name", "S")
    (repo / ".dispatcher.yaml").write_text("test: |\n  exit 7\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    (tmp_path / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    (tmp_path / "prompts").mkdir(exist_ok=True)
    jrnl = journal_mod.Journal.create(
        tmp_path / "j.jsonl",
        tasks_yaml_path=tmp_path / "tasks.yaml",
        reviewer_prompts_dir=tmp_path / "prompts",
    )

    row = {"key": "S-1", "summary": "s", "description": "d", "type": "Task",
           "role": "seals", "status": "To Do", "blockedBy": ["S-0"]}
    snap = orch.TaskSnapshot(
        key="S-1", summary="s", description="d", type="Task", labels=[],
        batch_keys=["S-1"],
        role_specs=[rpm.parse_task_role_spec(row, task_key="S-1")],
    )
    cfg = orch.RunConfig(
        tasks_path=tmp_path / "tasks.yaml", runs_dir=tmp_path / "runs",
        run_id="r", mode="unattended", max_parallel=1, max_iterations=1,
        reviewer_count=None, skip_design=False, skip_security_linter=False,
        financial_paths="", claude_bin="claude", worktree_base=None,
        label_filter=plan_mod.parse_label_filter(None), only_keys=None,
        verify_test_timeout_seconds=30, journal=jrnl,
    )

    outcome, detail = orch._verify_mechanical_and_maybe_retry(
        cfg, snap, wt_mod.Worktree(path=repo, branch="feat/seals"),
        tmp_path / "summary.md", {}, tmp_path / "gate.log",
        gate_base_sha=_git(repo, "rev-parse", "HEAD"),
        cycle=orch._VerificationCycle(),
    )
    assert (outcome, detail) == ("skipped", None), (
        f"a SEALS task's suite was judged: got {outcome!r} / {detail!r}. The "
        "fixture's test command is `exit 7`, so any non-skip outcome means "
        "the gate ran it")

    events = [e.payload for e in journal_mod.read_events(jrnl.path)
              if e.event_type
              == journal_mod.EventType.verification_mechanical.value]
    assert events, "the abstention was not journaled — a silent skip"
    assert events[-1]["reason"] == "role_suite_state_unjudged"
    assert "exit_code" not in events[-1], (
        "an exit code was journaled, so the suite ran after all")


def test_seal_D58_the_table_is_total_over_Role():
    """A new Role member must land in the raise, not in a default — the
    permissive answer here is GREEN, which is what accused DF-1-2."""
    assert set(rp._SUITE_EXPECTATIONS) == set(rp.Role)

    class _Fake:
        pass

    with pytest.raises(rp.RoleProtocolError) as exc:
        rp.suite_expectation(_Fake())          # type: ignore[arg-type]
    assert "not fall through" in str(exc.value)


# --- the retry guard --------------------------------------------------------

def test_seal_D58_a_seals_task_never_gets_a_fix_the_tests_respawn():
    """The dangerous path: an agent told the suite is red and to make it green,
    whose only route to green is weakening the seals. Structural, because
    exercising it needs a live spawn."""
    import ast
    import inspect

    from claude_dispatcher import orchestrator as orch

    tree = ast.parse(inspect.getsource(orch._verify_seal_redness))
    called = {
        n.func.id for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_retry_for_test_fix" not in called, (
        "the SEALS branch must never spawn the fix-the-tests corrective — its "
        "only route to green is weakening the seals")

    # And the green branch must still HAVE the retry, or this proves nothing.
    green = ast.parse(inspect.getsource(orch._verify_mechanical_and_maybe_retry))
    green_calls = {
        n.func.id for n in ast.walk(green)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "_retry_for_test_fix" in green_calls
