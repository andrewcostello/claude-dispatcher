"""D-66 — every role may record its own decisions, and only that.

DF-1-4 (adjudicate) ruled on a condemned seal, then wrote two docstrings saying
it had ruled — and was blocked. ADJUDICATE's writable set is exactly its
``disputed_paths``, which names the file to RULE ON and never the files that
POSE the dispute. The instinct was right: a module saying "P4 will rule on
this" is false the moment P4 rules.

Operator ruling 2026-08-14: a per-unit RULINGS file, not a docstring carve-out.
Measured before choosing — ``docs/rulings/`` was ALREADY writable by four of
five roles, so this widens exactly one role by exactly one documentation
directory, and leaves every deny table untouched.
"""

from __future__ import annotations

import pytest

from claude_dispatcher import role_protocol as rp

RULINGS = "docs/rulings/DF-1.md"


def _spec(role: rp.Role) -> rp.TaskRoleSpec:
    return rp.TaskRoleSpec(
        task_key="T-1",
        role=role,
        disputed_paths=("tests/x.py",) if role is rp.Role.ADJUDICATE else (),
    )


def _rule(role: rp.Role) -> rp.RoleRule:
    return rp.effective_rule(_spec(role), rp.built_in_policy())


def _decision(role: rp.Role, paths: list[str]) -> tuple:
    """What the DECISION says — rule, then floor unioned in, then the commons
    dropped. The commons lives here and not in any rule, so a row that asks
    `evaluate_changed_paths` alone is asking the wrong layer."""
    rule = _rule(role)
    floor = rp._floor_violations(paths)
    return rp._drop_commons(
        rp._union_with_floor(rp.evaluate_changed_paths(rule, paths), floor, paths),
        floor,
    )


# --- the channel exists for every role -------------------------------------

@pytest.mark.parametrize("role", list(rp.Role))
def test_seal_D66_every_role_may_write_the_rulings_record(role):
    """A scaffold condemning a seal, a body disclosing a deviation, an
    adjudicator ruling — each needs somewhere durable to say so. `summary.md`
    is archived per run and read by nobody afterwards."""
    assert not _decision(role, [RULINGS]), (
        f"{role.value} cannot record its own decisions")


def test_seal_D66_the_commons_is_not_in_any_rule(role=rp.Role.ADJUDICATE):
    """The design correction the existing seals forced.

    A first attempt added the rulings glob to ADJUDICATE's BUILT RULE and broke
    `test_effective_rule_for_allow_only_is_exactly_the_disputed_paths` —
    correctly. That seal pins a real property: the writable set of the most
    privileged role is entirely visible in its task row. A compiled-in glob
    silently added to it is the ADJUDICATE self-widening hazard in miniature.

    So the rule stays exactly the row, and the commons is applied beside it at
    the decision — the mirror of how the floor is unioned in.
    """
    built = _rule(role)
    assert built.globs == ("tests/x.py",), (
        f"the rulings glob leaked into the rule: {built.globs}")
    assert rp.RULINGS_GLOB not in built.globs
    # ...and the decision still permits it.
    assert not _decision(role, [RULINGS])


# --- and only that ----------------------------------------------------------

def test_seal_D66_the_channel_does_not_widen_anything_else(role=rp.Role.ADJUDICATE):
    """The whole argument for this shape over a docstring carve-out is that it
    widens ONE directory. An adjudicate branch must still be refused every path
    outside its disputed set."""
    for path in ("src/claude_dispatcher/merge_record.py",
                 "tests/test_merge_record.py",
                 "docs/not-rulings.md",
                 "docs/rulings.md"):
        assert _decision(role, [path]), (
            f"{path} became writable — the channel widened more than one dir")


def test_seal_D66_the_floor_is_untouched():
    """The floor is a separate stage and must stay that way. A rulings path
    passes it; the machinery paths do not."""
    assert not rp._floor_violations([RULINGS])
    for path in ("src/claude_dispatcher/orchestrator.py",
                 "src/claude_dispatcher/role_protocol.py"):
        assert rp._floor_violations([path]), f"{path} left the floor"


def test_seal_D66_the_floor_outranks_an_allow_list_that_would_permit_it():
    """The property the smuggling question actually turns on.

    An earlier version of this row asserted `evaluate_changed_paths(...) or
    True`, which passes however the code behaves — satisfiable by typing, the
    vacuous shape this project refuses. Replaced with the real invariant: the
    floor is a SEPARATE stage, so a floored path stays refused even when a
    role's own allow-list names it explicitly.
    """
    spec = rp.TaskRoleSpec(
        task_key="T-1", role=rp.Role.ADJUDICATE,
        disputed_paths=("src/claude_dispatcher/orchestrator.py",),
    )
    rule = rp.effective_rule(spec, rp.built_in_policy())
    allowed_by_rule = not rp.evaluate_changed_paths(
        rule, ["src/claude_dispatcher/orchestrator.py"])
    assert allowed_by_rule, (
        "fixture: the allow-list must name the floored path, or this row "
        "proves nothing about the floor outranking it")
    floor = rp._floor_violations(["src/claude_dispatcher/orchestrator.py"])
    assert floor, (
        "a role declared a floored path in its writable set and the floor let "
        "it through")
    # And the commons must not forgive it either.
    assert rp._drop_commons(floor, floor) == floor, (
        "the commons forgave a FLOORED path — the floor must outrank it")


