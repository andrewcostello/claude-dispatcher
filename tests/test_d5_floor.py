"""D5 seals (P2): the reachability gate joins the floor BEFORE it is enrolled.

The defect
----------
`src/claude_dispatcher/call_site_reachability.py` is a gate. It decides, per
seal, whether a subject is reachable from a production root, and turns that into
a :class:`Disposition` a branch is judged by. Measured against this worktree
(`feat/D5-adj3` @ 8f44d1c) under the module's own glob lens::

    src/claude_dispatcher/call_site_reachability.py               floor=None
    sub/project/src/claude_dispatcher/call_site_reachability.py   floor=None

and, end to end against real repositories, for a branch whose only change is
that file, body-only, no signature touched::

    scaffold    clean       violations=[]
    bodies      clean       violations=[]
    adjudicate  clean       violations=[]   (with the path in `disputed_paths:`)
    legacy      clean       violations=[]
    seals       violation   — but only because SEALS is denied `**/src/**`,
                              which is not the floor and is not about this file

**Four of the five roles may rewrite the module that will judge them.** Same
shape D1 closed for `role_protocol.py` and its five delegates, D2 for the Go
helper and D4 for the TypeScript parser subtree. The module's own WIRING
section raises it in as many words and defers it:

    ``FLOOR_GLOBS``. Once wired, this module is a gate whose decisions can be
    dissolved by editing it, so by the 2026-08-09 delegation-closure ruling it
    belongs on the floor. … Deferred, deliberately, and recorded rather than
    done.

Why this round is BEFORE enrolment
----------------------------------
D2's rule, restated by D4: *a floor that arrives with enrolment is a floor that
was absent for every commit that built the thing it protects.* The subject
matter makes it worse than usual here. D5's whole thesis is that failing to look
is not a pass; a D5 the branch under review can edit reports whatever that
branch wants, and its report is then indistinguishable from a clean tree — which
is this module's own subject matter, one level up.

What this file seals, and what it deliberately does not
-------------------------------------------------------
**NO GLOB STRING IS ASSERTED ANYWHERE IN THIS FILE.** `_FLOOR_ROWS` in
`test_role_protocol_floor.py` is a set difference against `FLOOR_GLOBS`, so a
string P2 invents that P4 has not written there reddens a live seal in another
file in order to protect an unwired module — the exact coordination D5's WIRING
section refused to perform. This file pins what the string must DO. The property
is three-sided and identical to the one P4 already ruled under on 2026-08-09
(`test_the_floor_glob_over_a_delegation_target_is_path_qualified`): the real
path covered, the vendored `sub/project/...` layout covered, a same-basename
file elsewhere NOT covered.

Three recorded facts about this engine the rows below depend on, none of them
rediscovered here:

  * **No brace expansion.** `**/src/claude_dispatcher/{a,b}.py` is a literal
    matching one impossible filename — a floor written that way is a silent
    no-op that reads as protection. That is why no row here asserts the
    PRESENCE of a string: every row proves a REFUSAL, either through
    `first_matching_glob` or through a verdict on a real repository.
  * **A glob whose last segment is `**` has no plan-time reach.**
    `_floor_glob_named_by` refuses a pure-wildcard tail by design, so the two
    subtree entries are diff-time only. This module's entry is a FILE glob, so
    Part 5's plan-time rows are reachable — asserted there, not assumed.
  * The floor is enforced by `role_protocol.first_matching_glob` ->
    `risk.matches_any_glob`, and `risk._compiled` carries `re.DOTALL` because a
    real newline in a path bypassed both gates until it did.

Nothing here is implemented, enrolled, or coordinated. `role_protocol.py`,
`call_site_reachability.py`, `_FLOOR_ROWS`, `_DELEGATION_TARGETS` and
`_CLOSURE_ROWS` are untouched.

Vacuity discipline
------------------
The bar is this unit's own history: of 43 clauses in the D5 seal file, 12
recorded a measurement against the shipped body and 31 against a reference
implementation that was discarded, and one was never true at all. So the two
kinds of clause are never spelled the same way here:

    Measured under:               a mutation that was RUN against this tree
    Predicted (unmeasured) under: a mutation that was NOT run

Every row carries an in-test control judged IN THE SAME CALL, so a row cannot
pass because its lens is broken, because its fixture is stale, or because the
answer would be the same for every input. No table is a comprehension across the
constant it pins.

Reuse, not restatement
----------------------
The delegation-closure analyzer, the "policy that protects nothing", the
one-file-branch repository fixture and the self-judging CI checkout are all
IMPORTED from D1's seal files rather than rewritten. D5's question is what it
OWES that machinery, and a second copy of the machinery could answer it
differently from the first — which is the drift every registry in this codebase
exists to prevent. `test_capstone.py` establishes the cross-file import pattern.

RULINGS (P4, 2026-08-11, on `feat/D5-floor-adj`)
------------------------------------------------
All four disputes below are ruled. Each ruling is recorded where it BINDS —
next to the row or the table it changes — and summarised here. Everything cited
was re-measured against `feat/D5-floor-seals` @ 59a648d rather than carried over
from the seal author's record; every recorded measurement reproduced.

  1. **SPELLING: `**/src/claude_dispatcher/call_site_reachability.py`.** One
     path-qualified FILE glob. Ruled and reasoned in full on `_FLOOR_ROWS` in
     `tests/test_role_protocol_floor.py` (points 12-15), which is where P3
     reads it and where "one notion of one fact" puts it. Measured here:
     basename-only also swallows `vendor/thirdparty/...`; the package subtree
     also swallows `plan.py` and `blast_radius.py` and buys no plan-time reach;
     the brace-compressed spelling matches nothing at all and leaves all
     seventeen rows red.

     **COORDINATION: SPLIT, and the split is forced rather than chosen.** P4
     landed the two `_FLOOR_ROWS` rows and both bounds (`>= 24 -> >= 26`,
     `>= 10 -> >= 11`) — seal amendments, which only P4 may make. P4 did NOT
     land the `FLOOR_GLOBS` constant: `role_protocol.py` is itself on the floor,
     and `check_branch` refuses that path to ADJUDICATE with `FLOOR_RATIONALE`
     even when it is declared in `disputed_paths:` (measured 2026-08-11). The
     gate under adjudication forbids the adjudicator from writing it. It is a
     reviewed edit on the protected base, and it is P3's.

     Consequence, stated because it moves the round's red count: this file is
     unchanged at 17 red, and
     `test_role_protocol_floor.py::test_every_floor_glob_the_ruling_wrote_out_
     is_in_the_constant` is red for the interval — 18 across the two files. That
     is the price that row's own docstring names and accepts. Measured joint
     satisfiability, `.git`-less clone, `__pycache__` cleared: constant + rows +
     bounds moves the suite from 17 failed / 2296 passed to 1 failed / 2312
     passed, and the one survivor is ruling 2's row.

  2. **THE IMPORT-TIME ORDERING GUARD: DEFERRED. The row stays red and gains a
     fifth control.** Not because the property is wrong but because the fix this
     round would have shipped is: the recommended derivation bricks the
     installed wheel, and the row could not see it. Ruled in full on
     `test_enrolment_is_impossible_while_the_floor_row_is_red`, which now
     carries control (e) and the measurement. What stops the ordering being
     forgotten is that this round DISCHARGES it — the floor lands first, and the
     only way back is deleting the glob, which reddens nineteen rows including
     the sibling seal that re-arms on exactly that edit. Measured.

  3. **THE PLAN-TIME BASENAME ASYMMETRY, 8 -> 9: CONFIRMED, not revisited.**
     Measured in the clone with the glob landed: `call_site_reachability.py`,
     the full path, AND `vendor/thirdparty/call_site_reachability.py` all return
     the new glob from `_floor_glob_named_by`, while `src/claude_dispatcher/**`
     returns None. Nine of eleven globs are plan-time reachable and two subtree
     globs are not. The 2026-08-09 reasoning holds unchanged and for its own
     reason rather than by precedent: the asymmetry can only false-refuse, never
     false-clear, and the false refusal has a spelling that works. The seal
     author's judgement that this is the least collision-prone of the nine
     stands — the eight incumbents include `risk.py`, `repo_config.py` and
     `yaml_io.py`, and no plausible unrelated file is named
     `call_site_reachability.py`.

  4. **THE CROSS-FILE IMPORTS: ACCEPTED AS WRITTEN. Do not fork the analyzer or
     the CI-checkout fixture.** The reasoning is right and this round is
     evidence for it: Part 2's finding is "nothing further is owed", and that
     finding is only worth anything because it was computed by the SAME analyzer
     D1's own closure is computed by. A second copy could answer D5's question
     differently from the way D1's answers its own, and the two would drift
     silently, in the one direction nobody looks. The recorded remedy is also
     right: if it bites, move the helpers to a shared module, do not copy them.

     **One thing the dispute understates, and it is the part with teeth.** The
     cost is not "an ERROR instead of a FAIL" — it is that a collection error is
     not a FAILED line, and THIS ROUND'S CONTRACT IS A RED COUNT. If D1's seal
     files are renamed, this file does not report 17 red; it reports none, and a
     gate reading FAILED lines sees the number improve. So the count is ruled
     insufficient on its own: any gate or hand-off that states this file's red
     count MUST state its collected count beside it. This file collects 34 items
     (17 red, 17 green); P4's amendment adds a control inside an existing row
     and collects 34 still. A 34 that becomes a 0 is the rename, and it is the
     only reading under which that is visible.

     **P4, 2026-08-11 (unit D6 floor round, ``feat/D6-floor2``): 34 -> 35, 0
     red.** The D6 round adds ONE row —
     `test_the_guard_judges_the_rows_own_module_and_its_helper` — and three
     defaulted axes to `_package_copy` that no existing row passes. The count
     obligation above is why the change is recorded here rather than only at the
     row: a file whose collected count moves without a line saying so is exactly
     the reading that hides a rename. Everything this file's dispute rulings say
     about the D5 round stands as written; the 17-red state they describe is
     history, and the whole file is green on this branch.

Disputes as the seal author raised them, kept verbatim below so the rulings can
be read against what was actually asked.

  1. **The spelling, and the coordination that comes with it.** Nothing here
     names a glob string, but the ruling is not free: `_FLOOR_ROWS` in
     `test_role_protocol_floor.py` is a set difference against `FLOOR_GLOBS` in
     BOTH directions, and its two bounds are absolute. Landing the glob without
     landing its rows reddens
     `test_the_floor_is_exactly_the_written_out_set_of_globs`; landing both
     without raising the bounds leaves the whole entry deletable in silence.
     Measured in a `.git`-less clone: the constant, plus two `_FLOOR_ROWS` rows
     (the real path and the `sub/project/...` layout), plus `>= 24 -> >= 26` and
     `>= 10 -> >= 11`, is the complete edit and the whole suite is green after
     it. P2 has NOT made it — it is a seal amendment in another unit's file,
     which is exactly the coordination D5's WIRING section refused to perform.

  2. **The enrolment-ordering row costs a production change, and the OTHER
     shape of it collides with a live D5 seal.** Recorded because the collision
     is not obvious and the first draft walked into it. Writing the ordering as
     "`validate_analyzers` refuses a well-formed row while the module is off the
     floor" reddens `test_call_site_reachability.py::
     test_validate_analyzers_refuses_a_row_no_path_can_reach`, which ends by
     asserting that a Go row IS accepted once its language is enrolled.
     `test_enrolment_is_impossible_while_the_floor_row_is_red` therefore states
     the property at IMPORT time and names no mechanism; `validate_analyzers`'s
     contract is untouched and that row stays green.

  3. **The plan-time basename asymmetry widens by one, and this entry is the
     mild case.** `_floor_glob_named_by` compares basenames, so once this glob
     lands, `call_site_reachability.py` declared ANYWHERE is refused at plan
     time — including a vendored copy the diff-time half would clear. P4
     accepted this on 2026-08-09 when the floor's basename count went 3 -> 8 and
     three of the new names (`risk.py`, `repo_config.py`, `yaml_io.py`) were
     names an unrelated file could plausibly acquire. This makes nine, and it is
     the least likely of the nine to collide. Recorded, not re-argued.

  4. **This file ERRORs rather than FAILS if D1's seal files are renamed.** It
     imports eight private helpers from `test_floor_closure` and seven names
     from `test_role_protocol_provenance`, and a collection error is not a red
     row.
     The alternative is a second copy of the analyzer and of the CI-checkout
     fixture, which could answer D5's question differently from the way D1's
     answers its own — the failure this whole effort exists to close. The cost
     is accepted deliberately; if it bites, the fix is to move those helpers to
     a shared module, not to fork them.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import call_site_reachability as csr
from claude_dispatcher import role_protocol as rp_mod
from claude_dispatcher.role_protocol import (
    FLOOR_GLOBS,
    FLOOR_RATIONALE,
    DiffVerdict,
    ExitCode,
    Role,
    RoleProtocolError,
    check_branch,
    first_matching_glob,
    parse_task_role_spec,
)

# D1's analyzer and repository fixtures, reused. See "Reuse, not restatement".
from test_floor_closure import (
    _STRIPPED_RATIONALE,
    _branch_that_only_edits,
    _delegation_closure,
    _in_package_imports,
    _module_level_in_package_imports,
    _package_source,
    _policy_that_protects_nothing,
    _spec,
)

# D1's self-judging CI checkout, reused. `ci_checkout_template` is a fixture and
# is imported into this namespace so pytest can resolve it here.
from test_role_protocol_provenance import (  # noqa: F401
    GATE_ENTRYPOINT,
    GATE_LIBRARY,
    _checkout,
    _commit,
    _run_gate,
    _trusted_script,
    ci_checkout_template,
)

#: The module under seal, as a Python module name and as git spells its path.
#: Written out; nothing here reads either off `FLOOR_GLOBS`, off `ANALYZERS` or
#: off the package directory.
_D5_MODULE = "call_site_reachability"
_REACHABILITY_GATE = "src/claude_dispatcher/call_site_reachability.py"

#: The vendored layout. This repository can sit inside another tree, which is
#: why every glob in `DEFAULT_ROLE_RULES` is spelled `**/x/**`.
_REACHABILITY_GATE_NESTED = (
    "sub/project/src/claude_dispatcher/call_site_reachability.py"
)

#: The row's own upper bound: a floor has no override, so a basename-only glob
#: would permanently forbid every file that ever acquires this basename.
_SAME_BASENAME_ELSEWHERE = "vendor/thirdparty/call_site_reachability.py"

#: The unit's established ordinary-source probe, and D1's: a floor reaching for
#: `**/src/claude_dispatcher/**` would stop BODIES doing its job, with no
#: override, forever.
_ORDINARY_SOURCE = "src/claude_dispatcher/plan.py"

#: A sibling scaffold in the same package that is NOT a gate. Second ordinary
#: probe, chosen because it is the file a "floor the analyzers" over-reach would
#: take first.
_SIBLING_SCAFFOLD = "src/claude_dispatcher/blast_radius.py"


# --------------------------------------------------------------------------- #
# Part 1 — the module is on the floor
# --------------------------------------------------------------------------- #


def test_the_reachability_gate_is_on_the_floor() -> None:
    """ONE ROW, RED. The whole round in a single question.

    Three-sided, and all three are judged in this call, because a floor entry
    that gets any one of them wrong is a different defect each time:

      a. the real path is covered — the round's subject;
      b. the vendored `sub/project/...` layout is covered — one pattern must
         cover both, as every other glob in this unit does;
      c. `vendor/thirdparty/call_site_reachability.py` is NOT covered — a floor
         has no override, so a basename-only spelling permanently forbids every
         file that ever acquires this basename, and nothing can buy it back.

    Two in-call controls come FIRST, so this row cannot pass on a broken lens
    and cannot be satisfied by flooring the package:

      * positive — `role_protocol.py`, already floored, is reported floored;
      * negative — `plan.py`, which three other seal files require to stay
        writable, is reported unfloored.

    RED TODAY. Measured against 8f44d1c: assertion (a) fails —
    `first_matching_glob(_REACHABILITY_GATE, FLOOR_GLOBS)` is None, as is the
    same call for the nested layout.

    Green when: some glob in `FLOOR_GLOBS` covers (a) and (b) and none covers
    (c). No string is named here; the spelling is P4's.

    Measured under: `FLOOR_GLOBS = ()` — the positive lens control fails first,
    so an emptied floor cannot make this row pass.
    Measured under: appending `**/call_site_reachability.py` (the basename-only
    spelling) — (a) and (b) pass and (c) FAILS, naming the vendored file.
    Measured under: appending `**/src/claude_dispatcher/**` (floor the package)
    — the negative lens control FAILS FIRST, before (a) is reached: "the floor
    grew to cover an ordinary source module".
    Measured under: appending
    `**/src/claude_dispatcher/{call_site_reachability,blast_radius}.py` (the
    compressed spelling this engine cannot expand) — the row stays RED exactly
    as it is today, which is the point: a floor string that is present and
    matches nothing is indistinguishable here from no floor at all.
    """
    # The lens works at all: the module the floor already covers is covered.
    assert (
        first_matching_glob("src/claude_dispatcher/role_protocol.py", FLOOR_GLOBS)
        is not None
    ), "the floor does not cover role_protocol.py; this row's lens is broken"
    # And it is not simply saying yes: an ordinary module stays writable.
    assert first_matching_glob(_ORDINARY_SOURCE, FLOOR_GLOBS) is None, (
        "the floor grew to cover an ordinary source module; flooring the "
        "package is not protecting the gate"
    )

    covering = first_matching_glob(_REACHABILITY_GATE, FLOOR_GLOBS)
    assert covering is not None, (
        f"{_REACHABILITY_GATE} is not on the floor. It decides, per seal, "
        "whether a subject is reachable, and a role that may write it may "
        f"decide what its own verdict is: {list(FLOOR_GLOBS)}"
    )
    assert first_matching_glob(_REACHABILITY_GATE_NESTED, FLOOR_GLOBS) is not None, (
        f"the floor covers {_REACHABILITY_GATE} but not the vendored layout "
        f"{_REACHABILITY_GATE_NESTED}; one pattern must cover both"
    )
    assert first_matching_glob(_SAME_BASENAME_ELSEWHERE, FLOOR_GLOBS) is None, (
        f"the floor glob covering the reachability gate also swallows "
        f"{_SAME_BASENAME_ELSEWHERE}. A floor has no override, so a "
        f"basename-only glob permanently forbids every file that ever acquires "
        f"that name: {covering!r}"
    )


# --------------------------------------------------------------------------- #
# Part 2 — the delegation closure: what D5's decisions reach
#
# D1's ruling is that every in-package module whose code RUNS while a floor
# decision is reached must itself be on the floor, and that the closure is
# DERIVED from source rather than enumerated. D5 is a second decision module, so
# the same question has to be asked about it: which modules does a D5 decision
# reach, and is each of them floored?
#
# The derivation below reuses D1's primitives (`_in_package_imports`,
# `_module_level_in_package_imports`) and differs from `_delegation_closure` in
# exactly one respect, which is a STRENGTHENING: D1 seeds from two written-out
# root functions and walks `role_protocol`'s intra-module call graph, and has a
# whole seal (`test_every_floor_decision_is_reachable_from_the_written_out_
# roots`) guarding that hand-written list against going stale. Here EVERY
# module-level function of `call_site_reachability` is a root, so the root list
# cannot go stale and there is nothing to guard.
#
# D1 could not do that: seeding `role_protocol` at everything drags `plan.py`
# into the closure through `validate`/`units_of` and would floor the unit's
# ordinary-source probe. Measured here, the widening costs nothing — the closure
# is the same three modules whether the roots are `check_tree` alone, the five
# decision functions, or all 26 module-level functions.
# --------------------------------------------------------------------------- #


def _d5_delegation_closure(read=_package_source) -> dict[str, str]:
    """Modules whose code runs while a D5 decision is reached → why.

    Same three steps as `_delegation_closure`, with the call-graph walk of step
    1 replaced by "every module-level function is a root" (see the section
    comment). `read` is the source seam, so the rows below can point this
    analyzer at a mutated copy of the package and check that it notices.

    `call_site_reachability` itself is dropped from the result for D1's reason:
    it is the module making the decision, and a self-row would make "everything
    in the closure is floored" one row less falsifiable.
    """
    source = read(_D5_MODULE)
    if source is None:
        raise AssertionError(
            f"the analyzer cannot find {_D5_MODULE}'s source; an empty closure "
            "would make every claim in Part 2 vacuously true"
        )
    tree = ast.parse(source, filename=f"{_D5_MODULE}.py")
    functions = {
        stmt.name: stmt
        for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if not functions:
        raise AssertionError(
            f"{_D5_MODULE} has no module-level functions, so this analyzer has "
            "no roots and would report an empty closure for the wrong reason"
        )

    why: dict[str, str] = {}
    frontier: list[str] = []

    def note(module: str, reason: str) -> None:
        if module not in why:
            why[module] = reason
            frontier.append(module)

    for name in sorted(functions):
        for node in ast.walk(functions[name]):
            for module in sorted(_in_package_imports(node)):
                note(module, f"imported by {_D5_MODULE}.{name}()")
    for module in sorted(_module_level_in_package_imports(tree)):
        note(module, f"imported by {_D5_MODULE} at module level")

    while frontier:
        module = frontier.pop()
        sub_source = read(module)
        if sub_source is None:
            continue
        sub_tree = ast.parse(sub_source, filename=f"{module}.py")
        for dep in sorted(_module_level_in_package_imports(sub_tree)):
            note(dep, f"executed at import of {module} (module-level import)")

    why.pop(_D5_MODULE, None)
    return why


def _closure_with_a_planted_import(target_function: str, planted: str) -> dict[str, str]:
    """The D5 closure computed over a copy of the package with one import added.

    The mutation is in memory only and the package on disk is never written.
    `target_function` must be a module-level function of `call_site_
    reachability`, or this raises rather than quietly planting nothing.
    """
    real_source = _package_source(_D5_MODULE)
    assert real_source is not None
    tree = ast.parse(real_source)
    hits = 0
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == target_function:
            stmt.body.insert(
                0,
                ast.ImportFrom(
                    module=None, names=[ast.alias(name=planted)], level=1
                ),
            )
            hits += 1
    assert hits == 1, (
        f"the injection point {target_function!r} was not found exactly once "
        f"({hits} hits), so this control planted nothing and proves nothing"
    )
    mutated = ast.unparse(ast.fix_missing_locations(tree))

    def read(module: str) -> str | None:
        return mutated if module == _D5_MODULE else _package_source(module)

    return _d5_delegation_closure(read)


def test_the_d5_analyzer_reads_real_source_and_can_report_a_new_delegation() -> None:
    """The analyzer's own non-vacuity, before anything is asserted with it.

    GREEN TODAY and must stay green. Four things in one call, each of which
    would make the two rows after it meaningless if it were false:

      1. the closure is non-empty — an empty closure makes "everything D5
         reaches is floored" vacuously true, and that is the single most likely
         way this whole Part reads as protection while proving nothing;
      2. it contains the two modules the source visibly imports at module level,
         `role_protocol` and `seal_verify` — so it is reading THIS module and
         not some other file;
      3. it does NOT contain `bakeoff`, a module nowhere near D5 — without this,
         "return every module in the package" satisfies the Part and would
         floor the tree;
      4. a `from . import bakeoff` planted inside `check_tree` — the shape a new
         D5 delegate would actually have — IS reported. A hand-written list
         cannot do this, which is why the derivation exists; a derivation nobody
         falsified is worse than the hand-written list, which is why (4) exists.

    Both the mutated and unmutated closures are computed in this one call, so
    the row proves the INJECTION is the difference and not something the
    analyzer says about `bakeoff` in general.

    Measured under: making `_d5_delegation_closure` return `{}` — (1) fails.
    Measured under: seeding the roots from `("check_tree",)` alone instead of
    from every module-level function — this row and both rows below are
    UNCHANGED, which is the measurement recorded in the section comment.
    Measured under: dropping the transitive step-3 walk — the closure becomes
    `['role_protocol', 'seal_verify']` and **NOTHING IN THIS FILE GOES RED**.
    (1)-(4) still pass here, and the row below still passes because both
    survivors are floored. Recorded as a LIMIT rather than dressed up as a
    guard: this file cannot tell a correct step 3 from an absent one while every
    module step 3 finds happens to be floored already. What would catch it is
    `test_floor_closure.py`'s own two-way pin, where `mechanical_verify` has a
    written-out row that a shrunken derivation contradicts.
    Predicted (unmeasured) under: `_in_package_imports` returning
    `frozenset()` — (2) fails.
    """
    closure = _d5_delegation_closure()
    assert closure, (
        "the analyzer found no delegation at all; an empty closure makes "
        "'every module a D5 decision reaches is floored' vacuously true"
    )
    assert {"role_protocol", "seal_verify"} <= set(closure), (
        "the analyzer did not find the two modules "
        f"{_D5_MODULE} imports at module level: {sorted(closure)}"
    )
    assert "bakeoff" not in closure, (
        "the analyzer reported a module that is nowhere on a D5 decision path; "
        "a closure that over-reaches would floor the tree, which is not a fix"
    )
    assert _D5_MODULE not in closure, (
        "the deciding module must not be a row in its own closure"
    )

    injected = _closure_with_a_planted_import("check_tree", "bakeoff")
    assert "bakeoff" in injected, (
        "a `from . import bakeoff` planted inside `check_tree` — the function "
        "that returns a D5 verdict — was not reported as a delegation, so a "
        "real new delegate would land unnoticed and the two rows below would "
        "be green about a closure they cannot see"
    )


def test_every_module_a_d5_decision_reaches_is_already_on_the_floor() -> None:
    """What D5 OWES the delegation closure, measured. GREEN TODAY, and the
    finding is that **nothing further is owed** — with the proof, not the claim.

    Measured against 8f44d1c, the closure and each module's floor status::

        role_protocol      **/src/claude_dispatcher/role_protocol.py
                           (imported by call_site_reachability at module level)
        seal_verify        **/src/claude_dispatcher/seal_verify.py
                           (imported by call_site_reachability at module level)
        mechanical_verify  **/src/claude_dispatcher/mechanical_verify.py
                           (executed at import of seal_verify)

    Three modules, three floor globs, no gap. `call_site_reachability` imports
    exactly `role_protocol` (for `COMPARATORS`, `Language`, `support_for_path`)
    and `seal_verify` (for `is_test_path`), both at module level and both
    already floored by D1's ruling; `seal_verify` drags `mechanical_verify` in
    at import, which D1 floored for that same reason. So D5's floor entry is one
    glob and not six, and this row is the evidence for that rather than the
    assertion of it.

    Two entry-point facts measured alongside, because D1's `_DELEGATION_TARGETS`
    checklist item (b) asks for exactly them: `role_protocol.support_for_path`
    and `seal_verify.is_test_path` are both LEAVES — neither reaches another
    in-package module, by call or by function-local import. So the closure is
    not merely floored today, it is shallow.

    THE BOUND, recorded because the next author will reach for the wider
    derivation and it is wrong. Measured: following EVERY in-package import at
    every scope — module-level, function-local and `TYPE_CHECKING` — transitively
    from this module reports two more, `plan` and `quality_levels`, both
    unfloored. Those arrive through `role_protocol`'s `if TYPE_CHECKING: from .
    import plan as plan_mod` and a function-local import in `validate`, neither
    of which executes on a D5 decision path. D1 excluded both shapes on purpose
    ("a `TYPE_CHECKING` import executes nothing and can rebind nothing", and
    widening the walk to closure members' call graphs is "over-reach in a floor
    [which] is permanent and unappealable"), and `plan.py` is the unit's
    ordinary-source probe that three seal files require to stay writable. The
    wide answer is therefore not a gap this round should close; it is the
    over-reach D1 already ruled against, reproduced here so the ruling is not
    rediscovered as a finding.

    GREEN TODAY and must stay green. Its value is the NEXT delegation: a D5 that
    grows an import of an unfloored module reddens here, naming it.

    Measured under: planting `from . import bakeoff` inside `check_tree` — this
    row FAILS naming `bakeoff`, which is what proves the assertion is not
    satisfied by the shape of the data. That mutation is run in this same call.
    Measured under: `FLOOR_GLOBS = ()` — this row fails naming all three.
    Measured under: deleting `**/src/claude_dispatcher/mechanical_verify.py`
    from `FLOOR_GLOBS` — fails naming `mechanical_verify` only.
    Measured under: appending `**/src/claude_dispatcher/**` — this row fails on
    its own IN-CALL CONTROL rather than on the closure, because a floor covering
    the package floors `bakeoff` too and the planted delegation is no longer
    unfloored. Recorded so the message is not misread as a real gap: the row is
    red under that mutation, and it is red because the mutation destroyed the
    control's ability to distinguish anything, which is itself the finding.
    """
    closure = _d5_delegation_closure()
    assert closure, "an empty closure would make the assertion below vacuous"

    def unfloored(members: dict[str, str]) -> list[str]:
        return sorted(
            module
            for module in members
            if first_matching_glob(f"src/claude_dispatcher/{module}.py", FLOOR_GLOBS)
            is None
        )

    # The control, judged in this same call: the assertion below is capable of
    # failing. One planted import into a D5 decision function is enough.
    injected = _closure_with_a_planted_import("check_tree", "bakeoff")
    assert "bakeoff" in unfloored(injected), (
        "a planted delegation to an unfloored module was not reported as "
        f"unfloored, so the assertion below cannot fail: {sorted(injected)}"
    )

    gaps = unfloored(closure)
    assert not gaps, (
        "a D5 decision runs code in modules the floor does not protect, so a "
        "branch can dissolve a D5 verdict while touching nothing the floor "
        "names. Floor them, or take them off the D5 decision path: "
        + "; ".join(f"{m} ({closure[m]})" for m in gaps)
    )


def test_flooring_d5_adds_no_row_to_the_floors_own_delegation_closure() -> None:
    """The other direction, and the reason this round needs no D1 coordination.

    GREEN TODAY. `role_protocol` does not import `call_site_reachability` — the
    dependency runs the other way — so D5 is not in the FLOOR's delegation
    closure, `_DELEGATION_TARGETS` needs no new row, and this round touches
    `tests/test_floor_closure.py` not at all. Measured: `call_site_reachability`
    is absent from `_delegation_closure()`, and nothing in the package imports
    it today (nobody: it is unenrolled, which is the state Part 6 pins).

    This is a real property and not bookkeeping. The day D5 is WIRED into a
    floor decision — `role_protocol` calling it, or importing it at module level
    — it enters the floor's own closure, `_DELEGATION_TARGETS` acquires a row,
    and that is a P4 round rather than a P3 edit. This row is what makes that
    day visible instead of silent.

    Measured under: planting `from . import call_site_reachability` inside
    `_floor_violations` (a function that reads `FLOOR_GLOBS`) — the first
    assertion below FAILS. That mutation is run in this same call, so the row
    is proven falsifiable rather than asserted to be.
    Measured under: `_delegation_closure` returning `{}` — the lens control
    fails first.
    """
    floors_closure = _delegation_closure()
    # The lens control: D1's analyzer is alive and finds the delegation the
    # panel reproduced. Without this, a broken analyzer passes the row below.
    assert "risk" in floors_closure, (
        "D1's analyzer did not find role_protocol.first_matching_glob -> "
        f"risk.matches_any_glob; the row below would be vacuous: {floors_closure}"
    )

    # The control, judged in this same call: a `role_protocol` that DID delegate
    # to D5 is reported. So the assertion after it can fail.
    real_source = _package_source("role_protocol")
    assert real_source is not None
    tree = ast.parse(real_source)
    planted = 0
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == "_floor_violations":
            stmt.body.insert(
                0,
                ast.ImportFrom(
                    module=None, names=[ast.alias(name=_D5_MODULE)], level=1
                ),
            )
            planted += 1
    assert planted == 1, "the injection point `_floor_violations` was not found once"
    mutated = ast.unparse(ast.fix_missing_locations(tree))

    def read(module: str) -> str | None:
        return mutated if module == "role_protocol" else _package_source(module)

    assert _D5_MODULE in _delegation_closure(read), (
        "a floor decision that imports the reachability gate was not reported "
        "as a delegation, so the assertion below cannot fail"
    )

    assert _D5_MODULE not in floors_closure, (
        "the reachability gate is now in the FLOOR's own delegation closure, "
        "so flooring it is no longer only D5's business: it needs a row in "
        "`_DELEGATION_TARGETS` and `_CLOSURE_ROWS` in tests/test_floor_"
        f"closure.py, which is a P4 round. Reason: {floors_closure[_D5_MODULE]}"
    )


# --------------------------------------------------------------------------- #
# Part 3 — the consequence, end to end, against real repositories
#
# Real repositories rather than a stubbed `run`, for D1's reason: a seam that
# could not answer `merge-base` turned refusal rows green, and a seam that
# answered a BODIES blob read wrongly turned writable rows red. A repository
# cannot answer a command the gate did not run. `_branch_that_only_edits` and
# `_policy_that_protects_nothing` are D1's, imported.
# --------------------------------------------------------------------------- #

#: (role, changed path). WRITTEN OUT, one row per role. Derived from nothing:
#: not from `Role`, not from `FLOOR_GLOBS`, not from a product comprehension.
#:
#: LEGACY is a row for the same reason the floor covers it: LEGACY is not
#: granted to anyone, it is what a row IS when the `role:` key is absent, so a
#: protection LEGACY escapes is bypassed by deleting one line.
_D5_GATE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", _REACHABILITY_GATE),
    ("seals", _REACHABILITY_GATE),
    ("bodies", _REACHABILITY_GATE),
    ("adjudicate", _REACHABILITY_GATE),
    ("legacy", _REACHABILITY_GATE),
)


@pytest.mark.parametrize(
    "role_value, changed", _D5_GATE_ROWS, ids=[f"{r}-{c}" for r, c in _D5_GATE_ROWS]
)
def test_no_role_gets_a_clean_verdict_for_editing_the_reachability_gate(
    role_value: str, changed: str, tmp_path
) -> None:
    """FIVE ROWS, ALL RED, under a policy that protects nothing.

    The whole branch is one body-only edit to the module that decides whether a
    subject is reachable. The supplied policy mentions the path nowhere and each
    row PROVES that first, so a refusal cannot come from the deny table, from
    `built_in_policy`, or from a repo `roles:` addition: it requires a tier no
    supplied policy can lower, which is what `FLOOR_GLOBS` is. The final
    assertion checks the violation did not carry the injected rationale, so a
    row cannot pass on a refusal the injected policy produced.

    This is the row that answers "prove refusal, not presence". A floor glob
    that is present and matches nothing — the compressed spelling — leaves every
    one of these five CLEAN.

    RED TODAY. Measured against 8f44d1c, real repositories: scaffold, seals,
    bodies, adjudicate and legacy all return `DiffVerdict.CLEAN` with
    `violations == ()` under this policy.
    Green when: each returns a VIOLATION naming exactly the changed path.

    Measured under: appending
    `**/src/claude_dispatcher/{call_site_reachability,blast_radius}.py` to
    `FLOOR_GLOBS` — all five rows stay RED. The compressed floor is not a floor.
    Measured under: appending `**/src/claude_dispatcher/**` — all five pass, and
    `test_flooring_the_reachability_gate_costs_the_rest_of_the_tree_nothing`
    goes red instead, which is the pairing that stops "refuse everything".
    Measured under: appending the path to every `DENY_GLOBS` rule's `globs`
    instead of to the floor — all five rows stay RED, because the policy these
    rows supply replaces the table wholesale. This is the difference between
    this row and the one below it, and it is why they are separate functions.
    """
    role = Role(role_value)
    policy = _policy_that_protects_nothing()
    rule = policy.rule_for(role)

    # The fixture exhibits the defect: nothing in the supplied policy protects
    # this path, so a violation can only come from a tier above the policy.
    assert first_matching_glob(changed, rule.globs) is None, (
        "the injected policy already denies the probe; this row would then "
        "pass without any floor existing"
    )
    spec = _spec(role, changed) if role is Role.ADJUDICATE else None
    if spec is not None:
        assert first_matching_glob(changed, spec.disputed_paths) == changed, (
            "the adjudicate declaration does not grant the probe, so this row "
            "would pass on an allowlist miss rather than on the floor"
        )

    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", role, policy=policy, spec=spec)

    assert [v.path for v in result.violations] == [changed], (
        f"role {role_value} rewrote {changed!r} — the module that decides "
        f"whether a subject is reachable — and the verdict was "
        f"{result.verdict.value}"
    )
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.violations[0].rationale != _STRIPPED_RATIONALE, (
        "the violation printed the injected policy's rationale, so it came "
        "from the policy — the one thing a caller can replace wholesale"
    )


@pytest.mark.parametrize(
    "role_value, changed", _D5_GATE_ROWS, ids=[f"{r}-{c}" for r, c in _D5_GATE_ROWS]
)
def test_the_reachability_gate_is_refused_under_the_policy_the_gate_runs_with(
    role_value: str, changed: str, tmp_path
) -> None:
    """The same five rows under `built_in_policy()` — the policy CI has.

    The row above proves unlowerability by stripping the policy; this one proves
    the protection is reachable on the path production takes. Separate functions
    on purpose: an implementation that put the path only in a caller-supplied
    default would satisfy one and not the other.

    RED TODAY for four of the five. Measured against 8f44d1c: scaffold, bodies,
    adjudicate and legacy return CLEAN. The `seals` row is ALREADY a VIOLATION
    for an unrelated reason — SEALS is ALLOW_ONLY_GLOBS and `**/src/**` is not
    in its writable set — and that is fine: this file's job is that no role gets
    CLEAN, not that every row gets there by a new mechanism. It is kept because
    a future narrowing of the SEALS rule would otherwise open the path silently.

    Green when: all five are VIOLATION naming the path.
    Measured under: `FLOOR_GLOBS = ()` — the four currently-red rows stay red
    and `seals` stays green, i.e. this row alone cannot tell a floor from the
    SEALS rule. That is what the row above is for.
    Measured under: appending the path to every `DENY_GLOBS` rule's `globs`
    instead of to the floor — `scaffold` and `bodies` go GREEN while
    `adjudicate` and `legacy` stay red. So this table alone cannot tell a floor
    from a deny addition either; the two rows that can are the stripped-policy
    table above and the rationale row below.
    """
    role = Role(role_value)
    spec = _spec(role, changed) if role is Role.ADJUDICATE else None
    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", role, spec=spec)
    assert [v.path for v in result.violations] == [changed], (
        f"under the built-in policy, role {role_value} may write {changed!r}"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_a_floor_violation_on_the_reachability_gate_reports_the_floors_own_reason(
    tmp_path,
) -> None:
    """ONE ROW, RED. The report an agent actually has to read.

    The refusal must arrive as a FLOOR refusal. For ADJUDICATE the role's own
    rationale says the writable set IS `disputed_paths:` — the one sentence that
    cannot explain refusing a path that is in `disputed_paths:`, and printing it
    would tell the agent the opposite of the truth.

    RED TODAY. Measured: the verdict is CLEAN, so there is no violation to
    inspect and the row fails on the first assertion.
    Green when: the violation carries `FLOOR_RATIONALE`.

    Measured under: implementing the protection through the ROLE TABLE instead
    of the floor — the path appended to every `DENY_GLOBS` rule's `globs` in
    `DEFAULT_ROLE_RULES`. **This is the mutation this row exists for, and it is
    the one that shows which rows in this file can and cannot tell a floor from
    a rule.** Seventeen red becomes thirteen. What the deny table buys: the
    `scaffold` and `bodies` rows of the built-in-policy table, and BOTH Part 4
    rows — a bodies branch editing the gate is refused end to end, so neither
    provenance row distinguishes the two mechanisms and neither claims to. What
    it cannot buy, and what stays red: THIS row, plus the `adjudicate` and
    `legacy` rows of that table (ADJUDICATE is ALLOW_ONLY_GLOBS and LEGACY is
    UNRESTRICTED — a deny addition reaches neither), plus all five rows under
    the stripped policy, plus all three plan-time rows.
    """
    repo = _branch_that_only_edits(tmp_path, _REACHABILITY_GATE)
    spec = _spec(Role.ADJUDICATE, _REACHABILITY_GATE)
    result = check_branch(repo, "main", "feat/x", Role.ADJUDICATE, spec=spec)
    assert result.verdict is DiffVerdict.VIOLATION, (
        "an adjudicate branch declared the reachability gate as its writable "
        f"set and was cleared: {result.verdict.value}"
    )
    assert result.violations[0].rationale == FLOOR_RATIONALE, (
        "the reachability gate is protected by something other than the floor, "
        "or the floor's reason was not carried to the report: "
        f"{result.violations[0].rationale!r}"
    )


#: (role, changed path) pairs that must STAY clean. Written out. Without these,
#: "deny `**/src/**` to everyone" satisfies the three rows above and makes the
#: protocol unusable: BODIES exists to write under `src/`.
#:
#: No SEALS row, for D1's reason: SEALS is denied `**/src/**` outright, so a
#: SEALS row here can never be green and a permanent red is not a control.
_STILL_WRITABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", _ORDINARY_SOURCE),
    ("scaffold", _SIBLING_SCAFFOLD),
    ("scaffold", _SAME_BASENAME_ELSEWHERE),
    ("bodies", _ORDINARY_SOURCE),
    ("bodies", _SIBLING_SCAFFOLD),
    ("bodies", _SAME_BASENAME_ELSEWHERE),
    ("legacy", _ORDINARY_SOURCE),
    ("legacy", _SAME_BASENAME_ELSEWHERE),
)


@pytest.mark.parametrize(
    "role_value, changed",
    _STILL_WRITABLE_ROWS,
    ids=[f"{r}-{c}" for r, c in _STILL_WRITABLE_ROWS],
)
def test_flooring_the_reachability_gate_costs_the_rest_of_the_tree_nothing(
    role_value: str, changed: str, tmp_path
) -> None:
    """EIGHT ROWS, GREEN TODAY, and they must STILL be green afterwards.

    The upper bound. `plan.py` is the row that matters most: the protection is
    about the module that DECIDES, not about the package it lives in, and a fix
    reaching for `**/src/claude_dispatcher/**` would make every legitimate
    change to the dispatcher unplannable with no override, because a floor has
    no override. `blast_radius.py` is the second: a sibling scaffold in the same
    package is exactly what a "floor the analyzers" over-reach takes next.
    `vendor/thirdparty/call_site_reachability.py` is the basename-only mutation
    seen from the VERDICT side rather than from the glob side, so `**/call_site_
    reachability.py` reddens here as well as in Part 1.

    Measured under: appending `**/src/claude_dispatcher/**` to `FLOOR_GLOBS` —
    FIVE rows go red (`scaffold`/`bodies` on both `plan.py` and
    `blast_radius.py`, and `legacy` on `plan.py`) while every row in Part 3
    above passes. Five and not four: the `legacy` row matters most of the three
    role words here, because LEGACY is what a task IS when `role:` is absent.
    Measured under: appending `**/call_site_reachability.py` — the three
    `vendor/thirdparty/...` rows go red while Part 3 passes.
    """
    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", Role(role_value))
    assert result.verdict is DiffVerdict.CLEAN, (
        f"role {role_value} may no longer write {changed!r}: "
        f"{[(v.path, v.matched_glob) for v in result.violations]}"
    )
    assert result.violations == ()


# --------------------------------------------------------------------------- #
# Part 4 — the floor is read from `<base>`, not from the working tree
#
# This is the round's whole point. Being on `FLOOR_GLOBS` makes the edit a
# VIOLATION *when a trusted run reads the diff*; these two rows are the other
# half — the run that judges a self-judging checkout must refuse it using the
# floor as `<base>` has it, not as the branch wrote it. The mechanism already
# exists (`scripts/check_body_branch.sh` materialises `<base>:${_src_rel}` when
# the gate lives inside the tree under judgement), and it is TRUE BY LOCATION
# for this module exactly as it is for the Go helper: `call_site_reachability.py`
# sits under the `src/` prefix the base-pinned block copies with a whole-subtree
# `ls-tree -r`. Sealed rather than assumed, for D2's reason: move the module and
# it silently stops travelling.
# --------------------------------------------------------------------------- #


def _branch_edits_the_reachability_gate(checkout) -> str:
    """Append a comment to the checkout's `call_site_reachability.py`.

    A COMMENT and not a `def`: the scaffolded-signature half of the BODIES gate
    must report CHECKED with zero changes, so both rows below turn on the PATH
    gate and cannot pass because the signature comparator happened to object.
    Returns the marker so the caller can prove the edit is really in the tree.
    """
    marker = "# the branch's own amendment to the gate that judges it\n"
    target = checkout / _REACHABILITY_GATE
    assert target.is_file(), f"the fixture has no {_REACHABILITY_GATE} to edit"
    with target.open("a", encoding="utf-8") as handle:
        handle.write(marker)
    return marker


def test_a_branch_that_edits_the_reachability_gate_is_refused_by_a_trusted_run(
    ci_checkout_template, tmp_path
) -> None:
    """ONE ROW, RED. The diff-time half, through the real entrypoint.

    A bodies branch whose only change is a comment appended to
    `call_site_reachability.py`, judged by a copy of the gate script the branch
    cannot write. Nothing about the gate is tampered with here; the question is
    only whether the path is refused when the diff is read honestly.

    The in-call control is the second assertion: the run must name THIS path as
    FORBIDDEN. Without it the row would be satisfied by any refusal at all —
    including one caused by a fixture that accidentally dirtied something else.

    **The `FORBIDDEN ` prefix is load-bearing and was MEASURED, not styled.**
    The report opens with a `changed paths examined:` listing that carries every
    path in the diff, this one included, so `_REACHABILITY_GATE in stdout` is
    TRUE for a branch that was cleared. The first draft of this row and of the
    one below asserted exactly that and the row below passed against 8f44d1c —
    green on an incidental substring, one of the seven shapes this unit
    measures. Both now read the verdict line.

    RED TODAY. Measured against 8f44d1c: the trusted run exits 0 and prints
    `check_body_branch: CLEAN`.
    Green when: it exits 2 and names the path.

    Measured under: appending
    `**/src/claude_dispatcher/{call_site_reachability,blast_radius}.py` to
    `FLOOR_GLOBS` — still exit 0, still CLEAN. Presence is not refusal.
    Measured under: appending the path to every `DENY_GLOBS` rule's `globs`
    instead of to the floor — this row goes GREEN. **It does not distinguish a
    floor from a deny addition and does not claim to**: the role here is BODIES,
    which a deny addition does reach. What this row owns is that the refusal
    survives the real entrypoint end to end; the mechanism is
    `test_a_floor_violation_on_the_reachability_gate_reports_the_floors_own_
    reason`'s to pin.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    marker = _branch_edits_the_reachability_gate(checkout)
    _commit(checkout, "an ordinary-looking body commit")

    # The fixture exhibits the defect: the branch really did edit the gate.
    assert marker in (checkout / _REACHABILITY_GATE).read_text(encoding="utf-8")

    trusted = _run_gate(_trusted_script(), checkout)
    assert trusted.returncode == ExitCode.VIOLATION.value, (
        "a bodies branch rewrote the module that decides whether a subject is "
        f"reachable, and a trusted run cleared it (rc={trusted.returncode})\n"
        f"stdout={trusted.stdout}\nstderr={trusted.stderr}"
    )
    assert f"FORBIDDEN {_REACHABILITY_GATE}" in trusted.stdout, (
        "the trusted run refused the branch, but not for this path — so this "
        f"row would pass on an unrelated refusal.\nstdout={trusted.stdout}"
    )


def test_the_floor_that_refuses_the_gate_is_the_bases_and_not_the_branchs(
    ci_checkout_template, tmp_path
) -> None:
    """ONE ROW, RED. The round's central claim: the floor cannot be dissolved by
    the branch it is judging.

    The branch does two things: it appends a comment to
    `call_site_reachability.py`, and it rebinds `FLOOR_GLOBS = ()` in its OWN
    `role_protocol.py`. Then the gate is invoked exactly as CI invokes it — the
    entrypoint that ships INSIDE the checkout under judgement. Under the
    branch's own rules there is no floor at all; under `<base>`'s there is, and
    the run must use `<base>`'s.

    The rebinding is INSERTED BEFORE the `__main__` guard, not appended, and
    that is D1's measured lesson rather than a style choice: `python -m pkg.mod`
    runs the module top to bottom and the guard raises `SystemExit`, so anything
    after it never executes — an appended rebinding tampers with the imported
    module and not with the one the gate runs, and it made D1's equivalent seal
    pass while the exploit was wide open. Control (a) below proves the rebinding
    took effect in the branch's own copy before the gate is ever run.

    THREE in-call controls, each closing a different way this row could pass
    for the wrong reason:

      a. the branch's own copy really has a zero-glob floor (else the row proves
         nothing about provenance — it would just be reading an untampered tree);
      b. the run really entered the base-pinned path, evidenced by the script's
         own stderr line; a run that never took that path says nothing about
         `<base>`;
      c. the base's floor is LIVE in that run — it names `role_protocol.py`,
         which the branch also touched and which IS floored at `<base>`. This is
         the positive control: the refusal machinery works, so the missing
         `call_site_reachability.py` is a fact about the FLOOR's membership and
         not about a broken run.

    Every path assertion reads the `FORBIDDEN <path>` verdict line and not the
    report as a whole, and that was MEASURED rather than styled: the report
    opens with `changed paths examined:` listing BOTH files, so a bare
    `_REACHABILITY_GATE in stdout` is true here for a branch the floor did not
    refuse. The first draft asserted exactly that and this row PASSED against
    8f44d1c — green on an incidental substring, which is one of the seven shapes
    this unit measures, committed inside the row written to catch it.

    RED TODAY. Measured against 8f44d1c: controls (a), (b) and (c) all pass —
    the run exits 2 and reports
    `FORBIDDEN src/claude_dispatcher/role_protocol.py` with the floor's own
    rationale, read out of `<base>` while the branch's own floor is empty — and
    the final assertion FAILS: `call_site_reachability.py` appears only in the
    `changed paths examined:` listing and is never FORBIDDEN, because `<base>`'s
    floor does not carry it either.

    Green when: the same report also reports it FORBIDDEN.

    Measured under: appending
    `**/src/claude_dispatcher/{call_site_reachability,blast_radius}.py` to
    `FLOOR_GLOBS` — controls (a)-(c) pass and the final assertion still FAILS.
    Measured under: appending the path to every `DENY_GLOBS` rule's `globs`
    instead of to the floor — this row goes GREEN, for the reason recorded on
    the row above: BODIES is a role a deny addition reaches. The provenance
    half of this round is about WHOSE rules ran, not about which tier they came
    from, and the tier is pinned elsewhere.
    Predicted (unmeasured) under: a `check_body_branch.sh` that dropped the
    base-pinned block — control (b) fails first, and the report would carry
    neither path because the branch's empty floor would be the one that ran.
    """
    checkout = _checkout(ci_checkout_template, tmp_path)
    marker = _branch_edits_the_reachability_gate(checkout)

    library = checkout / GATE_LIBRARY
    text = library.read_text(encoding="utf-8")
    guard = 'if __name__ == "__main__":'
    assert guard in text, "the gate library has no script face to insert before"
    amendment = (
        "\n# --- the branch's own amendment to the rules it is judged by\n"
        "FLOOR_GLOBS = ()\n\n"
    )
    text = text.replace(guard, amendment + guard, 1)
    library.write_text(text, encoding="utf-8")
    assert text.index(amendment) < text.index(guard)

    # (a) The tamper is live in the branch's own copy.
    probe = subprocess.run(
        [
            sys.executable,
            "-P",
            "-c",
            "import claude_dispatcher.role_protocol as m; print(len(m.FLOOR_GLOBS))",
        ],
        cwd=str(checkout),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(checkout / "src")},
        timeout=120,
    )
    assert probe.returncode == 0, (
        f"the tampered gate library does not import: {probe.stderr}"
    )
    assert probe.stdout.strip() == "0", (
        "the tamper did not take effect — the branch's own copy still carries "
        f"a floor, so this row would prove nothing: {probe.stdout!r}"
    )
    assert marker in (checkout / _REACHABILITY_GATE).read_text(encoding="utf-8")
    _commit(checkout, "delete the floor, then edit the gate it should protect")

    judged_by_itself = _run_gate(checkout / GATE_ENTRYPOINT, checkout)

    # (b) The run entered the base-pinned path.
    assert "the gate's own code lives inside the checkout under judgement" in (
        judged_by_itself.stderr
    ), (
        "the gate did not take the base-pinned path, so nothing below is a "
        f"statement about `<base>`\nstderr={judged_by_itself.stderr}"
    )

    # (c) The base's floor is live in this run: it refuses the gate library the
    # branch rewrote, with the floor's own reason, while the branch's floor is
    # empty. The refusal machinery works.
    assert judged_by_itself.returncode == ExitCode.VIOLATION.value, (
        "the branch emptied its own floor and edited two floored files, and "
        f"the run did not report a violation (rc={judged_by_itself.returncode})"
        f"\nstdout={judged_by_itself.stdout}\nstderr={judged_by_itself.stderr}"
    )
    assert f"FORBIDDEN {GATE_LIBRARY}" in judged_by_itself.stdout, (
        "the base's floor did not refuse `role_protocol.py`, so this run is "
        "not evidence about what the base's floor contains\n"
        f"stdout={judged_by_itself.stdout}"
    )

    assert f"FORBIDDEN {_REACHABILITY_GATE}" in judged_by_itself.stdout, (
        "a branch appended to `call_site_reachability.py` and emptied its own "
        "`FLOOR_GLOBS`, and the gate — running the base's rules, which it "
        "demonstrably did for `role_protocol.py` in this same run — did not "
        "refuse it. The module that decides whether a subject is reachable is "
        "writable by the branch whose seals it will be judging.\n"
        f"stdout={judged_by_itself.stdout}"
    )


# --------------------------------------------------------------------------- #
# Part 5 — the plan-time half
#
# `_floor_glob_named_by` reads the WHOLE of `FLOOR_GLOBS` and compares
# BASENAMES, so P4's "one floor, one meaning" ruling carries this module to plan
# time automatically — provided the entry is a FILE glob. It is: the two entries
# whose last segment is `**` (the Go and TypeScript subtrees) are the recorded
# exceptions with no plan-time reach, and this module is a file, not a tree.
# Sealed rather than assumed, because "automatically" is what the last eight
# instances of this defect class were also thought to be.
# --------------------------------------------------------------------------- #

_PLAN_TIME_DECLARATIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    ((_REACHABILITY_GATE,), "the reachability gate, named exactly"),
    (("call_site_reachability.py",), "the plain spelling"),
    (
        ("docs/adr/0011.md", _REACHABILITY_GATE),
        "hidden behind a genuine artifact",
    ),
)


@pytest.mark.parametrize(
    "disputed, case",
    _PLAN_TIME_DECLARATIONS,
    ids=[case for _d, case in _PLAN_TIME_DECLARATIONS],
)
def test_declaring_the_reachability_gate_is_refused_at_plan_time(
    disputed: tuple[str, ...], case: str
) -> None:
    """THREE ROWS, ALL RED. An adjudicate row may not declare the gate.

    Independent of Parts 3 and 4 by construction: nothing here calls
    `check_branch` and nothing here touches a repository. Plan time is the
    enforcement point that fires before any agent runs, and it is the one that
    saves a build cycle rather than a PR.

    The `plain spelling` row is the basename comparison, deliberately: once the
    module is floored, `call_site_reachability.py` declared ANYWHERE is refused
    at plan time, which is stricter than the diff-time half and is the accepted
    asymmetry P4 recorded on 2026-08-09 — it can only false-refuse, never
    false-clear, and the false refusal has a spelling that works (`vendor/**`).

    RED TODAY. Measured against 8f44d1c: `parse_task_role_spec` returns a
    `TaskRoleSpec` carrying the path in `disputed_paths` and raises nothing.
    Green when: it raises `RoleProtocolError` naming the task key and the entry.

    Measured under: appending `**/src/claude_dispatcher/**` to `FLOOR_GLOBS` —
    all three rows STILL fail, because a pure-wildcard tail is not a plan-time
    hit. The subtree spelling buys diff-time enforcement only, and this row is
    where that becomes visible rather than being rediscovered later.
    """
    row = {
        "key": "D5-FLOOR",
        "role": "adjudicate",
        "disputed_paths": list(disputed),
    }
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key="D5-FLOOR")
    message = str(exc.value)
    assert "D5-FLOOR" in message, "the message is read out of a run log; name the task"
    assert any(entry in message for entry in disputed), (
        f"the refusal must name the offending entry, not just the rule: {message}"
    )


@pytest.mark.parametrize(
    "disputed",
    [
        (_ORDINARY_SOURCE,),
        (_SIBLING_SCAFFOLD,),
        ("src/claude_dispatcher/**",),
        ("tests/test_d5_floor.py",),
    ],
    ids=[
        "an ordinary source file",
        "a sibling scaffold",
        "the package subtree that CONTAINS the gate",
        "a seal",
    ],
)
def test_a_legitimate_disputed_path_still_parses(disputed: tuple[str, ...]) -> None:
    """FOUR ROWS, GREEN TODAY, and they must stay green.

    Without them, "refuse every `src/` declaration" satisfies the rows above,
    and a floor has no override, so the cost would be permanent. The subtree row
    carries the 2026-08-07 ruling that plan time refuses declarations that NAME
    a floor file and does NOT refuse subtree globs that merely could contain
    one: only the diff knows whether they do, and the diff-time floor catches
    those for real.

    Predicted (unmeasured) under: implementing the plan-time rule as "refuse any
    declaration that COULD match the reachability gate" — the subtree row goes
    red. Not run: it needs a production edit to `_floor_glob_named_by`, which
    P2 may not make, and D1 measured the same shape for its own five modules.
    Measured under: appending `**/src/claude_dispatcher/**` to `FLOOR_GLOBS` —
    all four rows STAY GREEN, which is the 2026-08-07 ruling holding: a
    pure-wildcard tail names a tree and is not a plan-time hit.
    """
    row = {"key": "D5-OK", "role": "adjudicate", "disputed_paths": list(disputed)}
    spec = parse_task_role_spec(row, task_key="D5-OK")
    assert spec.disputed_paths == disputed


# --------------------------------------------------------------------------- #
# Part 6 — enrolment may not precede the floor
#
# `ANALYZERS = ()` is a claim, and `tests/test_call_site_reachability.py`
# already seals that it is empty TODAY. What nothing seals is the ORDER: that
# this module may not acquire an analyzer row before it acquires a floor row.
# Two rows, and they are deliberately different in kind, because only one of
# them can be had without a production change. See the report and the docstrings
# for the precise statement of which.
# --------------------------------------------------------------------------- #


#: The package on disk, resolved from the imported module rather than from this
#: file's location, so the copies below are made of the code the rest of the
#: suite imported. A layout change that breaks this is a loud error, never a
#: quietly empty copy — the row asserts the copy took more than 20 modules.
_PACKAGE_DIR = Path(rp_mod.__file__).resolve().parent

#: What replaces `ANALYZERS = ()` in an ENROLLED copy of the module: a registry
#: row well formed by every rule that exists today, plus the tuple that holds
#: it. Go, because `Language.GO` has a `COMPARATORS` row and
#: `validate_analyzers` refuses a language that has none;
#: `negative_is_conclusive` is a real `bool` for the same reason; the three
#: methods are callable and raise, which `validate_analyzers` explicitly
#: tolerates ("never raises for a row being unimplemented"). `Language` and
#: `ReachabilityAnalyzer` are already in that module's namespace at this point.
_ENROLMENT_PROBE_SOURCE = '''class _EnrolmentProbe:
    """A registry row well formed by every rule that exists today."""

    language = Language.GO
    negative_is_conclusive = True

    def roots(self, tree):
        raise NotImplementedError("a shape probe, never an analysis")

    def graph(self, tree):
        raise NotImplementedError("a shape probe, never an analysis")

    def test_root_predicate(self, symbol):
        raise NotImplementedError("a shape probe, never an analysis")


ANALYZERS: tuple[ReachabilityAnalyzer, ...] = (_EnrolmentProbe(),)'''


#: A floor glob that WOULD cover this module. It is a FIXTURE INPUT and never an
#: assertion: nothing in this file claims `FLOOR_GLOBS` contains this string, or
#: any string. It is used only to construct the hypothetical "the module is
#: floored" world one control below needs, and that control checks the world it
#: built is really floored (the copy reports its own floor as covering the
#: module) — the brace-expansion lesson applied to this file's own fixture.
_A_FLOOR_THAT_WOULD_COVER_D5 = "**/src/claude_dispatcher/call_site_reachability.py"


