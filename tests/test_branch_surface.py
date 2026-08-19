"""W2-2-2 seals: the widening is caught wherever in the diff it arrives.

THE SUBJECT is ``role_protocol.check_branch``'s verdict over a WHOLE DIFF and
the algebra it will reach through — ``branch_surface``'s ``build_surface``,
``compare_surfaces``, ``closure_request`` and ``fold_branch_signatures``. It is
deliberately NOT ``compare_signatures``: that function is per-file and correct
per-file, so a row pinning its answer pins the thing that is not wrong.

The defect, measured on this tree through the real ``check_branch``: the same
widening is VIOLATION when it is written into the file that seals the
interface and CLEAN when it arrives from a second file. Rows 2 and 6 of the
table in this file's commit message — a second Python module and a second Go
file — are W2-2-1's RULINGS and not defects, so they are here as
false-positive controls.

RED ROWS ARE THE ANSWER HERE, not an accident. Nothing skips, xfails, or is
conditioned on a hole being filled: a seal that goes quiet when its subject is
missing certifies by not asking. No red row asserts merely that a NAME exists
— each drives an input pair through the real surface and asserts the answer,
so filling a hole badly leaves it red. Which rows, and until which task, is in
this task's summary, for ``config/known-red.yaml``.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import tomllib
from collections.abc import Iterator, Sequence
from pathlib import Path

import pytest

from claude_dispatcher.branch_surface import (
    CLEAN_FOLD,
    MAX_CLOSURE_READS,
    SURFACE_BEHAVIOUR_ROWS,
    BranchFold,
    BranchSurfaceError,
    FileSurface,
    UnreadReason,
    _unenumerated,
    build_surface,
    closure_request,
    compare_surfaces,
    fold_branch_signatures,
    specifier_candidates,
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
    RoleDiffError,
    SignatureCheckStatus,
    check_branch,
    ts_symbol_key,
)

_REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# The repositories. Real git, real refs, real `check_branch` — no seam patched.
# --------------------------------------------------------------------------- #


#: The ambient git configuration these fixtures must not inherit. Both
#: ``GIT_CONFIG_*`` variables pointed at the null device delete a developer's
#: or a CI image's whole configuration from every ``_git`` call —
#: ``core.hooksPath``, ``commit.template`` and ``commit.gpgsign`` alike — and an
#: empty ``GIT_TEMPLATE_DIR`` stops ``git init`` copying a template's hooks in.
#: Naming them one at a time left the rest in play, which is the same
#: ambient-fault class over again.
#:
#: ``check_branch``'s own git calls still run under the caller's environment.
#: They are reads — ``rev-parse``, ``diff``, ``show`` — which fire no hook and
#: consult no commit template, so the fixture half is the whole exposure.
_ISOLATED_GIT: dict[str, str] = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TEMPLATE_DIR": "",
    "GIT_TERMINAL_PROMPT": "0",
}


def _git(repo: Path, *args: str) -> str:
    """git, with the ambient faults that are not this gate ruled out.

    ``timeout`` because a hung git must fail the row rather than the session;
    :data:`_ISOLATED_GIT` because a row here must fail for what it measures.
    """
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, **_ISOLATED_GIT},
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


def _assert_read(result, language: str) -> None:
    """The comparator RAN. Without it every CLEAN row below is satisfied by a
    gate that read nothing.

    Measured cost of not asserting it: ``ts_signature_fingerprint/typescript.js``
    is gitignored and absent from every fresh worktree here, and the whole
    TypeScript half of this file then passes as UNCHECKED_COMPARATOR_UNAVAILABLE
    — a green suite over a gate that never looked at a TypeScript file.
    """
    assert result.signature is not None, f"{language}: no signature was computed"
    assert result.signature.status is SignatureCheckStatus.CHECKED, (
        f"{language}: the signature gate did not read this diff "
        f"({result.signature.status}: {result.signature.detail}). Every "
        "assertion about what it found is vacuous until it has"
    )
    assert not result.signature.unsupported_paths, (
        f"{language}: paths nobody could read: "
        f"{result.signature.unsupported_paths}"
    )


_PY_SEALED = "class Wallet:\n    def debit(self, amount):\n        return amount\n"
_PY_WIDENED = (
    "class Wallet:\n"
    "    def debit(self, amount, currency=None):\n"
    "        return amount\n"
)
_PY_NEIGHBOUR = "class Ledger:\n    def note(self, entry):\n        return entry\n"

_TS_SEALED = "export interface Bet {\n  id: string;\n}\n"
_TS_WIDENED = "export interface Bet {\n  id: string;\n  wager: number;\n}\n"
_TS_NEIGHBOUR = "export interface Ledger {\n  id: string;\n}\n"

_GO_SEALED = (
    "package wallet\n\ntype Wallet struct{}\n\n"
    "func (w Wallet) Debit(a int) int { return a }\n"
)
_GO_WIDENED = (
    "package wallet\n\ntype Wallet struct{}\n\n"
    "func (w Wallet) Debit(a int, c string) int { return a }\n"
)
_GO_NEIGHBOUR = (
    "package wallet\n\ntype Ledger struct{}\n\n"
    "func (l Ledger) Note(a int) int { return a }\n"
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

    Reddens under: the fold reporting the in-place edit a second time; the
    per-file loop losing this file; a merged fingerprint that no longer equals
    the single contribution it was built from (``merge_fingerprints``' own
    one-contribution property).
    """
    result = _bodies(_branch(tmp_path, f"inplace_{language}", base, head))
    _assert_read(result, language)

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
    VIOLATION with 1 change, so the gate's answer is decided by which file the
    author put the text in.

    WHY THE SEALED FILE IS UNCHANGED, and it is not incidental: an unchanged
    path is not in the three-dot diff, so ``changed_paths`` is
    ``('web/src/aug.ts',)`` alone. The baseline for ``bet.ts`` can only be
    reached through ``closure_request`` -> ``specifier_candidates`` -> a read at
    the merge-base. A fix that only compares the paths git named cannot pass
    this row.

    WHAT IT ASSERTS BEYOND THE VERDICT, because "VIOLATION" alone is satisfied
    by any unrelated refusal:

      1. exactly ONE change — not a per-file report re-emitted, not two;
      2. its ``path`` is the AUGMENTING file, which is the file to edit;
      3. its ``symbol`` is the SEALED file's namespace plus ``i:Bet``. A symbol
         carrying ``aug.ts``'s own namespace would mean the augmentation was
         routed to its own space, which is the routing bug the module's
         ``s:<specifier>`` rule exists to prevent;
      4. ``before`` is EXACTLY the sealed file's own fingerprint for ``i:Bet``,
         derived here by calling the shipped fingerprinter rather than typed
         out, so the baseline came from the merge-base and not from the branch;
      5. ``after`` contains BOTH contributions. A widening reported as a
         REPLACEMENT would mean the merge dropped the sealed declaration, and
         ``compare_surfaces`` clause 3 would then fire on a pure move as well.

    Stays red under: resolving ``'./bet'`` against the attempted set rather
    than the tree, which makes the specifier six-way ambiguous and the answer
    UNDETERMINED (two inherited HIGH findings against W2-2-1); reading only
    ``changed_paths``; raising ``RoleDiffError`` for the unread ``aug.ts``
    space instead of routing the augmentation out of it.

    Greened by W2-2-3 filling the algebra AND W2-2-5 wiring it. Either alone
    leaves it red, and the reachability row below is what tells the two apart.
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
    _assert_read(result, "typescript")

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
# 3. THE RULED BOUNDARIES. Green today AND after. They are what stop the row
#    above being satisfied by "every same-named symbol in the diff is one
#    symbol".
#
#    THE SECOND FILE EXISTS AT THE MERGE-BASE in all three, and that is not
#    dressing: a file the branch ADDS has no base revision, so the per-file
#    loop skips it and these rows would be green through the new-file skip
#    rather than through SURFACE_RULES — green for the same reason the bypass
#    above is green, which is no evidence at all. With the file present at
#    both revisions a comparator runs on it, and `_assert_read` says so.
# --------------------------------------------------------------------------- #


