"""D1 seals (P2): the floor is closed under delegation.

The defect
----------
`FLOOR_GLOBS` is the non-overridable set of paths no role may write. Measured
against this worktree, 2026-08-09::

    role_protocol.py     floor=**/src/claude_dispatcher/role_protocol.py
    risk.py              floor=None
    seal_verify.py       floor=None
    repo_config.py       floor=None
    yaml_io.py           floor=None
    mechanical_verify.py floor=None

(all under `src/claude_dispatcher/`.)

**The floor protects the file that calls the matcher, but not the matcher.**
`role_protocol.first_matching_glob` — the one place glob semantics live, by
design (invariant 5) — delegates every glob decision, *including every floor
decision*, to `risk.matches_any_glob`. The BODIES/SCAFFOLD deny table delegates
"is this a test file?" to `seal_verify.is_test_path` via
`SEAL_VERIFY_TEST_PATHS`. `check_branch` reads the base policy through
`repo_config` + `yaml_io`, and reads the base blobs the scaffolded-signature
half compares through `repo_config.blob_text_at`. A branch that edits any of
those defeats the gate while touching nothing the floor names, and gets CLEAN.
Measured end to end (real repository, `built_in_policy()`, body-only edit that
changes no signature)::

    BODIES  src/claude_dispatcher/risk.py           -> clean, violations=[]
    BODIES  src/claude_dispatcher/seal_verify.py    -> clean, violations=[]
    BODIES  src/claude_dispatcher/role_protocol.py  -> violation

This is the **eighth** instance in this effort of a gate being writable by the
thing it gates, and the second one *inside the floor itself* after S2/S3.

What is sealed: the PROPERTY, not two filenames
-----------------------------------------------
Adding two literals fixes today and leaves the class open — the ninth
delegation is unprotected again, silently. What is sealed here is
**delegation closure**: every in-package module whose code runs while a floor
decision is being reached is itself on the floor.

The closure is DERIVED from the source, by AST, in `_delegation_closure`:

  1. From a written-out set of **roots** — the two functions that make a floor
     decision, `check_branch` (diff time) and `_floor_glob_named_by` (plan
     time) — walk `role_protocol`'s intra-module call graph.
  2. Collect every `claude_dispatcher.*` module those reached functions import
     (they are all function-local imports; the gate path deliberately keeps
     them lazy), plus `role_protocol`'s own non-`TYPE_CHECKING` module-level
     in-package imports.
  3. Transitively add the module-level in-package imports of each of those, and
     of theirs — because a module-level import EXECUTES the dependency's body
     on the gate path, and a body that runs can rebind anything, including
     `risk.matches_any_glob`.

Measured today the closure is five modules: `risk`, `seal_verify`,
`repo_config`, `yaml_io` (all reached from `check_branch`) and
`mechanical_verify` (reached only because `seal_verify` imports it at module
level).

Note what this makes available to the fixer, which is why it is a property and
not a list: a module can leave the closure EITHER by joining the floor OR by
being pushed off the gate path. `mechanical_verify` is in the closure solely
because of `seal_verify`'s top-level `from . import mechanical_verify`; making
that import function-local removes it from the closure and these seals go green
without it ever being floored. The seal pushes toward a small trusted base, not
merely a large floor.

**P4, 2026-08-09: the property is ENDORSED and the discharge is bounded, and
the paragraph above is corrected on one word.** Leaving the gate path is a real
fix and the only thing that stops this floor growing monotonically. But
"function-local" is not the same fact as "does not execute": measured, moving
that import into `seal_verify.is_test_path` instead — the function the deny
table calls — also removes the row from the derived closure, with the body
still running on every gate decision, and no seal here tells the two apart. So
a module leaves the closure by leaving the GATE PATH, not by relocating an
import; and the claim that it did is a P4 ruling, not a green run. Dispute 3
below carries the measurement and the checklist is on `_DELEGATION_TARGETS`.

WHAT THIS CAN DETECT
  * A new `from . import X` added inside any function reachable from a floor
    decision — the derived closure grows and both
    `test_the_delegation_closure_is_exactly_the_written_out_table` and
    `test_every_module_in_the_derived_closure_is_on_the_floor` redden, naming X.
  * A new module-level in-package import anywhere already inside the closure —
    same two seals, via step 3.
  * A new floor decision written as a function that is not reachable from the
    written-out roots — `test_every_floor_decision_is_reachable_from_the
    _written_out_roots` reddens naming it, so the hand-written root list
    cannot silently go stale.
  * Deletion of a floor glob covering a delegation target — the two floor
    coverage seals redden.
  * A floor glob spelled basename-only —
    `test_the_floor_glob_over_a_delegation_target_is_path_qualified` reddens.

WHAT THIS CANNOT DETECT
  * Delegation that is not a static import: `importlib.import_module(name)`
    with a computed name, `__getattr__`-based lazy module attributes, entry
    points / plugins, monkeypatching from outside the package, or a subprocess
    that runs another interpreter. The analyzer reads imports, not behaviour.
  * A call reached through a variable, an attribute, a callable parameter or a
    dispatch table rather than a bare `name(...)` — step 1's call graph
    resolves `ast.Name` callees only. A floor decision hidden behind
    `handlers[kind]()` is invisible to it. (The `run=` seam `check_branch`
    takes is exactly this shape, and is deliberately out of scope: it is
    injected by the caller, not supplied by the branch.)
  * Delegation to anything that is not an in-package Python module — a shell
    helper, a Go binary, a data file, a regex kept in YAML. The gate's shell
    entrypoint is on the floor already; a future non-Python delegate would need
    its own row.
  * Whether the FIX is any good. These seals say the closure is floored; they
    say nothing about whether `risk.matches_any_glob` is correct. The two
    CRITICALs the same panel found in these very modules — `is_test_path`'s
    regex anchor bypass and `risk.py`'s quoted-path escalation bypass — are
    other work and are not touched here.
  * **Whether a module that LEFT the derived closure actually left the gate
    path.** Added by P4, 2026-08-09, and measured, because the escape hatch
    described above is the first place a fixer will reach. Step 1 walks
    `role_protocol`'s call graph and step 3 reads only the MODULE-LEVEL imports
    of closure members, so an import moved INTO a closure member's function is
    invisible to both. Two branches were built and run in full, differing in
    one line — the honest discharge, with `seal_verify`'s
    `from . import mechanical_verify as mv_mod` function-local inside
    `run_seal_inversion` (which `is_test_path` does not call, so nothing on the
    gate path executes it), and the bypass, with the same import ALSO inside
    `is_test_path` itself (so its body runs on every gate decision). Both drop
    `mechanical_verify` from the derived closure. With the P4 table amendments
    a discharge requires, the two runs are IDENTICAL: 1653 passed, 13 skipped,
    no failures, in both. Nothing in this suite distinguishes the fix from the
    defect. See dispute 3 for what follows from that, and note what does NOT:
    a P3 cannot reach either state alone, because all three tables that have to
    shrink (`_DELEGATION_TARGETS`, `_CLOSURE_ROWS`, and `_FLOOR_ROWS` in
    `test_role_protocol_floor.py`) are seals.
  * The provenance question. `scripts/check_body_branch.sh` already materialises
    the WHOLE of `<base>:src/` when the gate lives inside the judged tree, so a
    trusted run of that script does not import the branch's `risk.py` today.
    That is a mitigation at ONE of the two enforcement points; the orchestrator's
    in-process `check_branch` has no such pinning, and in any case the floor's
    job is to refuse the write, not to survive it. Nothing here asserts anything
    about which copy runs — `test_role_protocol_provenance.py` owns that.

Derived vs written-out, and the vacuity rule
--------------------------------------------
The P4 rule from this unit is that **a table derived by a comprehension across
the constant it pins is vacuous** — deleting an entry from the constant deletes
the row instead of reddening it (18 of 28 rows caught nothing). A hand-written
list, on the other hand, cannot notice a new delegation. Squared as follows,
and the resolution is that neither artifact pins itself and neither is derived
from `FLOOR_GLOBS`:

  * `_DELEGATION_TARGETS` is WRITTEN OUT, one row per module, with its real
    path, its vendored path, a same-basename control path, and why it is in the
    closure. Nothing reads it off `FLOOR_GLOBS` and nothing reads it off the
    analyzer.
  * The **derived closure is the witness that keeps the written table honest.**
    Delete a row from `_DELEGATION_TARGETS` and
    `test_the_delegation_closure_is_exactly_the_written_out_table` reddens,
    because the AST still finds the delegation. That is the 18-of-28 mutation,
    and it is caught — by an artifact derived from the SOURCE, which is
    independent of both the written table and the constant.
  * The **written table is the witness that keeps the derivation honest.** Break
    the analyzer so it returns `{}` — the shape that would make a derived-only
    seal vacuously green — and the same seal reddens, because the written table
    still has five rows.
  * Both are then checked AGAINST `FLOOR_GLOBS`, in two separate seals (one
    over the literal rows, one over the derived set), and `FLOOR_GLOBS` is
    read by neither of them as an input to what the answer should be.

So: the literal table pins the derivation, the derivation pins the literal
table, and the two of them jointly pin the constant. There is no cycle in which
a single deletion is self-consistent.

Disputes — ADJUDICATED by P4, 2026-08-09
-----------------------------------------
  1. **The spelling. RULED, and it is binding on P3.** The five globs are, one
     string each and in this order:

         **/src/claude_dispatcher/risk.py
         **/src/claude_dispatcher/seal_verify.py
         **/src/claude_dispatcher/repo_config.py
         **/src/claude_dispatcher/yaml_io.py
         **/src/claude_dispatcher/mechanical_verify.py

     Written into `_FLOOR_ROWS` in `test_role_protocol_floor.py` with both
     probes each (6 rows -> 16) and the bound raised 6 -> 16, which is the
     coordination P3 may not perform. The recommendation was verified, not
     accepted: measured under `first_matching_glob`, each covers the real path
     and the vendored `sub/project/...` layout and covers neither
     `vendor/thirdparty/<name>.py` nor `src/claude_dispatcher/plan.py`, while
     the basename-only form `**/<name>.py` swallows both
     `vendor/thirdparty/risk.py` and `notsrc/claude_dispatcher/risk.py`.
     One correction to the recommendation's shorthand: this engine has NO brace
     expansion, so `**/src/claude_dispatcher/{risk,seal_verify,...}.py` is a
     silent no-op that matches only a file literally named that. Five strings.
     Joint satisfiability measured in a `.git`-less clone: appending exactly
     these five to `FLOOR_GLOBS` and changing nothing else turns all 62 rows
     here green with 1663 passed / 13 skipped elsewhere, the only remaining
     failure being the coordination seal P4 has now amended.

  2. **The scope. The root set stands; the derivation is untouched.** The three
     modules beyond the two the panel named are kept, and the reasons differ in
     kind, so they are recorded separately rather than as one bloc:

       * `repo_config` and `yaml_io` are NOT merely import-time collateral.
         `check_branch` reads the base-pinned policy through them and reads,
         through `repo_config.blob_text_at`, every base blob the scaffolded-
         signature half compares. A branch that rewrites either one controls
         what the gate believes the protected base says — the same authority as
         rewriting the matcher, reached one call further out. They are decision
         delegates and would belong on the floor even if nothing were imported
         at module level.
       * `mechanical_verify` is the one weak row: import-time reachability
         only, floored because `seal_verify` executes its body on the gate
         path. It is kept, and it is also the row with a discharge that costs
         no floor width — see dispute 3.

     The root set (`check_branch`, `_floor_glob_named_by`) is endorsed
     unchanged. Seeding lower would be the narrowing the seal author warns
     about and would reopen the class; seeding higher would drag `plan.py` in
     and floor the unit's ordinary-source probe. And the measured cost of the
     full closure is not a reason to narrow it: the whole suite outside this
     file is unaffected by flooring all five.

     What the ruling DOES cost, recorded because the next author will hit it:
     the two sibling CRITICALs live inside the closure — `is_test_path`'s
     anchor bypass in `seal_verify` and the quoted-path escalation in `risk` —
     so once these globs land, neither can be fixed by a branch under review.
     Both become reviewed edits on the protected base. That is the floor
     working as designed (`FLOOR_RATIONALE` says so in as many words), not an
     accident of this ruling, and it is the strongest practical argument for
     dispute 3's escape hatch.

  3. **Leave-by-lazy-import: the PROPERTY is ENDORSED, the DISCHARGE is
     bounded.** Endorsed because a floor has no override and therefore no way
     to shrink: without this property every delegation discovered forever is a
     permanent addition, and the incentive runs the wrong way — toward a large
     floor rather than a small trusted base. It is also the only route by which
     the two CRITICALs above become ordinarily fixable again.

     Bounded because no seal can check the claim, which was measured rather
     than argued. Two full-suite runs differing in one line (detailed in the
     last entry under WHAT THIS CANNOT DETECT): the honest discharge, where
     `mechanical_verify`'s import is function-local inside a `seal_verify`
     function the gate never calls, and the bypass, where it is ALSO inside
     `is_test_path`, so its body runs on every gate decision. Both leave the
     derived closure; with the table amendments a discharge requires, both are
     1653 passed / 0 failed. **The seals cannot tell the fix from the defect.**

     So the escape hatch's wording matters and is corrected here: a module
     leaves the closure by leaving the GATE PATH — its body no longer executes
     while a floor decision is reached — and NOT by relocating an import
     inward. Relocating changes what the analyzer reports and changes nothing
     about whose code runs.

     **The control is procedural, and it already exists.** Reaching either
     state requires deleting rows from `_DELEGATION_TARGETS`, from
     `_CLOSURE_ROWS`, and from `_FLOOR_ROWS` in `test_role_protocol_floor.py` —
     three tables, all seals, none of them P3's to edit. The discharge
     therefore cannot be taken, only REQUESTED, and the request lands on P4.
     What P4 owes it is the check the analyzer cannot do: read the enclosing
     function and establish that nothing the gate calls into that module
     reaches it. The checklist is on `_DELEGATION_TARGETS`.

     Two alternatives were considered and rejected. Widening the derivation to
     walk closure members' call graphs would grow the floor on any in-package
     import anywhere inside a member — over-reach in a floor is permanent and
     unappealable, the same asymmetry dispute 4 turns on. And a seal refusing
     every function-local in-package import inside a closure member was
     written, run and WITHDRAWN: measured, it reddens on the honest discharge
     exactly as it reddens on the bypass, so it is a row the correct fix cannot
     turn green. A permanent red is not a control; it is a seal the next author
     learns to amend away.

  4. **The basename/path-qualified asymmetry: ACCEPTED again, on the record.**
     Plan time (`_floor_glob_named_by`) compares BASENAMES; diff time
     (`_floor_violations`) matches the path-qualified glob. So once `risk.py`
     is floored, `vendor/thirdparty/risk.py` is unDECLARABLE and still
     WRITABLE. Three reasons it is not the fail-open it resembles:

       * The asymmetry runs in the SAFE direction. Plan time is STRICTER than
         diff time, so it can only produce a false refusal, never a false
         clearance. The dangerous shape — plan time laxer than diff time —
         does not exist here, and could not, because plan time has no diff to
         consult and deliberately over-approximates.
       * `vendor/thirdparty/risk.py` being writable is the floor CORRECTLY
         SCOPED, not the floor leaking. The gate imports `claude_dispatcher
         .risk`, resolved under the package root; a vendored copy at another
         root is never executed while a floor decision is reached, and
         rewriting it changes no floor decision. `_STILL_WRITABLE_ROWS` seals
         that as a required property, so "closing" this direction would mean
         deliberately reddening a control written to bound the fix.
       * The false-refusal side has a spelling that works. `_floor_glob_named_
         by` returns None for a tail of pure wildcards, so an adjudication that
         genuinely needs a vendored file declares the TREE (`vendor/**`,
         `vendor/thirdparty/**`) rather than the file, and diff time then
         clears it because the path is not floored. Measured 2026-08-09.

     Accepted, not free. The false-refusal surface is materially wider than it
     was when this asymmetry was accepted for `role_protocol.py`: the floor
     named three unusual basenames and now names eight, three of which
     (`risk.py`, `repo_config.py`, `yaml_io.py`) an unrelated file could
     plausibly acquire. The mitigation is that the refusal lands at PLAN time,
     names the entry, and has the subtree spelling above; if that proves
     insufficient in practice the fix is to give plan time the path-qualified
     comparison as a SECOND question — not to remove the basename one, which is
     what catches `risk.py` and `.dispatcher.*` and is the whole point of the
     2026-08-07 ruling.

  5. **The stale prose in `test_glob_newline.py`: FIXED.** Two places said
     "`risk.py` is not on `FLOOR_GLOBS`" (the module docstring's "One
     translator, not two" section, which also concluded "the fix needs no floor
     edit", and `test_both_gates_answer_the_same_question_the_same_way`'s
     docstring). No assertion depended on either. Both now state the fact this
     change establishes and the consequence for where a future fix may live.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import role_protocol as rp_mod
from claude_dispatcher.role_protocol import (
    FLOOR_GLOBS,
    FLOOR_RATIONALE,
    DiffVerdict,
    PolicySource,
    Role,
    RolePolicy,
    RoleProtocolError,
    RoleRule,
    RuleKind,
    TaskRoleSpec,
    check_branch,
    first_matching_glob,
    parse_task_role_spec,
)

#: The package's source directory, resolved from the imported module rather
#: than from this file's location, so the analyzer reads the same code the rest
#: of the suite imported. A layout change that breaks this is a loud
#: `FileNotFoundError`, never a quietly empty closure —
#: `test_the_analyzer_reads_real_source` pins that.
_PKG_ROOT = Path(rp_mod.__file__).resolve().parent


# --------------------------------------------------------------------------- #
# The analyzer: the delegation closure of a floor decision, derived from source
# --------------------------------------------------------------------------- #

#: The functions that MAKE a floor decision. WRITTEN OUT — this is the one
#: hand-written input to the derivation, and it is a decision, not a
#: measurement: `check_branch` is the function that returns a verdict, and
#: `_floor_glob_named_by` is the plan-time floor predicate.
#:
#: Seeded here and not higher on purpose. `validate` / `units_of` reach
#: `plan.py`, and `plan.py` is the established ORDINARY-SOURCE probe for the
#: whole unit (`_STILL_WRITABLE_ROWS`, `_GLOB_PROBES["**/src/**"]`, the
#: legitimate-declaration control). Seeding at the worklist loader would pull
#: the subject matter of the protocol into the machinery of the protocol and
#: floor a file three other seal files require to stay writable.
#:
#: This list going stale is itself sealed:
#: `test_every_floor_decision_is_reachable_from_the_written_out_roots` derives
#: the set of functions that name `FLOOR_GLOBS` and requires every one to be
#: reachable from here.
_FLOOR_DECISION_ROOTS: tuple[str, ...] = ("check_branch", "_floor_glob_named_by")


def _in_package_imports(node: ast.AST) -> frozenset[str]:
    """Every `claude_dispatcher` submodule an import statement names.

    All five spellings the package actually uses are handled: `from . import x`,
    `from .x import y`, `from claude_dispatcher import x`,
    `from claude_dispatcher.x import y` and `import claude_dispatcher.x`.
    Anything else — a relative import two levels up, a third-party import — is
    not in the package and is not a delegation this floor can own.
    """
    if isinstance(node, ast.ImportFrom):
        if node.level == 1:
            if node.module is None:
                return frozenset(alias.name for alias in node.names)
            return frozenset({node.module.split(".")[0]})
        if node.level == 0 and node.module == "claude_dispatcher":
            return frozenset(alias.name for alias in node.names)
        if node.level == 0 and (node.module or "").startswith("claude_dispatcher."):
            return frozenset({node.module.split(".")[1]})
        return frozenset()
    if isinstance(node, ast.Import):
        return frozenset(
            alias.name.split(".")[1]
            for alias in node.names
            if alias.name.startswith("claude_dispatcher.")
        )
    return frozenset()


def _is_type_checking_guard(stmt: ast.stmt) -> bool:
    """`if TYPE_CHECKING:` — a block whose imports never run.

    Excluded from the module-level scan because the whole point of step 3 is
    "this dependency's body EXECUTES on the gate path". A `TYPE_CHECKING`
    import executes nothing and can rebind nothing, and counting it would put
    `plan.py` — which `role_protocol` imports exactly that way — into the
    closure and onto the floor, which three other seal files forbid.
    """
    test = stmt.test if isinstance(stmt, ast.If) else None
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _module_level_in_package_imports(tree: ast.Module) -> frozenset[str]:
    """In-package modules whose body runs when THIS module's body runs."""
    found: set[str] = set()
    for stmt in tree.body:
        if _is_type_checking_guard(stmt):
            continue
        if isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        for node in ast.walk(stmt):
            found |= _in_package_imports(node)
    return frozenset(found)