#: P4, 2026-08-11 (unit D6). The same probe row, moved OUT of the gate module
#: into a module of its own, because that is the shape every real row has: D5 is
#: the mechanism, and a row is a class in another file. The inline probe above
#: cannot express the defect the D6 floor round found — with the row defined
#: inside `call_site_reachability.py`, "the row's defining module" and "this
#: module" are the same path, and a guard that checks only its own path looks
#: correct.
#:
#: The module name is the real row's, so the copy's floor surgery below can be
#: driven by the same repo-relative paths the floor names. It REPLACES the real
#: `go_reachability.py` in the copy rather than sitting beside it, so nothing
#: here depends on that scaffold's contents.
_ROW_MODULE_NAME = "go_reachability"
_ROW_MODULE = f"src/claude_dispatcher/{_ROW_MODULE_NAME}.py"

#: The row's HELPER: a program under the row's package whose output IS the call
#: graph. Two files, because the subtree half of a floor entry is only
#: falsifiable against more than one.
_ROW_HELPER_DIR = "go_call_reachability"
_ROW_HELPER_ENTRY = f"src/claude_dispatcher/{_ROW_HELPER_DIR}/main.go"

_ROW_MODULE_SOURCE = '''"""A registry row in a module of its own — the shape every real row has."""
from .call_site_reachability import ReachabilityAnalyzer
from .role_protocol import Language


class _RowInItsOwnModule:
    language = Language.GO
    negative_is_conclusive = True

    def roots(self, tree):
        raise NotImplementedError("a shape probe, never an analysis")

    def graph(self, tree):
        raise NotImplementedError("a shape probe, never an analysis")

    def test_root_predicate(self, symbol):
        raise NotImplementedError("a shape probe, never an analysis")


ROW = _RowInItsOwnModule()
'''