# --- the line that must not be crossed --------------------------------------

def test_seal_D66_no_verdict_machinery_reads_the_rulings_files():
    """The stated boundary, checked mechanically.

    These files are DOCUMENTATION. If anything that computes a verdict ever
    reads them, a role writing its own rulings becomes a role influencing its
    own judgement — the D-65 lesson (a prose contract no gate can enforce)
    running in reverse, and worse. This row fails the moment a gate module
    learns to read them.
    """
    import pathlib

    src = pathlib.Path(rp.__file__).parent
    verdict_modules = (
        "role_protocol.py", "loop_gate.py", "seal_verify.py",
        "mechanical_verify.py", "risk.py", "call_site_reachability.py",
        "branch_reachability.py",
    )
    for name in verdict_modules:
        path = src / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        # The constant's own definition and its prose are expected in
        # role_protocol; a READ is not.
        for marker in ("docs/rulings", "RULINGS_GLOB"):
            if marker not in text:
                continue
            assert name == "role_protocol.py", (
                f"{name} references {marker!r}: a verdict module must not read "
                "the rulings record, or a role influences its own judgement")


# --- through the REAL gate, not a hand-built decision ------------------------

def _repo(tmp_path):
    """A real repository with a base commit; the gate reads git, not a fake."""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()

    def g(*a):
        subprocess.run(["git", *a], cwd=str(repo), capture_output=True,
                       check=True, timeout=30)

    g("init", "-q", "-b", "main")
    g("config", "user.email", "s@e.invalid")
    g("config", "user.name", "S")
    (repo / "seed.txt").write_text("base\n")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    return repo, g


def test_seal_D66_check_branch_ACTUALLY_applies_the_commons(tmp_path):
    """CALL SITE, not just behaviour.

    The first version of these rows built the decision by hand — rule, floor,
    `_drop_commons` — and so a mutant that deleted the `_drop_commons` CALL
    inside `check_branch` reddened NOTHING. That is the protocol gap this
    project built D5-D8 for: a seal proves a function behaves, never that it
    runs. Measured, and then fixed by this row.
    """
    repo, g = _repo(tmp_path)
    g("checkout", "-q", "-b", "feat/x")
    (repo / "docs" / "rulings").mkdir(parents=True)
    (repo / "docs" / "rulings" / "DF-1.md").write_text("# ruling\n")
    g("add", "-A")
    g("commit", "-q", "-m", "adjudicate: record the ruling")

    spec = rp.TaskRoleSpec(
        task_key="T-1", role=rp.Role.ADJUDICATE,
        disputed_paths=("tests/x.py",),
    )
    res = rp.check_branch(
        repo, "main", "feat/x", rp.Role.ADJUDICATE,
        spec=spec, policy=rp.built_in_policy(),
    )
    assert res.verdict is rp.DiffVerdict.CLEAN, (
        f"the live gate refused a rulings-only branch: {res.verdict} "
        f"{[v.path for v in res.violations]}")


def test_seal_D66_check_branch_still_refuses_everything_else(tmp_path):
    """Control for the row above: the commons must not have opened the gate."""
    repo, g = _repo(tmp_path)
    g("checkout", "-q", "-b", "feat/y")
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / "not-rulings.md").write_text("# nope\n")
    g("add", "-A")
    g("commit", "-q", "-m", "adjudicate: out of scope")

    spec = rp.TaskRoleSpec(
        task_key="T-1", role=rp.Role.ADJUDICATE,
        disputed_paths=("tests/x.py",),
    )
    res = rp.check_branch(
        repo, "main", "feat/y", rp.Role.ADJUDICATE,
        spec=spec, policy=rp.built_in_policy(),
    )
    assert res.verdict is rp.DiffVerdict.VIOLATION


def test_seal_D66_the_floor_outranks_the_commons_if_the_sets_ever_overlap(monkeypatch):
    """The guard's own case, which is unreachable with today's globs.

    `**/docs/rulings/**` names no machinery, so the floor and the commons are
    disjoint by construction and a mutant removing the `v.path in floored`
    check reddens nothing. That is honest but useless — the guard exists for
    the day either list grows. So the overlap is constructed here.
    """
    overlap = "docs/rulings/POLICY.md"
    monkeypatch.setattr(rp, "FLOOR_GLOBS", (*rp.FLOOR_GLOBS, "**/docs/rulings/POLICY.md"))
    floor = rp._floor_violations([overlap])
    assert floor, "fixture: the overlap must be on the floor"
    assert rp._drop_commons(floor, floor) == floor, (
        "the commons forgave a path that is ALSO on the floor — the floor must "
        "outrank it, or a rulings spelling buys a machinery file")