def _package_source(module: str) -> str | None:
    """The source of one in-package module, or None if the package has no such
    module (a `from . import x` naming something that is not a module — a
    subpackage, a name re-exported by `__init__` — contributes nothing)."""
    path = _PKG_ROOT / f"{module}.py"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _delegation_closure(read=_package_source) -> dict[str, str]:
    """Modules whose code runs while a floor decision is reached → why.

    `read` is the source seam so the seals below can point the SAME analyzer at
    a mutated copy of the package and check that it notices — the analyzer is
    not allowed to be trusted any more than the code it reads.

    `role_protocol` itself is dropped from the result: it is the module making
    the decision, it is already on the floor, and a self-row would make the
    "everything in the closure is floored" seal one row less falsifiable.
    """
    source = read("role_protocol")
    if source is None:
        raise AssertionError(
            "the analyzer cannot find role_protocol's source; an empty closure "
            "would make every seal in this file vacuously green"
        )
    tree = ast.parse(source, filename="role_protocol.py")
    functions = {
        stmt.name: stmt
        for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    absent = [name for name in _FLOOR_DECISION_ROOTS if name not in functions]
    if absent:
        raise AssertionError(
            f"the written-out floor-decision roots are not module-level "
            f"functions of role_protocol any more: {absent}. A renamed root "
            "must be renamed here too, or this file measures nothing"
        )

    def callees(fn: ast.AST) -> set[str]:
        return {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in functions
        }

    reached = set(_FLOOR_DECISION_ROOTS)
    pending = list(reached)
    while pending:
        for callee in callees(functions[pending.pop()]):
            if callee not in reached:
                reached.add(callee)
                pending.append(callee)

    why: dict[str, str] = {}
    frontier: list[str] = []

    def note(module: str, reason: str) -> None:
        if module not in why:
            why[module] = reason
            frontier.append(module)

    for name in sorted(reached):
        for node in ast.walk(functions[name]):
            for module in sorted(_in_package_imports(node)):
                note(module, f"imported by role_protocol.{name}()")
    for module in sorted(_module_level_in_package_imports(tree)):
        note(module, "imported by role_protocol at module level")

    while frontier:
        module = frontier.pop()
        sub_source = read(module)
        if sub_source is None:
            continue
        sub_tree = ast.parse(sub_source, filename=f"{module}.py")
        for dep in sorted(_module_level_in_package_imports(sub_tree)):
            note(dep, f"executed at import of {module} (module-level import)")

    why.pop("role_protocol", None)
    return why


def _functions_that_read_the_floor(source: str) -> frozenset[str]:
    """Module-level functions of `role_protocol` naming `FLOOR_GLOBS`."""
    tree = ast.parse(source, filename="role_protocol.py")
    return frozenset(
        stmt.name
        for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(node, ast.Name) and node.id == "FLOOR_GLOBS"
            for node in ast.walk(stmt)
        )
    )