#: What replaces `ANALYZERS = ()` when the row lives in its own module. The
#: import is INSIDE a function called on the next line, not at module level: the
#: row module imports `ReachabilityAnalyzer` back out of this one, so a
#: module-level import here is a cycle that fails before the guard can run. This
#: is the shape a real enrolment will need too, and it is stated as fixture
#: input rather than as a claim about how enrolment must be written.
_ENROLMENT_FROM_ROW_MODULE_SOURCE = f'''ANALYZERS: tuple[ReachabilityAnalyzer, ...] = ()


def _enrol_from_the_row_module():
    global ANALYZERS
    from .{_ROW_MODULE_NAME} import ROW

    ANALYZERS = (ROW,)


_enrol_from_the_row_module()'''


def _enrolment_is_ordered(*, enrolled: bool, floored: bool) -> bool:
    """The ordering property, as one expression: a row may not arrive first."""
    return floored or not enrolled


def test_the_module_is_not_enrolled_while_it_is_off_the_floor() -> None:
    """ONE ROW, GREEN TODAY, and non-vacuous TODAY — which is when it matters.

    The sequence D5's first P4 escalated, stated as data: `ANALYZERS` may not
    acquire a row before `FLOOR_GLOBS` does. Measured against 8f44d1c the
    antecedent is TRUE — the module is off the floor — so the consequent is
    really checked, and this row reddens the moment a P3 enrols before flooring.

    Its shape is honest about its own end: once the floor lands, the implication
    is satisfied by its first disjunct and the row stops constraining anything.
    That is correct — the ordering has been discharged at that point — but it
    means this row is NOT the mechanical guard the brief asks for. It is a
    seal, and it only fires when the suite runs. The row after it is the
    mechanical one, and it needs a production change.

    **P4, 2026-08-11: "stops constraining anything" is true only while the floor
    is there, which is exactly when there is nothing to constrain. The row
    RE-ARMS on deletion, and that was measured rather than reasoned.** In a
    clone carrying the landed glob, deleting it from `FLOOR_GLOBS` and enrolling
    `ANALYZERS` in the same edit — the only route back into the world the
    ordering forbids — turns this row RED again, naming the analyzer row and the
    floor it is missing from, alongside 18 others. So this row is not a fuse
    that burns out at the first floor; it is armed whenever the antecedent is
    true, which is the whole of the property. That measurement is why the
    mechanical guard below is DEFERRED and not abandoned: it would move the
    failure from the suite to the first import, not add a case the suite misses.

    The in-call control is the predicate itself, exercised on both a satisfying
    and a violating pair, so the row cannot pass because
    `_enrolment_is_ordered` is a tautology — the "pass condition satisfiable by
    executing nothing" shape.

    Measured under: rebinding `csr.ANALYZERS` to a one-row tuple while the floor
    is untouched — this row FAILS, printing the row and the floor it is missing
    from. (Run as a mutation and deliberately not left in the file: a row that
    patched the constant it pins would be measuring its own fixture.)
    """
    # The control: the predicate is not a tautology and not a constant.
    assert not _enrolment_is_ordered(enrolled=True, floored=False), (
        "the ordering predicate accepts enrolment before flooring, so the "
        "assertion below cannot fail"
    )
    assert _enrolment_is_ordered(enrolled=True, floored=True)
    assert _enrolment_is_ordered(enrolled=False, floored=False)

    floored = first_matching_glob(_REACHABILITY_GATE, FLOOR_GLOBS) is not None
    enrolled = bool(csr.ANALYZERS)
    assert _enrolment_is_ordered(enrolled=enrolled, floored=floored), (
        "the reachability gate has an analyzer row and no floor glob. A gate "
        "that can be asked a question before it can be protected from the "
        "branch it is answering about is the ordering D5's first P4 "
        f"escalated: ANALYZERS={csr.ANALYZERS!r}, floor={list(FLOOR_GLOBS)}"
    )