def test_a_second_python_module_redeclaring_a_class_is_not_a_widening(
    tmp_path: Path,
) -> None:
    """W2-2-1's Python ruling, held through the whole gate. GREEN, both sides.

    ``src/wallet_v2.py`` grows a ``class Wallet`` with a widened ``debit``.
    That is NOT a branch-level widening and must never become one: a Python
    module is a file, so the second ``Wallet`` is a DIFFERENT symbol, and
    whether anything substitutes it for the first is a call-site question this
    gate does not answer.

    The commission asked for Python modules to merge declarations (like
    TypeScript's declaration merging), but measurement showed that is wrong —
    Python's module boundaries are namespace boundaries, and any same-named
    symbol in a different module is a different type entirely.

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
            {"src/wallet.py": _PY_SEALED, "src/wallet_v2.py": _PY_NEIGHBOUR},
            {"src/wallet_v2.py": _PY_NEIGHBOUR + _PY_WIDENED},
        )
    )
    _assert_read(result, "python")
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

    ``pkg/wallet/credit.go`` grows a ``func (w Wallet) Credit`` on a type
    sealed in ``wallet.go``. Go shares the package, so this is the closest
    thing Go has to declaration merging — and it is still not one: the method
    keys as ``Wallet.Credit``, which is an ADDED key, and clause 1 ("an added
    symbol is not a change") is the ruled rule this unit may not reverse.
    Re-declaring an EXISTING key in a second file does not compile, so there is
    no Go program that expresses the bypass.

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
            {
                "pkg/wallet/wallet.go": _GO_SEALED,
                "pkg/wallet/credit.go": _GO_NEIGHBOUR,
            },
            {
                "pkg/wallet/credit.go": (
                    _GO_NEIGHBOUR
                    + "\nfunc (w Wallet) Credit(a int) int { return a }\n"
                )
            },
        )
    )
    _assert_read(result, "go")
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
    """The false-positive control for the bypass row. GREEN, both sides.

    ``web/src/extra.ts`` grows its own ``export interface Bet`` and never names
    ``bet.ts``. TypeScript merges declarations WITHIN one declaration space,
    and two external modules are two spaces — this ``Bet`` is a different type,
    and nothing about ``bet.ts``'s ``Bet`` changed.

    This is the row that separates "the fold resolves the augmentation" from
    "the fold treats every same-named symbol in the diff as one symbol". It
    differs from ``test_the_widening_in_a_second_file_stops_being_zero_changes``
    in one respect only — a ``declare module './bet'`` wrapper — so an
    implementation that keys on the qualname alone passes that row and fails
    this one.

    The commission named "`interface Bet { newField: string }` in an importing
    file" as a second expression of the bypass (a way to widen an exported
    type). Measured on this tree: it is not. A non-ambient interface in a
    separate module is a separate type, and the bypass (the one widening
    captured by ``declare module``) is the only way to widen an exported type
    from outside its module.
    """
    result = _bodies(
        _branch(
            tmp_path,
            "ts_shadow",
            {_SEALED_TS_PATH: _TS_SEALED, "web/src/extra.ts": _TS_NEIGHBOUR},
            {
                "web/src/extra.ts": (
                    _TS_NEIGHBOUR
                    + "export interface Bet {\n  wager: number;\n}\n"
                    + "export const use = (b: Bet) => b;\n"
                )
            },
        )
    )
    _assert_read(result, "typescript")
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

    The consequence of the reorder is not cosmetic: with ``.ts`` stripped
    first, ``w.d.ts`` lands in namespace ``w.d`` and ``w.ts`` in ``w``, so a
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
# 4. THE ALGEBRA. `build_surface` + `compare_surfaces`. RED until W2-2-3.
#
#    THE TABLE BELOW IS A FROZEN COPY of `SURFACE_BEHAVIOUR_ROWS`, and it was
#    produced BY PRINTING that tuple rather than re-derived by hand. Saying so
#    is the point: what a copy can and cannot seal follows from it.
#
#      * It CAN stop the answers moving. These rows, not the module's, are the
#        input to every algebra row below, so W2-2-3 — who owns the module —
#        cannot get the merge wrong and edit `after` to match. The two literals
#        then disagree and `test_the_behaviour_table_matches_its_transcription`
#        reddens with a reviewer instead of agreeing quietly on a weakened
#        answer.
#      * It CANNOT say those answers were right to begin with. A copy inherits
#        an error in the scaffold's own expectations in silence.
#
#    So the copy is not the whole seal, and section 4b is the rest of it: four
#    rows whose fixtures AND answers are derived here from the three clauses
#    and from `merge_fingerprints`' stated properties, over shapes this table
#    does not contain at all.
#
#    Shape, per row:
#      (name, is_control, refused,
#       base files, base_attempted, head files, head_attempted,
#       expected changes, expected unread)
#    where a file is (path, language, is_module, ((key, fingerprint), ...)),
#    a change is (key label, before, after, introduced_by) and an unread is
#    (namespace label, reason value).
# --------------------------------------------------------------------------- #


_File = tuple[str, str, bool | None, tuple[tuple[str, str], ...]]
_Transcribed = tuple[
    str,
    bool,
    bool,
    tuple[_File, ...],
    tuple[str, ...],
    tuple[_File, ...],
    tuple[str, ...],
    tuple[tuple[str, str, str, tuple[str, ...]], ...],
    tuple[tuple[str, str], ...],
]

_TABLE: tuple[_Transcribed, ...] = (("in-place widening stays the per-file loop's, reported once",
      True,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A2'),)),),
      ('web/src/a.ts',),
      (),
      ()),
     ('a new file augmenting a sealed interface is one widening',
      False,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts',
        'typescript',
        True,
        (('s:.\\/a/i:Bet', 'B'), ('s:.\\/a/i:Bet/i:x', 'F')))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (('typescript:web/src/a::i:Bet', 'A', 'A + B', ('web/src/b.ts',)),),
      ()),
     ('an augmentation added to a file that already existed',
      False,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', True, (('k:export/i:run', 'E'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts',
        'typescript',
        True,
        (('k:export/i:run', 'E'), ('s:.\\/a/i:Bet', 'B')))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (('typescript:web/src/a::i:Bet', 'A', 'A + B', ('web/src/b.ts',)),),
      ()),
     ('an unchanged augmentation is not a widening a second time',
      True,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', True, (('s:.\\/a/i:Bet', 'B'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', True, (('s:.\\/a/i:Bet', 'B'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (),
      ()),
     ('an added key is not a change (clause 1, held in isolation)',
      True,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts',
        'typescript',
        True,
        (('i:Bet', 'A'), ('i:Bet/i:x', 'F'))),),
      ('web/src/a.ts',),
      (),
      ()),
     ('declare global leaves a space nothing can enumerate',
      False,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', True, (('k:global/i:S', 'G'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (),
      (('typescript:<global>', 'not_enumerable'),)),
     ('a bare specifier is unread, and keyed by the specifier',
      False,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', True, (('s:lodash/i:X', 'L'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (),
      (('typescript:<unresolved lodash>', 'unresolved_specifier'),)),
     ('./sub with sub.ts and sub/index.ts both present is unread',
      False,
      False,
      (('web/src/sub.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/sub/index.ts', 'typescript', True, (('i:Bet', 'I'),))),
      ('web/src/sub.ts', 'web/src/sub/index.ts'),
      (('web/src/sub.ts', 'typescript', True, (('i:Bet', 'A'),)),
       ('web/src/sub/index.ts', 'typescript', True, (('i:Bet', 'I'),)),
       ('web/src/b.ts', 'typescript', True, (('s:.\\/sub/i:Bet', 'B'),))),
      ('web/src/sub.ts', 'web/src/sub/index.ts', 'web/src/b.ts'),
      (),
      (('typescript:<unresolved ./sub>', 'unresolved_specifier'),)),
     ('a second SCRIPT declaring the same interface is not two files',
      False,
      False,
      (('web/src/a.ts', 'typescript', None, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', None, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', None, (('i:Bet/i:x', 'F'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (),
      (('typescript:<global>', 'module_ness_unreported'),)),
     ('a file the caller KNOWS is a script declares into the global space',
      False,
      False,
      (('web/src/a.ts', 'typescript', False, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts', 'typescript', False, (('i:Bet', 'A'),)),
       ('web/src/b.ts', 'typescript', False, (('i:Bet', 'B'),))),
      ('web/src/a.ts', 'web/src/b.ts'),
      (),
      (('typescript:<global>', 'not_enumerable'),)),
     ('an ordinary exported interface is NOT proof, and costs '
      'UNDETERMINED',
      False,
      False,
      (('web/src/a.ts',
        'typescript',
        None,
        (('i:Bet', '[export]interface'),)),),
      ('web/src/a.ts',),
      (('web/src/a.ts',
        'typescript',
        None,
        (('i:Bet', '[export]interface2'),)),),
      ('web/src/a.ts',),
      (),
      (('typescript:<global>', 'module_ness_unreported'),)),
     ('an export surface is proof of module-ness with nothing reported',
      True,
      False,
      (('web/src/a.ts',
        'typescript',
        None,
        (('i:Bet', 'A'), ('k:export/i:run', 'E'))),),
      ('web/src/a.ts',),
      (('web/src/a.ts',
        'typescript',
        None,
        (('i:Bet', 'A2'), ('k:export/i:run', 'E'))),),
      ('web/src/a.ts',),
      (),
      ()),
     ('a base file nobody attempted leaves its space unread',
      False,
      False,
      (('web/src/a.ts', 'typescript', True, (('i:Bet', 'A'),)),),
      ('web/src/a.ts',),
      (('web/src/b.ts', 'typescript', True, (('s:.\\/a/i:Bet', 'B'),)),),
      ('web/src/b.ts',),
      (),
      (('typescript:<unresolved ./a>', 'unresolved_specifier'),)),
     ('python does not merge: a second module is refused, not compared',
      False,
      True,
      (('src/pkg/wallet.py', 'python', None, (('Wallet', 'A'),)),),
      ('src/pkg/wallet.py',),
      (('src/pkg/wallet.py', 'python', None, (('Wallet', 'A'),)),
       ('src/pkg/wallet_v2.py', 'python', None, (('Wallet', 'B'),))),
      ('src/pkg/wallet.py', 'src/pkg/wallet_v2.py'),
      (),
      ()),
     ("go does not merge: a new file's method is an added key",
      False,
      True,
      (('pkg/wallet.go', 'go', None, (('Wallet', 'A'),)),),
      ('pkg/wallet.go',),
      (('pkg/wallet.go', 'go', None, (('Wallet', 'A'),)),
       ('pkg/debit.go', 'go', None, (('Wallet.Debit', 'D'),))),
      ('pkg/wallet.go', 'pkg/debit.go'),
      (),
      ()))


def _surfaces(files: tuple[_File, ...]) -> tuple[FileSurface, ...]:
    return tuple(
        FileSurface(path, Language(language), keys, is_module=is_module)
        for path, language, is_module, keys in files
    )


def test_the_behaviour_table_matches_its_transcription() -> None:
    """``SURFACE_BEHAVIOUR_ROWS`` == ``_TABLE``, field for field. GREEN TODAY.

    The production table is the module's own statement of what it must do and
    W2-2-3 owns the module. This row is what makes that safe: a row added,
    removed, renamed, re-fixtured, or given a different answer reddens here and
    arrives with a reviewer, and until someone updates ``_TABLE`` the two
    disagree loudly rather than agreeing quietly on a weakened answer.

    It also refuses the degenerate shapes the table could decay into: one where
    nothing expects a change is satisfied by an algebra that finds nothing, and
    one where nothing expects a clean answer is satisfied by one that refuses
    everything.
    """
    derived = tuple(
        (
            row.name,
            row.is_control,
            row.refused,
            tuple(
                (
                    surface.path,
                    surface.language.value,
                    surface.is_module,
                    tuple(surface.fingerprints),
                )
                for surface in row.base
            ),
            tuple(row.base_attempted),
            tuple(
                (
                    surface.path,
                    surface.language.value,
                    surface.is_module,
                    tuple(surface.fingerprints),
                )
                for surface in row.head
            ),
            tuple(row.head_attempted),
            tuple(
                (change.key, change.before, change.after, tuple(change.introduced_by))
                for change in row.changes
            ),
            tuple((unread.namespace, unread.reason.value) for unread in row.unread),
        )
        for row in SURFACE_BEHAVIOUR_ROWS
    )
    by_name = {row[0]: row for row in derived}
    transcribed = {row[0]: row for row in _TABLE}
    assert sorted(by_name) == sorted(transcribed), (
        "SURFACE_BEHAVIOUR_ROWS and this file's transcription name different "
        f"rows.\nonly in the module : {sorted(set(by_name) - set(transcribed))}"
        f"\nonly here          : {sorted(set(transcribed) - set(by_name))}"
    )
    for name in sorted(by_name):
        assert by_name[name] == transcribed[name], (
            f"{name}: the module's row and this file's transcription disagree."
            f"\nmodule : {by_name[name]}\nhere   : {transcribed[name]}"
        )
    assert derived == _TABLE, (
        "the rows agree one by one but not in ORDER, and the report and the "
        "seal must see one order"
    )

    assert any(row[7] for row in _TABLE), (
        "no row expects a change; an algebra that reports nothing passes them all"
    )
    assert any(
        not row[7] and not row[8] and not row[2] for row in _TABLE
    ), "no row expects a clean answer; an algebra that refuses everything passes"


@pytest.mark.parametrize("row", _TABLE, ids=[row[0] for row in _TABLE])
def test_the_surface_algebra_answers_its_own_behaviour_table(
    row: _Transcribed,
) -> None:
    """``build_surface`` and ``compare_surfaces``. **RED at HEAD: both are
    holes.** Green at W2-2-3.

    The seal, verbatim from ``BehaviourRow``'s own contract::

        base = build_surface(row.base, attempted=set(row.base_attempted))
        head = build_surface(row.head, attempted=set(row.head_attempted))
        got  = compare_surfaces(base, head)

    Asserted FIELD-FOR-FIELD, not by label: the merged fingerprints and the
    introducing paths are the part a wrong implementation gets wrong while
    still naming the right key.
    """
    (
        name,
        is_control,
        refused,
        base_files,
        base_attempted,
        head_files,
        head_attempted,
        expected_changes,
        expected_unread,
    ) = row

    if refused:
        _assert_refused_at_construction(name, base_files, base_attempted)
        _assert_refused_at_construction(name, head_files, head_attempted)
        return

    base = build_surface(_surfaces(base_files), attempted=set(base_attempted))
    head = build_surface(_surfaces(head_files), attempted=set(head_attempted))
    got = compare_surfaces(base, head)

    assert tuple(
        (
            change.key.label,
            change.before,
            change.after,
            tuple(change.introduced_by),
        )
        for change in got.changes
    ) == expected_changes, f"{name}: changes"

    assert tuple(
        (unread.namespace.label, unread.reason.value) for unread in got.unread
    ) == expected_unread, f"{name}: unread"

    if is_control:
        assert got.clean, (
            f"{name}: a CONTROL row is not clean. A change that reddens a "
            "control has broken the gate it was extending"
        )


def _assert_refused_at_construction(
    name: str, files: tuple[_File, ...], attempted: tuple[str, ...]
) -> None:
    """``build_surface`` itself refuses, and the message says what it refused.

    Both halves are the finding: a ``pytest.raises`` spanning base
    construction, head construction and the comparison is green when any one of
    the three raises for any reason — including a stub that raises on every
    input — so it cannot say a non-merging language was refused at all. The
    call is isolated per revision, and ``match`` requires the message to name
    the language or the file: ``BranchSurfaceError`` is also raised from
    ``Namespace``, ``SymbolKey`` and ``SurfaceEntry`` construction and from
    ``merge_fingerprints``, and a refusal that names none of its input is one
    no author can act on.
    """
    surfaces = _surfaces(files)
    wanted = "|".join(
        sorted(
            {re.escape(surface.language.value) for surface in surfaces}
            | {re.escape(surface.path) for surface in surfaces}
        )
    )
    with pytest.raises(BranchSurfaceError, match=wanted):
        build_surface(surfaces, attempted=set(attempted))


# --------------------------------------------------------------------------- #
# 4b. THE CLAUSES, DERIVED HERE. RED until W2-2-3.
#
#     Nothing below is drawn from the module: each fixture and each answer is
#     written from `compare_surfaces`' three clauses and from
#     `merge_fingerprints`' two stated properties, over a shape
#     `SURFACE_BEHAVIOUR_ROWS` does not contain. An answer already wrong in the
#     production table cannot green one of these, which is the one thing the
#     frozen copy above cannot do for itself.
# --------------------------------------------------------------------------- #


def _module_surface(path: str, keys: dict[str, str]) -> FileSurface:
    """A TypeScript file its caller KNOWS is a module, keys in writing order."""
    return FileSurface(
        path, Language.TYPESCRIPT, tuple(keys.items()), is_module=True
    )


#: The three files these rows move one contribution between, and the one key
#: they all touch. `_AUG_KEY` is built by the real key builder because a
#: specifier needs an escape no row should hand-spell; the FINGERPRINTS are
#: single letters so the merged value can be read at a glance.
_A_TS = "web/src/a.ts"
_B_TS = "web/src/b.ts"
_C_TS = "web/src/c.ts"
_I_BET = ts_symbol_key((("i", "Bet"),))
_AUG_A_BET = ts_symbol_key((("s", "./a"), ("i", "Bet")))
_A_SPACE = f"{ts_namespace_of(_A_TS).label}::{_I_BET}"


def test_a_second_files_contribution_merges_rather_than_replacing() -> None:
    """All three clauses at once, and the MERGE asserted whole.
    **RED at HEAD: both functions are holes.** Green at W2-2-3.

    ``a.ts`` seals ``i:Bet`` and does not move; the branch adds ``b.ts``
    augmenting ``./a``. Clause 1 holds (the key exists at base), clause 2 holds
    (``b.ts`` contributed nothing to it at base), clause 3 holds (the merged
    fingerprint differs).

    ``after`` is derived, not copied: :func:`merge_fingerprints` orders
    contributions by PATH and joins them with ``" + "``, so ``A + B`` and never
    ``B + A``. It must not be ``B`` alone — a widening reported as a
    REPLACEMENT means the merge dropped the sealed declaration, and a pure move
    would then differ from its base too and clause 3 would fire on it (which is
    the next row).
    """
    base = build_surface(
        (_module_surface(_A_TS, {_I_BET: "A"}),), attempted={_A_TS}
    )
    head = build_surface(
        (
            _module_surface(_A_TS, {_I_BET: "A"}),
            _module_surface(_B_TS, {_AUG_A_BET: "B"}),
        ),
        attempted={_A_TS, _B_TS},
    )

    got = compare_surfaces(base, head)

    assert not got.unread, f"nothing here is unreadable: {got.unread}"
    assert len(got.changes) == 1, [change.key.label for change in got.changes]
    change = got.changes[0]
    assert change.key.label == _A_SPACE, (
        f"the widening is keyed {change.key.label!r}, not {_A_SPACE!r}; a key "
        "in b.ts's own space means the augmentation was never routed to the "
        "module it augments"
    )
    assert (change.before, change.after) == ("A", "A + B"), (
        f"{(change.before, change.after)} is not the sealed contribution "
        "followed by the merge of both, ordered by path"
    )
    assert change.introduced_by == (_B_TS,), change.introduced_by


def test_a_contribution_that_only_moved_files_is_not_a_widening() -> None:
    """CLAUSE 3 alone, and it is the clause a merge-then-diff loses.
    **RED at HEAD.** Green at W2-2-3.

    The same augmentation of ``./a``, byte-identical, moves from ``b.ts`` to
    ``c.ts``. Clause 2 holds — ``c.ts`` is a new contributor — so an
    implementation missing clause 3 reports a widening. There is none:
    :func:`merge_fingerprints` keeps the path OUT of the merged text, so both
    revisions merge to ``A + B`` and nothing about ``Bet`` changed. The
    per-file loop still reports the removal from ``b.ts``, which is where a
    move is answered and W2-2-4's to rule.
    """
    base = build_surface(
        (
            _module_surface(_A_TS, {_I_BET: "A"}),
            _module_surface(_B_TS, {_AUG_A_BET: "B"}),
        ),
        attempted={_A_TS, _B_TS},
    )
    head = build_surface(
        (
            _module_surface(_A_TS, {_I_BET: "A"}),
            _module_surface(_C_TS, {_AUG_A_BET: "B"}),
        ),
        attempted={_A_TS, _C_TS},
    )

    got = compare_surfaces(base, head)

    assert got.changes == (), (
        "a contribution that only changed files was reported as a widening: "
        f"{[(c.key.label, c.before, c.after) for c in got.changes]}. The "
        "merged fingerprint carries no path, so both revisions merge to the "
        "same value"
    )
    assert got.clean, got.unread


def test_a_contribution_that_was_only_removed_is_not_a_widening() -> None:
    """CLAUSE 2 alone, in the direction that fails it.
    **RED at HEAD.** Green at W2-2-3.

    ``b.ts``'s augmentation is DELETED. The merged fingerprint changes
    (``A + B`` to ``A``), so clause 3 holds and clause 1 holds — an
    implementation that diffs merged fingerprints and calls the difference a
    widening reports one here, against a branch that removed code.

    ``b.ts`` stays in ``attempted`` at head and is absent from the tree, which
    is the second half of the row: a path attempted and absent has nothing to
    preserve and leaves NOTHING unread. Reading it as unread would make every
    deletion UNDETERMINED.
    """
    base = build_surface(
        (
            _module_surface(_A_TS, {_I_BET: "A"}),
            _module_surface(_B_TS, {_AUG_A_BET: "B"}),
        ),
        attempted={_A_TS, _B_TS},
    )
    head = build_surface(
        (_module_surface(_A_TS, {_I_BET: "A"}),), attempted={_A_TS, _B_TS}
    )

    got = compare_surfaces(base, head)

    assert got.changes == (), (
        "a removed contribution was reported as a widening: "
        f"{[(c.key.label, c.before, c.after) for c in got.changes]}. Clause 2 "
        "asks for a NEW contributor and a deletion has none"
    )
    assert got.unread == (), (
        f"a path attempted and absent left a space unread: {got.unread}"
    )


def test_a_specifier_resolves_when_its_other_candidates_were_never_there() -> None:
    """The seam BOTH inherited HIGH findings name. **RED at HEAD.**

    ``build_surface``'s routing rule says an ``s:<specifier>`` key resolves
    when "exactly one of ``specifier_candidates`` present resolves", and the
    only set it names is ``attempted``. But ``_fold`` puts EVERY closure
    candidate into ``attempted`` — all six spellings of ``./a``, whether or not
    the tree has them — so read as "present in ``attempted``" every real
    closure is six-way ambiguous and the flagship case can never be anything
    but UNDETERMINED.

    This row is the behaviour, and the behaviour is what a seal pins: all six
    candidates attempted, exactly ONE of them supplied as a file, and the
    answer is the widening. The scaffold's sentence is what has to give —
    "present" must mean "a file that came back at that revision", not "a path
    someone reached for". That contract repair belongs to W2-2-3 (the body that
    implements build_surface), which will redefine the routing rule; until then
    this row stays red.
    """
    candidates = specifier_candidates(_B_TS, "./a")
    assert _A_TS in candidates, (
        f"{_A_TS} is no longer a candidate for './a' written in {_B_TS}: "
        f"{candidates}; this row would measure nothing"
    )
    attempted = {*candidates, _A_TS, _B_TS}
    assert len(attempted) > 2, "the six candidates collapsed to the one file"

    base = build_surface(
        (_module_surface(_A_TS, {_I_BET: "A"}),), attempted=attempted
    )
    head = build_surface(
        (
            _module_surface(_A_TS, {_I_BET: "A"}),
            _module_surface(_B_TS, {_AUG_A_BET: "B"}),
        ),
        attempted=attempted,
    )

    got = compare_surfaces(base, head)

    assert not got.unread, (
        "the augmented module read as unresolved with five of its six "
        f"candidates merely attempted and absent: {got.unread}. A closure that "
        "tries every spelling would then make every resolution ambiguous"
    )
    assert [
        (change.key.label, change.before, change.after, change.introduced_by)
        for change in got.changes
    ] == [(_A_SPACE, "A", "A + B", (_B_TS,))], got.changes


# --------------------------------------------------------------------------- #
# 5. THE CLOSURE AND ITS BOUND. `closure_request`. RED until W2-2-3.
#
#    The cap is a gate surface in its own right: "a bound that drops candidates
#    quietly is a bypass anyone can buy with a large diff" is the module's own
#    sentence, and an implementation that enumerates past the cap and slices,
#    or that returns `truncated` and lets the caller ignore it, satisfies every
#    row about the algebra.
#
#    ONLY THE FIRST HALF IS CLOSED HERE — `closure_request`'s own return value
#    is all a row at this level can see. The second half is a fact about the
#    CALLER, and it is closed in section 6 by
#    `test_a_closure_too_large_to_finish_refuses_and_is_never_clean`, which
#    drives a real over-cap diff through `fold_branch_signatures` and demands
#    the refusal. Without that row an implementation could satisfy every
#    assertion below, resolve against the partial prefix, and answer CLEAN.
# --------------------------------------------------------------------------- #


def _ts(path: str, keys: tuple[tuple[str, str], ...]) -> FileSurface:
    """A TypeScript module surface with the key order the caller wrote.

    Order is the contract here — it is what the cap truncates — so this does
    not sort, and the rows below pass keys in the order they mean.
    """
    return FileSurface(path, Language.TYPESCRIPT, keys, is_module=True)


def _aug(specifier: str, *segments: tuple[str, str]) -> str:
    return ts_symbol_key((("s", specifier),) + segments)


#: `./a` written in `web/src/b.ts`, spelled out rather than derived: this is
#: the order `specifier_candidates` promises and the order the cap cuts.
_A_CANDIDATES: tuple[str, ...] = (
    "web/src/a.d.ts",
    "web/src/a.tsx",
    "web/src/a.ts",
    "web/src/a/index.d.ts",
    "web/src/a/index.tsx",
    "web/src/a/index.ts",
)
_C_CANDIDATES: tuple[str, ...] = (
    "web/src/c.d.ts",
    "web/src/c.tsx",
    "web/src/c.ts",
    "web/src/c/index.d.ts",
    "web/src/c/index.tsx",
    "web/src/c/index.ts",
)


def test_the_closure_enumerates_every_candidate_of_every_augmentation() -> None:
    """``closure_request``'s clauses 1 and 2. **RED at HEAD: it is a hole.**

    Three facts in one call, because they are one contract:

      1. a surface in a language that does not merge across files contributes
         NOTHING — the Go file here declares a key spelled like an
         augmentation, and Go has no ``declare module``;
      2. a file that augments nothing contributes nothing, so the request is
         not "every file in the diff";
      3. every candidate of every specifier, in KEY order, and a BARE specifier
         contributes none: ``lodash`` is resolved by ``tsconfig.json``, which
         lives in the tree under judgement, so reading it would let a branch
         decide how its own files are found.

    The expected list is written out rather than derived from
    ``specifier_candidates``, and the keys are supplied ``./c`` first so the
    order asserted is the file's key order and not a sort.
    """
    surfaces = (
        _ts("web/src/a.ts", (("i:Bet", "A"),)),
        _ts(
            "web/src/b.ts",
            (
                (_aug("./c", ("i", "X")), "C"),
                (_aug("./a", ("i", "Bet")), "B"),
                (_aug("lodash", ("i", "L")), "L"),
            ),
        ),
        FileSurface(
            "pkg/wallet/wallet.go", Language.GO, ((_aug("./a", ("i", "Bet")), "G"),)
        ),
    )

    request = closure_request(surfaces)

    assert request.candidates == _C_CANDIDATES + _A_CANDIDATES, (
        "the closure did not ask for every candidate of every relative "
        f"specifier in key order: {request.candidates}"
    )
    assert request.truncated is False, (
        f"{len(request.candidates)} candidates is under MAX_CLOSURE_READS "
        f"({MAX_CLOSURE_READS}) and must not report truncation"
    )
    assert _unenumerated(surfaces, request) == (), (
        "an untruncated request left a specifier partly enumerated, so the "
        "fold would report a space unread that it in fact bounded"
    )


def test_the_closure_deduplicates_and_keeps_the_first_spelling() -> None:
    """``closure_request``'s clause 3. **RED at HEAD: it is a hole.**

    Two files augment the SAME module under two spellings — ``./a`` from
    ``web/src/b.ts`` and ``../a`` from ``web/src/sub/d.ts`` — and both
    normalise to ``web/src/a``. The result is one list a caller may hand to
    git unchanged: each candidate once, in the order it was first named. A
    request that repeats them buys the same blob twice out of a bound whose
    whole job is to be the gate's cost.
    """
    surfaces = (
        _ts("web/src/b.ts", ((_aug("./a", ("i", "Bet")), "B"),)),
        _ts("web/src/sub/d.ts", ((_aug("../a", ("i", "Bet")), "D"),)),
    )

    request = closure_request(surfaces)

    assert request.candidates == _A_CANDIDATES, (
        "two spellings of one module produced something other than that "
        f"module's six candidates, once each: {request.candidates}"
    )
    assert request.truncated is False, request


def test_the_closure_stops_at_the_cap_and_says_it_stopped() -> None:
    """``closure_request``'s clause 4, and what makes it not a silent
    truncation. **RED at HEAD: it is a hole.**

    Forty-three relative specifiers at six candidates each is 258 reads against
    a cap of 256, so the last specifier is cut mid-way. Asserted:

      * ``truncated`` is True. A request that fills the cap and says nothing is
        the bypass — a branch buys silence by being large;
      * exactly ``MAX_CLOSURE_READS`` candidates, and they are the PREFIX of
        the full enumeration. A request that returns fewer stopped early, one
        that returns more ignored its own bound;
      * ``_unenumerated`` names the specifier that was cut and no other. That
        is the handoff: a partially enumerated specifier would otherwise
        RESOLVE against the candidates that were reached, picking a file
        because the rest were never looked for, and the fold's
        ``UnreadReason.BUDGET_EXCEEDED`` space is built from this list.

    This row does not pin the number 256. It pins that the request stops AT the
    cap, whatever the cap is, and that the remainder is reported.
    """
    specifiers = tuple(f"./m{index}" for index in range(43))
    surfaces = (
        _ts(
            "web/src/b.ts",
            tuple((_aug(specifier, ("i", "Bet")), "B") for specifier in specifiers),
        ),
    )
    full: tuple[str, ...] = ()
    for specifier in specifiers:
        full += specifier_candidates("web/src/b.ts", specifier)
    assert len(full) > MAX_CLOSURE_READS, (
        f"the fixture no longer exceeds the cap ({len(full)} candidates for a "
        f"cap of {MAX_CLOSURE_READS}); this row would measure nothing"
    )

    request = closure_request(surfaces)

    assert request.truncated is True, (
        "the closure filled its budget and reported no truncation; a bound "
        "that drops candidates quietly is a bypass anyone can buy with a "
        "large diff"
    )
    assert len(request.candidates) == MAX_CLOSURE_READS, (
        f"{len(request.candidates)} candidates against a cap of "
        f"{MAX_CLOSURE_READS}"
    )
    assert request.candidates == full[:MAX_CLOSURE_READS], (
        "the truncated request is not the prefix of the full enumeration, so "
        "which candidates were dropped is not the ones past the cap"
    )

    cut = _unenumerated(surfaces, request)
    covered = set(request.candidates)
    expected_cut = tuple(
        sorted(
            specifier
            for specifier in specifiers
            if not covered.issuperset(
                specifier_candidates("web/src/b.ts", specifier)
            )
        )
    )
    assert cut == expected_cut, (
        f"the specifiers left partly enumerated are {expected_cut}, reported "
        f"as {cut}; a specifier resolved against a partial candidate set picks "
        "a file because the rest were never looked for"
    )
    assert cut, "the fixture truncated nothing, so this row measured nothing"


# --------------------------------------------------------------------------- #
# 6. THE ENTRY POINT'S FAIL-CLOSED ORDER. `fold_branch_signatures`.
#    RED until W2-2-3.
# --------------------------------------------------------------------------- #


class _Touched(BaseException):
    """Raised by a tripwire the fold must not trip.

    Derived from ``BaseException`` and not ``Exception`` ON PURPOSE:
    ``fold_branch_signatures`` is contracted to turn every ``Exception`` into
    ``RoleDiffError``, so evidence raised as an ``Exception`` would be caught
    by the very contract the row is measuring and reported as the refusal it
    was trying to disprove.
    """


class _UnreadablePaths(Sequence):
    """A ``changed_paths`` that cannot be read without saying so.

    The fail-closed rule is an ORDER — ``merge_base is None`` decides before
    ``changed_paths`` is looked at — and an order is only observable if
    looking has a consequence.
    """

    def __len__(self) -> int:
        raise _Touched("len(changed_paths)")

    def __getitem__(self, index: object) -> str:
        raise _Touched("changed_paths[...]")

    def __iter__(self):
        raise _Touched("iter(changed_paths)")


def _forbidden_run(*args: object, **kwargs: object) -> object:
    raise _Touched("the fold ran git")


def test_an_unresolved_merge_base_refuses_before_the_diff_is_looked_at(
    tmp_path: Path,
) -> None:
    """``fold_branch_signatures`` clause 1. **RED at HEAD: it is a hole.**

    An unresolved merge-base is unknown input and unknown input denies. The
    ORDER is the clause: answering CLEAN because the diff happened to hold
    nothing this module reads is a gate clearing a branch it never established
    a baseline for, and that reading is the one a fold that filters
    ``changed_paths`` first falls into by accident on every docs-only branch.

    Both halves are asserted. The first call's ``changed_paths`` raises on any
    access, so a fold that looks at it before deciding fails with ``_Touched``
    rather than passing; the second passes a real, ordinary path list, so the
    row cannot be satisfied by a fold that refuses only inputs it cannot read.

    Nothing here is a claim that the name exists: both calls assert the
    RoleDiffError the driver maps to UNDETERMINED, which is a fold that lands
    on the wrong branch of its own first decision fails.
    """
    with pytest.raises(RoleDiffError):
        fold_branch_signatures(
            tmp_path, None, "feat/x", _UnreadablePaths(), run=_forbidden_run
        )

    with pytest.raises(RoleDiffError):
        fold_branch_signatures(
            tmp_path, None, "feat/x", ("web/src/bet.ts",), run=_forbidden_run
        )


def test_a_diff_with_no_merging_language_is_clean_and_reads_nothing(
    tmp_path: Path,
) -> None:
    """``fold_branch_signatures`` clause 2. **RED at HEAD: it is a hole.**

    Every diff in THIS repository is this case, so it is the arm that runs
    most: markdown has no comparator, and Python and Go are ruled not to merge
    across files. The answer is ``CLEAN_FOLD`` and the cost is zero blob reads
    — ``run`` raises if it is called at all, which is what makes "reads
    nothing" a measurement rather than a promise.

    ``merge_base`` here is a revision that does not exist. It is never
    resolved, and a fold that reaches for it before filtering fails.
    """
    fold = fold_branch_signatures(
        tmp_path,
        "0000000000000000000000000000000000000000",
        "feat/x",
        ("docs/plan.md", "src/wallet.py", "pkg/wallet/wallet.go"),
        run=_forbidden_run,
    )

    assert fold == CLEAN_FOLD, (
        f"a diff with no merging language folded to {fold}, not CLEAN_FOLD"
    )
    assert fold.status is SignatureCheckStatus.CHECKED, fold.status
    assert fold.changes == () and fold.detail == "", fold


def _fold_at(repo: Path, changed: tuple[str, ...]) -> BranchFold:
    """``fold_branch_signatures`` at the fixture's real merge-base.

    The merge-base is resolved from the repository rather than passed as
    ``main``: reading a baseline at ``base_ref``'s tip instead of at the
    revision the diff was measured from is the defect the module's own contract
    names, and a helper that hands it the wrong ref would hide it in every row
    below.
    """
    merge_base = _git(repo, "merge-base", "main", "feat/x").strip()
    return fold_branch_signatures(repo, merge_base, "feat/x", changed, run=None)


def test_the_fold_answers_the_second_file_widening_and_does_not_refuse_it(
    tmp_path: Path,
) -> None:
    """The bypass, at the fold rather than through the driver. **RED at HEAD.**

    This row replaces one that asserted only that no exception BUT
    ``RoleDiffError`` reached the driver, on this same fixture. That is an
    absence, and ``RoleDiffError`` is the WRONG answer here: an implementation
    that refuses the exact input the gate exists to catch satisfied it. The
    error contract is worth sealing and it is sealed in the next row, on an
    input where refusal is the contracted answer forever.

    Here the answer is a CHECKED fold carrying exactly one widening, and every
    field of it is asserted for the same reason as in the ``check_branch`` row:
    a verdict alone is satisfied by any unrelated refusal.
    """
    repo = _branch(
        tmp_path,
        "fold_bypass",
        {_SEALED_TS_PATH: _TS_SEALED},
        {_AUGMENTING_TS_PATH: _TS_AUGMENTATION},
    )

    try:
        fold = _fold_at(repo, (_AUGMENTING_TS_PATH,))
    except Exception as exc:  # noqa: BLE001 - the failure IS the finding
        pytest.fail(
            f"{type(exc).__name__}: {exc}\nThis input has an ANSWER — one "
            "widening of a sealed interface from a second file — so neither a "
            "refusal nor a traceback is one. A RoleDiffError here is a gate "
            "that declines to decide the case it was built for"
        )

    assert isinstance(fold, BranchFold), fold
    assert fold.status is SignatureCheckStatus.CHECKED, (
        f"the fold read a diff it could read and reported {fold.status.value}: "
        f"{fold.detail}"
    )
    assert len(fold.changes) == 1, [
        (change.path, change.symbol) for change in fold.changes
    ]
    change = fold.changes[0]
    expected_symbol = (
        f"{ts_namespace_of(_SEALED_TS_PATH).label}::{ts_symbol_key((('i', 'Bet'),))}"
    )
    assert (change.path, change.symbol) == (
        _AUGMENTING_TS_PATH,
        expected_symbol,
    ), (change.path, change.symbol)
    sealed = TYPESCRIPT_SUPPORT.fingerprinter.fingerprints(
        _SEALED_TS_PATH, _TS_SEALED
    )
    assert change.before == sealed["i:Bet"], (
        f"`before` is {change.before!r} and the sealed file's own fingerprint "
        f"at the merge-base is {sealed['i:Bet']!r}"
    )
    assert sealed["i:Bet"] in change.after and change.after != change.before, (
        f"`after` ({change.after!r}) is not the sealed declaration merged with "
        "the augmenting one"
    )
    assert _AUGMENTING_TS_PATH in fold.detail or expected_symbol in fold.detail, (
        f"the detail check_branch prints names neither the file to edit nor "
        f"the widened key: {fold.detail!r}"
    )


#: `declare global` — a declaration space no path list bounds, so no closure
#: read can complete it and no answer but a refusal is available. This is the
#: input on which `RoleDiffError` is CORRECT, today and after every task in
#: this wave, which is what makes it the one that can seal the error contract.
_TS_GLOBAL_AUGMENTATION = (
    "export {};\n"
    "declare global {\n"
    "  interface Bet {\n"
    "    wager: number;\n"
    "  }\n"
    "}\n"
)
_GLOBAL_TS_PATH = "web/src/glob.ts"


def test_an_unbounded_space_refuses_with_the_one_exception_the_driver_maps(
    tmp_path: Path,
) -> None:
    """The error contract, on an input whose answer IS a refusal. **RED at HEAD.**

    ``check_branch`` catches ``RoleDiffError`` and nothing else, so every other
    exception this module can raise aborts the gate with a traceback where it
    owed an UNDETERMINED — including the ``NotImplementedError`` its own holes
    raise now, which is why this row is red rather than passing by accident.

    Two halves, and the second is what the row it replaces was missing. The
    exception must be the mapped one, AND it must be raised for this input's
    own reason: the message must name the space nobody could enumerate. A
    ``RoleDiffError`` for any other reason — an unresolved specifier, a read
    fault, an unfilled hole reported through the funnel — is a refusal that
    happens to be spelled right, and this fixture would keep certifying it.
    """
    repo = _branch(
        tmp_path,
        "global_space",
        {_SEALED_TS_PATH: _TS_SEALED},
        {_GLOBAL_TS_PATH: _TS_GLOBAL_AUGMENTATION},
    )

    try:
        fold = _fold_at(repo, (_GLOBAL_TS_PATH,))
    except RoleDiffError as exc:
        assert "global" in str(exc).lower(), (
            f"the refusal does not name the space it could not bound: {exc}. "
            "The contract is that every unread space and its reason are named, "
            "and a refusal an author cannot act on is one nobody will act on"
        )
        return
    except Exception as exc:  # noqa: BLE001 - that is the finding
        pytest.fail(
            f"{type(exc).__name__} reached the floored driver: {exc}. "
            "check_branch catches RoleDiffError alone, so anything else is a "
            "traceback where the gate owed an UNDETERMINED"
        )

    pytest.fail(
        f"the fold answered {fold} over `declare global`, a space no path list "
        "bounds. 'I could not look' is not a pass, and a fold that clears it "
        "clears every global augmentation in every diff"
    )


#: A `bet.ts` that does not parse. It is the AUGMENTATION TARGET and it is
#: UNCHANGED, so it is not in the diff at all: `compare_signatures` never opens
#: it and only the fold's closure read at the merge-base meets the fault. That
#: is what makes the row below a measurement of `_fold` rather than of the
#: per-file loop, which reports an unparseable CHANGED file on its own.
_TS_UNPARSEABLE = "export interface Bet {\n  id: string;\n"


def test_a_baseline_that_does_not_parse_refuses_and_claims_no_widening(
    tmp_path: Path,
) -> None:
    """``_fold``'s FAULTS SHORT-CIRCUIT clause. **RED at HEAD.**

    The clause is "faults short-circuit, BEFORE the surfaces are built", and
    without a row on it the fold that discards faults and builds surfaces out
    of the ``None``s :func:`_surface_at` returns passes everything else in this
    file: the faulted file contributes no base keys, every key of the
    augmentation is then an ADDED key, clause 1 makes it not a change, and the
    branch reads CLEAN. That is a bypass bought by making the baseline
    unreadable.

    So three assertions, and the second is the load-bearing one:

      * the status is the fault's own, ranked worse than CHECKED, so the branch
        is refused;
      * ``changes`` is EMPTY. A fold that reports a widening it derived from a
        file it could not read is stating a fact it does not have;
      * the detail names the file, because ``UNCHECKED_UNPARSEABLE`` on its own
        does not say which revision of what.

    The end of the row is the consequence at the gate: ``UNCHECKED_UNPARSEABLE``
    is a BODIES-blocking status, so the verdict is UNDETERMINED and never
    CLEAN.
    """
    repo = _branch(
        tmp_path,
        "fault_baseline",
        {_SEALED_TS_PATH: _TS_UNPARSEABLE},
        {_AUGMENTING_TS_PATH: _TS_AUGMENTATION},
    )
    diff = _git(repo, "diff", "--name-only", "main...feat/x").split()
    assert diff == [_AUGMENTING_TS_PATH], (
        "the unparseable file is in the diff, so the per-file loop reports it "
        f"and this row no longer measures the fold at all: {diff}"
    )

    fold = _fold_at(repo, (_AUGMENTING_TS_PATH,))

    assert fold.status is SignatureCheckStatus.UNCHECKED_UNPARSEABLE, (
        f"a baseline that does not parse folded to {fold.status.value}: "
        f"{fold.detail}. A file this gate CAN read and could not finish "
        "reading refuses on BODIES"
    )
    assert fold.changes == (), (
        "the fold reported a widening derived from a file it could not read: "
        f"{[(c.path, c.symbol) for c in fold.changes]}"
    )
    assert _SEALED_TS_PATH in fold.detail, (
        f"the detail does not name the file that would not parse: "
        f"{fold.detail!r}"
    )

    result = _bodies(repo)
    assert result.verdict is DiffVerdict.UNDETERMINED, (
        "a branch whose sealed baseline could not be read was told "
        f"{result.verdict.value}: {result.detail}"
    )


#: Derived from the cap, never pinned to 256: one relative specifier costs
#: `specifier_candidates` entries, so this many of them just fit and one more
#: does not. A cap that moves moves these fixtures with it.
_PER_SPECIFIER = len(specifier_candidates("web/src/many.ts", "./m0"))
_UNDER_CAP = MAX_CLOSURE_READS // _PER_SPECIFIER
_OVER_CAP = _UNDER_CAP + 1


def _augmenting_tree(count: int) -> tuple[dict[str, str], dict[str, str]]:
    """A base of ``count`` sealed modules, and one branch file augmenting them all.

    Real TypeScript through the real fingerprinter, because the cap counts
    candidates the fold enumerated from keys a comparator produced — a
    hand-built ``FileSurface`` would prove the arithmetic and not the gate.
    """
    base = {
        f"web/src/m{index}.ts": (
            f"export interface Bet {{\n  id{index}: string;\n}}\n"
        )
        for index in range(count)
    }
    augmentation = "export {};\n" + "".join(
        f"declare module './m{index}' {{\n"
        f"  interface Bet {{\n    w{index}: number;\n  }}\n"
        "}\n"
        for index in range(count)
    )
    return base, {"web/src/many.ts": augmentation}


def test_a_closure_that_just_fits_catches_every_widening_in_it(
    tmp_path: Path,
) -> None:
    """THE CAP'S CONTROL. **RED at HEAD.** Green at W2-2-3.

    ``_UNDER_CAP`` sealed modules, every one of them augmented from a single
    new file, is the largest diff the closure can still close over. Every
    widening must come back.

    It is here so the refusal in the next row means "the closure ran out of
    budget" and not "a large diff is refused". Without it, an implementation
    that answers UNDETERMINED for anything over a handful of files passes the
    cap row and fails nothing.
    """
    base, head = _augmenting_tree(_UNDER_CAP)
    repo = _branch(tmp_path, "under_cap", base, head)

    fold = _fold_at(repo, ("web/src/many.ts",))

    assert fold.status is SignatureCheckStatus.CHECKED, (
        f"a closure of {_UNDER_CAP * _PER_SPECIFIER} candidates against a cap "
        f"of {MAX_CLOSURE_READS} was not completed: {fold.status.value} — "
        f"{fold.detail}"
    )
    assert len(fold.changes) == _UNDER_CAP, (
        f"{len(fold.changes)} widenings out of {_UNDER_CAP} augmented modules; "
        "a closure that stops short reports the ones it reached and is silent "
        "about the rest"
    )
    assert {change.symbol for change in fold.changes} == {
        f"{ts_namespace_of(f'web/src/m{index}.ts').label}::"
        f"{ts_symbol_key((('i', 'Bet'),))}"
        for index in range(_UNDER_CAP)
    }, sorted(change.symbol for change in fold.changes)


def test_a_closure_too_large_to_finish_refuses_and_is_never_clean(
    tmp_path: Path,
) -> None:
    """THE CAP'S CONSEQUENCE, which is the half no row about ``closure_request``
    can reach. **RED at HEAD.** Green at W2-2-3.

    One more augmented module than the previous row, so the enumeration stops
    mid-specifier and ``ClosureRequest.truncated`` is True. The seal is what
    the FOLD then does with it: ``BUDGET_EXCEEDED`` is an unread space, an
    unread space is a refusal, and the branch is UNDETERMINED. An
    implementation that receives ``truncated`` and resolves against the partial
    prefix answers CLEAN here and satisfies every other row in this file —
    that is the large-diff bypass, and it is bought by adding files.

    Every target module EXISTS at the merge-base, so no specifier is unresolved
    and the budget is the only thing that can be unread. The refusal must name
    it: a message that says something else is a refusal for another reason and
    would keep this row green after the cap stopped working.
    """
    base, head = _augmenting_tree(_OVER_CAP)
    repo = _branch(tmp_path, "over_cap", base, head)
    assert _OVER_CAP * _PER_SPECIFIER > MAX_CLOSURE_READS >= (
        _UNDER_CAP * _PER_SPECIFIER
    ), "the fixture no longer straddles the cap, so neither cap row measures it"

    try:
        fold = _fold_at(repo, ("web/src/many.ts",))
    except RoleDiffError as exc:
        assert "budget" in str(exc).lower(), (
            f"the refusal does not name the budget as the reason: {exc}. "
            f"The unread reason is spelled {UnreadReason.BUDGET_EXCEEDED.value!r} "
            "and a refusal that names something else is one for another cause"
        )
    except Exception as exc:  # noqa: BLE001 - that is the finding
        pytest.fail(
            f"{type(exc).__name__} reached the floored driver: {exc}"
        )
    else:
        pytest.fail(
            f"a closure that ran out of budget folded to {fold}. The cap "
            "exists so the gate's cost is bounded; a bound that drops "
            "candidates and answers anyway is a bypass anyone can buy with a "
            "large diff"
        )

    result = _bodies(repo)
    assert result.verdict is DiffVerdict.UNDETERMINED, (
        "a branch the gate could not finish reading was told "
        f"{result.verdict.value}: {result.detail}. Not looking is not a pass"
    )


# --------------------------------------------------------------------------- #
# 7. REACHABILITY. D-69's lesson: a correct module nothing calls is dark.
#    RED until W2-2-5.
# --------------------------------------------------------------------------- #


_PACKAGE = _REPO / "src" / "claude_dispatcher"
_GATE_SCRIPT = _REPO / "scripts" / "check_body_branch.sh"

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


def _decided(test: ast.expr) -> bool | None:
    """Whether ``test`` is settled without running anything.

    ``if TYPE_CHECKING`` is False at runtime, so the names it imports do not
    exist and a call through one could not happen.
    """
    if isinstance(test, ast.Constant):
        return bool(test.value)
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return False
    if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
        return False
    return None


#: Scopes whose bodies run only if something invokes them, and statements after
#: which nothing else in the same list runs.
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_TERMINAL = (ast.Return, ast.Raise, ast.Break, ast.Continue)


def _live_nodes(
    body: Sequence[ast.stmt], *, guarded: bool = False
) -> Iterator[tuple[ast.AST, bool]]:
    """Everything under ``body`` that can run, and whether it is CONDITIONAL."""
    for statement in body:
        yield from _live_statement(statement, guarded)
        if isinstance(statement, _TERMINAL):
            return


def _live_statement(
    statement: ast.stmt, guarded: bool
) -> Iterator[tuple[ast.AST, bool]]:
    """One statement's live nodes. Loop and branch bodies are conditional."""
    if isinstance(statement, _SCOPES):
        return
    yield statement, guarded
    if isinstance(statement, ast.If):
        decided = _decided(statement.test)
        yield from _live_expression(statement.test, guarded)
        branch = guarded or decided is None
        if decided is not False:
            yield from _live_nodes(statement.body, guarded=branch)
        if decided is not True:
            yield from _live_nodes(statement.orelse, guarded=branch)
        return
    if isinstance(statement, ast.While):
        decided = _decided(statement.test)
        yield from _live_expression(statement.test, guarded)
        if decided is not False:
            yield from _live_nodes(
                statement.body, guarded=guarded or decided is not True
            )
        if decided is not True:
            yield from _live_nodes(statement.orelse, guarded=True)
        return
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        yield from _live_expression(statement.iter, guarded)
        yield from _live_expression(statement.target, guarded)
        yield from _live_nodes(statement.body, guarded=True)
        yield from _live_nodes(statement.orelse, guarded=True)
        return
    for field, value in ast.iter_fields(statement):
        conditional = guarded or field == "orelse"
        items = value if isinstance(value, list) else [value]
        if items and all(isinstance(item, ast.stmt) for item in items):
            yield from _live_nodes(items, guarded=conditional)
            continue
        for item in items:
            if not isinstance(item, ast.AST):
                continue
            if isinstance(item, ast.excepthandler):
                yield item, True
                yield from _live_nodes(item.body, guarded=True)
            elif isinstance(item, ast.match_case):
                yield item, True
                yield from _live_nodes(item.body, guarded=True)
            else:
                yield from _live_expression(item, conditional)