def _reachable_functions(source: str) -> frozenset[str]:
    """Everything the written-out roots can call, transitively, by bare name."""
    tree = ast.parse(source, filename="role_protocol.py")
    functions = {
        stmt.name: stmt
        for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    reached = set(_FLOOR_DECISION_ROOTS)
    pending = list(reached)
    while pending:
        current = functions[pending.pop()]
        for node in ast.walk(current):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in functions
                and node.func.id not in reached
            ):
                reached.add(node.func.id)
                pending.append(node.func.id)
    return frozenset(reached)


# --------------------------------------------------------------------------- #
# The written-out table
# --------------------------------------------------------------------------- #

#: One row per module in the delegation closure. WRITTEN OUT: not a
#: comprehension over `_delegation_closure()`, not over `FLOOR_GLOBS`, not over
#: the package directory. Each row is
#: (module, its path, its vendored path, a same-basename control path, why).
#:
#: The control path is the row's own upper bound and is the reason the table
#: carries four strings rather than one: the floor glob that covers
#: `src/claude_dispatcher/risk.py` must NOT cover `vendor/thirdparty/risk.py`.
#: A floor has no override, so a basename-only glob would permanently forbid
#: every file that ever acquires that basename anywhere in the tree — the P4
#: ruling of 2026-08-09 recorded on `_FLOOR_ROWS`, applied to the five modules
#: that ruling did not yet know about.
#:
#: `mechanical_verify`'s reason is worth reading twice. It is in the closure
#: only because `seal_verify` imports it at MODULE level, so importing the
#: test-path matcher executes it on the gate path. It is the one row a fixer
#: can discharge without flooring anything: DELETE that import, and the derived
#: closure loses the row, at which point THIS table has to lose it too or
#: `test_the_delegation_closure_is_exactly_the_written_out_table` reddens.
#: Either resolution is a real fix; a silent divergence is not available.
#:
#: **P4, 2026-08-09 — one correction, and a checklist for whoever amends this
#: table.** As originally written the paragraph above said "make that import
#: function-local". Measured, that is not a fix: an import relocated into
#: `seal_verify.is_test_path` — the function the deny table calls — leaves the
#: derived closure and still executes on every gate decision, and no seal in
#: this suite distinguishes it from the honest deletion (dispute 3 records both
#: runs). Deleting a row here is therefore the ONLY route to that state, which
#: makes this table the control. Before deleting a row on a "left the gate
#: path" claim, P4 must establish, by reading the code and not by reading a
#: green run:
#:
#:   a. the module is not imported at MODULE level by any closure member — the
#:      derivation checks this one, and it is the only one it checks;
#:   b. every function-local import of it inside a closure member sits in a
#:      function that nothing the gate calls into that member can reach.
#:      `role_protocol` enters `risk` at `matches_any_glob`, `seal_verify` at
#:      `is_test_path`, and `repo_config`/`yaml_io` through the policy and blob
#:      reads in `check_branch`; the reachable set is those entry points'
#:      intra-module call graphs;
#:   c. the same two rows in `_CLOSURE_ROWS` and `_FLOOR_ROWS` come out in the
#:      same commit, so the three tables cannot disagree about which modules
#:      are in the trusted base.
#:
#: Deleting a row on any weaker basis converts this seal from a protection into
#: a record of one.
_DELEGATION_TARGETS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "risk",
        "src/claude_dispatcher/risk.py",
        "sub/project/src/claude_dispatcher/risk.py",
        "vendor/thirdparty/risk.py",
        "role_protocol.first_matching_glob delegates EVERY glob decision, "
        "including every floor decision, to risk.matches_any_glob",
    ),
    (
        "seal_verify",
        "src/claude_dispatcher/seal_verify.py",
        "sub/project/src/claude_dispatcher/seal_verify.py",
        "vendor/thirdparty/seal_verify.py",
        "the deny table delegates 'is this a test file' to "
        "seal_verify.is_test_path via SEAL_VERIFY_TEST_PATHS",
    ),
    (
        "repo_config",
        "src/claude_dispatcher/repo_config.py",
        "sub/project/src/claude_dispatcher/repo_config.py",
        "vendor/thirdparty/repo_config.py",
        "check_branch reads the base-pinned policy and every base blob the "
        "scaffolded-signature half compares through repo_config",
    ),
    (
        "yaml_io",
        "src/claude_dispatcher/yaml_io.py",
        "sub/project/src/claude_dispatcher/yaml_io.py",
        "vendor/thirdparty/yaml_io.py",
        "load_role_policy_from_base parses the base-pinned `roles:` section "
        "with it, and risk imports it at module level",
    ),
    (
        "mechanical_verify",
        "src/claude_dispatcher/mechanical_verify.py",
        "sub/project/src/claude_dispatcher/mechanical_verify.py",
        "vendor/thirdparty/mechanical_verify.py",
        "seal_verify imports it at MODULE level, so its body executes on the "
        "gate path and can rebind anything the gate is about to call",
    ),
)