def _package_copy(
    tmp_path,
    *,
    enrolled: bool,
    floored: bool | None,
    layout: str = "src",
    row_in_its_own_module: bool = False,
    helper: bool = False,
    unfloor: tuple[str, ...] = (),
):
    """An importable copy of `claude_dispatcher`, doctored along six axes.

    Only the package's top-level `.py` files are copied — enough to import
    `call_site_reachability` and everything it reaches, and it leaves the 8.8 MB
    vendored TypeScript parser where it is.

    `layout` NAMES THE DIRECTORY THE PACKAGE SITS IN, and it is an axis rather
    than a constant because of what P4 measured on 2026-08-11:

        "src"            a source checkout — the shape every other row in this
                         file judges, and the shape a fix that derives its own
                         repo-relative path from `__file__` needs, since
                         `Path(__file__).resolve().parts[-3:]` is
                         `src/claude_dispatcher/<module>.py` only here;
        "site-packages"  an INSTALLED dispatcher. `pyproject.toml` builds a
                         setuptools wheel with `where = ["src"]`, so the shipped
                         package does NOT live under `src/` and that derivation
                         returns `site-packages/claude_dispatcher/<module>.py`,
                         which no path-qualified floor glob matches.

    The second value is not hypothetical tidiness. It was the axis this fixture
    did not have, and the row below could not see the defect without it — see
    that row's docstring for the measurement.

    `enrolled` REPLACES the `ANALYZERS = ()` line with a one-row tuple, so that
    every line after it in the module — `validate_analyzers(ANALYZERS)` and
    anything a fixer adds beside it — runs against an enrolled registry. It is a
    replacement and not an append for D1's measured reason, one file to the
    left: an append runs after the module's body has already decided
    everything, and would tamper with nothing.

    `floored` rebinds `FLOOR_GLOBS` in the copy's `role_protocol.py`, before its
    `__main__` guard, so the rebinding has happened by the time
    `call_site_reachability` imports it:

        True   the floor is made to cover the module — appended if the tree
               does not already carry it, so the world is the same either way;
        False  every glob covering the module is REMOVED — stated as a filter
               and not as "leave it alone", because "the tree today" is not a
               world this fixture may assume. Measured: it is exactly the
               assumption that made the first draft of this row pass in the
               joint-satisfiability clone, where the floor already carried the
               entry and `floored=False` silently meant `floored=True`;
        None   the copy is left alone, which is the control that proves the
               copy reflects this tree.

    **P4, 2026-08-11 (unit D6): THREE MORE AXES, all defaulting to the world
    every existing row already builds, so nothing above this line changed.**

        `row_in_its_own_module`  the enrolled row is defined in
                                 `go_reachability.py` instead of inline. This is
                                 the shape every real row has, and it is the
                                 axis without which "the row's defining module"
                                 and "this module" are the same path and a guard
                                 that checks only its own path looks correct;
        `helper`                 the row's package gets a
                                 `go_call_reachability/` directory holding two
                                 files — a program whose output would BE the
                                 call graph;
        `unfloor`               repo-relative paths whose covering globs are
                                 removed from the copy's floor, applied AFTER
                                 `floored`. It is what lets one world floor the
                                 gate and un-floor the row, which is exactly the
                                 world the D5 guard permitted.

    Nothing is monkeypatched and no mechanism is named: this constructs a world
    and then imports it.
    """
    # The directory name must separate worlds that differ ONLY in `unfloor`, or
    # the second such copy lands on the first and the fixture silently judges a
    # world it did not build. Measured: with the count alone in the slug, the
    # row-un-floored and helper-un-floored worlds collided.
    named = "".join(sorted(p.rpartition("/")[2].partition(".")[0] for p in unfloor))
    slug = f"-r{int(row_in_its_own_module)}h{int(helper)}u{named}"
    root = tmp_path / f"pkg-e{int(enrolled)}-f{floored}-{layout}{slug}" / layout
    package = root / "claude_dispatcher"
    package.mkdir(parents=True)
    copied = 0
    for source in sorted(_PACKAGE_DIR.glob("*.py")):
        shutil.copy2(source, package / source.name)
        copied += 1
    assert copied > 20, f"the copy took {copied} modules; it is not the package"

    if row_in_its_own_module:
        (package / f"{_ROW_MODULE_NAME}.py").write_text(
            _ROW_MODULE_SOURCE, encoding="utf-8"
        )

    if helper:
        directory = package / _ROW_HELPER_DIR
        directory.mkdir()
        (directory / "main.go").write_text("package main\n", encoding="utf-8")
        (directory / "go.mod").write_text("module probe\n", encoding="utf-8")

    if enrolled:
        target = package / "call_site_reachability.py"
        text = target.read_text(encoding="utf-8")
        anchor = "ANALYZERS: tuple[ReachabilityAnalyzer, ...] = ()"
        assert text.count(anchor) == 1, (
            "the `ANALYZERS` definition was not found exactly once, so this "
            "fixture enrolled nothing and would prove nothing"
        )
        enrolment = (
            _ENROLMENT_FROM_ROW_MODULE_SOURCE
            if row_in_its_own_module
            else _ENROLMENT_PROBE_SOURCE
        )
        text = text.replace(anchor, enrolment, 1)
        target.write_text(text, encoding="utf-8")

    if floored is not None:
        target = package / "role_protocol.py"
        text = target.read_text(encoding="utf-8")
        guard = 'if __name__ == "__main__":'
        assert guard in text, "the gate library has no script face to insert before"
        if floored:
            rebinding = (
                "\n# --- this fixture's floor, landed before anything imports it\n"
                "FLOOR_GLOBS = tuple(dict.fromkeys(\n"
                f"    FLOOR_GLOBS + ({_A_FLOOR_THAT_WOULD_COVER_D5!r},)\n"
                "))\n\n"
            )
        else:
            rebinding = (
                "\n# --- this fixture removes every glob covering the module\n"
                "FLOOR_GLOBS = tuple(\n"
                "    _g for _g in FLOOR_GLOBS\n"
                f"    if first_matching_glob({_REACHABILITY_GATE!r}, (_g,)) is None\n"
                ")\n\n"
            )
        text = text.replace(guard, rebinding + guard, 1)
        assert text.index(rebinding) < text.index(guard)
        target.write_text(text, encoding="utf-8")

    if unfloor:
        target = package / "role_protocol.py"
        text = target.read_text(encoding="utf-8")
        guard = 'if __name__ == "__main__":'
        assert guard in text, "the gate library has no script face to insert before"
        removal = (
            "\n# --- this fixture removes every glob covering these paths\n"
            "FLOOR_GLOBS = tuple(\n"
            "    _g for _g in FLOOR_GLOBS\n"
            "    if not any(\n"
            f"        first_matching_glob(_p, (_g,)) is not None for _p in {list(unfloor)!r}\n"
            "    )\n"
            ")\n\n"
        )
        text = text.replace(guard, removal + guard, 1)
        target.write_text(text, encoding="utf-8")

    return root