def _live_expression(
    node: ast.AST, guarded: bool
) -> Iterator[tuple[ast.AST, bool]]:
    """One expression's nodes, with the operands that may not be evaluated
    marked conditional."""
    if isinstance(node, _SCOPES):
        return
    yield node, guarded
    if isinstance(node, ast.IfExp):
        yield from _live_expression(node.test, guarded)
        yield from _live_expression(node.body, True)
        yield from _live_expression(node.orelse, True)
        return
    if isinstance(node, ast.BoolOp):
        for index, value in enumerate(node.values):
            yield from _live_expression(value, guarded or index > 0)
        return
    for child in ast.iter_child_nodes(node):
        yield from _live_expression(child, guarded)


def _in_package_aliases(
    body: Sequence[ast.stmt], known: frozenset[str]
) -> dict[str, str]:
    """Local name -> in-package module, for the imports ``body`` itself runs."""
    found: dict[str, str] = {}
    for node, _ in _live_nodes(body):
        if isinstance(node, ast.ImportFrom):
            named = (
                node.names
                if (node.level == 1 and node.module is None)
                or (node.level == 0 and node.module == "claude_dispatcher")
                else ()
            )
            for alias in named:
                if alias.name in known:
                    found[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if not alias.name.startswith("claude_dispatcher."):
                    continue
                module = alias.name.split(".")[1]
                if module in known:
                    found[alias.asname or alias.name] = module
    return found


def _rebound(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names ``function`` binds itself, which are therefore not the package's."""
    args = function.args
    names = {
        arg.arg
        for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
    }
    for extra in (args.vararg, args.kwarg):
        if extra is not None:
            names.add(extra.arg)
    for node, _ in _live_nodes(function.body):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    return names


def _package_call_graph() -> tuple[CallGraph, frozenset[tuple[str, str]]]:
    """The package's module-level call graph, by AST."""
    known = frozenset(
        path.stem for path in _PACKAGE.glob("*.py") if path.stem != "__init__"
    )
    trees: dict[str, ast.Module] = {}
    functions: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {}
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
    unconditional: set[tuple[str, str]] = set()
    unresolved: list[tuple[Symbol, str, str]] = []
    for module in sorted(known):
        module_aliases = _in_package_aliases(trees[module].body, known)
        for name, node in functions[module].items():
            caller = symbols[f"claude_dispatcher.{module}.{name}"]
            aliases = {**module_aliases, **_in_package_aliases(node.body, known)}
            rebound = _rebound(node)
            for shadowed in rebound & set(aliases):
                del aliases[shadowed]
            for call, guarded in _live_nodes(node.body):
                if not isinstance(call, ast.Call):
                    continue
                site = f"src/claude_dispatcher/{module}.py:{call.lineno}"
                func = call.func
                target: str | None = None
                if (
                    isinstance(func, ast.Name)
                    and func.id in functions[module]
                    and func.id not in rebound
                ):
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
                edges.append(Edge(caller, symbols[target], EdgeKind.DIRECT, site))
                if not guarded:
                    unconditional.add((caller.key, target))
    return (
        CallGraph(
            symbols=symbols,
            edges=tuple(edges),
            unresolved_calls=tuple(unresolved),
            unreadable_paths=(),
        ),
        frozenset(unconditional),
    )


def _is_main_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and any(
            isinstance(other, ast.Constant) and other.value == "__main__"
            for other in test.comparators
        )
    )


def _module_main_target(module: str) -> str:
    """The function ``python -m <module>`` actually enters.

    Read out of the module's own ``if __name__ == "__main__"`` guard rather
    than assumed to be ``main``: ``role_protocol``'s guard deliberately
    delegates to the PACKAGE's copy of itself under an alias, and a root named
    by convention would be a root that is not the one CI runs.
    """
    path = _PACKAGE / f"{module.rsplit('.', 1)[-1]}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    guard = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.If) and _is_main_guard(node.test)
        ),
        None,
    )
    assert guard is not None, (
        f"{module} has no `if __name__ == \"__main__\"` guard, so "
        f"{_GATE_SCRIPT.name}'s `python -m {module}` enters nothing"
    )
    imported: dict[str, str] = {}
    for node in ast.walk(guard):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imported[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    local = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in ast.walk(guard):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in imported:
                return imported[node.func.id]
            if node.func.id in local:
                return f"{module}.{node.func.id}"
    raise AssertionError(f"{module}'s __main__ guard calls no function of it")


def _production_roots() -> tuple[tuple[str, EntrypointKind, str], ...]:
    """Every production entrypoint, DERIVED from what installs and runs them.

    Two sources, and neither is a list in this file: ``pyproject.toml``'s
    ``[project.scripts]``, which is what a ``pipx install`` puts on PATH, and
    ``scripts/check_body_branch.sh``, which is what CI runs the diff-time gate
    through. A hand-written root list is a list that stays right until someone
    adds an entrypoint, and then reports every symbol only the new one reaches
    as dark.
    """
    roots: list[tuple[str, EntrypointKind, str]] = []
    scripts = tomllib.loads(
        (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["scripts"]
    for name, target in sorted(scripts.items()):
        module, _, attribute = target.partition(":")
        roots.append(
            (
                f"{module}.{attribute}",
                EntrypointKind.PYTHON_CONSOLE_SCRIPT,
                f"pyproject.toml [project.scripts] {name} = {target}",
            )
        )

    modules = sorted(
        {
            found
            for line in _GATE_SCRIPT.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
            for found in re.findall(
                r"-m\s+(claude_dispatcher\.[A-Za-z_]\w*)", line
            )
        }
    )
    assert modules, (
        f"{_GATE_SCRIPT.name} no longer runs `python -m claude_dispatcher.…`, "
        "so the entrypoint CI checks branches through is not derivable and "
        "this row's traversal would start in the wrong place"
    )
    for module in modules:
        roots.append(
            (
                _module_main_target(module),
                EntrypointKind.PYTHON_MODULE_MAIN,
                f"scripts/{_GATE_SCRIPT.name} runs `python -P -m {module}`",
            )
        )
    return tuple(roots)


def test_the_branch_surface_algebra_is_reached_from_production() -> None:
    """D-69, held before it is paid for. **RED at HEAD: the module is dark.**

    Every other row in this file proves that the surface algebra BEHAVES. Not
    one of them proves anything RUNS it, and a correct-but-unwired module passes
    all of them — "the money net is dark", which is the failure this unit would
    otherwise ship. ``branch_surface`` is unfloored, fully contracted and
    imported by nothing on the gate path today.

    Derived, not asserted: the call graph is read out of the package's own
    source using enrolled analyzers, the roots out of ``pyproject.toml`` and
    ``scripts/check_body_branch.sh``, and the reach computed by the enrolled
    ``call_site_reachability.reachable_from``. Nothing is hand-listed but the
    subjects and the lens control.

    THREE CONTROLS, all before the subjects are looked at, because a
    reachability row that cannot fail is worse than none:

      * with NO roots the reach is empty. A traversal that answers "everything"
        regardless of where it starts would green every subject below;
      * the reach is a PROPER SUBSET of the package's functions. An analyzer
        that resolves every call site into one blob reports reach for code
        nothing runs;
      * ``branch_reachability.check_branch_reachability`` — the D7 gate wired at
        ``check_branch`` step 6 — comes back reachable. It is reached through
        exactly the shape W2-2-5 adds (a function-local aliased ``from .
        import`` and an attribute call), so a green control means the analyzer
        can see that shape and a dark subject is a fact about the WIRING.

    Greened by W2-2-3 AND W2-2-5, and the dark list is what tells them apart:
    with the amendment's edit 1 applied and the holes still unfilled,
    ``fold_branch_signatures`` leaves the dark list and the other four stay in
    it, because a hole that raises calls nothing. So "the module is not wired"
    and "the module is wired and its own procedure never reaches the algebra"
    are two different failure messages from this one row, which is the
    distinction D-69 did not have.

    Reddens under: the amendment's edit 1 reverted; ``_fold`` filled so that
    it never calls ``build_surface`` or ``compare_surfaces``.
    """
    graph, _ = _package_call_graph()

    assert not reachable_from(graph, []), (
        "the traversal reports reach from no roots at all, so it is not "
        "following edges and every claim below is vacuous"
    )

    roots = []
    for key, kind, evidence in _production_roots():
        assert key in graph.symbols, (
            f"the production entrypoint {key!r} is not a module-level function "
            "of this package any more; the traversal below would start nowhere"
        )
        roots.append(Root(graph.symbols[key], kind, RootKind.PRODUCTION, evidence))

    reach = reachable_from(graph, roots)

    assert len(reach) < len(graph.symbols), (
        f"every one of the package's {len(graph.symbols)} module-level "
        "functions came back reachable, which no tree with test-only and "
        "dead code in it is; the analyzer is over-resolving and can only "
        "over-report reach"
    )
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

    entry = "claude_dispatcher.branch_surface.fold_branch_signatures"
    drivers = sorted(
        {
            edge.caller.key
            for edge in graph.edges
            if edge.callee.key == entry
            and not edge.caller.key.startswith("claude_dispatcher.branch_surface.")
        }
    )
    assert drivers, (
        f"{entry} is reachable but nothing outside its own module calls it, so "
        "whatever reaches it is not the gate"
    )