# --------------------------------------------------------------------------- #
# Part 1 — the closure mechanism, and the proof that it can fail
# --------------------------------------------------------------------------- #


def test_the_analyzer_reads_real_source() -> None:
    """The analyzer's own non-vacuity, before anything is asserted with it.

    Three things in one call, each of which would make every other seal in
    Part 1 meaningless if it were false: the closure is non-empty, it contains
    the delegation the panel reproduced, and it does NOT contain a module that
    is nowhere on the gate path. Without the third, "return every module in the
    package" satisfies this file and would floor the whole tree.

    GREEN TODAY and must stay green.
    Falsify (measured): make `_delegation_closure` return `{}` — the first
    assertion reddens; make it return every module under `_PKG_ROOT` — the
    third reddens on `bakeoff`.
    """
    closure = _delegation_closure()
    assert closure, (
        "the analyzer found no delegation at all; an empty closure makes "
        "every 'the closure is floored' seal in this file vacuously true"
    )
    assert "risk" in closure, (
        "the analyzer did not find the delegation the panel reproduced — "
        f"role_protocol.first_matching_glob -> risk.matches_any_glob: {closure}"
    )
    assert "bakeoff" not in closure, (
        "the analyzer reported a module that is not on the gate path at all; "
        "a closure that over-reaches would floor the tree, which is not a fix"
    )
    assert "role_protocol" not in closure, (
        "the deciding module must not be a row in its own closure"
    )