def _import_the_copy(root):
    """Import `claude_dispatcher.call_site_reachability` out of `root`, alone.

    `-P` so the cwd cannot supply a different package, and `PYTHONPATH` set to
    the copy and nothing else. The probe prints the two facts each assertion
    turns on — how many analyzer rows the copy carries, and whether the copy's
    own floor covers the module — so a green run is evidence about the COPY
    rather than about the installed tree.
    """
    return subprocess.run(
        [
            sys.executable,
            "-P",
            "-c",
            "import claude_dispatcher.call_site_reachability as m;"
            "import claude_dispatcher.role_protocol as r;"
            "print('IMPORTED', len(m.ANALYZERS), r.first_matching_glob("
            f"{_REACHABILITY_GATE!r}, r.FLOOR_GLOBS) is not None)",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        | {"PYTHONPATH": str(root)},
        timeout=180,
    )


def test_enrolment_is_impossible_while_the_floor_row_is_red(tmp_path) -> None:
    """ONE ROW, RED, and it REQUIRES A PRODUCTION CHANGE. Stated plainly,
    because the brief asks whether the ordering is sealable without one: the row
    above is, this one is not, and they are different properties.

    The row above is a SEAL — it fires when the suite runs, and a P3 that
    enrolled before flooring would see a red row and could argue with it. This
    one asks for the sequence to be MECHANICAL: a `call_site_reachability` that
    carries an analyzer row while its own path is off `FLOOR_GLOBS` must not
    IMPORT. That makes the ordering a property of the artifact rather than of
    the test run, and it makes the failure arrive at the first collection
    instead of at the end of a build cycle.

    NO MECHANISM IS NAMED. The row does not call `validate_analyzers`, does not
    monkeypatch a constant, and does not require the check to live in any
    particular function. It builds four copies of the package, imports each in a
    fresh interpreter, and asks which ones come up. A fixer may put the check in
    `validate_analyzers`, beside the module-level `validate_analyzers(
    ANALYZERS)` call, or anywhere else that runs while the module's body does.

    **Why it is not written as `validate_analyzers` refusing the row, which was
    the first draft. MEASURED, in a clone.** Putting the refusal inside
    `validate_analyzers` reddens an existing D5 seal —
    `test_validate_analyzers_refuses_a_row_no_path_can_reach` ends by asserting
    that a Go row IS ACCEPTED once its language is enrolled, and that call would
    then raise. A seal whose satisfaction reddens a live seal in the unit it
    belongs to is not a seal, it is a coordination, and P2 may not perform one.
    The import-time property has no such collision: `validate_analyzers`'s
    contract is unchanged and that row stays green.

    **P4 RULING, 2026-08-11: DEFERRED out of this round, and this row stays
    RED as the standing requirement. Two reasons, one procedural and one
    measured.**

    Procedural: the guard is production code in
    `call_site_reachability.py`, and an adjudication rules, it does not
    implement. That alone would only be a handoff.

    Measured, and the reason this is a deferral rather than a handoff: **the
    reference implementation recorded below bricks the shipped wheel, and this
    row as written could not see it.** `pyproject.toml` builds a setuptools
    wheel with `where = ["src"]`, so an installed dispatcher lives at
    `.../site-packages/claude_dispatcher/call_site_reachability.py` and
    `"/".join(Path(__file__).resolve().parts[-3:])` returns
    `site-packages/claude_dispatcher/call_site_reachability.py`, which no
    path-qualified floor glob matches — measured 2026-08-11 against
    `**/src/claude_dispatcher/call_site_reachability.py`, which returns None for
    it and the glob for the checkout spelling. So a guard reading "derive my
    path, refuse if it is not on the floor" refuses every INSTALLED copy the
    moment the module is enrolled, including copies whose repository floors it
    correctly. Control (c) could not catch that, because `_package_copy` hard
    coded the `src/` prefix: the fixture stated only the world the fix wanted.

    Control (e) is P4's amendment and closes it. Measured 2026-08-11 in a
    throwaway clone, against a reference implementation of the guard **that was
    then discarded** — recorded that way on purpose, because 31 of this unit's
    43 earlier clauses cited a reference implementation that no longer existed
    and one was never true:

      * the guard with the derivation conditioned on the copy actually being a
        `src/` checkout — all 34 rows in this file green together, so (a)-(e)
        are jointly satisfiable and this row is not asking for the impossible;
      * the same guard WITHOUT that condition — the derivation exactly as
        recorded below — control (e) FAILS with the `ImportError` and every
        other row stays green. So control (e) is the only thing in this file
        that catches the brick, and without it the brick ships green.

    **What stops the ordering being forgotten while this is deferred.** Not
    goodwill, and not this row. The floor lands FIRST in this round, which is
    the round's whole thesis, and that DISCHARGES the ordering rather than
    postponing it: there is no interval in which the module is enrolled and
    unfloored, because enrolment has not happened and the floor is landing now.
    The only route back into the forbidden world is DELETING the floor glob, and
    the sibling row above re-arms the instant that happens — measured
    2026-08-11 in a clone carrying the landed glob: delete it from `FLOOR_GLOBS`
    and enrol `ANALYZERS` in the same edit, and NINETEEN rows go red, including
    `test_the_module_is_not_enrolled_while_it_is_off_the_floor` (which the
    docstring above calls discharged — it is discharged only while the floor is
    there, which is precisely when there is nothing to constrain) and
    `test_role_protocol_floor.py::test_every_floor_glob_the_ruling_wrote_out_
    is_in_the_constant`. A mechanical guard would move that failure from the
    suite to the first import. It would not add a case the suite misses.

    **ONE CONSTRAINT ON THE FIX, and it was MEASURED rather than anticipated:
    the check may not name this module's own path as a string literal.**
    `test_the_module_declares_no_file_extension_and_calls_no_endswith` sweeps
    `call_site_reachability.py` by AST for any non-prose constant matching
    `^\\S*\\.[A-Za-z0-9]{1,5}$`, and
    `"src/claude_dispatcher/call_site_reachability.py"` matches it. The
    reference implementation that proved joint satisfiability derives the path
    instead — `"/".join(Path(__file__).resolve().parts[-3:])` — which costs
    nothing, satisfies that seal, and cannot drift if the file is renamed.
    Measured 2026-08-11 and left standing: the string-literal form is reported
    by `_extension_literals`, the derived form is reported by neither that sweep
    nor `_endswith_sites`. **That derivation is necessary and NOT sufficient —
    see the P4 ruling above for what it does to an installed copy, and control
    (e) for the row that now says so.**

    FIVE copies, judged in this one call, and the four controls come first:

      a. UNDOCTORED — imports, reports an empty registry and this tree's own
         answer to "is the module floored". The copy machinery works and
         reflects the tree it was made from;
      b. UNENROLLED AND NOT FLOORED — imports. This is today's world, stated
         explicitly, and it is the control that stops "refuse whenever the
         module is off the floor", which would make the package unimportable
         right now. It also proves the un-flooring surgery works;
      c. ENROLLED AND FLOORED — imports, reports one analyzer row and a floor
         that covers the module. This is the control that stops "refuse every
         non-empty registry", which would make enrolment permanently impossible
         — a permanent refusal is not a control, it is a rule the next author
         deletes. It also proves the probe row is well formed, since it survives
         `validate_analyzers` on the way through;
      d. ENROLLED AND NOT FLOORED — must NOT import. This is the row.
      e. ENROLLED AND FLOORED, in an INSTALLED layout — imports. P4's
         amendment, 2026-08-11. It is control (c) asked in the deployment shape
         `pip install` produces, and it is the one that stops a fix from
         reading "I cannot find myself on the floor" as "I am not on the
         floor". A permanent refusal is not a control; a permanent refusal that
         only fires off the developer's machine is worse, because the suite is
         green when it ships.

    Controls (b) and (c) between them pin the refusal to the CONJUNCTION.
    Neither axis alone may cause it. Control (e) pins the third axis nobody had
    asked about: the refusal must be a fact about the FLOOR, not about where the
    package happens to be sitting.

    RED TODAY, and re-measured 2026-08-11 against `feat/D5-floor-seals` @
    59a648d: copy (d) imports cleanly and prints `IMPORTED 1 False`. Nothing
    refuses it, at import or anywhere else. Still red after the floor lands —
    measured in the clone that carries the glob, where it is the ONLY remaining
    failure in the whole suite (1 failed, 2312 passed), which is what makes it
    the round's standing requirement rather than one red among seventeen.
    Green when: (d) fails to import while (a), (b), (c) and (e) still do.

    Measured under: building copy (d) by "leave the floor alone" instead of by
    removing every covering glob — in the joint-satisfiability clone, where the
    floor already carries the entry, `floored=False` silently means
    `floored=True` and the row passes for exactly the wrong reason. That is why
    `_package_copy` states both worlds as edits. Confirmed 2026-08-11: with the
    glob landed in the clone, control (b) still reports `IMPORTED 0 False`, so
    the un-flooring surgery does the work the omission used to be credited with.
    Measured under: the derived-path guard WITHOUT a check that the copy is a
    `src/` checkout — control (e) fails with the guard's own `ImportError` and
    all 33 other rows stay green. This is the mutation control (e) exists for
    and it is the reference implementation this row previously recommended.
    Measured under: the same guard WITH that check — all 34 rows green, so the
    five controls are jointly satisfiable. Both against a reference
    implementation that was DISCARDED; no clause here describes shipped code.
    Predicted (unmeasured) under: a fix that raises for every non-empty registry
    regardless of the floor — control (c) fails.
    """
    undoctored = _import_the_copy(_package_copy(tmp_path, enrolled=False, floored=None))
    assert undoctored.returncode == 0, (
        "an undoctored copy of the package does not import, so nothing below "
        f"is a statement about enrolment\nstderr={undoctored.stderr}"
    )
    floored_here = first_matching_glob(_REACHABILITY_GATE, FLOOR_GLOBS) is not None
    assert undoctored.stdout.split() == ["IMPORTED", "0", str(floored_here)], (
        "the undoctored copy did not report the registry and the floor answer "
        f"this tree has; the fixture is reading something else: "
        f"{undoctored.stdout!r}"
    )

    bare = _import_the_copy(_package_copy(tmp_path, enrolled=False, floored=False))
    assert bare.returncode == 0, (
        "a copy that is neither enrolled nor floored does not import. That is "
        "today's world: a rule that refuses it refuses the package as it "
        f"ships, and is not a control\nstderr={bare.stderr}"
    )
    assert bare.stdout.split() == ["IMPORTED", "0", "False"], (
        "the un-flooring surgery did not take, so copy (d) below would not be "
        f"unfloored either: {bare.stdout!r}"
    )

    floored = _import_the_copy(_package_copy(tmp_path, enrolled=True, floored=True))
    assert floored.returncode == 0, (
        "a copy that is BOTH enrolled and floored does not import. Enrolment "
        "after flooring is the whole point of the ordering; a rule that "
        "refuses it too is not a control, it is a permanent refusal\n"
        f"stderr={floored.stderr}"
    )
    assert floored.stdout.split() == ["IMPORTED", "1", "True"], (
        "the enrolled-and-floored copy did not come up with one analyzer row "
        "and a floor covering the module, so this control is not describing "
        f"the world it claims to: {floored.stdout!r}"
    )

    unfloored = _import_the_copy(_package_copy(tmp_path, enrolled=True, floored=False))
    assert unfloored.returncode != 0, (
        "a copy of the package carrying an analyzer row while its own path is "
        "off FLOOR_GLOBS imported cleanly. Enrolment before flooring is "
        "therefore possible in production and is prevented only by whoever "
        "remembers the order — which is the sequence D5's first P4 escalated. "
        f"stdout={unfloored.stdout!r}"
    )
    assert _D5_MODULE in unfloored.stderr or "floor" in unfloored.stderr.lower(), (
        "the module refused to import, but not for a reason anyone reading the "
        "traceback could act on: it must say that this module is not on the "
        f"floor.\nstderr={unfloored.stderr}"
    )

    # (e) ENROLLED AND FLOORED, but INSTALLED rather than checked out. Added by
    # P4 on 2026-08-11 against a measured brick; see the docstring. This copy
    # carries an analyzer row, its repository floors the module, and it lives
    # where `pip install` puts it — so there is no `src/` component and no
    # repo-relative path to match a floor glob against. It must still import.
    installed = _import_the_copy(
        _package_copy(tmp_path, enrolled=True, floored=True, layout="site-packages")
    )
    assert installed.returncode == 0, (
        "an ENROLLED and FLOORED copy of the package failed to import because "
        "it was installed rather than checked out. The ordering guard refused "
        "the shipped wheel: `pyproject.toml` builds with `where = [\"src\"]`, so "
        "an installed dispatcher has no `src/` component and a floor glob "
        "cannot match a path derived from its `__file__`. A guard that treats "
        "'I cannot find myself on the floor' as 'I am not on the floor' bricks "
        "every install of a repository that floors this module correctly — "
        "which is the opposite of the property this row is asking for.\n"
        f"stderr={installed.stderr}"
    )


def test_the_guard_judges_the_rows_own_module_and_its_helper(tmp_path) -> None:
    """ONE ROW, GREEN as of the D6 floor round, and it is the row the D5 guard
    could not have passed.

    **The finding, measured at ``feat/D5-relation-body`` @ ``6e18fc0``.** The
    guard resolved ``_floor_relative_path()`` from ``Path(__file__)`` — its own
    path and nothing else — so the conjunction it enforced was "the MECHANISM is
    floored", not "the artifacts this row's answer is computed from are
    floored". A row is a class in another file, and that file's helper is a
    program whose output IS the call graph. Both were writable: measured on that
    revision, ``first_matching_glob`` returned None for
    ``src/claude_dispatcher/go_reachability.py`` and for both entry points under
    ``src/claude_dispatcher/go_call_reachability/``, and neither this guard nor
    ``validate_analyzers`` looked at either.

    Four worlds, and the first two are the finding:

      a. ENROLLED from a row in ITS OWN MODULE, gate floored, ROW MODULE
         un-floored — must NOT import. **Measured against HEAD~ (the guard as
         D5 shipped it): this world IMPORTS CLEANLY.** That is the defect, and
         it is why this row is not a restatement of the one above.
      b. the same, ROW MODULE floored, HELPER SUBTREE un-floored — must NOT
         import. **Measured against HEAD~: imports cleanly.**
      c. all three floored — must import. The control that stops "refuse every
         non-empty registry" from passing this row, and it also proves the
         cycle-shaped enrolment the fixture writes really produces a registry
         with a row in it.
      d. all three UN-floored, in an INSTALLED layout — must import. Control (e)
         of the row above, asked of the widened subject: a wheel derives
         ``site-packages/claude_dispatcher/...`` for the row module and for
         every file of the helper, not just for the gate, so the widening had to
         carry the skip forward for all three kinds at once. A guard that reads
         "I cannot find myself on the floor" as "I am not on the floor" bricks
         every installed copy, and widening the subject widens the brick.

    Reddens on: reverting the guard's subject to ``Path(__file__)`` (worlds a
    and b, measured); dropping the ``_floor_relative_path`` None-is-a-skip
    conjunct (world d); refusing whenever the registry is non-empty (world c).

    Measured under: ``feat/D6-floor2``, 2026-08-11, four package copies imported
    in fresh interpreters. Measured under (the same four against
    ``6e18fc0``'s ``call_site_reachability.py``): a and b IMPORT, c and d
    import, so exactly the two worlds this row exists for flip.
    """
    common = dict(enrolled=True, row_in_its_own_module=True, helper=True)

    floored = _import_the_copy(_package_copy(tmp_path, floored=True, **common))
    assert floored.returncode == 0, (
        "a copy whose gate, row module and helper subtree are ALL on the floor "
        "does not import. Enrolment after flooring is the whole point of the "
        f"ordering; refusing it is a permanent refusal\nstderr={floored.stderr}"
    )
    assert floored.stdout.split() == ["IMPORTED", "1", "True"], (
        "the enrolled-and-floored copy did not come up with one analyzer row, "
        "so the three worlds below are not statements about an enrolled "
        f"registry: {floored.stdout!r}"
    )

    row_unfloored = _import_the_copy(
        _package_copy(tmp_path, floored=True, unfloor=(_ROW_MODULE,), **common)
    )
    assert row_unfloored.returncode != 0, (
        "a copy carrying an analyzer row whose DEFINING MODULE is off the floor "
        "imported cleanly. The gate is floored and the row is not, so the "
        "branch being judged may rewrite what its tree starts from and what "
        "calls what, while the guard reports the mechanism protected. That is "
        "the defect the D6 floor round found in the guard as D5 shipped it.\n"
        f"stdout={row_unfloored.stdout!r}"
    )
    assert _ROW_MODULE in row_unfloored.stderr, (
        "the copy refused, but not for a reason anyone reading the traceback "
        f"could act on: it must name {_ROW_MODULE}\n{row_unfloored.stderr}"
    )

    helper_unfloored = _import_the_copy(
        _package_copy(tmp_path, floored=True, unfloor=(_ROW_HELPER_ENTRY,), **common)
    )
    assert helper_unfloored.returncode != 0, (
        "a copy carrying an analyzer row whose HELPER SUBTREE is off the floor "
        "imported cleanly. The helper is a program whose output IS the call "
        "graph, so a branch that can rewrite it can make every subject in its "
        "own tree reachable — with the gate and the row both floored and the "
        f"guard silent.\nstdout={helper_unfloored.stdout!r}"
    )
    assert _ROW_HELPER_ENTRY in helper_unfloored.stderr, (
        "the copy refused without naming the helper file that is off the "
        f"floor\n{helper_unfloored.stderr}"
    )

    installed = _import_the_copy(
        _package_copy(
            tmp_path,
            floored=True,
            layout="site-packages",
            unfloor=(_REACHABILITY_GATE, _ROW_MODULE, _ROW_HELPER_ENTRY),
            **common,
        )
    )
    assert installed.returncode == 0, (
        "an INSTALLED copy failed to import. `pyproject.toml` builds with "
        '`where = ["src"]`, so a wheel has no `src/` component and NO path a '
        "floor glob can match — not the gate's, not the row module's, and not "
        "one file of the helper's. A None derivation must be a skip, never a "
        "refusal, or the widened guard bricks every install of a repository "
        f"that floors all three correctly.\nstderr={installed.stderr}"
    )
