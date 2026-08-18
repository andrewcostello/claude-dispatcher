"""W2-2-2 seals: the widening is caught wherever in the diff it arrives.

THE SUBJECT is ``role_protocol.check_branch``'s verdict over a WHOLE DIFF, and
the unfloored algebra it will reach through — ``branch_surface.build_surface``
and ``branch_surface.compare_surfaces``. It is deliberately NOT
``compare_signatures``: that function is per-file and it is CORRECT per-file, so
a row pinning its answer pins the thing that is not wrong.

MEASURED ON THIS TREE, 2026-08-18, through the real ``check_branch`` over real
git repositories — this is the defect, in one table::

    python      Wallet.debit widened in src/wallet.py        VIOLATION, 1 change
    python      the same class re-declared in wallet_v2.py   CLEAN,     0 changes
    typescript  Bet widened in web/src/bet.ts                VIOLATION, 1 change
    typescript  `declare module './bet'` in web/src/aug.ts   CLEAN,     0 changes
    go          Wallet.Debit widened in pkg/wallet/wallet.go VIOLATION, 1 change
    go          a new method on Wallet in pkg/wallet/credit.go CLEAN,   0 changes

Row 4 is the bypass. A branch that cannot widen a sealed interface in the file
that declares it widens it from a second file and is told CLEAN.

WHICH OF THOSE SIX ARE DEFECTS, AND WHICH ARE RULINGS. Only row 4. W2-2-1
measured the other two languages and ruled them in ``SURFACE_RULES``: Python has
no cross-file declaration space at all (a second module declaring ``Wallet``
declares a DIFFERENT symbol, and the substitution that makes that a bypass is a
call-site question, not a signature one), and Go shares a package but every
cross-file contribution to it is an ADDED key — ``Wallet.Credit`` keys as
``Wallet.Credit``, and re-declaring an existing key does not compile. So rows 2
and 6 are CLEAN today and must still be CLEAN after the fix; they are the
false-positive controls that stop row 4 being satisfied by an implementation
that merges every same-named symbol in the diff. See the Deviation note in this
task's summary: the commission asked for rows 2 and 6 in the same shape as row
4, and that shape contradicts the contract they would be sealing.

WHAT IS RED HERE, ON PURPOSE, AND UNTIL WHEN
--------------------------------------------
Nothing in this file skips, xfails, or is conditioned on a hole being filled.
Red is the answer; a seal that goes quiet when its subject is missing certifies
by not asking.

  * ``test_the_surface_algebra_answers_its_own_behaviour_table`` (15 rows) —
    RED until **W2-2-3** fills ``build_surface`` and ``compare_surfaces``.
  * ``test_the_widening_in_a_second_file_stops_being_zero_changes`` and
    ``test_the_branch_surface_algebra_is_reached_from_production`` — RED until
    **W2-2-5**, the operator row that transcribes
    ``docs/branch-surface-amendment.md`` into ``_compare_branch_signatures``.
    W2-2-3 alone does not green them: an algebra nothing calls decides nothing.

None of the red rows is a row about a NAME being absent. Each one drives an
input pair through the real surface and asserts the answer, so filling a hole
badly leaves it red — which is the trap this codebase measured and D8 P2
declined ("a row pinning a transient unimplementedness goes green when someone
adds the name and proves nothing about behaviour").

The exact node ids are in the summary, for ``config/known-red.yaml``.

WHAT THE RED ROWS FORCE, WHICH THE INHERITED PANEL FINDINGS SAID THEY MUST
--------------------------------------------------------------------------
Two HIGH findings against W2-2-1 say ``build_surface``'s specifier rule, read
literally, resolves nothing: ``attempted`` holds every candidate TRIED, ``_fold``
tries all six spellings per specifier, and "exactly one of
``specifier_candidates`` present in ``attempted``" is then never one.
``test_the_widening_in_a_second_file_stops_being_zero_changes`` is the row that
decides it — the flagship case, with ``bet.ts`` unchanged and therefore reached
only through the closure. It requires a widening to be REPORTED, so an
implementation that reads "present" as "attempted" (six-way ambiguous ⇒ unread ⇒
``RoleDiffError`` ⇒ UNDETERMINED) fails it. The ruling those findings ask for is
that resolution is by PRESENCE IN THE TREE; this file does not make that ruling,
it makes the wrong answer visible.

``test_the_two_spellings_of_one_module_share_a_namespace`` discharges the third
and fourth findings, on the ``.d.ts`` suffix order: ``_validate_rules``' second
anchor probes ``TYPESCRIPT_SUPPORT.extensions``, which is ``(".ts", ".tsx")``, so
it cannot see ``.d.ts`` move behind ``.ts``. That row probes the pair that
matters and is red under exactly the reorder the panel measured.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher.branch_surface import (
    SURFACE_BEHAVIOUR_ROWS,
    BehaviourRow,
    BranchSurfaceError,
    build_surface,
    compare_surfaces,
    surface_rule_for,
    ts_namespace_of,
)
from claude_dispatcher.call_site_contract import (
    CallGraph,
    Edge,
    EdgeKind,
    EntrypointKind,
    Root,
    RootKind,
    Symbol,
)
from claude_dispatcher.call_site_reachability import reachable_from
from claude_dispatcher.role_protocol import (
    TYPESCRIPT_SUPPORT,
    DiffVerdict,
    Language,
    Role,
    check_branch,
    ts_symbol_key,
)


# --------------------------------------------------------------------------- #
# The repositories. Real git, real refs, real `check_branch` — no seam patched.
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _write(repo: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _branch(
    tmp_path: Path, name: str, base: dict[str, str], head: dict[str, str]
) -> Path:
    """A repository whose ``main`` holds ``base`` and whose ``feat/x`` adds ``head``.

    ``head`` is applied ON TOP of ``base``, so a path absent from it is
    UNCHANGED and therefore absent from the three-dot diff — which is the whole
    point of the second-file rows: the sealed file is not in ``changed_paths``
    and only the closure read can reach it.
    """
    repo = tmp_path / name
    repo.mkdir(parents=True)
    _write(repo, base)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "seals@example.invalid")
    _git(repo, "config", "user.name", "W2-2-2 seals")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "the sealed base")
    _git(repo, "checkout", "-q", "-b", "feat/x")
    _write(repo, head)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "the branch")
    return repo


def _bodies(repo: Path):
    """``check_branch`` as the orchestrator and ``check_body_branch.sh`` call it."""
    return check_branch(repo, "main", "feat/x", Role.BODIES)


_PY_SEALED = "class Wallet:\n    def debit(self, amount):\n        return amount\n"
_PY_WIDENED = (
    "class Wallet:\n"
    "    def debit(self, amount, currency=None):\n"
    "        return amount\n"
)
_TS_SEALED = "export interface Bet {\n  id: string;\n}\n"
_TS_WIDENED = "export interface Bet {\n  id: string;\n  wager: number;\n}\n"
_GO_SEALED = (
    "package wallet\n\ntype Wallet struct{}\n\n"
    "func (w Wallet) Debit(a int) int { return a }\n"
)
_GO_WIDENED = (
    "package wallet\n\ntype Wallet struct{}\n\n"
    "func (w Wallet) Debit(a int, c string) int { return a }\n"
)

#: `declare module './bet'` — the module's own text calls this one "augment
#: another module outright". `export {};` is what makes the file an external
#: module; the relative specifier is what makes it provable
#: (`FileSurface.module_evidence`).
_TS_AUGMENTATION = (
    "export {};\n"
    "declare module './bet' {\n"
    "  interface Bet {\n"
    "    wager: number;\n"
    "  }\n"
    "}\n"
)

_SEALED_TS_PATH = "web/src/bet.ts"
_AUGMENTING_TS_PATH = "web/src/aug.ts"


# --------------------------------------------------------------------------- #
# 1. THE CONTROLS. Green today. A fix that reddens one has broken the gate it
#    was extending, and that is the whole reason they are here.
# --------------------------------------------------------------------------- #


_IN_PLACE: tuple[tuple[str, dict[str, str], dict[str, str], str, str], ...] = (
    (
        "python",
        {"src/wallet.py": _PY_SEALED},
        {"src/wallet.py": _PY_WIDENED},
        "src/wallet.py",
        "Wallet.debit",
    ),
    (
        "typescript",
        {_SEALED_TS_PATH: _TS_SEALED},
        {_SEALED_TS_PATH: _TS_WIDENED},
        _SEALED_TS_PATH,
        "i:Bet",
    ),
    (
        "go",
        {"pkg/wallet/wallet.go": _GO_SEALED},
        {"pkg/wallet/wallet.go": _GO_WIDENED},
        "pkg/wallet/wallet.go",
        "Wallet.Debit",
    ),
)


@pytest.mark.parametrize(
    "language,base,head,path,symbol",
    _IN_PLACE,
    ids=[row[0] for row in _IN_PLACE],
)
def test_the_in_place_widening_is_exactly_one_change(
    tmp_path: Path,
    language: str,
    base: dict[str, str],
    head: dict[str, str],
    path: str,
    symbol: str,
) -> None:
    """THE CONTROL, in all three enrolled languages. GREEN TODAY, must stay green.

    ``exactly one`` is the load-bearing word and it carries two failures at
    once. Fewer is the gate switched off. MORE is the branch-wide half
    re-reporting what the per-file loop already reported — the defect clause 2
    of ``compare_surfaces`` exists to prevent, and the one an implementation
    that merges first and diffs second produces silently.

    The symbol and the path are asserted because "one change" alone is met by a
    gate that found some other change in the same diff.

    Reddens under: the fold reporting the in-place edit a second time; the
    per-file loop losing this file; a merged fingerprint that no longer equals
    the single contribution it was built from (``merge_fingerprints``' own
    one-contribution property).
    """
    result = _bodies(_branch(tmp_path, f"inplace_{language}", base, head))

    assert result.verdict is DiffVerdict.VIOLATION, (
        f"{language}: an in-place widening of a sealed signature was not "
        f"refused: {result.verdict} — {result.detail}"
    )
    changes = list(result.signature.changes)
    assert len(changes) == 1, (
        f"{language}: expected exactly one change and got {len(changes)}: "
        f"{[(c.path, c.symbol) for c in changes]}. More than one means the "
        "branch-wide half is re-reporting what the per-file loop reported"
    )
    assert (changes[0].path, changes[0].symbol) == (path, symbol), (
        f"{language}: the one change names {(changes[0].path, changes[0].symbol)}, "
        f"not {(path, symbol)}"
    )
    assert changes[0].before != changes[0].after, (
        f"{language}: a change whose before and after are equal is not a change"
    )


# --------------------------------------------------------------------------- #
# 2. THE SUBJECT. RED until W2-2-5.
# --------------------------------------------------------------------------- #


def test_the_widening_in_a_second_file_stops_being_zero_changes(
    tmp_path: Path,
) -> None:
    """THE BYPASS. **RED at HEAD, and it is red for behaviour, not for a name.**

    ``web/src/bet.ts`` seals ``interface Bet``. The branch does not touch it.
    It adds ``web/src/aug.ts`` carrying ``declare module './bet' { interface Bet
    { wager: number } }``, which widens ``Bet`` for every importer in the
    program. Measured through the real ``check_branch`` on this tree:
    **CLEAN, 0 changes**. The same widening written into ``bet.ts`` is
    VIOLATION with 1 change (the ``typescript`` row of
    ``test_the_in_place_widening_is_exactly_one_change``), so the gate's answer
    is decided by which file the author put the text in.

    WHY THE SEALED FILE IS UNCHANGED, and it is not incidental: an unchanged
    path is not in the three-dot diff, so ``changed_paths`` is
    ``('web/src/aug.ts',)`` alone. The baseline for ``bet.ts`` can only be
    reached through ``closure_request`` -> ``specifier_candidates`` -> a read at
    the merge-base. A fix that only compares the paths git named cannot pass
    this row.

    WHAT IT ASSERTS BEYOND THE VERDICT, because "VIOLATION" alone is satisfied
    by any unrelated refusal:

      1. exactly ONE change — not a per-file report re-emitted, not two;
      2. its ``path`` is the AUGMENTING file, which is the file to edit. A
         report naming ``bet.ts`` sends the author to the file that is correct;
      3. its ``symbol`` is the SEALED file's namespace plus ``i:Bet``. A bare
         qualname is ambiguous once spaces merge, and a symbol carrying
         ``aug.ts``'s own namespace would mean the augmentation was routed to
         its own space, which is the routing bug the module's
         ``s:<specifier>`` rule exists to prevent;
      4. ``before`` is EXACTLY the sealed file's own fingerprint for ``i:Bet``,
         derived here by calling the shipped fingerprinter rather than typed
         out, so the baseline came from the merge-base and not from the branch;
      5. ``after`` contains BOTH contributions. A widening reported as a
         REPLACEMENT — ``after`` holding only the augmentation — would mean the
         merge dropped the sealed declaration, and clause 3 would then fire on
         a pure move as well.

    Reddens (that is, stays red) under: resolving ``'./bet'`` against the
    attempted set rather than the tree, which makes the specifier six-way
    ambiguous and the answer UNDETERMINED (the two inherited HIGH findings);
    reading only ``changed_paths``; raising ``RoleDiffError`` for the unread
    ``aug.ts`` space instead of routing the augmentation out of it.

    Greened by: W2-2-3 filling the five holes AND W2-2-5 transcribing
    ``docs/branch-surface-amendment.md``. Either alone leaves it red, and the
    reachability row below is what tells the two apart.
    """
    repo = _branch(
        tmp_path,
        "second_file",
        {_SEALED_TS_PATH: _TS_SEALED},
        {_AUGMENTING_TS_PATH: _TS_AUGMENTATION},
    )

    # The premise, measured rather than assumed: the sealed file is NOT in the
    # diff. Without this the row could pass on a gate that merely compares the
    # paths git named, and the reader could not tell.
    diff = _git(repo, "diff", "--name-only", "main...feat/x").split()
    assert diff == [_AUGMENTING_TS_PATH], (
        "the fixture put the sealed file in the diff, so this row no longer "
        f"measures the closure read at all: {diff}"
    )

    result = _bodies(repo)

    assert result.verdict is DiffVerdict.VIOLATION, (
        "a branch widened a sealed interface from a second file and was told "
        f"{result.verdict.value}: {result.detail}"
    )
    changes = list(result.signature.changes)
    assert len(changes) == 1, (
        f"expected exactly one branch-level widening, got {len(changes)}: "
        f"{[(c.path, c.symbol) for c in changes]}"
    )
    change = changes[0]

    assert change.path == _AUGMENTING_TS_PATH, (
        f"the widening is reported against {change.path!r}; the file to edit "
        f"is {_AUGMENTING_TS_PATH!r}, which is the one that introduced the "
        "contribution"
    )
    expected_symbol = (
        f"{ts_namespace_of(_SEALED_TS_PATH).label}::{ts_symbol_key((('i', 'Bet'),))}"
    )
    assert change.symbol == expected_symbol, (
        f"the widening is keyed {change.symbol!r}, not {expected_symbol!r}. "
        "The namespace must be the AUGMENTED module's, or the augmentation was "
        "routed into the augmenting file's own space"
    )

    sealed = TYPESCRIPT_SUPPORT.fingerprinter.fingerprints(
        _SEALED_TS_PATH, _TS_SEALED
    )
    augmenting = TYPESCRIPT_SUPPORT.fingerprinter.fingerprints(
        _AUGMENTING_TS_PATH, _TS_AUGMENTATION
    )
    contributed = [
        value
        for key, value in augmenting.items()
        if key.endswith(ts_symbol_key((("i", "Bet"),)))
    ]
    assert len(contributed) == 1, (
        "the fixture's augmenting file no longer contributes exactly one "
        f"`i:Bet` key, so the assertions below measure nothing: {augmenting}"
    )

    assert change.before == sealed["i:Bet"], (
        f"`before` is {change.before!r}; the sealed file's own fingerprint at "
        f"the merge-base is {sealed['i:Bet']!r}. A `before` that is neither is "
        "a baseline read at the wrong revision"
    )
    assert sealed["i:Bet"] in change.after, (
        f"`after` ({change.after!r}) has lost the sealed declaration, so the "
        "merge replaced the contribution instead of merging it"
    )
    assert contributed[0] in change.after, (
        f"`after` ({change.after!r}) does not carry the augmenting file's "
        "contribution, so nothing was merged in"
    )


# --------------------------------------------------------------------------- #
# 3. THE RULED BOUNDARIES. Green today AND after. They are what stop row 2
#    being satisfied by "every same-named symbol in the diff is one symbol".
# --------------------------------------------------------------------------- #


def test_a_second_python_module_redeclaring_a_class_is_not_a_widening(
    tmp_path: Path,
) -> None:
    """W2-2-1's Python ruling, held through the whole gate. GREEN, both sides.

    ``src/wallet_v2.py`` declares ``class Wallet`` with a widened ``debit``.
    That is NOT a branch-level widening and must never become one: a Python
    module is a file, so the second ``Wallet`` is a DIFFERENT symbol, and
    whether anything substitutes it for the first is a call-site question this
    gate does not answer. ``SURFACE_RULES`` is where that is ruled, and the row
    is asserted here too — a table row flipped to ``merges_across_files=True``
    would make this scenario a widening, and then the two halves of the seal
    disagree loudly instead of the gate quietly growing a false positive.

    THE COMMISSION ASKED FOR THE OPPOSITE and it is wrong; see the Deviation in
    this task's summary.

    Reddens under: routing Python declarations into any shared space; a
    ``build_surface`` that accepts a non-merging language instead of refusing
    it.
    """
    assert surface_rule_for(Language.PYTHON).merges_across_files is False, (
        "SURFACE_RULES now says Python merges declarations across files. "
        "Nothing in this repository measured that, and it makes every "
        "same-named class in a diff one symbol"
    )
    result = _bodies(
        _branch(
            tmp_path,
            "python_second",
            {"src/wallet.py": _PY_SEALED},
            {"src/wallet_v2.py": _PY_WIDENED},
        )
    )
    assert result.verdict is DiffVerdict.CLEAN, (
        "a second Python module declaring its own Wallet was refused as a "
        f"branch-level widening: {result.verdict} — {result.detail}"
    )
    assert not result.signature.changes, [
        (c.path, c.symbol) for c in result.signature.changes
    ]


def test_a_go_file_adding_a_method_is_an_added_key_not_a_widening(
    tmp_path: Path,
) -> None:
    """W2-2-1's Go ruling, held through the whole gate. GREEN, both sides.

    ``pkg/wallet/credit.go`` adds ``func (w Wallet) Credit`` to a type sealed in
    ``wallet.go``. Go shares the package, so this is the closest thing Go has to
    declaration merging — and it is still not one: the method keys as
    ``Wallet.Credit``, which is an ADDED key, and clause 1 ("an added symbol is
    not a change") is the ruled rule this unit may not reverse. Re-declaring an
    EXISTING key in a second file does not compile, so there is no Go program
    that expresses the bypass.

    Reddens under: clause 1 reversed; Go's ``SURFACE_RULES`` row flipped, which
    is asserted here so the two say the same thing or neither passes.
    """
    assert surface_rule_for(Language.GO).merges_across_files is False, (
        "SURFACE_RULES now says Go merges declarations across files; every "
        "cross-file contribution to a Go package is an ADDED key"
    )
    result = _bodies(
        _branch(
            tmp_path,
            "go_second",
            {"pkg/wallet/wallet.go": _GO_SEALED},
            {
                "pkg/wallet/credit.go": (
                    "package wallet\n\n"
                    "func (w Wallet) Credit(a int) int { return a }\n"
                )
            },
        )
    )
    assert result.verdict is DiffVerdict.CLEAN, (
        "a new Go method on an existing type was refused as a branch-level "
        f"widening: {result.verdict} — {result.detail}"
    )
    assert not result.signature.changes, [
        (c.path, c.symbol) for c in result.signature.changes
    ]


def test_a_second_typescript_module_declaring_the_same_name_is_not_a_merge(
    tmp_path: Path,
) -> None:
    """The false-positive control for the row above it. GREEN, both sides.

    ``web/src/extra.ts`` declares its own ``export interface Bet`` and never
    names ``bet.ts``. TypeScript merges declarations WITHIN one declaration
    space, and two external modules are two spaces — this ``Bet`` is a different
    type, and nothing about ``bet.ts``'s ``Bet`` changed.

    This is the row that separates "the fold resolves the augmentation" from
    "the fold treats every same-named symbol in the diff as one symbol". The
    two files differ from
    ``test_the_widening_in_a_second_file_stops_being_zero_changes`` in one
    respect only — a ``declare module './bet'`` wrapper — so an implementation
    that keys on the qualname alone passes that row and fails this one.

    The commission named this shape ("`interface Bet { newField: string }` in an
    importing file") as a second expression of the bypass. Measured: it is not
    one. See the Deviation in this task's summary.
    """
    result = _bodies(
        _branch(
            tmp_path,
            "ts_shadow",
            {_SEALED_TS_PATH: _TS_SEALED},
            {
                "web/src/extra.ts": (
                    "export interface Bet {\n  wager: number;\n}\n"
                    "export const use = (b: Bet) => b;\n"
                )
            },
        )
    )
    assert result.verdict is DiffVerdict.CLEAN, (
        "a second TypeScript module declaring its own Bet was reported as a "
        f"widening of another module's: {result.verdict} — {result.detail}"
    )
    assert not result.signature.changes, [
        (c.path, c.symbol) for c in result.signature.changes
    ]


def test_the_two_spellings_of_one_module_share_a_namespace() -> None:
    """``w.d.ts`` and ``w.ts`` are ONE module to every importer. GREEN TODAY.

    ``_validate_rules``' second anchor is documented as "what catches a table
    reordered so ``.ts`` shadows ``.d.ts``" and it does not: it probes
    ``TYPESCRIPT_SUPPORT.extensions``, which is ``(".ts", ".tsx")``, and
    ``.d.ts`` is not an enrolled extension, so neither probe discriminates the
    order. Both inherited HIGH findings on that anchor are correct, and this row
    is the probe they are missing — it asserts the PROPERTY the anchor claims,
    over the pair that carries it.

    The consequence of the reorder is not cosmetic: with ``.ts`` stripped first,
    ``w.d.ts`` lands in namespace ``w.d`` and ``w.ts`` in ``w``, so a
    declaration sealed in one and widened in the other are in different spaces
    and the gate reports nothing.

    Reddens under: ``TS_NAMESPACE_SUFFIXES`` reordered so ``.ts`` precedes
    ``.d.ts`` — measured to leave ``_validate_rules`` passing.
    """
    assert ts_namespace_of("web/src/w.d.ts") == ts_namespace_of("web/src/w.ts"), (
        "web/src/w.d.ts and web/src/w.ts are in different namespaces, so a "
        "declaration sealed in one and widened in the other is invisible to "
        "the fold. TS_NAMESPACE_SUFFIXES must strip .d.ts before .ts"
    )
    assert ts_namespace_of("web/src/w.d.ts").name == "web/src/w", (
        ts_namespace_of("web/src/w.d.ts").name
    )


# --------------------------------------------------------------------------- #
# 4. THE ALGEBRA. `build_surface` + `compare_surfaces`, driven from the
#    scaffold's own input table. RED until W2-2-3.
# --------------------------------------------------------------------------- #


#: The table's shape, TRANSCRIBED — `(name, is_control, changes, unread,
#: refused)`. Neither side of the equality below is derived from the other, so a
#: row deleted from `SURFACE_BEHAVIOUR_ROWS` shrinks the derived side alone and
#: a row whose expectation is quietly emptied changes its counts. Without it the
#: parametrised rows below are satisfied by a table someone gutted.
_TABLE_SHAPE: tuple[tuple[str, bool, int, int, bool], ...] = (
    ("in-place widening stays the per-file loop's, reported once", True, 0, 0, False),
    ("a new file augmenting a sealed interface is one widening", False, 1, 0, False),
    ("an augmentation added to a file that already existed", False, 1, 0, False),
    ("an unchanged augmentation is not a widening a second time", True, 0, 0, False),
    ("an added key is not a change (clause 1, held in isolation)", True, 0, 0, False),
    ("declare global leaves a space nothing can enumerate", False, 0, 1, False),
    ("a bare specifier is unread, and keyed by the specifier", False, 0, 1, False),
    ("./sub with sub.ts and sub/index.ts both present is unread", False, 0, 1, False),
    ("a second SCRIPT declaring the same interface is not two files", False, 0, 1, False),
    (
        "a file the caller KNOWS is a script declares into the global space",
        False,
        0,
        1,
        False,
    ),
    (
        "an ordinary exported interface is NOT proof, and costs UNDETERMINED",
        False,
        0,
        1,
        False,
    ),
    ("an export surface is proof of module-ness with nothing reported", True, 0, 0, False),
    ("a base file nobody attempted leaves its space unread", False, 0, 1, False),
    ("python does not merge: a second module is refused, not compared", False, 0, 0, True),
    ("go does not merge: a new file's method is an added key", False, 0, 0, True),
)


def test_the_behaviour_table_has_not_been_gutted() -> None:
    """The two-way pin on ``SURFACE_BEHAVIOUR_ROWS``. GREEN TODAY.

    The rows below are parametrised over a table that lives in the module they
    judge, which is only sound while the table cannot shrink unnoticed. A row
    deleted, renamed, or emptied of its expectation reddens here; a row ADDED
    reddens here too, so a new behaviour arrives with a reviewer looking at it.

    It also refuses the degenerate shapes the whole table could decay into: a
    table where nothing expects a change is satisfied by an algebra that finds
    nothing, and one where nothing expects a clean answer is satisfied by one
    that refuses everything.
    """
    derived = tuple(
        (row.name, row.is_control, len(row.changes), len(row.unread), row.refused)
        for row in SURFACE_BEHAVIOUR_ROWS
    )
    assert derived == _TABLE_SHAPE, (
        "SURFACE_BEHAVIOUR_ROWS no longer matches the transcribed shape. A row "
        "added here needs a line in _TABLE_SHAPE and a reviewer; a row removed "
        "took a sealed behaviour with it.\n"
        f"derived : {derived}\nwritten : {_TABLE_SHAPE}"
    )
    assert any(row.changes for row in SURFACE_BEHAVIOUR_ROWS), (
        "no row expects a change; an algebra that reports nothing passes them all"
    )
    assert any(
        not row.changes and not row.unread and not row.refused
        for row in SURFACE_BEHAVIOUR_ROWS
    ), "no row expects a clean answer; an algebra that refuses everything passes"


@pytest.mark.parametrize(
    "row", SURFACE_BEHAVIOUR_ROWS, ids=[row.name for row in SURFACE_BEHAVIOUR_ROWS]
)
def test_the_surface_algebra_answers_its_own_behaviour_table(
    row: BehaviourRow,
) -> None:
    """``build_surface`` and ``compare_surfaces``, in the shape the scaffold
    specified. **RED at HEAD: both are holes.** Green at W2-2-3.

    The seal the scaffold wrote its table for, verbatim from
    ``BehaviourRow``'s own contract::

        base = build_surface(row.base, attempted=set(row.base_attempted))
        head = build_surface(row.head, attempted=set(row.head_attempted))
        got  = compare_surfaces(base, head)

    Asserted FIELD-FOR-FIELD, not by label: ``ExpectedChange`` carries the
    merged fingerprints and the introducing paths because those are the part a
    wrong implementation gets wrong while still naming the right key. A row
    asserting labels alone passes an algebra that merged the wrong
    contributions.

    ``refused`` rows assert ``BranchSurfaceError`` out of ``build_surface``
    itself — a language that does not merge must be refused at construction,
    not compared and found equal, because a space that could never be proven
    read is a gate that decides nothing while costing something.
    """
    if row.refused:
        with pytest.raises(BranchSurfaceError):
            head = build_surface(row.head, attempted=set(row.head_attempted))
            # Reached only if `build_surface` accepted the non-merging file; the
            # comparison is here so a refusal deferred to `compare_surfaces`
            # still counts, and an implementation that refuses NOWHERE fails.
            compare_surfaces(
                build_surface(row.base, attempted=set(row.base_attempted)), head
            )
        return

    base = build_surface(row.base, attempted=set(row.base_attempted))
    head = build_surface(row.head, attempted=set(row.head_attempted))
    got = compare_surfaces(base, head)

    assert tuple(
        (
            change.key.label,
            change.before,
            change.after,
            tuple(change.introduced_by),
        )
        for change in got.changes
    ) == tuple(
        (expected.key, expected.before, expected.after, expected.introduced_by)
        for expected in row.changes
    ), f"{row.name}: changes"

    assert tuple(
        (unread.namespace.label, unread.reason) for unread in got.unread
    ) == tuple(
        (expected.namespace, expected.reason) for expected in row.unread
    ), f"{row.name}: unread"

    if row.is_control:
        assert got.clean, (
            f"{row.name}: a CONTROL row is not clean. A change that reddens a "
            "control has broken the gate it was extending"
        )


# --------------------------------------------------------------------------- #
# 5. REACHABILITY. D-69's lesson: a correct module nothing calls is dark.
#    RED until W2-2-5.
# --------------------------------------------------------------------------- #


_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "claude_dispatcher"

#: The two production entrypoints that reach the diff-time gate, derived from
#: the files that declare them: `pyproject.toml [project.scripts] dispatcher`,
#: and the `if __name__ == "__main__":` guard `scripts/check_body_branch.sh`
#: runs as `python -P -m claude_dispatcher.role_protocol`.
_PRODUCTION_ENTRYPOINTS: tuple[tuple[str, EntrypointKind, str], ...] = (
    (
        "claude_dispatcher.cli.main",
        EntrypointKind.PYTHON_CONSOLE_SCRIPT,
        "pyproject.toml [project.scripts] dispatcher = claude_dispatcher.cli:main",
    ),
    (
        "claude_dispatcher.role_protocol.main",
        EntrypointKind.PYTHON_MODULE_MAIN,
        "src/claude_dispatcher/role_protocol.py `if __name__ == \"__main__\"`, "
        "run by scripts/check_body_branch.sh",
    ),
)

#: The already-wired D7 gate. The LENS CONTROL: it is reached through exactly
#: the shape W2-2-5's patch adds — a function-local aliased `from . import x`
#: plus an attribute call — so if the analyzer cannot see it, the analyzer is
#: blind and the dark list below means nothing.
_WIRED_CONTROL = "claude_dispatcher.branch_reachability.check_branch_reachability"

#: What must be reached once the fold is wired. `fold_branch_signatures` alone
#: is not enough: a fold that runs and never builds or compares a surface is
#: the same dark module wearing a call site.
_SUBJECTS: tuple[str, ...] = (
    "claude_dispatcher.branch_surface.fold_branch_signatures",
    "claude_dispatcher.branch_surface._fold",
    "claude_dispatcher.branch_surface.build_surface",
    "claude_dispatcher.branch_surface.compare_surfaces",
    "claude_dispatcher.branch_surface.closure_request",
)


def _in_package_aliases(node: ast.AST, known: frozenset[str]) -> dict[str, str]:
    """Local name -> in-package module, for every import under ``node``.

    Keyed by the AS-NAME because that is what the call site spells;
    ``role_protocol`` imports its siblings function-locally and under aliases
    (``from . import branch_surface as _branch_surface``), and a mapping keyed
    by the real name would miss every one of them.
    """
    found: dict[str, str] = {}
    for child in ast.walk(node):
        if isinstance(child, ast.ImportFrom):
            named = (
                child.names
                if (child.level == 1 and child.module is None)
                or (child.level == 0 and child.module == "claude_dispatcher")
                else ()
            )
            for alias in named:
                if alias.name in known:
                    found[alias.asname or alias.name] = alias.name
        elif isinstance(child, ast.Import):
            for alias in child.names:
                if not alias.name.startswith("claude_dispatcher."):
                    continue
                module = alias.name.split(".")[1]
                if module in known:
                    found[alias.asname or alias.name] = module
    return found


def _package_call_graph() -> CallGraph:
    """The package's module-level call graph, by AST, in the enrolled shape.

    Deliberately NARROW and deliberately not an analyzer enrolment: nodes are
    module-level functions, edges are same-module ``name(...)`` calls and
    ``alias.name(...)`` calls through an in-package import. It under-approximates
    — a call through a class, a partial or a registry is not an edge — which is
    the safe direction for a row that asserts something IS reached, and the
    reason ``_WIRED_CONTROL`` is judged in the same call.

    ``unresolved_calls`` is populated because the contract names it "THE
    non-vacuity field of the graph": a graph reporting zero of them is an
    analyzer that is not counting.
    """
    known = frozenset(
        path.stem for path in _PACKAGE.glob("*.py") if path.stem != "__init__"
    )
    trees: dict[str, ast.Module] = {}
    functions: dict[str, dict[str, ast.stmt]] = {}
    symbols: dict[str, Symbol] = {}
    for module in sorted(known):
        tree = ast.parse(
            (_PACKAGE / f"{module}.py").read_text(encoding="utf-8"),
            filename=f"{module}.py",
        )
        trees[module] = tree
        functions[module] = {}
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions[module][stmt.name] = stmt
                key = f"claude_dispatcher.{module}.{stmt.name}"
                symbols[key] = Symbol(
                    key, f"src/claude_dispatcher/{module}.py", stmt.lineno
                )

    edges: list[Edge] = []
    unresolved: list[tuple[Symbol, str, str]] = []
    for module in sorted(known):
        module_aliases = _in_package_aliases(trees[module], known)
        for name, node in functions[module].items():
            caller = symbols[f"claude_dispatcher.{module}.{name}"]
            aliases = {**module_aliases, **_in_package_aliases(node, known)}
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                site = f"src/claude_dispatcher/{module}.py:{call.lineno}"
                func = call.func
                target: str | None = None
                if isinstance(func, ast.Name) and func.id in functions[module]:
                    target = f"claude_dispatcher.{module}.{func.id}"
                elif isinstance(func, ast.Attribute) and isinstance(
                    func.value, ast.Name
                ):
                    reached = aliases.get(func.value.id)
                    if reached and func.attr in functions.get(reached, {}):
                        target = f"claude_dispatcher.{reached}.{func.attr}"
                if target is None:
                    unresolved.append(
                        (caller, site, "not an in-package module-level function")
                    )
                    continue
                edges.append(
                    Edge(caller, symbols[target], EdgeKind.DIRECT, site)
                )
    return CallGraph(
        symbols=symbols,
        edges=tuple(edges),
        unresolved_calls=tuple(unresolved),
        unreadable_paths=(),
    )


def test_the_branch_surface_algebra_is_reached_from_production() -> None:
    """D-69, held before it is paid for. **RED at HEAD: the module is dark.**

    Every other row in this file proves that the surface algebra BEHAVES. Not
    one of them proves anything RUNS it, and a correct-but-unwired module passes
    all of them — "the money net is dark", which is the failure this unit would
    otherwise ship. ``branch_surface`` is unfloored, fully contracted and
    imported by nothing on the gate path today.

    Derived, not asserted: the call graph is read out of the package's own
    source by AST and the reach is computed by the enrolled
    ``call_site_reachability.reachable_from`` over the enrolled
    ``CallGraph``/``Root``/``Symbol`` types, from the two PRODUCTION
    entrypoints that reach the diff-time gate. No monkeypatch, nothing
    hand-listed except the entrypoints and the subjects.

    THE LENS CONTROL, in this same call and before the subjects are looked at:
    ``branch_reachability.check_branch_reachability`` — the D7 gate wired at
    ``check_branch`` step 6 — must come back reachable. It is reached through
    exactly the shape W2-2-5 adds (a function-local aliased ``from . import``
    and an attribute call), so a green control means the analyzer can see that
    shape and a dark subject is a fact about the wiring rather than about this
    row. Without it, deleting the analyzer's attribute-call arm would leave the
    subjects dark and the row would read as a correct red.

    Greened by W2-2-3 AND W2-2-5, and the dark list is what tells them apart —
    measured by applying the amendment's edit 1 to this tree with the holes
    still unfilled: ``fold_branch_signatures`` leaves the dark list and the
    other four stay in it, because a hole that raises calls nothing. So "the
    module is not wired" and "the module is wired and its own procedure never
    reaches the algebra" are two different failure messages from this one row,
    which is the distinction D-69 did not have.

    Reddens under: the amendment's edit 1 reverted; the call moved behind a
    condition that drops it; ``_fold`` filled so that it never calls
    ``build_surface`` or ``compare_surfaces``.
    """
    graph = _package_call_graph()
    assert graph.unresolved_calls, (
        "the analyzer resolved every call site in the package, which means it "
        "is not counting; an over-resolved graph can only over-report reach"
    )

    roots = []
    for key, kind, evidence in _PRODUCTION_ENTRYPOINTS:
        assert key in graph.symbols, (
            f"the production entrypoint {key!r} is not a module-level function "
            "of this package any more; the traversal below would start nowhere"
        )
        roots.append(Root(graph.symbols[key], kind, RootKind.PRODUCTION, evidence))

    reach = reachable_from(graph, roots)

    assert _WIRED_CONTROL in reach, (
        f"the analyzer cannot reach {_WIRED_CONTROL!r}, which check_branch has "
        "called since the D7 wiring landed. It is blind to the call shape "
        "W2-2-5 adds, so every claim below is vacuous"
    )

    for key in _SUBJECTS:
        assert key in graph.symbols, (
            f"{key!r} is not a module-level function of branch_surface. This "
            "row judges the WIRING; a renamed or deleted subject needs a "
            "reviewer, not a silent pass"
        )
    dark = [key for key in _SUBJECTS if key not in reach]
    assert not dark, (
        "no production entrypoint reaches these, so the branch-wide half of "
        "the signature gate does not run and the second-file widening is "
        f"CLEAN in production however correct the algebra is: {dark}. "
        "Wire it per docs/branch-surface-amendment.md (task W2-2-5)"
    )