def test_the_analyzer_notices_a_delegation_that_is_not_there_today() -> None:
    """THE control that makes this whole file worth writing: the closure seal
    must be able to fail when a NEW delegation appears.

    A hand-written list cannot do this, which is why the derivation exists; a
    derivation nobody falsified is worse than the hand-written list, which is
    why this row exists. Both injections are judged in this one call, against
    the REAL package source, mutated in memory only:

      1. a function-local `from . import bakeoff` planted inside
         `_floor_violations` — the shape of a new decision delegate;
      2. a module-level `from . import bakeoff` planted in `seal_verify` — the
         shape of a new import-time reachability, one hop out from the gate.

    Both are absent from the unmutated closure in the same call, so the row
    proves the INJECTION is the difference and not something the analyzer says
    about `bakeoff` in general.

    GREEN TODAY and must stay green.
    Falsify (measured): make `_delegation_closure` ignore function-local
    imports — injection 1 reddens; make it skip step 3's transitive walk —
    injection 2 reddens.
    """
    baseline = _delegation_closure()
    assert "bakeoff" not in baseline, baseline

    real_source = _package_source("role_protocol")
    assert real_source is not None
    tree = ast.parse(real_source)
    planted = 0
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.FunctionDef)
            and stmt.name == "_floor_violations"
        ):
            stmt.body.insert(
                0,
                ast.ImportFrom(
                    module=None, names=[ast.alias(name="bakeoff")], level=1
                ),
            )
            planted += 1
    assert planted == 1, (
        "the injection point `_floor_violations` was not found exactly once, "
        "so this control planted nothing and proves nothing"
    )
    mutated = ast.unparse(ast.fix_missing_locations(tree))

    def read_call_site(module: str) -> str | None:
        return mutated if module == "role_protocol" else _package_source(module)

    injected_call = _delegation_closure(read_call_site)
    assert "bakeoff" in injected_call, (
        "a `from . import bakeoff` planted inside `_floor_violations` — a "
        "function that reads FLOOR_GLOBS — was not reported as a delegation, "
        "so a real new delegate would land unnoticed"
    )

    seal_verify_source = _package_source("seal_verify")
    assert seal_verify_source is not None

    def read_import_time(module: str) -> str | None:
        if module == "seal_verify":
            return "from . import bakeoff\n" + seal_verify_source
        return _package_source(module)

    injected_import = _delegation_closure(read_import_time)
    assert "bakeoff" in injected_import, (
        "a module-level `from . import bakeoff` in seal_verify — whose body "
        "runs whenever the gate asks 'is this a test file' — was not reported, "
        "so the transitive half of the closure is not being computed"
    )


def test_every_floor_decision_is_reachable_from_the_written_out_roots() -> None:
    """The guard on the one hand-written input to the derivation.

    `_FLOOR_DECISION_ROOTS` is a decision and cannot be derived (see its
    comment). What CAN be derived is whether it has gone stale: every
    module-level function of `role_protocol` that names `FLOOR_GLOBS` is a
    floor decision, and every one must be reachable from the roots — otherwise
    the closure is computed over a subset of the floor decisions and a
    delegation added under the missing one is invisible.

    Measured today: three functions name `FLOOR_GLOBS` — `check_branch`,
    `_floor_glob_named_by` (both roots) and `_floor_violations` (called by
    `check_branch`).

    GREEN TODAY and must stay green.
    Falsify (measured): drop `_floor_glob_named_by` from the roots — it names
    `FLOOR_GLOBS`, nothing reachable calls it, and this reddens naming it.
    """
    source = _package_source("role_protocol")
    assert source is not None
    readers = _functions_that_read_the_floor(source)
    assert readers, (
        "no function in role_protocol names FLOOR_GLOBS — either the floor is "
        "gone or this analyzer is reading the wrong file"
    )
    reachable = _reachable_functions(source)
    unreachable = sorted(readers - reachable)
    assert not unreachable, (
        "these functions make a floor decision but are not reachable from "
        f"{list(_FLOOR_DECISION_ROOTS)!r}, so the delegation closure was "
        f"computed without them: {unreachable}"
    )


def test_the_delegation_closure_is_exactly_the_written_out_table() -> None:
    """The two-way pin, and the answer to derived-vs-written-out.

    Neither side of this equality is derived from the other, and neither is
    derived from `FLOOR_GLOBS`:

      * derived side — `_delegation_closure()`, read out of the package's
        source by AST;
      * written side — `_DELEGATION_TARGETS`, typed out by hand.

    So a NEW delegation reddens it (derived grows, written does not) and a
    DELETED written row reddens it (written shrinks, derived does not) — the
    18-of-28 mutation, caught, on a table that a comprehension could not have
    made falsifiable. And an analyzer broken to return `{}` reddens it too,
    which is what keeps the derivation from being the vacuous half.

    GREEN TODAY and must stay green. Its value is the NEXT delegation.
    Falsify (measured): delete the `risk` row — reddens with `only in the
    code: ['risk']`; add a `plan` row — reddens with `only in the table:
    ['plan']`.
    """
    derived = _delegation_closure()
    written = {module for module, _p, _n, _c, _why in _DELEGATION_TARGETS}
    assert len(written) == len(_DELEGATION_TARGETS), (
        f"_DELEGATION_TARGETS names a module twice: {_DELEGATION_TARGETS}"
    )
    new_delegations = sorted(set(derived) - written)
    stale_rows = sorted(written - set(derived))
    assert (new_delegations, stale_rows) == ([], []), (
        "the floor's delegation closure and the written-out table disagree.\n"
        f"  only in the code (a NEW delegation — write its row, and floor it): "
        f"{[(m, derived[m]) for m in new_delegations]}\n"
        f"  only in the table (the delegation is gone — drop the row): "
        f"{stale_rows}"
    )


