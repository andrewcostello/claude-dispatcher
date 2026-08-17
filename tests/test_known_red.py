"""Seals for the known-red register (D-68 fix, operator-authored 2026-08-17).

What this file is for
---------------------
The register makes a FAILING TEST ROW STOP FAILING A BRANCH. That is a
suppression mechanism in a project whose recorded history is false greens, so
the rows below are weighted toward the two questions that decide whether it is
safe rather than toward its happy path:

  * can it hide a row from the one task that must still see it? (`applies_to`)
  * can a wrong entry hide something nobody meant to hide? (fail-safe)

Non-vacuity: `test_deselect_actually_suppresses_and_a_typo_does_not` runs REAL
pytest against a REAL failing row. Everything else in this file is arithmetic
over my own dataclasses, and arithmetic cannot tell me that `--deselect`
behaves the way the design assumes. D-58's register seals made the same choice
for the same reason ("a fake returning canned exit codes cannot tell them
apart").
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from claude_dispatcher import known_red as kr


def _entry(**kw) -> kr.KnownRedEntry:
    base = dict(
        rows=("tests/test_a.py::test_one",),
        seals_task="U-2",
        body_task="U-3",
        reason="P2 seal; body U-3 not landed",
    )
    base.update(kw)
    return kr.KnownRedEntry(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# The property the whole design rests on: the body is never excused.
# --------------------------------------------------------------------------

def test_an_entry_never_hides_its_rows_from_its_own_body_task() -> None:
    """The unit's whole point is that P3 turns these rows green, so P3 is the
    one gate that must still fail on them.

    Measured under: delete the `self.body_task == task_key` branch in
    `KnownRedEntry.applies_to` and this row reddens — the body's gate would
    then pass with its own seals suppressed, which is the vacuous seal moved up
    one tier. This is the single most important row in the file.
    """
    reg = kr.Register(entries=(_entry(rows=("t.py::a", "t.py::b")),))
    assert kr.rows_for_task(reg, task_key="U-3") == ()
    # ...while every other task in the wave is shielded from them.
    assert kr.rows_for_task(reg, task_key="OTHER-3") == ("t.py::a", "t.py::b")


def test_an_entry_retires_when_its_body_is_done() -> None:
    """Retirement is what stops the register becoming permanent suppression.

    Measured under: delete the `self.body_task in done_keys` branch and this
    reddens. Note the Done set is read from the tasks YAML rather than from the
    running run's memory, which is what makes an entry retire even when the body
    landed in an EARLIER run — the D-70 case where red rows are frozen into a
    preserved branch and merging the body never reached it.
    """
    reg = kr.Register(entries=(_entry(),))
    assert kr.rows_for_task(reg, task_key="OTHER-3") == ("tests/test_a.py::test_one",)
    assert kr.rows_for_task(reg, task_key="OTHER-3", done_keys={"U-3"}) == ()


def test_rows_are_shell_quoted_so_a_parametrised_id_survives() -> None:
    """Parametrised node ids carry spaces and brackets.

    Wave 1's own flake was
    ``...::test_every_optional_marker_lives_in_an_always_present_bracket_slot[a
    plain property]``. Unquoted, that id splits into several shell words,
    deselects NOTHING, and leaves the gate red for a reason no reader could
    see — a silent no-op that reads as protection.

    Measured under: drop `shlex.quote` from `deselect_args` and this reddens.
    """
    rendered = kr.deselect_args(("t.py::test_x[a plain property]",))
    assert rendered == "--deselect 't.py::test_x[a plain property]'"
    # And the quoting must be real shell quoting, not a wrapper in quotes:
    import shlex
    assert shlex.split(rendered) == [
        "--deselect", "t.py::test_x[a plain property]",
    ]


def test_rows_are_deduplicated_in_stable_registration_order() -> None:
    """Two units can register the same row; the rendered command must be
    reproducible so a journal payload diffs cleanly across runs.

    Measured under: swap the `seen` set for a plain list-extend (duplicates
    appear) or sort the output (order stops being registration order).
    """
    reg = kr.Register(entries=(
        _entry(rows=("t.py::b", "t.py::a"), body_task="U-3"),
        _entry(rows=("t.py::a", "t.py::c"), body_task="V-3"),
    ))
    assert kr.rows_for_task(reg, task_key="Z") == ("t.py::b", "t.py::a", "t.py::c")


# --------------------------------------------------------------------------
# Named faults: every way the arrangement can fail must BLOCK, never degrade.
# --------------------------------------------------------------------------

def test_active_entries_with_no_declared_style_is_a_named_block() -> None:
    """A repo that cannot express the exclusion must stop, not run the gate.

    Running anyway is precisely the D-68 tax: the task is judged against rows it
    has no way to fix, pays a fix-the-tests spawn that cannot help, and cascades.

    Measured under: return `Exclusions()` instead of the fault and this reddens.
    """
    reg = kr.Register(entries=(_entry(),))
    out = kr.resolve(reg, task_key="Z", style=None, test_command="pytest tests/")
    assert out.fault is kr.RegisterFault.UNSUPPORTED_STYLE
    assert out.applied is False
    # The detail must name the rows, or the block cannot be acted on.
    assert "tests/test_a.py::test_one" in out.detail


def test_a_declared_style_the_command_ignores_is_a_named_block() -> None:
    """Declaring `test_exclusion:` and never placing the variable would drop
    every exclusion silently — the gate goes red and the operator believes the
    register handled it.

    Measured under: delete the `EXCLUSION_ENV not in test_command` check and
    this reddens.
    """
    reg = kr.Register(entries=(_entry(),))
    out = kr.resolve(
        reg, task_key="Z",
        style=kr.ExclusionStyle.PYTEST_DESELECT,
        test_command="pytest tests/ -q",
    )
    assert out.fault is kr.RegisterFault.COMMAND_IGNORES_EXCLUSIONS


def test_an_empty_active_register_is_never_a_fault() -> None:
    """Every repo starts here and must behave EXACTLY as it did before this
    module existed — including repos that will never declare a style.

    Measured under: raise the UNSUPPORTED_STYLE fault whenever `style is None`
    regardless of rows, and this reddens. That mutation is the plausible one: it
    reads as stricter and it would break every existing repo's gate.
    """
    empty = kr.Register(entries=())
    out = kr.resolve(empty, task_key="Z", style=None, test_command="pytest")
    assert out.fault is None and out.rows == () and out.env is None
    # Retired-only register: entries exist, none active. Also not a fault.
    reg = kr.Register(entries=(_entry(),))
    out = kr.resolve(
        reg, task_key="Z", done_keys={"U-3"}, style=None, test_command="pytest",
    )
    assert out.fault is None and out.env is None


def test_the_applied_case_hands_over_exactly_the_env_the_repo_reads(
    tmp_path: Path,
) -> None:
    """Measured under: rename the key in the returned `env` and this reddens —
    the repo's test command references `EXCLUSION_ENV` by name, so a mismatch
    is a silent no-op.
    """
    reg = kr.Register(entries=(_entry(rows=("t.py::a",)),))
    out = kr.resolve(
        reg, task_key="Z",
        style=kr.ExclusionStyle.PYTEST_DESELECT,
        test_command=f"pytest tests/ ${kr.EXCLUSION_ENV}",
        rows_dir=tmp_path,
    )
    assert out.applied is True
    assert set(out.env or {}) == {kr.EXCLUSION_ENV}
    assert Path((out.env or {})[kr.EXCLUSION_ENV]).name == kr.ROWS_FILENAME


def test_a_decision_with_no_delivery_is_not_reported_as_applied() -> None:
    """`applied` must require the env, not merely the rows.

    Measured under: drop `and bool(self.env)` from `Exclusions.applied` and this
    reddens. A suppression that was decided but never delivered would otherwise
    be logged as though it had happened, which is the one thing an operator
    reading the log must not be told wrongly.
    """
    reg = kr.Register(entries=(_entry(),))
    out = kr.resolve(
        reg, task_key="Z",
        style=kr.ExclusionStyle.PYTEST_DESELECT,
        test_command=f"pytest ${kr.EXCLUSION_ENV}",
        rows_dir=None,
    )
    assert out.rows and out.fault is None
    assert out.applied is False


def test_the_rows_file_is_ids_only_and_never_arguments(tmp_path: Path) -> None:
    """The correction this row exists to keep made.

    An earlier version handed over a pre-rendered
    ``--deselect 'a.py::t[x y]'`` string. That cannot work: the shell does not
    re-parse quotes after expanding a variable, so an unquoted expansion splits
    on whitespace and pytest receives ``--deselect``, ``'a.py::t[x`` and
    ``y]'``, while a quoted expansion passes the whole string as ONE argument
    that pytest rejects.

    Measured under: render the file with `deselect_args` instead of
    `rows_payload` and this reddens on the `--deselect` check.
    """
    path = kr.write_rows_file(("a.py::t[x y]", "b.py::t"), directory=tmp_path)
    body = path.read_text()
    assert "--deselect" not in body
    assert body.splitlines() == ["a.py::t[x y]", "b.py::t"]
    # No shell quoting either: each line is read as one argv element verbatim,
    # so a quote character here would become part of the node id.
    assert "'" not in body and '"' not in body
    # Trailing newline, so the repo's `while read` sees the last row. A file
    # whose final line lacks one is still read by `IFS= read -r` only because
    # the `[ -n "$row" ]` guard runs after a partial read — do not rely on it.
    assert body.endswith("\n")


# --------------------------------------------------------------------------
# Loading: fail CLOSED.
# --------------------------------------------------------------------------

def test_an_absent_register_is_empty_and_a_malformed_one_raises(
    tmp_path: Path,
) -> None:
    """A malformed register must never read as an empty one.

    An empty register suppresses nothing, which is safe to reach by accident. A
    malformed register that READ as empty would silently restore the D-68 tax
    while the file on disk claims otherwise — and the operator would be looking
    at entries that are not in force.

    Measured under: catch `RegisterError` in `load` and return
    `Register(entries=())`, and this reddens.
    """
    assert kr.load(tmp_path).is_empty          # absent file

    cfg = tmp_path / kr.REGISTER_RELPATH
    cfg.parent.mkdir(parents=True, exist_ok=True)

    cfg.write_text("entries:\n  - rows: []\n    seals_task: a\n"
                   "    body_task: b\n    reason: c\n")
    with pytest.raises(kr.RegisterError, match="non-empty list"):
        kr.load(tmp_path)

    cfg.write_text("entries:\n  - seals_task: a\n    body_task: b\n    reason: c\n")
    with pytest.raises(kr.RegisterError, match="missing required key"):
        kr.load(tmp_path)

    cfg.write_text("entries: 3\n")
    with pytest.raises(kr.RegisterError, match="expected a list"):
        kr.load(tmp_path)

    cfg.write_text("- not\n- a\n- mapping\n")
    with pytest.raises(kr.RegisterError, match="expected a mapping"):
        kr.load(tmp_path)

    # And the case that is NOT structural: bytes that are not YAML at all.
    #
    # ADDED after mutation verification found this branch unsealed. Every case
    # above raises from the structural checks, so replacing `load`'s
    # YAML-parse-error `raise` with `return Register(entries=())` fired NO row —
    # the one mutation of nine that this file missed. A register that is
    # unparseable is the MOST likely malformed state in practice (a truncated
    # write, a merge conflict marker) and it was the one state whose fail-closed
    # behaviour nothing pinned.
    cfg.write_text("entries: [unclosed\n  - {{{\n")
    with pytest.raises(kr.RegisterError, match="not parseable as YAML"):
        kr.load(tmp_path)

    # A merge conflict marker, which is how this actually arrives in a repo
    # where two branches both registered rows.
    cfg.write_text("<<<<<<< HEAD\nentries: []\n=======\nentries: [x]\n>>>>>>> b\n")
    with pytest.raises(kr.RegisterError):
        kr.load(tmp_path)


def test_a_well_formed_register_round_trips(tmp_path: Path) -> None:
    cfg = tmp_path / kr.REGISTER_RELPATH
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(textwrap.dedent("""\
        entries:
          - rows:
              - tests/test_x.py::test_widening_is_caught
            seals_task: W2-2-2
            body_task: W2-2-3
            reason: "P2 seal; body not landed"
            registered_at_sha: deadbee
    """))
    reg = kr.load(tmp_path)
    assert len(reg.entries) == 1
    e = reg.entries[0]
    assert e.body_task == "W2-2-3" and e.registered_at_sha == "deadbee"
    assert e.rows == ("tests/test_x.py::test_widening_is_caught",)


# --------------------------------------------------------------------------
# The non-vacuity anchor: real pytest, real failing row.
# --------------------------------------------------------------------------

def test_deselect_actually_suppresses_and_a_typo_does_not(tmp_path: Path) -> None:
    """The mechanism itself, executed — not asserted about.

    Four runs of REAL pytest against a REAL failing row. This is the row that
    would catch pytest changing `--deselect` semantics, or `deselect_args`
    rendering something pytest does not accept — neither of which any amount of
    dataclass arithmetic above can see.

    The fourth run is the one that makes the design safe rather than merely
    convenient: pytest does NOT error on a `--deselect` that matches no test, so
    a stale or misspelled entry leaves the row RUNNING. The mechanism fails
    TOWARD red. Measured under: nothing in this repo can mutate that — it is a
    property of pytest — which is exactly why it is pinned here rather than
    assumed in a comment.
    """
    suite = tmp_path / "test_suite.py"
    suite.write_text(textwrap.dedent("""\
        def test_healthy():
            assert True

        def test_seal_red_by_design():
            assert False, "P2 seal: body does not exist yet"
    """))

    def run(*extra: str) -> int:
        return subprocess.run(
            [sys.executable, "-m", "pytest", "test_suite.py", "-q", "--tb=no",
             *extra],
            cwd=tmp_path, capture_output=True, text=True,
        ).returncode

    red_row = "test_suite.py::test_seal_red_by_design"

    # 1. Today's behaviour: the whole suite is red, so the gate fails.
    assert run() != 0

    # 2. With the registered row deselected — rendered by the module under
    #    test, not hand-written — the suite is GREEN.
    import shlex
    args = shlex.split(kr.deselect_args((red_row,)))
    assert run(*args) == 0

    # 3. A targeted run of the registered row is red, which is how an operator
    #    (or a later auto-registration step) confirms it belongs in the
    #    register — exit code only, no report parsing.
    assert subprocess.run(
        [sys.executable, "-m", "pytest", red_row, "-q", "--tb=no"],
        cwd=tmp_path, capture_output=True, text=True,
    ).returncode != 0

    # 4. FAIL-SAFE: a typo'd entry deselects nothing and the suite stays red.
    typo = shlex.split(kr.deselect_args(("test_suite.py::test_does_not_exist",)))
    assert run(*typo) != 0


def test_this_repos_own_test_command_consumes_the_rows_file(tmp_path: Path) -> None:
    """The integration row: THIS repo's real `.dispatcher.yaml` idiom, run under
    `/bin/sh`, against a PARAMETRISED failing row.

    Every other row in this file tests the dispatcher's half. This one tests the
    contract between the halves, which is where both earlier designs died:

      * a pre-rendered argument string cannot survive shell expansion;
      * setting `IFS` to a newline is correct shell but cannot be WRITTEN inside
        the YAML block scalar that holds the command — a line holding a bare
        `"` at column 0 terminates the scalar and made `.dispatcher.yaml`
        unparseable.

    Neither failure is visible to a unit test of `known_red` alone, and the
    second was not visible to a shell test either. So the loop is closed here:
    the reader is the ACTUAL command out of the ACTUAL config file, executed by
    `/bin/sh` (dash on this machine — no arrays, no herestrings), and the rows
    file is written by the module under test.

    Measured under: revert the `.dispatcher.yaml` block to consume
    `$DISPATCHER_KNOWN_RED_ROWS` and this reddens; the parametrised id is what
    makes it bite rather than a plain one.
    """
    from claude_dispatcher import repo_config as rc

    repo_root = Path(__file__).resolve().parents[1]
    command = rc.load(repo_root).test
    assert command and kr.EXCLUSION_ENV in command, (
        "this repo's test command must reference the rows-file variable, or the "
        "register is declared and silently inert"
    )

    # Reduce the real command to its exclusion-reading prologue plus a pytest
    # invocation over a throwaway suite. The prologue is taken VERBATIM from the
    # config so a change to it reddens here.
    start = command.index("set --")
    end = command.index("PYTHONPATH=src")
    prologue = command[start:end]

    suite = tmp_path / "test_suite.py"
    suite.write_text(textwrap.dedent("""\
        import pytest

        def test_healthy():
            assert True

        @pytest.mark.parametrize("v", ["a plain property", "a static property"])
        def test_seal(v):
            assert False, "P2 seal: body does not exist yet"
    """))

    rows = (
        "test_suite.py::test_seal[a plain property]",
        "test_suite.py::test_seal[a static property]",
    )
    rows_file = kr.write_rows_file(rows, directory=tmp_path / "artifacts")

    script = prologue + f'{sys.executable} -m pytest test_suite.py -q --tb=no "$@"\n'

    def run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", "-c", script], cwd=tmp_path, capture_output=True,
            text=True, env={"PATH": "/usr/bin:/bin", **env},
        )

    # Without the file: two parametrisations fail, so the gate is red. This is
    # the state every task downstream of a seals task is in today.
    bare = run({})
    assert bare.returncode != 0, bare.stdout

    # With it: green, and pytest reports the rows as DESELECTED rather than
    # passed — the distinction that says they were excluded, not made to pass.
    applied = run({kr.EXCLUSION_ENV: str(rows_file)})
    assert applied.returncode == 0, applied.stdout
    assert "2 deselected" in applied.stdout, applied.stdout

    # Fail-safe, through the real idiom: a stale entry deselects nothing.
    stale = kr.write_rows_file(
        ("test_suite.py::test_seal[a renamed property]",),
        directory=tmp_path / "stale",
    )
    assert run({kr.EXCLUSION_ENV: str(stale)}).returncode != 0

    # A missing file is not an error either — the guard is `[ -f ]`, so a run
    # whose artifact dir was cleaned falls back to today's behaviour.
    assert run({kr.EXCLUSION_ENV: str(tmp_path / "gone.txt")}).returncode != 0


def test_a_suppressed_row_that_starts_passing_is_not_hidden_forever(
    tmp_path: Path,
) -> None:
    """Once the body lands, the entry retires and the row is REQUIRED green.

    This is the closing half of the loop and it is what stops the register from
    becoming a permanent excuse: retirement is driven by the body reaching Done,
    and after that the row runs like any other. Executed rather than asserted,
    for the same reason as the row above.
    """
    suite = tmp_path / "test_suite.py"
    suite.write_text("def test_seal():\n    assert True\n")  # body has landed
    reg = kr.Register(entries=(_entry(
        rows=("test_suite.py::test_seal",), body_task="U-3",
    ),))
    # Retired: nothing to exclude, so the gate runs the row and it must pass.
    assert kr.rows_for_task(reg, task_key="Z", done_keys={"U-3"}) == ()
    assert subprocess.run(
        [sys.executable, "-m", "pytest", "test_suite.py", "-q", "--tb=no"],
        cwd=tmp_path, capture_output=True, text=True,
    ).returncode == 0