@pytest.mark.parametrize(
    "module, path, why",
    [(m, p, w) for m, p, _n, _c, w in _DELEGATION_TARGETS],
    ids=[m for m, _p, _n, _c, _w in _DELEGATION_TARGETS],
)
def test_every_delegation_target_is_on_the_floor(
    module: str, path: str, why: str
) -> None:
    """The property, over the written-out rows. FIVE ROWS, ALL RED.

    Red now (measured 2026-08-09): `first_matching_glob(path, FLOOR_GLOBS)` is
    `None` for all five.
    Green when: each path is covered by some glob in `FLOOR_GLOBS`.
    Falsify: the in-row control below — `src/claude_dispatcher/plan.py` must
    stay off the floor — so "put `**/src/**` on the floor" reddens instead of
    passing, and the positive control proves the lens itself works.
    """
    # The lens works: the one module the floor already covers is covered.
    assert (
        first_matching_glob(
            "src/claude_dispatcher/role_protocol.py", FLOOR_GLOBS
        )
        is not None
    ), "the floor does not cover role_protocol.py; this seal's lens is broken"
    # The upper bound, in the same call: an ordinary module stays writable.
    assert (
        first_matching_glob("src/claude_dispatcher/plan.py", FLOOR_GLOBS) is None
    ), (
        "the floor grew to cover an ordinary source module; flooring the "
        "package is not closing the delegation"
    )

    assert first_matching_glob(path, FLOOR_GLOBS) is not None, (
        f"{path} is not on the floor, and {why}. A role that may write it may "
        f"decide what the floor means: {list(FLOOR_GLOBS)}"
    )


def test_every_module_in_the_derived_closure_is_on_the_floor() -> None:
    """The same property over the DERIVED set — the row a future delegation
    reddens even if nobody writes its table row.

    Not a duplicate of the parametrized seal above. That one is literal and
    survives a broken analyzer; this one is derived and survives a deleted
    literal row. Together they mean no single deletion is self-consistent.

    Red now (measured): all five derived modules report `floor=None`.
    Green when: every module in the closure is covered by some floor glob, or
    has been pushed off the gate path so that it is no longer in the closure.
    Falsify: an analyzer returning `{}` passes THIS row and reddens
    `test_the_delegation_closure_is_exactly_the_written_out_table`.
    """
    derived = _delegation_closure()
    unfloored = sorted(
        module
        for module in derived
        if first_matching_glob(f"src/claude_dispatcher/{module}.py", FLOOR_GLOBS)
        is None
    )
    assert not unfloored, (
        "the floor delegates its decision to modules it does not protect, so "
        "a branch can defeat the floor while touching nothing the floor "
        "names. Floor them, or take them off the gate path: "
        + "; ".join(f"{m} ({derived[m]})" for m in unfloored)
    )


@pytest.mark.parametrize(
    "module, path, nested, control",
    [(m, p, n, c) for m, p, n, c, _w in _DELEGATION_TARGETS],
    ids=[m for m, _p, _n, _c, _w in _DELEGATION_TARGETS],
)
def test_the_floor_glob_over_a_delegation_target_is_path_qualified(
    module: str, path: str, nested: str, control: str
) -> None:
    """P4's 2026-08-09 spelling ruling, applied to the five modules it did not
    yet know about. FIVE ROWS, ALL RED.

    A floor has no override. A basename-only glob (`**/risk.py`) permanently
    forbids every file that ever acquires that basename — a vendored copy, a
    fixture, an unrelated future module — with nothing able to buy it back. So
    the property is three-sided and all three are asserted here: the real path
    is covered, the VENDORED layout is covered (the repo can sit inside another
    tree, which is why `DEFAULT_ROLE_RULES` spells its globs `**/x/**`), and a
    same-basename file elsewhere is NOT.

    No glob STRING is asserted. The spelling is P4's, because `_FLOOR_ROWS` in
    `test_role_protocol_floor.py` is a set difference against `FLOOR_GLOBS` and
    a string P3 invents that P4 has not written there reddens that seal. This
    row pins what the string must DO; P4 ruled the strings on 2026-08-09 and
    they are written out in `_FLOOR_ROWS` and quoted under dispute 1 in this
    module's docstring. **P3: use them verbatim.** Note in particular that they
    are five separate strings — this engine has no brace expansion, and a
    `{a,b,c}` alternation is a floor that matches nothing.

    Red now (measured): the first assertion fails — no glob covers the path.
    Green when: all three hold.
    Falsify: spell the glob `**/risk.py` — the third assertion reddens.
    """
    covering = first_matching_glob(path, FLOOR_GLOBS)
    assert covering is not None, f"{path} is not on the floor at all"
    assert first_matching_glob(nested, FLOOR_GLOBS) is not None, (
        f"the floor covers {path} but not the vendored layout {nested}; one "
        "pattern must cover both, as every other glob in this unit does"
    )
    assert first_matching_glob(control, FLOOR_GLOBS) is None, (
        f"the floor glob covering {module} also swallows {control}. A floor "
        "has no override, so a basename-only glob permanently forbids every "
        f"file that ever acquires that name: {covering!r}"
    )


# --------------------------------------------------------------------------- #
# Part 2 — the consequence, end to end, against a real repository
#
# Real repositories rather than a stubbed `run`. The seals here are about a
# verdict on a branch, and the two D1 lessons about stubbed gates (a seam that
# could not answer `merge-base` turned refusal rows green; a seam that answered
# a BODIES blob read wrongly turned writable rows red) both cost a P4 round.
# A repository cannot answer a command the gate did not run.
# --------------------------------------------------------------------------- #

_BASE_TEXT = "MARKER = 1\n\n\ndef helper(a: int) -> int:\n    return a\n"

#: The branch's edit: one CONSTANT changes, no `def` and no `class` changes.
#: Deliberate — the scaffolded-signature half of the BODIES gate must report
#: CHECKED with zero changes, so every verdict below turns on the PATH gate and
#: a row cannot pass because the signature comparator happened to object.
_BRANCH_TEXT = "MARKER = 2\n\n\ndef helper(a: int) -> int:\n    return a\n"

_STRIPPED_RATIONALE = "injected policy with the delegation deliberately open"


def _policy_that_protects_nothing() -> RolePolicy:
    """A complete, well-formed policy under which every probe below is writable.

    Models both ways a policy can arrive — a base-pinned `roles:` section from
    a repo that does not carry these paths, and a caller-supplied `policy=`,
    which the contract says wins verbatim. Every refusal row asserts the probe
    is writable under this policy BEFORE asserting the refusal, so a pass can
    only come from a tier no supplied policy can lower, which is what
    `FLOOR_GLOBS` is.
    """
    rules: list[RoleRule] = []
    for role in Role:
        if role is Role.LEGACY:
            rules.append(
                RoleRule(Role.LEGACY, RuleKind.UNRESTRICTED, (), _STRIPPED_RATIONALE)
            )
        elif role is Role.ADJUDICATE:
            rules.append(
                RoleRule(
                    Role.ADJUDICATE, RuleKind.ALLOW_ONLY_GLOBS, (), _STRIPPED_RATIONALE
                )
            )
        else:
            rules.append(
                RoleRule(
                    role,
                    RuleKind.DENY_GLOBS,
                    ("**/never-touched/**",),
                    _STRIPPED_RATIONALE,
                )
            )
    return RolePolicy(
        rules=tuple(rules), source=PolicySource.BASE_PINNED_CONFIG, base_ref="main"
    )


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _branch_that_only_edits(tmp_path: Path, path: str) -> Path:
    """A repo on `main` whose `feat/x` changes exactly one file, in its body."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "T"], repo)
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_BASE_TEXT, encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "base"], repo)
    _git(["checkout", "-q", "-b", "feat/x"], repo)
    target.write_text(_BRANCH_TEXT, encoding="utf-8")
    _git(["add", "."], repo)
    _git(["commit", "-q", "-m", "the whole branch"], repo)
    return repo


def _spec(role: Role, *disputed: str) -> TaskRoleSpec:
    return TaskRoleSpec(
        task_key="D1-CLOSURE", role=role, disputed_paths=tuple(disputed)
    )


#: (role, changed path). WRITTEN OUT, one row per pair — five roles times the
#: five delegation targets. Derived from nothing: not from `Role`, not from
#: `FLOOR_GLOBS`, not from `_DELEGATION_TARGETS`, not from a product
#: comprehension. Same discipline and same shape as `_GATE_ROWS` in
#: `test_role_protocol_provenance.py`, which is the table this one extends from
#: the gate's two halves to the five modules the gate delegates to.
#:
#: LEGACY is a row for the same reason the floor covers it: LEGACY is not
#: granted to anyone, it is what a row IS when the `role:` key is absent, so a
#: protection LEGACY escapes is bypassed by deleting one line — and the deleted
#: line would buy the right to rewrite the matcher every floor decision runs
#: through.
_CLOSURE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", "src/claude_dispatcher/risk.py"),
    ("scaffold", "src/claude_dispatcher/seal_verify.py"),
    ("scaffold", "src/claude_dispatcher/repo_config.py"),
    ("scaffold", "src/claude_dispatcher/yaml_io.py"),
    ("scaffold", "src/claude_dispatcher/mechanical_verify.py"),
    ("seals", "src/claude_dispatcher/risk.py"),
    ("seals", "src/claude_dispatcher/seal_verify.py"),
    ("seals", "src/claude_dispatcher/repo_config.py"),
    ("seals", "src/claude_dispatcher/yaml_io.py"),
    ("seals", "src/claude_dispatcher/mechanical_verify.py"),
    ("bodies", "src/claude_dispatcher/risk.py"),
    ("bodies", "src/claude_dispatcher/seal_verify.py"),
    ("bodies", "src/claude_dispatcher/repo_config.py"),
    ("bodies", "src/claude_dispatcher/yaml_io.py"),
    ("bodies", "src/claude_dispatcher/mechanical_verify.py"),
    ("adjudicate", "src/claude_dispatcher/risk.py"),
    ("adjudicate", "src/claude_dispatcher/seal_verify.py"),
    ("adjudicate", "src/claude_dispatcher/repo_config.py"),
    ("adjudicate", "src/claude_dispatcher/yaml_io.py"),
    ("adjudicate", "src/claude_dispatcher/mechanical_verify.py"),
    ("legacy", "src/claude_dispatcher/risk.py"),
    ("legacy", "src/claude_dispatcher/seal_verify.py"),
    ("legacy", "src/claude_dispatcher/repo_config.py"),
    ("legacy", "src/claude_dispatcher/yaml_io.py"),
    ("legacy", "src/claude_dispatcher/mechanical_verify.py"),
)


@pytest.mark.parametrize(
    "role_value, changed", _CLOSURE_ROWS, ids=[f"{r}-{c}" for r, c in _CLOSURE_ROWS]
)
def test_no_role_gets_a_clean_verdict_for_editing_a_delegation_target(
    role_value: str, changed: str, tmp_path: Path
) -> None:
    """THE consequence, under a policy that protects nothing. TWENTY-FIVE ROWS.

    The whole branch is one body-only edit to one module the floor's own
    decision runs through. The supplied policy mentions none of these paths and
    each row proves that first, so a refusal cannot come from the deny table,
    from `built_in_policy`, or from a repo `roles:` addition: it requires a tier
    no supplied policy can lower, which is what the floor is for.

    Red now (measured 2026-08-09, real repositories): every row returns
    `DiffVerdict.CLEAN` with `violations == ()`.
    Green when: each returns a VIOLATION naming exactly the changed path.
    Falsify: `test_flooring_the_closure_costs_the_rest_of_the_tree_nothing`
    below — "refuse every `src/` path" reddens there while passing here; and
    the in-row assertion that the policy grants the path, so a row cannot pass
    on a deny the policy already carried.
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
    if role is Role.LEGACY:
        assert rule.kind is RuleKind.UNRESTRICTED, rule.kind

    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", role, policy=policy, spec=spec)

    assert [v.path for v in result.violations] == [changed], (
        f"role {role_value} rewrote {changed!r} — a module every floor "
        f"decision runs through — and the verdict was {result.verdict.value}"
    )
    assert result.verdict is DiffVerdict.VIOLATION
    violation = result.violations[0]
    assert violation.rationale != _STRIPPED_RATIONALE, (
        "the violation printed the injected policy's rationale, so it came "
        "from the policy — the one thing a caller can replace wholesale"
    )


@pytest.mark.parametrize(
    "role_value, changed", _CLOSURE_ROWS, ids=[f"{r}-{c}" for r, c in _CLOSURE_ROWS]
)
def test_a_delegation_target_is_refused_under_the_policy_the_gate_runs_with(
    role_value: str, changed: str, tmp_path: Path
) -> None:
    """The same twenty-five rows under `built_in_policy()` — the policy CI has.

    The seal above proves unlowerability by stripping the policy; this one
    proves the protection is reachable on the path production takes. Separate
    functions on purpose: an implementation that put the paths only in a
    caller-supplied default would satisfy one and not the other.

    Five rows are already VIOLATION today for an unrelated reason — SEALS is
    denied `**/src/**`, which covers all five probes — and that is fine: this
    file's job is that no role gets CLEAN, not that every row gets there by a
    new mechanism.

    Red now (measured): twenty of the twenty-five return CLEAN.
    Green when: all twenty-five are VIOLATION naming the path.
    """
    role = Role(role_value)
    spec = _spec(role, changed) if role is Role.ADJUDICATE else None
    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", role, spec=spec)
    assert [v.path for v in result.violations] == [changed], (
        f"under the built-in policy, role {role_value} may write {changed!r}"
    )
    assert result.verdict is DiffVerdict.VIOLATION


def test_a_floor_violation_on_a_delegation_target_reports_the_floors_own_reason(
    tmp_path: Path,
) -> None:
    """One row, separate from the tables, for the report an agent has to read.

    The refusal must arrive as a FLOOR refusal. For ADJUDICATE the role's own
    rationale says the writable set IS `disputed_paths:` — the one sentence
    that cannot explain refusing a path that is in `disputed_paths:`.

    Red now: CLEAN, so there is no violation to inspect.
    Green when: the violation carries `FLOOR_RATIONALE`.
    Falsify: implement the protection by appending to each role's `globs` — this
    then prints the role's own rationale and reddens, while the tables above
    still pass.
    """
    changed = "src/claude_dispatcher/risk.py"
    repo = _branch_that_only_edits(tmp_path, changed)
    spec = _spec(Role.ADJUDICATE, changed)
    result = check_branch(repo, "main", "feat/x", Role.ADJUDICATE, spec=spec)
    assert result.verdict is DiffVerdict.VIOLATION
    assert result.violations[0].rationale == FLOOR_RATIONALE, (
        "the glob matcher is protected by something other than the floor, or "
        "the floor's reason was not carried to the report: "
        f"{result.violations[0].rationale!r}"
    )


#: (role, changed path) pairs that must STAY clean. Written out. Without these,
#: "deny `**/src/**` to everyone" and "refuse every diff" both satisfy the two
#: tables above, and each would make the protocol unusable: BODIES exists to
#: write under `src/`. `plan.py` is the unit's established ordinary-source
#: probe and is the twin control the brief asks for — a branch whose only change
#: is an ordinary module must still be CLEAN.
#:
#: Only `.py` probes, and no SEALS row: a BODIES diff with no Python in it is
#: UNDETERMINED after I5 (the signature aggregate has nothing to read), and
#: SEALS is denied `**/src/**` outright. Neither is what this table is about,
#: and `_STILL_WRITABLE_ROWS` in `test_role_protocol_provenance.py` already
#: carries both shapes.
_STILL_WRITABLE_ROWS: tuple[tuple[str, str], ...] = (
    ("scaffold", "src/claude_dispatcher/plan.py"),
    ("scaffold", "src/claude_dispatcher/brand_new_unit.py"),
    ("scaffold", "vendor/thirdparty/risk.py"),
    ("bodies", "src/claude_dispatcher/plan.py"),
    ("bodies", "src/claude_dispatcher/brand_new_unit.py"),
    ("bodies", "vendor/thirdparty/risk.py"),
    ("legacy", "src/claude_dispatcher/plan.py"),
    ("legacy", "vendor/thirdparty/seal_verify.py"),
)


@pytest.mark.parametrize(
    "role_value, changed",
    _STILL_WRITABLE_ROWS,
    ids=[f"{r}-{c}" for r, c in _STILL_WRITABLE_ROWS],
)
def test_flooring_the_closure_costs_the_rest_of_the_tree_nothing(
    role_value: str, changed: str, tmp_path: Path
) -> None:
    """The upper bound, and the twin control the brief requires.

    `src/claude_dispatcher/plan.py` is the row that matters: the protection is
    about the modules the gate DELEGATES TO, not about the package they live
    in. A fix reaching for `**/src/claude_dispatcher/**` would stop BODIES doing
    its job and would make every legitimate change to the dispatcher
    unplannable, with no override, because a floor has no override.

    `vendor/thirdparty/risk.py` is the second row that matters: it is the
    basename-only mutation seen from the verdict side rather than from the glob
    side, so `**/risk.py` reddens here as well as in
    `test_the_floor_glob_over_a_delegation_target_is_path_qualified`.

    GREEN TODAY, all eight, and they must STILL be green afterwards.
    Falsify: floor the directory instead of the files — these go red while the
    two tables above stay green.
    """
    repo = _branch_that_only_edits(tmp_path, changed)
    result = check_branch(repo, "main", "feat/x", Role(role_value))
    assert result.verdict is DiffVerdict.CLEAN, (
        f"role {role_value} may no longer write {changed!r}: "
        f"{[(v.path, v.matched_glob) for v in result.violations]}"
    )
    assert result.violations == ()


# --------------------------------------------------------------------------- #
# Part 3 — the plan-time half
#
# `_floor_glob_named_by` reads the WHOLE of `FLOOR_GLOBS` and compares
# basenames, so P4's 2026-08-09 ruling ("one floor, one meaning": the two
# enforcement points cover the same set) carries these modules to plan time
# automatically. Sealed rather than assumed, because "automatically" is what
# the last seven instances of this defect class were also thought to be.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "disputed, case",
    [
        (("src/claude_dispatcher/risk.py",), "the glob matcher, named exactly"),
        (
            ("src/claude_dispatcher/seal_verify.py",),
            "the test-path matcher, named exactly",
        ),
        (("risk.py",), "the plain spelling"),
        (("**/src/claude_dispatcher/risk.py",), "the floor glob verbatim"),
        (
            ("docs/adr/0007.md", "src/claude_dispatcher/yaml_io.py"),
            "hidden behind a genuine artifact",
        ),
    ],
    ids=[
        "the glob matcher, named exactly",
        "the test-path matcher, named exactly",
        "the plain spelling",
        "the floor glob verbatim",
        "hidden behind a genuine artifact",
    ],
)
def test_declaring_a_delegation_target_is_refused_at_plan_time(
    disputed: tuple[str, ...], case: str
) -> None:
    """An adjudicate row may not declare a module the floor delegates to.

    Independent of Part 2 by construction: nothing here calls `check_branch`.

    Red now (measured): `parse_task_role_spec` returns a `TaskRoleSpec`
    carrying the path in `disputed_paths`; no exception is raised.
    Green when: it raises `RoleProtocolError` naming the task key and the entry.
    Falsify: the control below, which must keep parsing.
    """
    row = {
        "key": "D1-CLOSURE",
        "role": "adjudicate",
        "disputed_paths": list(disputed),
    }
    with pytest.raises(RoleProtocolError) as exc:
        parse_task_role_spec(row, task_key="D1-CLOSURE")
    message = str(exc.value)
    assert "D1-CLOSURE" in message, (
        "the message is read out of a run log; name the task"
    )
    assert any(entry in message for entry in disputed), (
        f"the refusal must name the offending entry, not just the rule: {message}"
    )


@pytest.mark.parametrize(
    "disputed",
    [
        ("src/claude_dispatcher/plan.py",),
        ("src/claude_dispatcher/**",),
        ("src/**",),
        ("features/d1/tasks.yaml",),
        ("tests/test_floor_closure.py",),
    ],
    ids=[
        "an ordinary source file",
        "the package subtree that CONTAINS the matchers",
        "a source subtree",
        "a tasks file",
        "a seal",
    ],
)
def test_a_legitimate_disputed_path_still_parses_with_the_closure_floored(
    disputed: tuple[str, ...],
) -> None:
    """The upper bound on Part 3, and the non-vacuity companion to it.

    Without it, "refuse every `src/` declaration" — or "refuse every `.py`" —
    satisfies the seal above, and a floor has no override, so the cost would be
    permanent. The subtree rows carry the 2026-08-07 ruling that plan time
    refuses declarations that NAME a floor file and does not refuse subtree
    globs that merely could contain one: only the diff knows whether they do,
    and the diff-time floor catches those for real.

    GREEN TODAY and must stay green.
    Falsify: implement the plan-time rule as "refuse any glob that could match a
    delegation target" — the two subtree rows go red.
    """
    row = {"key": "D1-OK", "role": "adjudicate", "disputed_paths": list(disputed)}
    spec = parse_task_role_spec(row, task_key="D1-OK")
    assert spec.disputed_paths == disputed

