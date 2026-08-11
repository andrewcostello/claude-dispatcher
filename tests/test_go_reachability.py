r"""D6 seals (P2) — the Go reachability analyzer, D5's first concrete row.

Written against ``src/claude_dispatcher/go_reachability.py`` and
``src/claude_dispatcher/go_call_reachability/main.go`` at ``b451cfc`` by an
author who did not write the scaffold and does not write the body. Every row
below is either RED at HEAD — the seven stubs raise
:class:`NotImplementedError`, and ``analyze`` in the Go helper returns
``errNotImplemented`` — or, for the rows that pin the seven functions the
scaffold implemented on purpose and the rows that pin a STRUCTURAL property of
the module's own text, MUTATION-VERIFIED in a clone and named as such at the
row.

Baseline for this file: ``feat/D6-seals``, branched from ``feat/D6-go-analyzer``
at ``b451cfc``. Suite measured 2026-08-11 on that base, after
``python3 -m claude_dispatcher.ts_parser_vendor``: **2313 passed, 0 failed, 13
skipped.**

NOTHING HERE ENROLS THE ROW
===========================
:data:`~claude_dispatcher.call_site_reachability.ANALYZERS` is ``()`` at HEAD
and this commit does not change it; ``role_protocol`` and ``FLOOR_GLOBS`` are
untouched. Rows that need ``check_tree`` to reach the Go row monkeypatch
``ANALYZERS`` for the duration of one call, which is
``tests/test_call_site_reachability.py``'s own established move (it does it at
twenty-odd sites) and is not enrolment: the module's tuple is unchanged, the
import-time guard never runs against a floored module, and
:func:`test_nothing_in_this_commit_enrols_the_go_row` is the row that says so.

THE DEFECT, THE FIXTURE, AND WHY THE NAIVE SCAN CANNOT SATISFY ANY OF THIS
==========================================================================
*A seal proves a function BEHAVES, and nothing proves the function RUNS.*

The acceptance instance is vendored, verbatim, under
``tests/fixtures/d6_g2_preserve/`` — ``cmd/gates/`` and ``cmd/iterate/`` of the
**``claude-workflow``** repository at ``83b0b9729f03ab8092da7c3997459c7c6110db97``
(``feat/G2-adj``). That is a DIFFERENT repository from this one, so no seal can
read the tree out of an object store at test time and vendoring is the only
route; see the fixture's ``PROVENANCE.md``, which carries every count this file
cites.

It is the B1 shape twice, and it is a better fixture than ``d5_b1_classify`` in
two measured respects:

  1. **The naive scan certifies both, and has no discriminating power at all
     here.** Measured 2026-08-11 over the four vendored production files: ten
     exported top-level funcs, and *"an exported func with no non-test mention"*
     flags **none of them**, because Go's doc-comment convention opens a
     comment with the name of the thing it documents and both
     ``VerifyPreservation`` doc comments do. The refined scan — mentions on
     non-comment, non-declaration production lines — scores **0 for exactly
     ``VerifyPreservation``, in each module, and for nothing else**; the same
     scan over ``d5_b1_classify`` scores 0 for seven functions of fourteen.
     :func:`test_the_naive_scan_certifies_both_dark_functions_and_still_refuses_an_orphan`
     runs both scans and carries a synthetic ``func Orphan()`` with no doc
     comment as the POSITIVE control, so that "the naive scan says clean" is
     shown to be a fact about idiomatic Go rather than a scan that has stopped
     working.
  2. **The key collides unless it is module-qualified.** Two modules, both
     ``package main``, both declaring a top-level ``func VerifyPreservation``
     with an identical signature. D5's :class:`Symbol` declares ``path`` and
     ``line`` as ``field(compare=False)``, so a collision is not a near-miss —
     it is one symbol wearing two declarations, in a mechanism that decides
     "is this reached" by set membership on the key.

DISPUTES — RAISED FOR P4, NOT PAPERED OVER
===========================================

  **D1. THE CONTRACT'S ACCEPTANCE COUNT IS WRONG. It is SEVEN findings, not
  eight.** ``go_reachability.py``'s WHAT A CORRECT ANALYZER MUST REPORT says
  "Five seals in ``cmd/iterate/preserve_seal_test.go`` … call it, nine times"
  and totals "Eight BREACHes from these two symbols alone". **Measured under**
  ``claude-workflow`` @ ``83b0b97``, 2026-08-11, by two independent methods that
  agree — a line-oriented scan attributing each ``VerifyPreservation(`` to its
  enclosing ``func``, and the reference call-graph walk described below:
  ``cmd/iterate`` has **four** seals and **eight** calls, not five and nine. The
  contract's own list names four distinct functions and then adds "and the
  licence row", which is the first of the four; the ninth call does not exist.
  ``cmd/gates`` is right as written: three seals, eight calls. So the acceptance
  answer is **3 + 4 = 7 (seal, subject) pairs, 16 calls**, and the module
  qualification argument is untouched — seven and not two.
  :func:`test_the_acceptance_case_is_seven_seal_subject_pairs_over_two_keys`
  seals seven and names each of the seven. **A body author must not "fix" this
  to eight.** The scaffold's own instruction — "the one a body author should
  re-measure before believing any number here" — is what found it.

  **D2. THE STEP-3 ABSTENTION IS NOT A PREDICTION ANY MORE. It is MEASURED, and
  it holds — but P4 CORRECTED THE NUMBER AND THE REASON (D6 adjudication,
  2026-08-11).** The contract marks it *Predicted (unmeasured)* and calls it
  "the most likely way this unit fails to earn its keep". The seal author
  measured **55** unresolved sites over a 106-symbol production closure, ~51 of
  them method calls through untypeable receivers. **That measured a
  non-conformant walk, not the tree**: ``main.go``'s EDGE GRAMMAR files a method
  call on an unresolved receiver as an ``interface`` edge, not a hole, and
  ``unresolved[]`` means the walk could not NAME the target — never "the target
  is out of tree". The prose did not close either (51 + 7 > 55).

  **Re-measured under** ``feat/D6-seals`` @ ``5669cb7``, 2026-08-11, by two
  independent walks written for the adjudication — a name-level walk obeying
  the grammar, and a full ``go/types`` walk under a hostile environment. They
  agree: production closure **106 symbols**, and **SEVEN** unresolved sites
  inside it, **every one a call through a FUNCTION VALUE** — ``cancel``
  (``context.CancelFunc``) twice in ``cmd/gates`` and a ``setMember`` closure
  five times in ``cmd/iterate``. Only 2 of the ~50 method-call sites even name a
  method that exists in this tree.

  So the conclusion stands — step 4 is never reached and **all seven findings
  come back ``UndecidedReason.DYNAMIC_EDGE``** — and "even the most permissive
  honest reading leaves the closure holed" is true. The REASON is not the one
  recorded. **Type information moves 50 sites and moves the verdict on none**,
  because nothing types the target of a call through a function value: that is
  dataflow, not typing. See
  :func:`test_a_named_out_of_tree_target_is_not_a_hole_and_a_func_value_call_is`,
  the row P4 added because nothing here distinguished the two.

  This file does NOT seal "it abstains", which would seal the failure, and does
  not seal "it breaches", which would demand a name-level walk that types
  ``time.Time``. It seals the IMPLICATION, total over the two states, at
  :func:`test_the_step_three_abstention_is_measured_and_the_implication_is_total`
  — and :func:`test_a_fully_resolved_production_closure_reaches_the_tests_only_verdict`
  is the row that keeps the other branch from being a dead letter, because a
  conditional whose consequent nothing can satisfy is a green that measures
  nothing.

  **D3. ``null`` IS NOT ``[]``, AND THE SCAFFOLD'S OWN HELPER CANNOT EMIT A
  CONTRACT-CONFORMANT ``parse_error`` DOCUMENT UNDER THE OTHER READING.**
  ``main.go``'s ``Response`` declares the four arrays without ``,omitempty``, so
  Go's ``encoding/json`` writes a nil slice as ``null`` and every
  ``parse_error`` document carries ``"symbols":null,"roots":null,…``. Adding
  ``omitempty`` is NOT the repair: in Go it omits an EMPTY slice too, which
  would destroy the "``[]`` is an answer" rule the same paragraph states. So the
  two sentences are compatible under exactly one reading — **a ``null`` array is
  ABSENT and an ``[]`` array is PRESENT-and-empty** — and that reading is what
  the contract's "``[]`` is an answer and ``null`` is not" is for.
  **Measured 2026-08-11** in the clone: a decoder that read ``null`` as
  "present" refused every ``parse_error`` document the scaffold's own helper can
  produce, and ``build_call_graph`` turned it into a whole-check
  ``CallSiteReachabilityError``. Sealed at
  :func:`test_a_null_array_is_absent_and_an_empty_one_is_an_answer`. P4 owes a
  sentence in ``main.go`` saying which; the row seals the only reading under
  which both halves of the contract are true.

  **D4. ``roots`` HAS NO CHANNEL FOR A UNIT THAT DID NOT PARSE, and the
  contract needs it to have none.** :meth:`GoReachabilityAnalyzer.roots` must
  not raise :class:`SourceUnreadable` (the scaffold rules this, at length, and
  this file adopts it). What follows and is not written down: ``roots`` must
  therefore SKIP a unit whose response carries ``parse_error`` and return the
  roots of every unit that parsed, silently, while ``graph`` records the file.
  A seal cannot distinguish "skipped the unparsed unit" from "found no roots in
  it", and does not try; it pins the two facts that matter and that the two
  methods must agree on
  (:func:`test_an_unparseable_file_never_raises_from_roots_and_lands_in_unreadable_paths`).

WHAT THESE SEALS DELIBERATELY DO NOT PIN
=========================================
**The ruling grid.** No row asserts a ``(Reach, PathQuality)`` pair maps to a
named :class:`Disposition`; that is D5's, and D5's own seal file declines it for
the same reason.

**The prose of any ``detail`` or ``evidence`` string.** ``evidence`` is
contracted as human-checkable and no decision reads it. A row asserting its
wording would be a row a body satisfies by copying a string.

**Whether the helper binary is tracked.** The scaffold RECOMMENDS not tracking
and gives three measured reasons; a seal that pinned the recommendation would
pin a decision P4 has not made. What IS pinned is the consequence nobody may
lose either way — the helper's source location is a pure function of this
package's own location (:func:`test_the_helper_directory_is_derived_from_this_packages_own_location`).

**The 169 ms / 68 s figures.** They are D4's, measured there, and re-asserting
them here would be a recording measuring a frozen artifact.

NON-VACUITY — WHAT EACH ROW OWES
=================================
Seven shapes are measured on this codebase: green on an unproducible input; a
pass condition satisfiable by executing nothing; green on an incidental
substring; a collapsed input space; a recording that measures a frozen artifact;
a test reading through the same struct shape that caused the loss; and a seal
asserting truthiness of a value now known wrong. Every row below carries, in its
own docstring, the mutation that reddens it and the evidence class of that
claim, spelled **``Measured under:``** or **``Predicted (unmeasured) under:``**
and never the struck ``Reddens under:``.

JOINT SATISFIABILITY
====================
**Measured 2026-08-11.** A throwaway reference implementation — ``analyze`` in
Go (a name-level ``go/ast`` walk, stdlib only) plus reference bodies for the
seven Python stubs — was written in a ``cp -a`` clone with the ``.git`` FILE
removed, and **every row in this file passes against it**, in one
implementation, at once — **97 passed, 0 failed**, against 57 red at HEAD. The
clone is not offered to P3 and no line of it is a proposal; it exists to show
the set is not impossible and to take the measurements D1, D2 and D3 rest on.

**The mutation ledger, measured 2026-08-11 in that clone: 39 mutations, 37 of
them red at least one row, and each redden-set named at its row.** Two are
recorded as NOT independently observable and both are recorded rather than
repaired, because in each case the contract says the two states are one fact:
dropping ``go_reachability_helper_dir``'s ``is_dir`` check (an absent directory
is also an absent ``main.go``, so the entry-point loop catches it), and
rewriting ONE of ``preserve.go``'s eight comment mentions (one mention is
enough to certify, which is why the fixture is eight-deep). Two further
mutations were UNCOVERED on their first spelling and the fault was the
mutation's, not the row's — both were no-ops on the reference walk, and both
redden the intended row once spelled to bite.

Two recorded artifacts of the clone procedure: ``__pycache__`` must be cleared
between runs, and with the ``.git`` FILE removed
``test_role_protocol_provenance.py`` ERRORs on 5 rows in EVERY clone run,
mutated or not, so the seal file is run alone there and those 5 never enter a
count.

**Suite state at this commit, measured 2026-08-11 with ``-o addopts=""``:**
without this file, **2313 passed / 0 failed / 13 skipped** — the baseline
exactly. With it, **2353 passed / 57 failed / 13 skipped**: 40 new green rows
(the seven implemented functions, the structural sweeps and the fixture
controls) and **57 red, every one of them by ``NotImplementedError`` from a
stub, and none of them outside this file.**
"""

from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

import pytest

import claude_dispatcher.call_site_reachability as csr
import claude_dispatcher.go_reachability as gr
from claude_dispatcher.call_site_reachability import (
    GO_REACHABILITY_PACKAGE_DIR,
    GO_REACHABILITY_SCHEMA,
    AnalyzerFault,
    AnalyzerUnavailable,
    CallGraph,
    Disposition,
    Edge,
    EdgeKind,
    EntrypointKind,
    PathQuality,
    Reach,
    Seal,
    Symbol,
    UndecidedReason,
    validate_analyzers,
)
from claude_dispatcher.go_reachability import (
    GO_INIT_SYMBOL_TEMPLATE,
    GO_PACKAGE_VAR_SYMBOL,
    GO_REACHABILITY_ANALYZER,
    GO_REACHABILITY_HELPER_ENTRY_POINTS,
    GoReachabilityAnalyzer,
    GoSourceFile,
    GoUnit,
    decode_go_reachability_response,
    discover_units,
    edge_kind_for_wire,
    encode_go_reachability_request,
    entrypoint_kind_for_wire,
    go_reachability_helper_dir,
    go_symbol_key,
    go_test_root_predicate,
)
from claude_dispatcher.role_protocol import Language
from claude_dispatcher.seal_verify import is_test_path

# --------------------------------------------------------------------------- #
# Where things are. Derived from ``__file__`` and never written as a literal:
# the D5 floor guard hit exactly this and had to derive its path the same way,
# and a path literal in a seal file is also a literal that D5's own AST sweep
# would have to be taught to ignore.
# --------------------------------------------------------------------------- #

_TESTS_DIR = Path(__file__).resolve().parent
_REPO = _TESTS_DIR.parent
_SRC = _REPO / "src" / "claude_dispatcher"

#: The vendored acceptance fixture. See its ``PROVENANCE.md`` for every count.
_FIXTURE = _TESTS_DIR / "fixtures" / "d6_g2_preserve"

#: The two module paths, read off the recorded ``go.mod`` files rather than
#: written out, so a row cannot pass because the fixture and the seal drifted
#: together.
_GATES_MODULE = "github.com/yourorg/claude-workflow/gates"
_ITERATE_MODULE = "github.com/yourorg/claude-workflow/iterate"

_SUBJECT_NAME = "VerifyPreservation"

#: The seven (seal, subject) pairs the acceptance case owes. MEASURED — see
#: DISPUTE D1; the contract predicts eight and ``cmd/iterate`` has four seals,
#: not five.
_ACCEPTANCE_SEALS = {
    "cmd/gates": (
        "TestSeal_G1_VerifyPreservation_ReportsEditsOutsideTheLicensedPaths",
        "TestSeal_G1_VerifyPreservation_TreatsADeletionUnderGatesAsAViolation",
        "TestSeal_G1_VerifyPreservation_RefusesWhatItCannotCheck",
    ),
    "cmd/iterate": (
        "TestSeal_G2_Licence_GatesIsLicensedForGatesAndForbiddenForIterate",
        "TestSeal_G2_VerifyPreservation_CatchesEveryArrayMalformationFromTheLicenceAlone",
        "TestSeal_G2_VerifyPreservation_DerivesTheLicenceFromTheEditListNotTheOutput",
        "TestSeal_G2_VerifyPreservation_RefusesWhatItCannotCheckOnItsOwnTerms",
    ),
}

#: What ``go.mod`` is called in the fixture, so ``go build ./...`` cannot pick
#: the vendored tree up. Spelled once; the seals rename it back into ``tmp_path``
#: because ``discover_units`` reads ``module_path`` from the nearest enclosing
#: ``go.mod`` and a fixture withholding it would exercise a different function.
_RECORDED_GO_MOD = "go.mod.recorded"
_LIVE_GO_MOD = "go.mod"


# --------------------------------------------------------------------------- #
# Helpers. None of these implements anything under seal: they build inputs and
# read outputs, and where a helper computes an expectation it is written out
# rather than derived from a function this file is also sealing.
# --------------------------------------------------------------------------- #


def _acceptance_tree(tmp_path: Path) -> Path:
    """The vendored fixture, copied into ``tmp_path`` with its ``go.mod`` live.

    Copied rather than analysed in place for two reasons a row depends on: the
    analyzer is contracted never to write into the tree it reads, and a run that
    mutated the fixture would make the next row's input a function of the
    previous row's body.
    """
    tree = tmp_path / "acceptance"
    shutil.copytree(_FIXTURE, tree)
    (tree / "PROVENANCE.md").unlink()
    for recorded in tree.rglob(_RECORDED_GO_MOD):
        recorded.rename(recorded.with_name(_LIVE_GO_MOD))
    return tree


def _package(
    tmp_path: Path,
    files: dict[str, str],
    *,
    module: str = "example.com/tiny",
    directory: str = "p",
    name: str = "tree",
) -> Path:
    """One synthetic Go package in a tree of its own. Returns the TREE root."""
    tree = tmp_path / name
    package = tree / directory
    package.mkdir(parents=True)
    (package / _LIVE_GO_MOD).write_text(f"module {module}\n\ngo 1.21\n")
    for filename, source in files.items():
        (package / filename).write_text(source)
    return tree


def _with_go_row(monkeypatch) -> None:
    """Point ``ANALYZERS`` at the Go row for one call. NOT enrolment."""
    monkeypatch.setattr(csr, "ANALYZERS", (GO_REACHABILITY_ANALYZER,))


def _response_document(**overrides) -> dict:
    """A well-formed one-symbol response, as a mutable dict.

    Written out rather than produced by the encoder, because a row that fed the
    decoder the encoder's output would be green whenever the two agreed with
    each other and wrong together.
    """
    document = {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": {
            "module_path": "example.com/tiny",
            "package_dir": "p",
            "package_name": "main",
        },
        "symbols": [
            {"key": "example.com/tiny/p.main", "path": "p/main.go", "line": 3,
             "kind": "func"},
            {"key": "example.com/tiny/p.Dark", "path": "p/main.go", "line": 7,
             "kind": "func"},
        ],
        "roots": [
            {"symbol": "example.com/tiny/p.main", "kind": "go_main",
             "evidence": "p/main.go:3 func main, package main"},
        ],
        "edges": [
            {"caller": "example.com/tiny/p.main", "callee": "example.com/tiny/p.Dark",
             "kind": "direct", "site": "p/main.go:4"},
        ],
        "unresolved": [],
    }
    document.update(overrides)
    return document


def _extension_shaped(value: str) -> bool:
    """A bare extension, or a bare filename carrying one. WHOLE-string only.

    Deliberately not a substring search: this module's ``raise`` messages are
    prose and one of them contains "the nearest enclosing go.mod", which a
    substring rule reports as a literal. Prose inside a raise is not a
    docstring, so the shape filter cannot catch it and the match must.
    """
    if not value or any(c.isspace() for c in value):
        return False
    return bool(re.fullmatch(r"\.[A-Za-z0-9]{1,6}", value)) or bool(
        re.fullmatch(r"[A-Za-z0-9_-]+\.(go|mod|py|ts|tsx|json|sql|java)", value)
    )


def _docstring_constants(tree: ast.AST) -> set[int]:
    """Every string constant that is prose: a bare ``Expr`` wrapping a string."""
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                prose.add(id(node.value))
    return prose


def _extension_literals(source: str) -> list[tuple[int, str]]:
    """Extension-shaped string constants that are not prose. Sorted."""
    tree = ast.parse(source)
    prose = _docstring_constants(tree)
    return sorted(
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in prose
        and _extension_shaped(node.value)
    )


def _endswith_sites(source: str) -> list[int]:
    """Every ``<expr>.endswith(...)`` CALL. Lines, sorted."""
    tree = ast.parse(source)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "endswith"
    )


def _naive_scan(production: dict[str, str]) -> list[str]:
    """*"An exported func with no non-test mention."* The scan that certifies B1.

    Deliberately crude, because being crude is the whole point: it counts every
    occurrence of the identifier anywhere in the production text, so a doc
    comment opening with the function's own name is a mention. Returns the names
    it FLAGS.
    """
    flagged = []
    for name in _exported_funcs(production):
        mentions = sum(
            len(re.findall(rf"\b{name}\b", text)) for text in production.values()
        )
        if mentions <= 1:  # its own declaration and nothing else
            flagged.append(name)
    return sorted(flagged)


def _refined_scan(production: dict[str, str]) -> list[str]:
    """Mentions on non-comment, non-declaration production lines. Zero-scorers."""
    zero = []
    for name in _exported_funcs(production):
        score = 0
        for text in production.values():
            for line in text.split("\n"):
                stripped = line.strip()
                if name not in line:
                    continue
                if stripped.startswith("//") or re.match(rf"^func {name}\(", stripped):
                    continue
                score += len(re.findall(rf"\b{name}\b", line))
        if score == 0:
            zero.append(name)
    return sorted(zero)


def _exported_funcs(production: dict[str, str]) -> list[str]:
    names = []
    for text in production.values():
        names += re.findall(r"^func ([A-Z]\w*)\(", text, flags=re.MULTILINE)
    return sorted(set(names))


def _production_text(module: str) -> dict[str, str]:
    """One module's vendored PRODUCTION files, by fixture-relative path.

    Per MODULE and not over both at once: the two packages are two resolution
    scopes and three exported names are declared in both, so a union would make
    "five exported funcs" read as seven and would let one module's mention
    certify the other module's function.
    """
    return {
        f"{module}/{name}": (_FIXTURE / module / name).read_text()
        for name in ("main.go", "preserve.go")
    }


# =========================================================================== #
# Part 1 — the row is a row, and this commit does not enrol it
# =========================================================================== #


def test_the_shape_check_accepts_a_row_whose_analysis_methods_raise():
    """A row is validated for SHAPE and never for implementedness.

    D5 contracts it in as many words and it is what lets a scaffolded row be
    validated before it works. The claim is DURABLE and this row is written so
    it stays true after P3 lands: the unimplemented row is a LOCAL double whose
    ``roots`` and ``graph`` raise, so the property survives the day the real
    row's methods stop raising. An earlier draft asserted
    ``pytest.raises(NotImplementedError)`` against
    :data:`GO_REACHABILITY_ANALYZER` itself; that pins the scaffold's transient
    state, goes red the moment a body lands, and is therefore a row a body
    author deletes rather than satisfies. **Measured in the clone, 2026-08-11**:
    with the reference bodies installed the old spelling was the only row in
    this file that failed for being satisfied.

    Recorded, not asserted: at ``b451cfc`` the real row's ``roots`` and ``graph``
    do raise ``NotImplementedError``, which is what makes every row in Parts
    8-11 red today.

    What IS asserted about the real row is what must never change: it is Go's,
    its negative is a real ``True``, and the two methods the scaffold
    implemented answer rather than raise — a body that stubbed
    ``test_root_predicate`` would break ``discover_seals`` for every Go tree.

    GREEN at HEAD and after the body. **Measured under** ``feat/D6-seals``,
    2026-08-11, in a clone, three mutations, each red on its own:

      * ``negative_is_conclusive`` returning ``1`` instead of ``True`` —
        ``validate_analyzers`` raises on the truthy non-bool, which is the
        ``explicit-state`` coercion defect applied to the one field that decides
        whether this mechanism may emit a BREACH;
      * ``language`` returning ``Language.PYTHON`` — the row then claims a
        language that already has a different answer to
        ``negative_is_conclusive``;
      * ``validate_analyzers`` growing an implementedness probe — the local
        double below is refused and the scaffold could never have been
        validated at all.
    """

    class _Unimplemented:
        """A row that satisfies the protocol and answers nothing."""

        language = Language.GO
        negative_is_conclusive = True

        def roots(self, tree):
            raise NotImplementedError("scaffold")

        def graph(self, tree):
            raise NotImplementedError("scaffold")

        def test_root_predicate(self, symbol):
            raise NotImplementedError("scaffold")

    validate_analyzers((_Unimplemented(),))
    validate_analyzers((GO_REACHABILITY_ANALYZER,))

    assert GO_REACHABILITY_ANALYZER.language is Language.GO
    assert GO_REACHABILITY_ANALYZER.negative_is_conclusive is True, (
        "Go's negative must be a real bool and it must be True: Go has no "
        "runtime lookup of a package-level function by name, and that single "
        "boolean is what lets this row emit a BREACH at all"
    )

    probe = Symbol(key=f"{_GATES_MODULE}/cmd/gates.TestSeal_G1_X",
                   path="cmd/gates/preserve_seal_test.go", line=1)
    assert GO_REACHABILITY_ANALYZER.test_root_predicate(probe) is True
    assert GO_REACHABILITY_ANALYZER.test_id(probe) == "cmd/gates.TestSeal_G1_X"


def test_nothing_in_this_commit_enrols_the_go_row():
    """``ANALYZERS`` is ``()``, no path resolves to a Go analyzer, no floor edit.

    The non-vacuity guard on "do not enrol". Without it, every ``UNSUPPORTED_LANGUAGE``
    answer elsewhere in the suite would be indistinguishable from an answer this
    branch changed, and the enrolment checklist's five items would look
    discharged.

    The floor half matters independently: ``FLOOR_GLOBS`` must grow
    ``**/src/claude_dispatcher/go_call_reachability/**`` before enrolment, and
    that entry reddens a table P4 has ruled P3 may not edit. A branch that
    enrolled without it would be judged by a helper it could rewrite.

    **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone: appending
    ``GO_REACHABILITY_ANALYZER`` to ``ANALYZERS`` reddens this row on the first
    assertion, and the module's own import-time guard
    (``_refuse_enrolment_before_flooring``) then refuses the import outright,
    which is the second, independent refusal working.
    """
    assert csr.ANALYZERS == (), (
        "ANALYZERS grew a row; enrolment is a separate decision with separate "
        "evidence, and this unit does not make it"
    )
    assert csr.analyzer_for_path("cmd/gates/preserve.go") is None
    assert csr.analyzer_for_path("src/claude_dispatcher/risk.py") is None

    from claude_dispatcher.role_protocol import FLOOR_GLOBS

    assert not any(GO_REACHABILITY_PACKAGE_DIR in glob for glob in FLOOR_GLOBS), (
        "the Go reachability helper reached FLOOR_GLOBS; that entry and its "
        "literal row in _FLOOR_ROWS are one P4 commit, not a P2 one"
    )


# =========================================================================== #
# Part 2 — where the helper is
# =========================================================================== #


def test_the_helper_directory_is_derived_from_this_packages_own_location(tmp_path, monkeypatch):
    """Resolved against this module's ``__file__``, and against nothing else.

    The rule binds harder here than in D4 because this helper computes a CALL
    GRAPH: a helper read out of the judged repository would be a call-graph
    analyzer supplied by the branch whose call graph it is computing. The row
    redirects the module's own ``__file__`` — which is exactly the input the
    contract says the answer is a pure function of — and then builds each of the
    three refusals under ``tmp_path``. Redirecting ``__file__`` is also what
    makes the row honest: nothing is written into ``src/``.

    Four states in one call, so a body that met one by accident fails the rest:
    the happy path, an absent directory, each absent entry point, and a symlink
    that escapes the package while satisfying every existence check.

    GREEN at HEAD (the function is one of the seven the scaffold implemented).
    **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone: deleting the
    containment check reddens this row; deleting the entry-point loop reddens
    it; **deleting the ``is_dir`` check alone does NOT**, and that is recorded
    rather than repaired. An absent directory is also an absent ``main.go``, so
    the entry-point loop catches it and the ``is_dir`` guard is not
    independently observable from outside. That is the contract's own sentence
    — *"all three are the same fact: the helper this build claims to ship is
    not there"* — and it is why this row asserts the FAULT rather than which of
    the three refusals produced it. A row that asserted the message would be
    pinning a branch the contract says is interchangeable.
    """
    # Happy path, against the real install.
    real = go_reachability_helper_dir()
    assert real.is_dir() and real.name == GO_REACHABILITY_PACKAGE_DIR
    assert real.parent == Path(gr.__file__).resolve().parent

    package = tmp_path / "claude_dispatcher"
    package.mkdir()
    monkeypatch.setattr(gr, "__file__", str(package / "go_reachability.py"))

    with pytest.raises(AnalyzerUnavailable) as absent:
        go_reachability_helper_dir()
    assert absent.value.fault is AnalyzerFault.HELPER_MISSING, (
        "an install that dropped the asset is a broken install, never 'this "
        "build has no Go analysis' — the second reading hands every Go branch "
        "a clean bill of health for as long as the install stays broken"
    )

    helper = package / GO_REACHABILITY_PACKAGE_DIR
    helper.mkdir()
    for entry in GO_REACHABILITY_HELPER_ENTRY_POINTS:
        for other in GO_REACHABILITY_HELPER_ENTRY_POINTS:
            (helper / other).write_text("x")
        (helper / entry).unlink()
        with pytest.raises(AnalyzerUnavailable) as missing:
            go_reachability_helper_dir()
        assert missing.value.fault is AnalyzerFault.HELPER_MISSING
        assert entry in str(missing.value), (
            f"the refusal must name {entry}; go.mod pins the module to stdlib "
            "only and fixes the language version the parse runs under, so an "
            "install that dropped it reaches go build and fails there with a "
            "module error, which names the wrong party"
        )

    for other in GO_REACHABILITY_HELPER_ENTRY_POINTS:
        (helper / other).write_text("x")
    outside = tmp_path / "judged_tree"
    outside.mkdir()
    (outside / "main.go").write_text("package main")
    (helper / "main.go").unlink()
    (helper / "main.go").symlink_to(outside / "main.go")
    with pytest.raises(AnalyzerUnavailable) as escaped:
        go_reachability_helper_dir()
    assert escaped.value.fault is AnalyzerFault.HELPER_MISSING, (
        "a symlink from main.go into the judged tree satisfies every existence "
        "check while restoring the exact defect this unit exists to prevent, "
        "with a one-byte artifact"
    )


def test_the_helper_is_two_files_and_its_module_requires_nothing(tmp_path):
    """Stdlib only, forever — and ``go.mod`` is a parser input, not packaging.

    *"A dependency would need a module cache, and a module cache is a network
    fetch and a writable HOME on the gate path"* — two more ways to be
    ``TOOLCHAIN_UNUSABLE`` in CI, which is a fail-open surface on the gate path.
    The row reads the shipped ``go.mod`` and refuses a ``require`` directive, so
    the day somebody reaches for ``x/tools/go/ssa`` — which is the CORRECT tool
    for this job and would resolve interface dispatch properly — the trade is
    made in a P4 round rather than in an import line.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    adding ``require golang.org/x/tools v0.24.0`` to the helper's ``go.mod``
    reddens the last assertion; the entry-point assertion is independent and
    reddens on removing either name from the tuple.
    """
    assert GO_REACHABILITY_HELPER_ENTRY_POINTS == ("main.go", "go.mod")
    directory = go_reachability_helper_dir()
    module = (directory / "go.mod").read_text()
    assert re.search(r"^module\s+\S+", module, flags=re.MULTILINE)
    assert "require" not in module, (
        "the helper's module grew a dependency; stdlib only, forever — a "
        "module cache is a network fetch and a writable HOME on the gate path"
    )
    assert all((directory / name).is_file() for name in GO_REACHABILITY_HELPER_ENTRY_POINTS)


# =========================================================================== #
# Part 3 — the one spelling of a key
# =========================================================================== #


def test_the_two_acceptance_declarations_get_two_keys_and_an_unqualified_one_collides():
    """The collision is real, is in the fixture, and is what the qualifier buys.

    **Measured under** ``claude-workflow`` @ ``83b0b97``, 2026-08-11: seven
    modules declare ``package main``, and ``cmd/gates`` and ``cmd/iterate`` each
    declare a top-level ``func VerifyPreservation`` with an identical signature.
    Under D5's :class:`Symbol` — ``path`` and ``line`` are
    ``field(compare=False)`` — a collision is one symbol wearing two
    declarations, and the seven findings the two subjects owe would become four.

    The control is in the same call and is the whole evidence: the unqualified
    spelling ``main.VerifyPreservation`` is constructed alongside and shown to
    collide, so "the two keys differ" is not satisfiable by any spelling that
    happens to differ.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    dropping ``package_dir`` from ``go_symbol_key``'s qualifier reddens the
    first assertion; dropping ``module_path`` reddens it too, because the two
    modules' ``cmd/`` directories are named differently but the module paths are
    what the fixture's two ``go.mod`` files differ in.
    """
    gates = go_symbol_key(_GATES_MODULE, "cmd/gates", "main", None, _SUBJECT_NAME)
    iterate = go_symbol_key(_ITERATE_MODULE, "cmd/iterate", "main", None, _SUBJECT_NAME)

    assert gates != iterate, (
        "the two acceptance subjects share a key; D5's Symbol compares on key "
        "alone, so this is one symbol in two files at once and the seven "
        "findings collapse to four"
    )
    assert gates == f"{_GATES_MODULE}/cmd/gates.{_SUBJECT_NAME}"
    assert iterate == f"{_ITERATE_MODULE}/cmd/iterate.{_SUBJECT_NAME}"

    # The control, MEASURED off the fixture rather than asserted: the two
    # packages' clauses are the SAME WORD, so nothing but the module path and
    # the directory can separate the keys. If they differed, the assertion
    # above would prove nothing about the qualifier.
    clauses = {
        re.search(r"^package (\w+)$", (_FIXTURE / module / "preserve.go").read_text(),
                  flags=re.MULTILINE).group(1)
        for module in ("cmd/gates", "cmd/iterate")
    }
    assert clauses == {"main"}, (
        f"the control failed: the two packages are {clauses}, so they are "
        "separable without the qualifier and this row proves nothing"
    )
    assert f"main.{_SUBJECT_NAME}" == f"main.{_SUBJECT_NAME}"

    assert Symbol(key=gates, path="cmd/gates/preserve.go", line=1) != Symbol(
        key=iterate, path="cmd/iterate/preserve.go", line=1
    )
    assert Symbol(key=gates, path="a.go", line=1) == Symbol(key=gates, path="b.go", line=9), (
        "the premise of the whole row: D5's Symbol identity is over key alone, "
        "which is why a shared key is a merge and not a near-miss"
    )


def test_an_external_test_package_never_shares_a_key_with_the_package_beside_it():
    """``foo`` and ``foo_test`` are the one pair Go lets share a directory.

    The scaffold records this as a defect found in its OWN first draft — the
    parameter was missing, so the two produced one key — and recording it rather
    than quietly fixing it is why the seal can be written against the reasoning:
    *a key unique over the inputs somebody happened to think of.* The ``_test``
    suffix on a PACKAGE CLAUSE is a total discriminator by the language's spec,
    not a heuristic, and it is applied to the QUALIFIER so the two packages'
    symbol sets can never interleave.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    removing the ``package_name`` branch from ``go_symbol_key`` reddens the
    first assertion; applying the suffix to the MEMBER instead of the qualifier
    keeps the first assertion green and reddens the third, which is why the
    third is there.
    """
    inside = go_symbol_key("example.com/m", "p", "foo", None, "Helper")
    outside = go_symbol_key("example.com/m", "p", "foo_test", None, "Helper")

    assert inside != outside
    assert outside == "example.com/m/p[foo_test].Helper"
    assert outside.startswith("example.com/m/p[foo_test]."), (
        "the discriminator belongs on the QUALIFIER; on the member, the two "
        "packages' symbol sets interleave in one namespace"
    )
    # A package merely CONTAINING the suffix is not the external test package.
    assert go_symbol_key("example.com/m", "p", "foo_testing", None, "Helper") == (
        "example.com/m/p.Helper"
    )


def test_a_pointer_receiver_and_a_value_receiver_are_two_bodies_here():
    """The deliberate divergence from the fingerprinter, and why it is safe.

    ``go_signature_fingerprint``'s ``receiverBaseName`` STRIPS ``*`` so that
    changing a receiver's pointer-ness reads as one symbol changing rather than
    two swapping. That is right for "did this contract change" and wrong for
    "does execution arrive here": ``func (T) M`` and ``func (*T) M`` are two
    bodies. Go forbids declaring both, so the keys cannot collide by accident,
    and the divergence costs nothing.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    stripping ``*`` in ``go_symbol_key`` reddens the first assertion.
    """
    value = go_symbol_key("example.com/m", "p", "main", "Config", "Match")
    pointer = go_symbol_key("example.com/m", "p", "main", "*Config", "Match")
    generic = go_symbol_key("example.com/m", "p", "main", "*Set[T]", "Add")

    assert value != pointer
    assert value == "example.com/m/p.(Config).Match"
    assert pointer == "example.com/m/p.(*Config).Match"
    assert generic == "example.com/m/p.(*Set[T]).Add", (
        "the receiver travels EXACTLY as written; normalising type arguments "
        "here would be a second spelling of a key, in the module whose whole "
        "job is that there is one"
    )


def test_the_synthetic_spellings_cannot_be_produced_by_any_go_declaration():
    """``<vars>`` and ``<init:N>`` are synthetic BECAUSE a root needs a symbol.

    A root with no symbol has no outgoing edges and would contribute silently
    nothing, which is the failure this module is about. And ``init`` alone is
    not a key: the spec permits several ``func init()`` per package and real
    code uses them, so ``init`` is a duplicate key waiting to happen — which is
    the decoder's rule 9 fault, i.e. a whole-response refusal.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    respelling ``GO_PACKAGE_VAR_SYMBOL`` as ``"vars"`` reddens the last
    assertion, because ``vars`` is a legal Go identifier and would collide with
    a declaration named ``vars``.
    """
    assert GO_PACKAGE_VAR_SYMBOL == "<vars>"
    assert GO_INIT_SYMBOL_TEMPLATE.format(ordinal=0) == "<init:0>"
    assert GO_INIT_SYMBOL_TEMPLATE.format(ordinal=1) != GO_INIT_SYMBOL_TEMPLATE.format(
        ordinal=0
    ), "several func init() per package are legal; one key for all of them is rule 9"

    identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for synthetic in (GO_PACKAGE_VAR_SYMBOL, GO_INIT_SYMBOL_TEMPLATE.format(ordinal=0)):
        assert not identifier.match(synthetic), (
            f"{synthetic!r} is a legal Go identifier, so a declaration could "
            "produce it and the synthetic symbol could collide with a real one"
        )


# =========================================================================== #
# Part 4 — the naming half of "is this a test"
# =========================================================================== #


@pytest.mark.parametrize(
    "name,expected",
    [
        ("TestSeal_G1_VerifyPreservation_RefusesWhatItCannotCheck", True),
        ("TestMain", True),
        ("Test", True),
        ("Testify", False),
        ("TestingTheWaters", False),
        ("BenchmarkX", True),
        ("Benchmarking", False),
        ("Fuzz", True),
        ("FuzzyMatch", False),
        ("Example", True),
        ("ExampleFoo", True),
        ("Example_suffix", True),
        ("Examples", False),
        ("VerifyPreservation", False),
        ("mustParse", False),
        ("", False),
    ],
)
def test_the_test_name_rule_is_gos_rune_check_and_not_a_prefix_match(name, expected):
    """``cmd/go``'s ``isTest``: the prefix, then a rune that is not lower-case.

    Both wrong answers are intolerable in the way :class:`RootKind` describes: a
    test root read as production silently certifies everything below it, and a
    production root read as test floods the report with false BREACHes. The
    parameters are chosen so that ``startswith`` alone is red on four of them —
    ``Testify``, ``TestingTheWaters``, ``Benchmarking``, ``FuzzyMatch`` and
    ``Examples`` — and so that
    the rune rule's own edge, a bare prefix with nothing after it, is present in
    all four spellings' worth of shape.

    ``TestMain`` is True and that is correct rather than a corner: it IS an
    entrypoint, it is the one ``go test`` calls first, and everything it reaches
    is genuinely reached under test.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    replacing the rune check with ``startswith`` reddens exactly the five
    lower-case-continuation parameters and nothing else; deleting ``"Fuzz"``
    from the prefix table reddens exactly ``Fuzz``.
    """
    assert go_test_root_predicate(name) is expected


def test_every_acceptance_seal_is_a_test_root_and_the_helpers_are_not():
    """Measured over the vendored text, not over names this author chose.

    The naming half is only half: ``discover_seals`` requires ``is_test_path``
    over the declaring file too, and this module does not re-ask that question.
    The row asserts both halves over the real fixture, and the 42 ``g1``/``g2``
    helpers supply the negative population — a predicate that accepted them
    would make every helper a root and flood the report.

    **Measured under** ``claude-workflow`` @ ``83b0b97``, 2026-08-11, and it is
    a correction to this row's first draft: ``cmd/iterate``'s helper file
    declares a REAL Go test, ``func TestDebit``, beside ``func Debit``. It is
    not a false positive — it is a test, in a test file, and ``go test`` runs
    it — so the row names it rather than excluding the file. ``cmd/gates``'s
    helper file declares none. A row asserting "no helper file holds a test"
    would have been a claim about a population nobody had counted.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    ``startswith`` in ``go_test_root_predicate`` leaves this row green (no name
    in the fixture has a lower-case continuation after a prefix), which is
    exactly why the parametrized row above exists and why this one is not a
    substitute for it.
    """
    #: The one helper-file test in the fixture, measured. Named here so that the
    #: negative population below is the helpers and not "whatever is left".
    incidental_tests = {"cmd/gates": frozenset(), "cmd/iterate": frozenset({"TestDebit"})}

    for module, seals in _ACCEPTANCE_SEALS.items():
        seal_file = _FIXTURE / module / "preserve_seal_test.go"
        declared = set(
            re.findall(r"^func (\w+)\(t \*testing\.T\)", seal_file.read_text(),
                       flags=re.MULTILINE)
        )
        assert set(seals) <= declared, (
            f"a seal this file names is not declared in {module}; the fixture "
            "and the expectation have drifted"
        )
        for name in seals:
            assert go_test_root_predicate(name) is True
        assert is_test_path(f"{module}/preserve_seal_test.go") is True

        helpers = _FIXTURE / module / "preserve_seal_helpers_test.go"
        helper_names = set(
            re.findall(r"^func (\w+)\(", helpers.read_text(), flags=re.MULTILINE)
        )
        assert len(helper_names) >= 18, (
            "the negative population is too small to prove anything"
        )
        accepted = {n for n in helper_names if go_test_root_predicate(n)}
        assert accepted == incidental_tests[module], (
            f"{module}'s helper file: expected {incidental_tests[module]} to "
            f"read as test entrypoints and got {accepted}; every other helper "
            "becoming a root would flood the report with false BREACHes"
        )


def test_the_row_reads_the_member_and_never_the_module_path():
    """A module whose name begins with ``Test`` must not make everything a root.

    The contract says it in as many words and the failure is silent: every
    symbol in such a module becomes a TEST_FUNCTION root, ``_validate_root``
    raises because those symbols are not in test files, and the whole check dies
    on a repository whose only sin is its module name.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    ``test_root_predicate`` reading ``symbol.key`` whole instead of its last
    segment reddens the first assertion.
    """
    row = GoReachabilityAnalyzer()
    trap = Symbol(key="example.com/TestSuite/p.helper", path="p/main.go", line=1)
    assert row.test_root_predicate(trap) is False

    seal = Symbol(key="example.com/TestSuite/p.TestSeal_X",
                  path="p/main_test.go", line=1)
    assert row.test_root_predicate(seal) is True

    method = Symbol(key="example.com/m/p.(*Config).Match", path="p/main.go", line=1)
    assert row.test_root_predicate(method) is False


def test_the_rows_test_id_is_the_directory_spelling_go_test_run_takes():
    """``cmd/gates.TestSeal_G1_…`` — derived from the DIRECTORY, not the module.

    A human runs ``go test ./cmd/gates -run TestSeal_G1_…`` from a directory and
    not from an import path, so a ``test_id`` built off ``module_path`` sends
    people to a string ``go test`` does not take. The row is ahead of the
    protocol on purpose (D5 ESCALATED the four coupled edits) and changes no
    verdict — ``test_id`` is a label and no dispatch reads it — which is exactly
    why it needs a seal: nothing else would notice it being wrong.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    deriving from ``symbol.key``'s qualifier instead of ``symbol.path`` yields
    ``github.com/yourorg/claude-workflow/gates/cmd/gates.TestSeal_…`` and reddens
    the first assertion.
    """
    row = GoReachabilityAnalyzer()
    seal = Symbol(
        key=f"{_GATES_MODULE}/cmd/gates.{_ACCEPTANCE_SEALS['cmd/gates'][0]}",
        path="cmd/gates/preserve_seal_test.go",
        line=358,
    )
    assert row.test_id(seal) == f"cmd/gates.{_ACCEPTANCE_SEALS['cmd/gates'][0]}"
    assert _GATES_MODULE not in row.test_id(seal), (
        "the module path is not a directory a human can cd into"
    )

    bare = Symbol(key="example.com/m.Loose", path="main.go", line=1)
    assert row.test_id(bare) == "Loose", "a symbol at the tree root has no directory"


# =========================================================================== #
# Part 5 — the two wire vocabularies, and the case whose absence is the answer
# =========================================================================== #


@pytest.mark.parametrize(
    "wire,kind",
    [
        ("direct", EdgeKind.DIRECT),
        ("method", EdgeKind.METHOD),
        ("interface", EdgeKind.INTERFACE),
        ("reference", EdgeKind.REFERENCE),
    ],
)
def test_each_wire_edge_kind_maps_to_exactly_one_edge_kind(wire, kind):
    """The table, member by member.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    deleting any one row from ``_EDGE_KIND_BY_WIRE`` reddens exactly that
    parameter, and no other.
    """
    assert edge_kind_for_wire(wire) is kind


def test_the_edge_kind_table_raises_rather_than_defaulting_and_names_four():
    """A default on this dispatch decides for the whole repository, silently.

    It decides whether an unmarked over-approximation reads as the strong pass,
    which is D5's own argument for ``_RESOLVED_EDGE_KINDS`` being two tables. A
    fifth kind is refused by name because the one thing that must never become a
    kind is a call the walk cannot name at all: naming it a fifth kind invites a
    body to treat the absence of a target as a target.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    replacing the ``raise`` with ``return EdgeKind.DIRECT`` reddens the first
    two assertions; the fault-member assertion is independent and reddens on
    returning ``HELPER_FAILED``, which would blame the process rather than the
    document.
    """
    for absent in ("dynamic", "unresolved", "satisfies", "embedded", "DIRECT", ""):
        with pytest.raises(AnalyzerUnavailable) as refused:
            edge_kind_for_wire(absent)
        assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID

    assert set(gr._EDGE_KIND_BY_WIRE) == {"direct", "method", "interface", "reference"}
    assert set(gr._EDGE_KIND_BY_WIRE.values()) == set(EdgeKind), (
        "every EdgeKind must be reachable from the wire; a member no dispatch "
        "emits will never fire and will be read as coverage"
    )


def test_exactly_the_two_marked_kinds_are_the_two_d5_calls_unresolved():
    """The Python face of the grammar must agree with D5's strength classes.

    Two of the four force :attr:`PathQuality.OVER_APPROXIMATED` and two do not,
    and the two tables live in different modules. If they disagree, an
    over-approximated path is spelled like a resolved one — a REPORT read as an
    OK — and nothing else in the system would notice.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    moving ``EdgeKind.METHOD`` into ``_OVER_APPROXIMATING_EDGE_KINDS`` in D5
    reddens this row, which is the point — this row is a cross-module agreement
    check and is red when EITHER side moves.
    """
    resolved = {edge_kind_for_wire("direct"), edge_kind_for_wire("method")}
    approximating = {edge_kind_for_wire("interface"), edge_kind_for_wire("reference")}

    assert all(csr._edge_is_resolved(kind) for kind in resolved)
    assert not any(csr._edge_is_resolved(kind) for kind in approximating)
    assert resolved | approximating == set(EdgeKind)
    assert not resolved & approximating


@pytest.mark.parametrize(
    "wire,kind",
    [
        ("go_main", EntrypointKind.GO_MAIN),
        ("go_init", EntrypointKind.GO_INIT),
        ("go_package_var", EntrypointKind.GO_PACKAGE_VAR),
        ("test_function", EntrypointKind.TEST_FUNCTION),
    ],
)
def test_each_wire_entrypoint_kind_maps_to_exactly_one_entrypoint_kind(wire, kind):
    """Four members and no more; every other member of the enum is Python's.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    deleting any one row reddens exactly that parameter.
    """
    assert entrypoint_kind_for_wire(wire) is kind


def test_the_entrypoint_table_has_no_public_api_member_and_the_fixture_says_why():
    """A rule that made an exported symbol a root would certify the defect.

    This is not an abstract preference and the fixture measures it:
    ``VerifyPreservation`` is EXPORTED, in both modules. A ``PUBLIC_API``
    entrypoint kind would make it a production root, so the mechanism built to
    catch this defect would report it REACHED on its first run — against the
    very tree it was built for.

    The row also refuses the four Python kinds on the Go wire: a Go row emitting
    ``python_import_time`` would be claiming a start it cannot derive.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    adding ``"public_api": EntrypointKind.GO_MAIN`` to
    ``_ENTRYPOINT_KIND_BY_WIRE`` reddens the first assertion here AND the
    ``11 a root kind outside the vocabulary`` parameter of the decoder row —
    two rows, which is what a vocabulary that two layers read should do.
    """
    assert set(gr._ENTRYPOINT_KIND_BY_WIRE) == {
        "go_main", "go_init", "go_package_var", "test_function"
    }
    assert not any("public" in wire for wire in gr._ENTRYPOINT_KIND_BY_WIRE)

    for python_kind in (
        "python_console_script", "python_module_main",
        "python_script_main", "python_import_time",
    ):
        with pytest.raises(AnalyzerUnavailable) as refused:
            entrypoint_kind_for_wire(python_kind)
        assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID, (
            "a root whose kind this module cannot classify is not a root, and "
            "skipping it would make everything below it a false BREACH"
        )

    production = {
        entrypoint_kind_for_wire(w)
        for w in ("go_main", "go_init", "go_package_var")
    }
    assert all(csr._ROOT_KIND_BY_ENTRYPOINT[k] is csr.RootKind.PRODUCTION for k in production)
    assert csr._ROOT_KIND_BY_ENTRYPOINT[
        entrypoint_kind_for_wire("test_function")
    ] is csr.RootKind.TEST


# =========================================================================== #
# Part 6 — the request
# =========================================================================== #


def test_the_request_is_one_object_carrying_the_schema_the_unit_and_the_files():
    """RED at HEAD: ``encode_go_reachability_request`` raises NotImplementedError.

    The document's shape is the contract's, field for field. ``source`` travels
    VERBATIM — BOM, CRLF and all — because normalising here would make the
    Python and Go sides disagree about what the file says, and that disagreement
    would show up as a missing edge, which is indistinguishable from an edge
    that does not exist.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone, with the reference body in place, it
    is green, and it reddens again on emitting the schema from the request
    argument instead of from :data:`GO_REACHABILITY_SCHEMA` — the mutation that
    would let a stale caller and a current helper agree to disagree.
    """
    unit = GoUnit(module_path=_GATES_MODULE, package_dir="cmd/gates", package_name="main")
    files = (
        GoSourceFile(path="cmd/gates/main.go", source="package main\r\n\r\nfunc main() {}\n"),
        GoSourceFile(path="cmd/gates/preserve.go", source="﻿package main\n"),
    )

    document = json.loads(encode_go_reachability_request(unit, files))

    assert document["schema"] == GO_REACHABILITY_SCHEMA
    assert document["unit"] == {
        "module_path": _GATES_MODULE,
        "package_dir": "cmd/gates",
        "package_name": "main",
    }
    assert [f["path"] for f in document["files"]] == [f.path for f in files]
    assert [f["source"] for f in document["files"]] == [f.source for f in files], (
        "source must survive verbatim; a normalised CRLF or a stripped BOM "
        "makes the two sides disagree about what the file says"
    )
    assert set(document) == {"schema", "unit", "files"}


def test_the_request_survives_a_source_that_is_not_valid_utf8():
    """RED at HEAD. ``ensure_ascii=True`` is not a style choice.

    ``source`` is whatever the read accepted, which can include lone surrogates
    from a blob that is not valid UTF-8. ``ensure_ascii=False`` RAISES on
    encoding those, which turns a bad FILE — a fact about the branch — into an
    environment fault, i.e. into a whole-check outage.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    ``ensure_ascii=False``, with ``UnicodeEncodeError: 'utf-8' codec can't
    encode character '\\udcff'`` — the exact failure the flag exists to prevent.
    """
    unit = GoUnit(module_path="example.com/m", package_dir="p", package_name="main")
    lone_surrogate = "package main // \udcff\n"
    files = (GoSourceFile(path="p/main.go", source=lone_surrogate),)

    document = encode_go_reachability_request(unit, files)

    assert document.isascii(), (
        "the encoded request must be ASCII; a lone surrogate in a source file "
        "is a fact about the branch and must not become an environment fault"
    )
    assert json.loads(document)["files"][0]["source"] == lone_surrogate


def test_two_encodings_of_one_package_are_one_byte_string():
    """RED at HEAD. A nondeterministic request makes the witness nondeterministic.

    ``main.go`` contracts edge order as REQUEST order, and the witness path is
    the whole evidence a BREACH offers. If the request is not byte-stable, two
    runs over one tree hand a human two different paths to check for one
    unchanged defect.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    ``sort_keys=True`` combined with a dict built in a different order — which
    is the shape a body reaches for when it thinks determinism means sorting.
    """
    unit = GoUnit(module_path="example.com/m", package_dir="p", package_name="main")
    files = (
        GoSourceFile(path="p/a.go", source="package main\n"),
        GoSourceFile(path="p/b.go", source="package main\n"),
    )
    first = encode_go_reachability_request(unit, files)
    second = encode_go_reachability_request(unit, files)
    assert first == second

    swapped = encode_go_reachability_request(unit, tuple(reversed(files)))
    assert swapped != first, (
        "the caller sorts and the helper contracts edge order as REQUEST order; "
        "an encoder that re-sorted would take that decision away from the caller"
    )


# =========================================================================== #
# Part 7 — the response, and the twelve ways it can be wrong
# =========================================================================== #


@pytest.mark.parametrize(
    "rule,document",
    [
        ("1 empty stdout", ""),
        ("1 whitespace only", "   \n\t "),
        ("2 not JSON", "{not json"),
        ("2 a JSON value that is not an object", "[]"),
        ("2 a JSON scalar", "3"),
        ("3 schema absent", {"unit": {}, "symbols": []}),
        ("3 schema is another version", {"schema": "x/v0"}),
        ("4 unit absent", "no-unit"),
        ("4 unit is not an object", "unit-scalar"),
        ("5 parse_error AND arrays", "both"),
        ("5 neither parse_error nor arrays", "neither"),
        ("6 parse_error with an empty path", "parse-error-empty-path"),
        ("6 parse_error is not an object", "parse-error-scalar"),
        ("7 symbols absent", "drop-symbols"),
        ("7 roots absent", "drop-roots"),
        ("7 edges absent", "drop-edges"),
        ("7 unresolved absent", "drop-unresolved"),
        ("7 an array is not a list", "symbols-not-a-list"),
        ("8 a record is not an object", "symbol-scalar"),
        ("8 a key that is not a non-empty string", "symbol-empty-key"),
        ("8 a line that is not a positive integer", "symbol-zero-line"),
        ("8 a line that is a bool", "symbol-bool-line"),
        ("9 a duplicate symbol key", "duplicate-key"),
        ("10 a duplicate root symbol", "duplicate-root"),
        ("10 a root naming an undeclared symbol", "undeclared-root"),
        ("11 an edge kind outside the vocabulary", "bad-edge-kind"),
        ("11 a root kind outside the vocabulary", "bad-root-kind"),
        ("12 an edge from an undeclared caller", "edge-from-nowhere"),
        ("12 a hole from an undeclared caller", "hole-from-nowhere"),
    ],
)
def test_the_decoder_refuses_every_malformed_class_its_contract_lists(rule, document):
    """RED at HEAD. The list is EXHAUSTIVE and this row is total over it.

    Twelve numbered classes, several with more than one shape, and every one is
    :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID` — never ``HELPER_FAILED``, which
    would blame the process for a document, and never a best-effort read. The
    parameter ids carry the rule number so a body author reading a failure sees
    which sentence they broke.

    Rule 9 gets its own row below because its CONSEQUENCE is the sharpest thing
    in this unit and cannot be shown by a refusal alone.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError`` on all 29 parameters. In the clone with the
    reference body: all 29 green, and each of five sampled mutations reddens
    exactly its own parameters and no others — dropping the empty-stdout guard
    reddens 2, dropping the duplicate-key guard reddens 1, dropping the
    required-array check reddens 5, dropping the ``caller`` membership check
    reddens 2, and returning ``HELPER_FAILED`` instead reddens all 29.
    """
    stdout = _malformed(document)
    with pytest.raises(AnalyzerUnavailable) as refused:
        decode_go_reachability_response(stdout)
    assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID, (
        f"{rule}: every way a document can be wrong is HELPER_OUTPUT_INVALID; "
        "HELPER_FAILED would blame the process for the document"
    )


def _malformed(document) -> str:
    """Build one malformed stdout. Written out per case, never generated."""
    if isinstance(document, str) and document not in _MALFORMED_BUILDERS:
        return document
    if isinstance(document, dict):
        return json.dumps(document)
    return json.dumps(_MALFORMED_BUILDERS[document]())


def _drop(field):
    def build():
        document = _response_document()
        del document[field]
        return document
    return build


def _mutate(mutation):
    def build():
        document = _response_document()
        mutation(document)
        return document
    return build


_MALFORMED_BUILDERS = {
    "no-unit": _drop("unit"),
    "unit-scalar": _mutate(lambda d: d.__setitem__("unit", "cmd/gates")),
    "both": _mutate(
        lambda d: d.__setitem__("parse_error", {"path": "p/a.go", "message": "boom"})
    ),
    "neither": lambda: {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": _response_document()["unit"],
    },
    "parse-error-empty-path": lambda: {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": _response_document()["unit"],
        "parse_error": {"path": "", "message": "boom"},
    },
    "parse-error-scalar": lambda: {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": _response_document()["unit"],
        "parse_error": "boom",
    },
    "drop-symbols": _drop("symbols"),
    "drop-roots": _drop("roots"),
    "drop-edges": _drop("edges"),
    "drop-unresolved": _drop("unresolved"),
    "symbols-not-a-list": _mutate(lambda d: d.__setitem__("symbols", {})),
    "symbol-scalar": _mutate(lambda d: d["symbols"].append("example.com/tiny/p.X")),
    "symbol-empty-key": _mutate(
        lambda d: d["symbols"].append(
            {"key": "", "path": "p/main.go", "line": 1, "kind": "func"}
        )
    ),
    "symbol-zero-line": _mutate(
        lambda d: d["symbols"].append(
            {"key": "example.com/tiny/p.Z", "path": "p/main.go", "line": 0,
             "kind": "func"}
        )
    ),
    "symbol-bool-line": _mutate(
        lambda d: d["symbols"].append(
            {"key": "example.com/tiny/p.Z", "path": "p/main.go", "line": True,
             "kind": "func"}
        )
    ),
    "duplicate-key": _mutate(
        lambda d: d["symbols"].append(
            {"key": "example.com/tiny/p.Dark", "path": "p/main_test.go", "line": 9,
             "kind": "func"}
        )
    ),
    "duplicate-root": _mutate(
        lambda d: d["roots"].append(
            {"symbol": "example.com/tiny/p.main", "kind": "go_main", "evidence": "again"}
        )
    ),
    "undeclared-root": _mutate(
        lambda d: d["roots"].append(
            {"symbol": "example.com/tiny/p.Ghost", "kind": "go_main", "evidence": "x"}
        )
    ),
    "bad-edge-kind": _mutate(lambda d: d["edges"][0].__setitem__("kind", "satisfies")),
    "bad-root-kind": _mutate(lambda d: d["roots"][0].__setitem__("kind", "public_api")),
    "edge-from-nowhere": _mutate(
        lambda d: d["edges"].append(
            {"caller": "example.com/tiny/p.Ghost",
             "callee": "example.com/tiny/p.Dark", "kind": "direct",
             "site": "p/main.go:1"}
        )
    ),
    "hole-from-nowhere": _mutate(
        lambda d: d["unresolved"].append(
            {"caller": "example.com/tiny/p.Ghost", "site": "p/main.go:1",
             "detail": "x"}
        )
    ),
}


def test_the_schema_is_checked_before_anything_else_is_read():
    """RED at HEAD. It is what makes ignoring unknown fields safe.

    A document that is wrong in four other ways AND carries the wrong schema
    must be refused FOR THE SCHEMA. The order is not cosmetic: the
    ignore-unknown-fields CHOICE rests on it — an unknown field can only arrive
    from a document that has already lied about its version — and a decoder that
    validated records first would report the fourth-most-interesting fact about
    a document from a helper it should never have spoken to.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and moving the schema
    check below the array checks reddens it with a message naming the missing
    arrays instead.
    """
    hostile = {
        "schema": "claude-dispatcher/go-call-reachability/v0",
        "unit": "not an object",
        "symbols": {},
        "parse_error": "also wrong",
    }
    with pytest.raises(AnalyzerUnavailable) as refused:
        decode_go_reachability_response(json.dumps(hostile))
    assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID
    assert GO_REACHABILITY_SCHEMA in str(refused.value), (
        "the refusal must name the schema; checked FIRST is the sentence that "
        "makes ignoring unknown fields safe"
    )


def test_a_duplicate_symbol_key_is_refused_because_it_can_turn_a_breach_into_an_exclusion():
    """RED at HEAD. The sharpest consequence in this unit, with the flip shown.

    The sibling's duplicate-key guard exists because two fingerprints for one
    key means one is unreachable. Here it is worse and the reason is D5's own
    dataclass: :class:`Symbol` declares ``path`` and ``line`` as
    ``field(compare=False)``, so identity is over ``key`` alone and two records
    with one key are ONE symbol whose ``path`` is decided by dict insertion
    order — and ``path`` is what ``seal_verify.is_test_path`` reads to decide
    whether a symbol is EXCLUDED from a subject set.

    The control demonstrates the flip through D5's real
    :func:`~claude_dispatcher.call_site_reachability.subjects_of_seal`, judged
    in this same call, so the refusal is shown to be preventing a verdict change
    rather than enforcing tidiness: with the production ``path`` winning, the
    seal has a subject; with the test ``path`` winning, the identical graph
    yields :attr:`SubjectGap.ALL_TARGETS_IN_TESTS` and NO finding at all.

    **The gap was live once already**, in the module this one is modelled on:
    the scaffold records removing ``role_protocol._decode_helper_response``'s
    ``if name in seen`` raise and measuring **2 failed, 2311 passed, 13 skipped**
    on ``feat/D6-go-analyzer`` @ ``0238aa2``, both failures in D4's shared row.
    The interesting fact is not that it is covered now.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and deleting the
    ``key in seen`` raise reddens it together with the ``9 a duplicate symbol
    key`` parameter of the decoder row — two rows and no others, so the guard
    is covered here in the module it is copied FROM as well as in D4's shared
    row.
    """
    document = _response_document()
    document["symbols"].append(
        {"key": "example.com/tiny/p.Dark", "path": "p/main_test.go", "line": 9,
         "kind": "func"}
    )
    with pytest.raises(AnalyzerUnavailable) as refused:
        decode_go_reachability_response(json.dumps(document))
    assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID

    # The control: what the two paths would have decided, through D5 itself.
    seal_symbol = Symbol(key="example.com/tiny/p.TestSeal_Dark",
                         path="p/main_test.go", line=1)
    seal = Seal(symbol=seal_symbol, test_id="p.TestSeal_Dark")

    def judged(path: str):
        subject = Symbol(key="example.com/tiny/p.Dark", path=path, line=7)
        graph = CallGraph(
            symbols={seal_symbol.key: seal_symbol, subject.key: subject},
            edges=(Edge(caller=seal_symbol, callee=subject, kind=EdgeKind.DIRECT,
                        site="p/main_test.go:4"),),
            unresolved_calls=(),
            unreadable_paths=(),
        )
        return csr.subjects_of_seal(seal, graph)

    production_won = judged("p/main.go")
    test_won = judged("p/main_test.go")

    assert [s.key for s in production_won.symbols] == ["example.com/tiny/p.Dark"]
    assert production_won.gap is None
    assert test_won.symbols == ()
    assert test_won.gap is csr.SubjectGap.ALL_TARGETS_IN_TESTS, (
        "the control failed: if both paths yielded a subject, the duplicate "
        "key could not turn a BREACH into an exclusion and the refusal above "
        "would be tidiness"
    )


def test_duplicate_edges_are_deduplicated_and_never_refused():
    """RED at HEAD. ``f(f(x))`` is ordinary Go, and blaming it is the defect.

    The consistent-looking answer is to refuse them as rule 9 refuses a
    duplicate key, and it is wrong: a nested call emits two identical
    ``(caller, callee, kind, site)`` tuples. That is the lesson
    ``go_signature_fingerprint``'s ``isBlank`` records after ``stringer`` output
    produced duplicate keys across GOROOT. A duplicate edge is the same answer
    twice, not two answers, and reachability is a set property, so the dedup
    cannot move a verdict.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    refusing duplicates (the whole document is then rejected) and separately on
    KEEPING both (the second assertion), so the row pins both directions.
    """
    document = _response_document()
    document["edges"].append(dict(document["edges"][0]))

    response = decode_go_reachability_response(json.dumps(document))

    assert len(response.edges) == 1, (
        "identical edges are the same answer twice; refusing them blames the "
        "machine for a legal program, and keeping both is a second answer"
    )
    # An edge differing only in SITE is a different answer and survives.
    document["edges"][1]["site"] = "p/main.go:99"
    assert len(decode_go_reachability_response(json.dumps(document)).edges) == 2


def test_unknown_fields_are_ignored_at_every_level():
    """RED at HEAD. The version check already owns the state this would refuse.

    A second refusal for a state the first check owns is a second answer site.
    The rejected alternative — refusing unknown fields — buys only one thing the
    version check does not, catching a field RENAMED without a schema bump, and
    rule 7 already catches that as a missing required array.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    refusing unknown fields. The rename control in the same call is what keeps
    the ignore from being a hole.
    """
    document = _response_document()
    document["future_top_level"] = 1
    document["unit"]["future_unit"] = "x"
    document["symbols"][0]["future_symbol"] = [1, 2]
    document["roots"][0]["future_root"] = None
    document["edges"][0]["future_edge"] = {"nested": True}

    response = decode_go_reachability_response(json.dumps(document))
    assert len(response.symbols) == 2 and len(response.edges) == 1

    # The control: a RENAMED required field is not an unknown field, it is a
    # missing one, and rule 7 refuses it.
    renamed = _response_document()
    renamed["symbol_list"] = renamed.pop("symbols")
    with pytest.raises(AnalyzerUnavailable):
        decode_go_reachability_response(json.dumps(renamed))


def test_a_null_array_is_absent_and_an_empty_one_is_an_answer():
    """RED at HEAD. DISPUTE D3: it is the only reading under which both hold.

    ``main.go``'s ``Response`` carries no ``,omitempty`` on the four arrays, so
    Go writes a nil slice as ``null`` and **every** ``parse_error`` document the
    scaffold's own helper can produce carries ``"symbols":null``. Adding
    ``omitempty`` is not the repair — in Go it omits an EMPTY slice too, which
    destroys "``[]`` is an answer". So ``null`` is ABSENT and ``[]`` is
    PRESENT-and-empty, which is what the contract's "``[]`` is an answer and
    ``null`` is not" is for.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone, a decoder reading ``null`` as present
    refused every ``parse_error`` document as "parse_error AND arrays", and
    ``build_call_graph`` escalated it to a whole-check
    ``CallSiteReachabilityError`` — one unparseable file taking the check down,
    which is the outage ``unreadable_paths`` exists to prevent.
    """
    as_go_writes_it = {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": _response_document()["unit"],
        "symbols": None,
        "roots": None,
        "edges": None,
        "unresolved": None,
        "parse_error": {"path": "p/main.go", "message": "expected ';', found 'is'"},
    }
    response = decode_go_reachability_response(json.dumps(as_go_writes_it))
    assert response.parse_error is not None
    assert response.parse_error.path == "p/main.go"

    empty = _response_document(symbols=[], roots=[], edges=[], unresolved=[])
    decoded = decode_go_reachability_response(json.dumps(empty))
    assert decoded.parse_error is None
    assert decoded.symbols == () and decoded.roots == (), (
        "a package declaring only a package clause and imports declares "
        "nothing, and that is an ANSWER — faulting here would fault on it"
    )


def test_a_parse_error_document_is_returned_intact_and_decides_nothing():
    """RED at HEAD. One place per decision, and this is not it.

    An unparseable file is a successful run of the helper and a fact about the
    file. The decoder returns the document; it is the ANALYZER that turns it into
    an entry in :attr:`CallGraph.unreadable_paths`. A decoder that raised
    :class:`SourceUnreadable` here would move the decision into the layer that
    cannot see how many units there are.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on raising
    ``SourceUnreadable`` from the decoder.
    """
    document = {
        "schema": GO_REACHABILITY_SCHEMA,
        "unit": _response_document()["unit"],
        "parse_error": {"path": "p/broken.go", "message": "expected declaration"},
    }
    response = decode_go_reachability_response(json.dumps(document))

    assert response.parse_error == gr.GoWireParseError(
        path="p/broken.go", message="expected declaration"
    )
    assert response.symbols == () and response.edges == ()
    assert response.unit.module_path == "example.com/tiny"


def test_a_unit_that_declares_nothing_is_an_answer_and_not_a_fault():
    """RED at HEAD. The whole-tree emptiness guard belongs a layer up.

    Faulting here is what D5's ``HELPER_OUTPUT_INVALID`` wording reads like in
    isolation, and it would fault on a file holding only a package clause and
    imports. This layer cannot see how many Go files the sweep found, so a claim
    about that population made here is a claim about a population this function
    cannot see — R1's discriminator exactly. The guard is at
    :meth:`GoReachabilityAnalyzer.graph`; see the row that pins it there.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on adding
    an "empty response" fault to the decoder.
    """
    empty = _response_document(symbols=[], roots=[], edges=[], unresolved=[])
    response = decode_go_reachability_response(json.dumps(empty))
    assert response.symbols == ()
    assert response.roots == ()
    assert response.edges == ()
    assert response.unresolved == ()
    assert response.parse_error is None


# =========================================================================== #
# Part 8 — the sweep, and the one question this module refuses to answer
# =========================================================================== #


def test_a_directory_holding_two_packages_is_two_units(tmp_path):
    """RED at HEAD. ``package foo_test`` beside ``package foo`` is two packages.

    They are two by the language's own rules — ``foo_test`` reaches ``foo`` only
    through an import, exactly as any other package does — and merging them
    would put two unqualified-identifier scopes in one resolution pass, which is
    the one thing a name-level resolver may not do. It is also the only way two
    packages can occupy one directory, so a sweep keyed on the DIRECTORY is
    wrong exactly here and nowhere else, which is why a fixture that used one
    package per directory would be green on a broken sweep.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on keying
    the sweep on ``(directory,)`` instead of ``(directory, package clause)``.
    """
    tree = _package(tmp_path, {
        "main.go": "package foo\n\nfunc Helper() int { return 1 }\n",
        "in_test.go": (
            'package foo\n\nimport "testing"\n\n'
            "func TestSeal_In(t *testing.T) { _ = Helper() }\n"
        ),
        "foo_test.go": (
            'package foo_test\n\nimport "testing"\n\n'
            "func TestSeal_X(t *testing.T) { _ = t }\n"
        ),
    }, module="example.com/m")

    units = discover_units(tree)

    assert [(u.package_dir, u.package_name) for u, _ in units] == [
        ("p", "foo"), ("p", "foo_test")
    ]
    inside = dict(units)[[u for u, _ in units if u.package_name == "foo"][0]]
    assert sorted(f.path for f in inside) == ["p/in_test.go", "p/main.go"], (
        "a package's _test.go files are IN its unit; the seals whose subjects "
        "this mechanism judges live there, and a seal the graph does not "
        "declare makes discover_seals raise"
    )


def test_the_module_path_is_the_nearest_enclosing_go_mod(tmp_path):
    """RED at HEAD. Seven ``go.mod`` files, none at the repository root.

    "The repository's ``go.mod``" is not the rule and there is not one; the
    nearest enclosing one is. A directory with no enclosing ``go.mod`` is not a
    unit and must be recorded rather than guessed at, because a synthesised
    module path is a key nobody can join to anything — and every decision in D5
    is set membership on that key.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on taking
    the OUTERMOST ``go.mod``, which is the reading that makes both packages one
    module and both keys collide when the directory names match.
    """
    tree = tmp_path / "nested"
    for module, directory in (("example.com/outer", "."), ("example.com/inner", "sub")):
        target = tree / directory
        target.mkdir(parents=True, exist_ok=True)
        (target / _LIVE_GO_MOD).write_text(f"module {module}\n\ngo 1.21\n")
        (target / "main.go").write_text("package main\n\nfunc main() {}\n")

    by_dir = {unit.package_dir: unit.module_path for unit, _ in discover_units(tree)}

    assert by_dir[""] == "example.com/outer"
    assert by_dir["sub"] == "example.com/inner", (
        "the nearest enclosing go.mod governs; the outermost one would give "
        "two directories one module and invite the collision the qualifier "
        "exists to prevent"
    )


def test_the_sweep_is_deterministic_and_writes_nothing(tmp_path):
    """RED at HEAD. The analyzer READS.

    ``main.go`` contracts edge order as request order, so a nondeterministic
    sweep makes the witness path a human is asked to check nondeterministic too
    — even where the verdict is stable. And a gate that writes into the tree it
    judges has changed the thing it is judging.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    emitting units in ``os.listdir`` order over a tree whose directory order and
    sorted order differ.
    """
    tree = _package(tmp_path, {
        "z.go": "package main\n\nfunc z() {}\n",
        "a.go": "package main\n\nfunc main() { z() }\n",
        "m.go": "package main\n\nfunc m() {}\n",
    })
    (tree / "q").mkdir()
    (tree / "q" / _LIVE_GO_MOD).write_text("module example.com/q\n\ngo 1.21\n")
    (tree / "q" / "q.go").write_text("package q\n\nfunc Q() {}\n")

    before = sorted((p.relative_to(tree).as_posix(), p.stat().st_mtime_ns)
                    for p in tree.rglob("*") if p.is_file())

    first = discover_units(tree)
    second = discover_units(tree)

    assert first == second
    assert [(u.package_dir, u.package_name) for u, _ in first] == [("p", "main"), ("q", "q")]
    assert [f.path for f in first[0][1]] == ["p/a.go", "p/m.go", "p/z.go"]

    after = sorted((p.relative_to(tree).as_posix(), p.stat().st_mtime_ns)
                   for p in tree.rglob("*") if p.is_file())
    assert before == after, "the analyzer reads; it never writes into the tree"


def test_this_module_asks_role_protocol_what_a_go_file_is_and_never_matches_one():
    """Exactly ONE ``endswith`` here, over a package CLAUSE, and no extension.

    ``role_protocol.support_for_path`` is the one place in this codebase where a
    file extension decides anything, and a second table would drift silently —
    on files neither gate had been pointed at yet. The module's one ``endswith``
    is ``package_name.endswith("_test")`` in :func:`go_symbol_key`, which is not
    a path, not an extension, and not a language decision about a judged tree:
    it is the language's own total discriminator between the two packages that
    may share a directory. The row pins that it is exactly one and that it is
    that one.

    Sealed by AST and not by grep, for D5's stated reason in both directions:
    this module's PROSE names ``main.go``, ``go.mod`` and ``.gitignore`` at
    length, so a grep is red on a clean module, and a body could hide
    ``path.endswith(".go")`` behind a line a grep pattern misses. Positive
    control in the same call: ``role_protocol.py`` must still yield both, or the
    empty result above proves only that the sweep stopped working.

    The paths are derived from ``__file__``. The D5 floor guard hit exactly this
    and had to do the same: a path literal in the seal is a literal that the
    sweep would have to be taught to ignore.

    GREEN at HEAD. **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone:
    adding ``path.endswith(".go")`` to ``discover_units``' body reddens the
    ``endswith`` count assertion and the extension assertion, independently.
    Measured 2026-08-11 at HEAD: the sweep finds exactly ``go.mod`` and
    ``main.go`` — the helper's own two entry points, which the module docstring
    names — and exactly one ``endswith``, over ``package_name``.
    """
    source = (_SRC / "go_reachability.py").read_text(encoding="utf-8")

    #: The two apparent exceptions, and they are not exceptions: they name
    #: files inside THIS package, which is the one place a filename is a fact
    #: about this build rather than a question about a judged tree. The row
    #: requires EXACTLY them, so a third literal is red whatever it spells.
    literals = sorted(value for _, value in _extension_literals(source))
    assert literals == sorted(GO_REACHABILITY_HELPER_ENTRY_POINTS), (
        f"go_reachability.py declares the filename literals {literals}; the "
        "only permitted two are the helper's own entry points "
        f"{sorted(GO_REACHABILITY_HELPER_ENTRY_POINTS)}. Exactly one place in "
        "this codebase decides what language a JUDGED file is, and this module "
        "asks it"
    )
    assert not any(
        value.startswith(".") for value in literals
    ), "a bare extension is never a filename inside this package"

    sites = _endswith_sites(source)
    assert len(sites) == 1, (
        f"expected exactly one endswith and found {len(sites)} at lines "
        f"{sites}; the one is over a Go PACKAGE CLAUSE in go_symbol_key"
    )
    tree = ast.parse(source)
    the_call = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "endswith"
    ][0]
    assert isinstance(the_call.func.value, ast.Name)
    assert the_call.func.value.id == "package_name", (
        "the one endswith must be over the package clause; over a path it "
        "would be a second answer to the question role_protocol owns"
    )

    registry = (_SRC / "role_protocol.py").read_text(encoding="utf-8")
    control = [value for _, value in _extension_literals(registry)]
    assert ".go" in control and _endswith_sites(registry), (
        "the positive control failed: role_protocol declares no extension "
        "literal or calls no endswith, so the results above prove nothing"
    )


# =========================================================================== #
# Part 9 — the edge grammar, through the graph the row builds
# =========================================================================== #


def test_a_call_is_not_a_reference_and_only_one_of_them_over_approximates(tmp_path):
    """RED at HEAD. ``sort.Slice(xs, less)`` reaches ``less``, weakly.

    Dropping function values would be a large false-BREACH source — it is a real
    way production reaches code. Calling them DIRECT would be a false pass: the
    value may never be invoked. So a reference is an edge and it is marked, and
    the two facts are asserted over one package so a body cannot satisfy one by
    losing the other.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green; emitting ``direct`` for a
    value use reddens the kind assertion, and dropping value uses entirely
    reddens the membership assertion.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        "func called() {}\n\n"
        "func referenced() {}\n\n"
        "func main() {\n"
        "\tcalled()\n"
        "\tvar f = referenced\n"
        "\t_ = f\n"
        "}\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)
    kinds = {
        (edge.caller.key.rpartition(".")[2], edge.callee.key.rpartition(".")[2]): edge.kind
        for edge in graph.edges
    }
    assert kinds[("main", "called")] is EdgeKind.DIRECT
    assert kinds[("main", "referenced")] is EdgeKind.REFERENCE
    assert not csr._edge_is_resolved(kinds[("main", "referenced")])


def test_interface_satisfaction_produces_no_edge_and_a_call_through_one_produces_many(tmp_path):
    """RED at HEAD. **The absence from the table is the answer.**

    Go's satisfaction is implicit and structural, so a name-level walk cannot
    compute it and must not pretend to. A type declaring an interface's methods
    yields NOTHING, and ``var _ I = (*T)(nil)`` yields nothing either **because
    it names no method** — the row asserts both, and the second is the one a
    body will get wrong, because the assertion idiom looks like a use.

    What DOES produce edges is a CALL through an interface-typed value, and the
    only honest name-level resolution is one edge to EVERY in-tree method of that
    name, marked ``OVER_APPROXIMATED``. The fixture declares two types with the
    same method name so "every" is more than one and a body that emitted the
    first match is red.

    A receiver whose type IS readable from the text is a METHOD edge and is not
    marked, and it is in the same package so the two answers are distinguished
    by the walk's confidence rather than by the code's shape.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and three mutations
    redden it independently: emitting an edge for the ``var _`` assertion;
    emitting an edge from ``Real`` to ``Fetcher`` for satisfaction; and emitting
    only the first in-tree ``Fetch`` from ``use``.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        "type Fetcher interface{ Fetch() string }\n\n"
        "type Real struct{}\n\n"
        'func (r Real) Fetch() string { return "real" }\n\n'
        "type Other struct{}\n\n"
        'func (o *Other) Fetch() string { return "other" }\n\n'
        "var _ Fetcher = Real{}\n\n"
        "func use(f Fetcher) string { return f.Fetch() }\n\n"
        "func direct() string {\n\tr := Real{}\n\treturn r.Fetch()\n}\n\n"
        "func main() { println(use(Real{}) + direct()) }\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)
    by_caller: dict[str, set[tuple[str, EdgeKind]]] = {}
    for edge in graph.edges:
        by_caller.setdefault(edge.caller.key.rpartition(".")[2], set()).add(
            (edge.callee.key.rpartition("/")[2], edge.kind)
        )

    assert by_caller["use"] == {
        ("p.(Real).Fetch", EdgeKind.INTERFACE),
        ("p.(*Other).Fetch", EdgeKind.INTERFACE),
    }, "one edge per IN-TREE method of that name; the first match is a guess"
    assert by_caller["direct"] == {("p.(Real).Fetch", EdgeKind.METHOD)}
    assert csr._edge_is_resolved(EdgeKind.METHOD)
    assert not csr._edge_is_resolved(EdgeKind.INTERFACE)

    assert GO_PACKAGE_VAR_SYMBOL in "".join(graph.symbols), (
        "the package-level var still needs its synthetic symbol: a root with "
        "no symbol has no outgoing edges and contributes silently nothing"
    )
    synthetic = [k for k in graph.symbols if k.endswith(GO_PACKAGE_VAR_SYMBOL)][0]
    assert not [e for e in graph.edges if e.caller.key == synthetic], (
        "`var _ Fetcher = Real{}` names no METHOD, so it produces no edge; a "
        "walk that emitted one is claiming to have computed satisfaction"
    )
    assert not [
        e for e in graph.edges if e.caller.key.endswith("p.(Real).Fetch")
    ], "satisfying an interface is not a call and is not an edge"


def test_go_and_defer_are_calls_and_a_closure_belongs_to_its_named_declaration(tmp_path):
    """RED at HEAD. Without the second half every table-driven seal has no subject.

    ``go f()`` and ``defer f()`` are named in the grammar only because a walk
    that keys on ``*ast.CallExpr`` gets them for free and a walk that keys on
    statement types silently drops both.

    The attribution half is load-bearing and not a convenience:
    ``subjects_of_seal`` defines a seal's subject as what the seal's own body
    calls directly, *"including nested closures, table-driven subtest bodies,
    and t.Run literals declared inside it"*, and a synthetic symbol per closure
    would empty the subject set of every table-driven seal in the target
    repositories. The row therefore asserts the attribution through D5's real
    ``subjects_of_seal`` over a ``t.Run`` literal, not through the edge set
    alone — the edge set is where a body would satisfy it by accident.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green; keying the walk on
    statement types reddens the first two assertions, and minting a synthetic
    symbol per ``*ast.FuncLit`` reddens the subject assertion with an empty set.
    """
    tree = _package(tmp_path, {
        "main.go": (
            "package main\n\n"
            "func spawned() {}\n\n"
            "func deferred() {}\n\n"
            "// Subject does the thing.\n"
            "func Subject(x int) int { return x }\n\n"
            "func main() {\n\tgo spawned()\n\tdefer deferred()\n}\n"
        ),
        "main_test.go": (
            'package main\n\nimport "testing"\n\n'
            "func TestSeal_Table(t *testing.T) {\n"
            "\tfor _, c := range []int{1, 2} {\n"
            '\t\tt.Run("case", func(t *testing.T) {\n'
            "\t\t\tif Subject(c) != c {\n"
            '\t\t\t\tt.Error("red")\n'
            "\t\t\t}\n"
            "\t\t})\n"
            "\t}\n"
            "}\n"
        ),
    })
    row = GoReachabilityAnalyzer()
    graph = row.graph(tree)
    from_main = {
        e.callee.key.rpartition(".")[2] for e in graph.edges
        if e.caller.key.endswith(".main")
    }
    assert "spawned" in from_main, "`go f()` is a call"
    assert "deferred" in from_main, "`defer f()` is a call"

    seals = csr.discover_seals(graph, row.roots(tree))
    table = [s for s in seals if s.symbol.key.endswith(".TestSeal_Table")][0]
    subject = csr.subjects_of_seal(table, graph)
    assert [s.key.rpartition(".")[2] for s in subject.symbols] == ["Subject"], (
        "a t.Run literal's calls belong to the innermost enclosing NAMED "
        "declaration; a synthetic symbol per closure empties this set"
    )
    assert subject.gap is None


def test_a_call_the_walk_cannot_name_is_a_hole_and_never_a_fifth_edge_kind(tmp_path):
    """RED at HEAD. The non-vacuity record of the whole document.

    ``unresolved_calls`` is the exact quantity that decides whether a "no path"
    answer is conclusive, so a walk that reports zero of them over a real package
    is either extraordinarily good or not counting, and those two must not be the
    same value. A hole is not an edge and must never become a fifth kind: naming
    it one invites a body to treat the absence of a target as a target.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    emitting a ``reference`` edge to every in-tree func for an unnameable call —
    which is the "helpful" mutation that would make ``DYNAMIC_EDGE``
    unreachable and every abstention a pass.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        "func target() {}\n\n"
        "func main() {\n"
        "\tfns := []func(){target}\n"
        "\tfns[0]()\n"
        "}\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)

    assert graph.unresolved_calls, (
        "`fns[0]()` is a call this walk cannot name; a graph reporting zero "
        "holes over it is not counting"
    )
    caller, site, detail = graph.unresolved_calls[0]
    assert caller.key.endswith(".main")
    assert site.startswith("p/main.go:")
    assert detail

    # The value use IS an edge and is marked; the indexed call is not.
    kinds = {e.kind for e in graph.edges if e.callee.key.endswith(".target")}
    assert kinds == {EdgeKind.REFERENCE}, (
        "`[]func(){target}` names target as a VALUE, which is a reference; the "
        "call through the slice is a hole, and the two are different facts"
    )


def test_a_named_out_of_tree_target_is_not_a_hole_and_a_func_value_call_is(tmp_path):
    """RED at HEAD. **P4 ADDED THIS ROW (D6 adjudication, 2026-08-11).**

    The gap it closes was live and it was not small: at ``5669cb7`` **nothing in
    this file distinguished "the walk could not NAME the target" from "the
    target is named and lives outside the tree"**, and a body that filed the
    second as a hole was green on all 97 rows. Every entry inside the production
    closure abstains at ``check_subject`` step 3, so that body ships a mechanism
    which returns :attr:`UndecidedReason.DYNAMIC_EDGE` for every subject of
    every real Go tree, forever — indistinguishable from a walk that cannot see,
    and the "unrun check" this repository records as its most expensive failure,
    reached from the opposite direction to the one the other rows guard.

    It is the mistake that was actually made: the reference walk behind DISPUTE
    D2 filed ~50 stdlib method calls as holes and reported 55 where there are
    **seven**.

    **The rule is total, and the totality is why this is not a narrowing.** A
    call site ``x.M(…)`` that lands on a target this walk cannot name lands on
    an in-tree method NAMED ``M`` or on nothing at all — Go's method-call
    syntax names the method — so one ``interface`` edge per in-unit method
    named ``M`` is a SUPERSET of the possible targets THE WALK HAS NOT ALREADY
    RESOLVED. Nothing is filed harmless because it could not be typed; the
    residue is empty by construction.

    **P4 AMENDED THIS ROW'S WITNESS (D6 adjudication round 4, 2026-08-11), AND
    THE SENTENCE ABOVE IS THE AMENDED FORM OF ONE ROUND 3 STRUCK.** The
    original read "a SUPERSET of the possible in-tree targets" with no
    qualifier, and applied the fan-out to EVERY selection whose target is not
    in this unit. Round 3 measured that false and ruled that a selection on a
    receiver whose base type is not an interface is a question go/types has
    ALREADY answered, so the walk must emit ``calleeKey(fn)`` as ``method`` and
    keep the fan-out for genuine interface dispatch only.

    **The two rulings collide on exactly one thing: this row's chosen
    witness.** The original fixture built ``now.UTC()`` on a ``time.Time``
    beside an in-unit ``func (Clock) UTC`` and required an ``interface`` edge
    ``stamp → Clock.UTC``. That is a CONCRETE receiver, so round 3 removes the
    edge and the assertion went red.

    **THE PRICE OF THE STRUCK SENTENCE DECIDED THIS RULING, AND P4 RE-MEASURED
    IT RATHER THAN INHERITING THE NUMBER. Measured under** ``feat/D6-adj4``,
    **2026-08-11**, over the acceptance fixture, running round 2's rule (the
    receiver discriminator forced never-taken) against the shipped one:

        round 2   738 edges — 655 ``direct``, 39 ``method``, 44 ``interface``
        round 3   694 edges — 655 ``direct``, 39 ``method``,  0 ``interface``

    Holes are 3 under both. **All 44 removed are** ``interface``, **none is
    added**, every one is named ``String``, and the 8 sites they come from all
    have a CONCRETE receiver — ``b.String()`` at ``cmd/gates/preserve.go:509``
    and ``cmd/iterate/preserve.go:458``, ``t.String()`` at ``:739`` and
    ``:697``, ``stderr.String()`` in four seal helpers. The fan-out was claiming
    that a call to ``strings.Builder.String`` might reach every unrelated
    in-tree ``String`` method.

    So the struck sentence bought **44 false edges and 0 true ones**, and the
    concrete receiver is the wrong witness for a property about UNRESOLVED
    targets. **The escalation stands; the witness moves.**

    Both ways of forcing the original witness green were weighed and both
    rejected, and this row records the rejection so no later round re-proposes
    them: emitting the resolved edge AND the fan-out leaves the false
    certification (a method production never calls, reading as called) that is
    half the measured harm; suppressing the fan-out only where the resolved
    target happens to land in-tree keeps a provably-false edge in exactly the
    case where it is provably false.

    The fixture puts every half in one tree so no assertion can be satisfied by
    a walk that has simply stopped counting:

      * ``stamp`` calls two methods on a CONCRETE stdlib receiver. ``UTC``
        shares its name with an in-tree method and ``Format`` does not; **both
        must yield no edge and neither may be a hole**, because go/types
        resolved both out of the tree. This is the half that reddens if round
        2's fan-out is restored.
      * ``describe`` calls ``s.String()`` on an ``fmt.Stringer`` — GENUINE
        interface dispatch, where the target is decided by the dynamic value
        and the walk has resolved nothing. **The fan-out onto the in-tree
        ``Clock.String`` is the answer**, and this is the half that reddens if
        the fan-out is dropped. It is also the half that carries the row's
        title: ``fmt.Stringer.String`` is a NAMED OUT-OF-TREE target, it is not
        a hole, and it is not a hole because the fan-out answered it.
      * ``spin`` makes the one genuinely unnameable call. **The hole list must
        be exactly this** — a walk that over-counts is red on the equality, and
        a walk that counts nothing is red on the same equality.

    **Measured under** ``feat/D6-seals`` @ ``5669cb7``, 2026-08-11: red by
    ``NotImplementedError``. The property is measured over the acceptance tree
    by two independent walks — see
    :func:`test_the_step_three_abstention_is_measured_and_the_implication_is_total`.

    **PROOF THAT THE AMENDED ROW CAN STILL FAIL, measured under**
    ``feat/D6-adj4``, **2026-08-11 — four mutations of the shipped mechanism,
    each applied alone, each run against this row:**

      1. filing an out-of-unit method receiver as a hole (the mistake this row
         exists for) — **red on the hole equality**;
      2. dropping the ``interface`` fan-out, so genuine interface dispatch
         emits only the interface's own method — **red on ``describe →
         Clock.String``**;
      3. **restoring round 2's fan-out on concrete receivers** — **red on
         ``stamp``, which acquires the very ``interface`` edge to ``Clock.UTC``
         this row used to demand**;
      4. defeating the both-ends rule so an out-of-tree callee survives — **red
         on the ``time.``/``fmt.`` assertion**.

    Mutations 2 and 3 are opposite errors and **neither half catches both**:
    ``describe`` is green under 3 and ``stamp`` is green under 2. That is why
    the fixture carries a concrete receiver AND an interface one, and it is the
    guard against this row being re-amended into whichever shape the next body
    happens to implement.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        "import (\n\t\"fmt\"\n\t\"time\"\n)\n\n"
        "type Clock struct{}\n\n"
        "// UTC is an in-tree method sharing a name with time.Time's.\n"
        "func (c Clock) UTC() string { return \"in-tree\" }\n\n"
        "// String is an in-tree method sharing a name with fmt.Stringer's.\n"
        "func (c Clock) String() string { return \"clock\" }\n\n"
        "func stamp() string {\n"
        "\tnow := time.Now()\n"
        "\t_ = now.UTC()\n"
        "\treturn now.Format(\"\")\n"
        "}\n\n"
        "func describe(s fmt.Stringer) string { return s.String() }\n\n"
        "func dark() {}\n\n"
        "func spin() {\n"
        "\tfns := []func(){dark}\n"
        "\tfns[0]()\n"
        "}\n\n"
        "func main() {\n"
        "\tprintln(stamp())\n"
        "\tprintln(describe(Clock{}))\n"
        "\tspin()\n"
        "}\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)

    holes = {(caller.key.rpartition(".")[2], detail) for caller, _, detail in
             graph.unresolved_calls}
    assert {caller for caller, _ in holes} == {"spin"}, (
        "the hole list must be EXACTLY the func-value call: `now.UTC()`, "
        "`now.Format()` and `s.String()` are answered questions — two whose "
        "answer is 'nothing in this tree' and one answered by the fan-out — "
        "and filing them as holes abstains on every real Go tree"
    )

    assert not [e for e in graph.edges
                if "time." in e.callee.key or "fmt." in e.callee.key], (
        "a call whose target is outside the tree has one end outside the tree "
        "and yields no edge, whichever branch resolved it"
    )
    assert not [e for e in graph.edges if e.caller.key.endswith(".stamp")], (
        "`now.UTC()` and `now.Format(\"\")` are calls on a CONCRETE receiver "
        "whose type is declared outside this tree, so go/types has already "
        "named the one target and it is out of tree. `stamp` must therefore "
        "have NO outgoing edge at all. An `interface` edge to `Clock.UTC` "
        "here is round 2's struck fan-out: a method production cannot reach, "
        "certified as called. Measured price of that rule over the acceptance "
        "fixture: 44 false edges, 0 true ones"
    )
    fan = [e for e in graph.edges
           if e.caller.key.endswith(".describe") and e.callee.key.endswith(".String")]
    assert len(fan) == 1 and fan[0].kind is EdgeKind.INTERFACE, (
        "`s.String()` on an `fmt.Stringer` is GENUINE interface dispatch: the "
        "target is decided by the dynamic value, the walk has resolved "
        "nothing, and one INTERFACE edge per in-tree method of that name is "
        "the superset that makes the site ANSWERED rather than holed. A walk "
        "that drops it has narrowed the abstention instead of answering it"
    )
    assert not [e for e in graph.edges if e.callee.key.endswith(".Format")], (
        "no in-tree method is named Format, so nothing lands — which is an "
        "answer, not a hole"
    )


def test_the_sole_binding_func_literal_rule_clears_one_shape_and_no_other(tmp_path):
    """RED at HEAD. **P4 ADDED THIS ROW (D6 adjudication round 2, 2026-08-11).**

    It is added because a ruling in that round ADOPTED a NARROWING of the hole
    set — ``main.go``'s SOLE-BINDING FUNC LITERAL rule — and a narrowing of an
    abstention is the one direction this repository will not accept unsealed. A
    hole ABSTAINS; deleting holes makes the mechanism louder and more confident,
    and a body that implements the rule too generously ships a walk that reports
    a fully-resolved production closure over a tree it did not resolve. That
    turns a reached symbol into an unreached one, which is a manufactured
    BREACH, which is the direction anti-requirement 2 forbids.

    **The failure mode is not hypothetical: it was MADE, in the adjudication
    that ruled the rule.** That round's first implementation discharged the
    no-reassignment obligation by enumerating the ASSIGNING constructs and
    clearing anything it did not recognise. ``for _, f = range fns`` is an
    ``*ast.RangeStmt`` and not an ``*ast.AssignStmt``, so it walked straight
    through and the rule CLEARED a call whose target is rebound once per
    iteration. Nothing in this file would have caught it. ``ranged`` below is
    that exact shape and it is why the fixture has five functions and not two.

    **The rule is a POSITIVE claim, and each half of this row pins one side of
    it.** The claim is that the identifiers which can name a function-local
    variable are exactly the identifiers inside that function's own
    declaration — a theorem about Go, not an observation about a tree — so the
    region to search is one finite AST subtree and the search over it is
    exhaustive. ``cleared`` is the one shape that discharges all four
    obligations. The other four each break exactly one of them, and each must
    stay a hole:

      * ``reassigned`` — a second assignment, in a branch (obligation 3);
      * ``ranged`` — reassigned by a range clause that is not an assignment
        statement (obligation 3, and the measured defect above);
      * ``addressed`` — ``p := &f; *p = …``, the one route by which the value
        changes with no syntax naming it (obligation 3b);
      * ``viaPackageVar`` — a package-level ``var`` of func type, whose value
        any file in the package may replace (obligation 1).

    The hole list must be **exactly** the four, so a walk that over-clears and a
    walk that clears nothing are both red on one equality — the shape
    :func:`test_a_named_out_of_tree_target_is_not_a_hole_and_a_func_value_call_is`
    uses, for its reason.

    The edge half is the other way a body could get this wrong. A cleared call
    yields **no edge**, because the ATTRIBUTION rule gives a closure no symbol
    of its own: the literal's calls are already attributed to the enclosing
    named declaration and the call site is inside it, so caller and callee are
    the same symbol. ``cleared`` must therefore have exactly ONE outgoing edge,
    the ``direct`` one to ``target`` that the literal's own body produces. A
    body that invented a synthetic symbol per literal, or emitted a self-edge,
    is red here — and the first of those is the mutation that would empty the
    subject set of every table-driven seal in the target repositories.

    **Measured under** ``feat/D6-adj2``, 2026-08-11: red today by
    ``NotImplementedError``. The fixture compiles, vets clean and type-checks
    with zero errors — which it must, or the type-error ruling would route the
    whole unit through ``parse_error`` and this row would pass by abstaining.
    An implementation of the four obligations run over it clears ``cleared``
    and declines the other four, each naming the obligation it failed; run over
    the acceptance fixture the same implementation clears exactly the five
    ``setMember`` sites and declines both ``cancel`` sites.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        "func target() {}\n\n"
        "func cleared() {\n"
        "\tf := func() { target() }\n"
        "\tf()\n"
        "}\n\n"
        "func reassigned(b bool) {\n"
        "\tf := func() { target() }\n"
        "\tif b {\n"
        "\t\tf = func() {}\n"
        "\t}\n"
        "\tf()\n"
        "}\n\n"
        "func ranged(fns []func()) {\n"
        "\tf := func() { target() }\n"
        "\tfor _, f = range fns {\n"
        "\t}\n"
        "\tf()\n"
        "}\n\n"
        "func addressed() {\n"
        "\tf := func() { target() }\n"
        "\tp := &f\n"
        "\t*p = func() {}\n"
        "\tf()\n"
        "}\n\n"
        "var pkgLevel = func() { target() }\n\n"
        "func viaPackageVar() { pkgLevel() }\n\n"
        "func main() {\n"
        "\tcleared()\n"
        "\treassigned(true)\n"
        "\tranged(nil)\n"
        "\taddressed()\n"
        "\tviaPackageVar()\n"
        "}\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)

    holed = {caller.key.rpartition(".")[2] for caller, _, _ in graph.unresolved_calls}
    assert holed == {"reassigned", "ranged", "addressed", "viaPackageVar"}, (
        "the hole list must be EXACTLY these four. `cleared` in it means the "
        "rule was not implemented and the mechanism still abstains on the "
        "shape the ruling adopted it for; any of the other four MISSING from "
        "it means the rule over-cleared, which deletes the only record that "
        "the tree was not fully read"
    )

    from_cleared = [e for e in graph.edges if e.caller.key.endswith(".cleared")]
    assert [e.callee.key.rpartition(".")[2] for e in from_cleared] == ["target"], (
        "a cleared call produces NO edge: the literal has no symbol of its own "
        "under the ATTRIBUTION rule, so its body's call to `target` is already "
        "attributed to `cleared` and caller and callee would be one symbol. A "
        "synthetic symbol per literal is the mutation that empties the subject "
        "set of every table-driven seal"
    )
    assert from_cleared[0].kind is EdgeKind.DIRECT
    assert not [e for e in graph.edges if e.caller.key == e.callee.key], (
        "and never a self-edge, which is the other way to spell the same wrong "
        "answer"
    )


def test_an_edge_is_kept_only_when_both_ends_are_declared_in_the_tree(tmp_path):
    """RED at HEAD. A call into the standard library is dropped.

    :class:`CallGraph`'s own rule. Modelling dependency internals would need
    their sources and make the graph unbounded, and it would add nothing: a
    subject in this tree is reached from this tree's roots, and a dependency
    that calls back into it does so through a value this tree handed it, which
    the REFERENCE edge already records — which is why the callback in this
    fixture must survive while the ``sort.Slice`` call itself does not.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on keeping
    edges whose callee is out of tree (the first assertion) and separately on
    dropping the callback with them (the second), so both directions are pinned.
    """
    tree = _package(tmp_path, {"main.go": (
        "package main\n\n"
        'import "sort"\n\n'
        "func less(i, j int) bool { return i < j }\n\n"
        "func main() {\n"
        "\txs := []int{3, 1}\n"
        "\tsort.Slice(xs, less)\n"
        "}\n"
    )})
    graph = GoReachabilityAnalyzer().graph(tree)

    assert not [e for e in graph.edges if "sort." in e.callee.key], (
        "a call into the standard library has one end outside the tree and is "
        "dropped; keeping it makes the graph unbounded and answers nothing"
    )
    callback = [e for e in graph.edges if e.callee.key.endswith(".less")]
    assert callback and callback[0].kind is EdgeKind.REFERENCE, (
        "the callback PASSED to the stdlib is kept as a reference; this is a "
        "real way production reaches code and dropping it is a false BREACH"
    )


# =========================================================================== #
# Part 10 — roots and graph, and the two guards that live in graph
# =========================================================================== #


def test_every_go_root_kind_is_derived_and_survives_validate_root(tmp_path):
    """RED at HEAD. There is no ``ENTRYPOINTS`` constant and there must not be.

    The precedent is concrete: an earlier hand-list in this repo omitted
    ``recheck_min_severity``, the safety floor, and an emitter built from it
    would have silently skipped every MEDIUM finding. The row builds one package
    carrying all four kinds and requires every one of them, so a body that
    derived three and hand-listed the fourth is red — and it pushes each through
    ``_validate_root``, which refuses a row that asserts its own ``root_kind``.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    dropping ``GO_INIT`` (one kind missing) and on asserting
    ``RootKind.PRODUCTION`` for the test root, which ``_validate_root`` refuses
    outright with "two disagreeing notions of 'is this a test file'".
    """
    tree = _package(tmp_path, {
        "main.go": (
            "package main\n\n"
            "var table = build()\n\n"
            "func build() int { return 1 }\n\n"
            "func init() { _ = table }\n\n"
            "func main() {}\n"
        ),
        "main_test.go": (
            'package main\n\nimport "testing"\n\n'
            "func TestSeal_Root(t *testing.T) { _ = build() }\n"
        ),
    })
    roots = GoReachabilityAnalyzer().roots(tree)
    for root in roots:
        csr._validate_root(root)

    kinds = {root.kind for root in roots}
    assert kinds == {
        EntrypointKind.GO_MAIN,
        EntrypointKind.GO_INIT,
        EntrypointKind.GO_PACKAGE_VAR,
        EntrypointKind.TEST_FUNCTION,
    }, "all four Go kinds are DERIVED from this one package; none is optional"

    package_var = [r for r in roots if r.kind is EntrypointKind.GO_PACKAGE_VAR][0]
    assert package_var.symbol.key.endswith(GO_PACKAGE_VAR_SYMBOL)
    assert all(root.evidence for root in roots), (
        "a root nobody can verify is a root nobody will believe when it "
        "produces a BREACH, and derived-not-hand-listed is auditable only here"
    )
    assert all(
        root.root_kind is csr._ROOT_KIND_BY_ENTRYPOINT[root.kind] for root in roots
    )


def test_an_unparseable_file_never_raises_from_roots_and_lands_in_unreadable_paths(tmp_path, monkeypatch):
    r"""RED at HEAD. DISPUTE D4, and the composition trace that forces it.

    ``discover_roots`` wraps ANY :class:`AnalyzerError` from ``roots`` into a
    ``CallSiteReachabilityError`` and the whole check dies. But P4 ruled that
    ``PARSE_FAILED`` outranks ``NO_ENTRYPOINT`` *precisely because* "an unparsed
    file is exactly where an undiscovered ``func main`` would be" — a ruling
    that can only ever take effect if a tree containing an unparsed file REACHES
    step 1b. So ``roots`` returns what parsed and the graph carries the file.

    Raising from ``graph`` is no better and lands two layers further on:
    ``build_call_graph`` catches :class:`SourceUnreadable` and ``continue``\ s,
    discarding this row's ENTIRE graph, after which ``discover_seals`` raises
    because no test root is declared in an empty symbol map.

    **The tree is TWO packages and that is not decoration.** A parse error kills
    a whole UNIT — the response carries ``parse_error`` and no arrays — so a
    one-package tree has no symbols, no roots and no seals left, and
    ``check_tree`` returns zero findings. Zero findings is not "the tree
    abstained", it is "there was nothing to judge", and a row that accepted it
    would be green on a mechanism that had silently stopped. **Measured in the
    clone, 2026-08-11:** the one-package spelling returned
    ``findings=()`` and was this file's only false premise. The live package
    supplies the seal and the subject; the broken one supplies the hole; and
    ``PARSE_FAILED`` is whole-tree, so the abstention crosses the module
    boundary — which is the property D5's CHOICE actually states.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and raising
    ``SourceUnreadable`` from ``graph`` reddens the ``check_tree`` half with
    exactly the ``discover_seals`` failure above.
    """
    tree = tmp_path / "twopkg"
    for directory, module, files in (
        ("broken", "example.com/broken", {"oops.go": "package main\n\nfunc oops( { not go\n"}),
        ("live", "example.com/live", {
            "main.go": (
                "package main\n\n"
                "// Dark is dark.\n"
                "func Dark() int { return 7 }\n\n"
                "func main() {}\n"
            ),
            "main_test.go": (
                'package main\n\nimport "testing"\n\n'
                "func TestSeal_Dark(t *testing.T) {\n"
                "\tif Dark() != 7 {\n\t\tt.Error(\"red\")\n\t}\n}\n"
            ),
        }),
    ):
        target = tree / directory
        target.mkdir(parents=True)
        (target / _LIVE_GO_MOD).write_text(f"module {module}\n\ngo 1.21\n")
        for name, source in files.items():
            (target / name).write_text(source)

    row = GoReachabilityAnalyzer()
    roots = row.roots(tree)   # must not raise
    graph = row.graph(tree)   # must not raise

    assert graph.unreadable_paths == ("broken/oops.go",)
    assert any(r.kind is EntrypointKind.TEST_FUNCTION for r in roots), (
        "the unit that PARSED must still contribute its roots; a partial root "
        "set is the failure, and a total outage is a bigger one"
    )
    assert any(key.endswith(".Dark") for key in graph.symbols)

    _with_go_row(monkeypatch)
    report = csr.check_tree(tree)

    dark = [f for f in report.findings if f.subject.key.endswith(".Dark")]
    assert len(dark) == 1, (
        "the live package's seal must still be judged; zero findings would be "
        "'nothing to judge' wearing an abstention's clothes"
    )
    assert dark[0].reach is Reach.UNDECIDED
    assert dark[0].reason is UndecidedReason.PARSE_FAILED, (
        "every no-path answer over this tree is computed around a hole of "
        "unknown size, and PARSE_FAILED is the confession — whole-tree, so it "
        "crosses the module boundary"
    )
    assert csr.adjudicate(dark[0], None) is Disposition.ABSTAIN


def test_a_unit_that_does_not_type_check_is_reported_and_never_silently_partial(
    tmp_path, monkeypatch
):
    """RED at HEAD. **P4 ADDED THIS ROW (D6 adjudication, 2026-08-11).**

    The operator ratified type-checking with ``go/types`` and
    ``importer.ForCompiler(fset, "source", nil)``. This row pins the sentence
    that ratification owed, because the failure mode is a fail-open wearing a
    type-checker's clothes.

    ``types.Config.Error`` swallows errors by design and ``conf.Check`` returns
    a POPULATED ``Info`` regardless, so a package that does not type-check looks
    exactly like one that does. **Measured 2026-08-11** on a package containing
    ``var s string = 42``: one type error raised, and the walk still resolved
    every one of its five call sites — zero unresolved, a full edge set, nothing
    in the output telling the two apart. **Measured the same day** on two files
    guarded by mutually exclusive ``//go:build`` constraints declaring one name:
    two type errors (``platform redeclared in this block``), and again zero
    unresolved.

    **A lost EDGE is not a hole**, which is why "trust the holes to show it" is
    not available: a production closure that silently shrank makes a REACHED
    subject look unreached, and that is a manufactured ``BREACH`` — the one
    direction anti-requirement 2 forbids. So a unit that did not type-check is
    reported the way a unit that did not PARSE is, and the tree abstains.

    The tree is TWO packages for
    :func:`test_an_unparseable_file_never_raises_from_roots_and_lands_in_unreadable_paths`'s
    measured reason: with one, there is nothing left to judge and ``findings=()``
    is "nothing to judge" wearing an abstention's clothes.

    **Measured under** ``feat/D6-seals`` @ ``5669cb7``, 2026-08-11: red today by
    ``NotImplementedError``. Two mutations redden it: emitting the partial graph
    for the ill-typed unit (both the ``unreadable_paths`` assertion and the
    ``PARSE_FAILED`` one), and raising rather than recording, which takes the
    whole check down instead of abstaining.
    """
    tree = tmp_path / "twopkg"
    for directory, module, files in (
        ("illtyped", "example.com/illtyped", {"main.go": (
            "package main\n\n"
            "func reached() int { return 1 }\n\n"
            "func broken() int {\n"
            "\tvar s string = 42\n"
            "\t_ = s\n"
            "\treturn reached()\n"
            "}\n\n"
            "func main() { println(broken()) }\n"
        )}),
        ("live", "example.com/live", {
            "main.go": (
                "package main\n\n"
                "// Dark is dark.\n"
                "func Dark() int { return 7 }\n\n"
                "func main() {}\n"
            ),
            "main_test.go": (
                'package main\n\nimport "testing"\n\n'
                "func TestSeal_Dark(t *testing.T) {\n"
                "\tif Dark() != 7 {\n\t\tt.Error(\"red\")\n\t}\n}\n"
            ),
        }),
    ):
        target = tree / directory
        target.mkdir(parents=True)
        (target / _LIVE_GO_MOD).write_text(f"module {module}\n\ngo 1.21\n")
        for name, source in files.items():
            (target / name).write_text(source)

    row = GoReachabilityAnalyzer()
    roots = row.roots(tree)   # must not raise
    graph = row.graph(tree)   # must not raise

    assert graph.unreadable_paths == ("illtyped/main.go",), (
        "a unit that did not type-check is a unit that was not fully read, and "
        "it travels the channel an unparsed unit travels; emitting its partial "
        "graph instead is how a shrunken closure manufactures a BREACH"
    )
    assert not [k for k in graph.symbols if k.startswith("example.com/illtyped")], (
        "the ill-typed unit contributes NO symbols: a document carrying "
        "parse_error carries no arrays, and half of one is the silent partial"
    )
    assert any(key.endswith(".Dark") for key in graph.symbols), (
        "the unit that DID type-check must still contribute; a total outage is "
        "a bigger failure than a partial one"
    )
    assert any(r.kind is EntrypointKind.TEST_FUNCTION for r in roots)

    _with_go_row(monkeypatch)
    report = csr.check_tree(tree)

    dark = [f for f in report.findings if f.subject.key.endswith(".Dark")]
    assert len(dark) == 1, "zero findings would be 'nothing to judge'"
    assert dark[0].reason is UndecidedReason.PARSE_FAILED
    assert csr.adjudicate(dark[0], None) is Disposition.ABSTAIN


def test_a_tree_of_go_files_that_yields_no_symbol_at_all_is_a_fault(tmp_path):
    """RED at HEAD. The whole-tree emptiness guard, at the only layer that can.

    D5 demands it explicitly — *"including an EMPTY graph where a graph was
    expected"* — and names the failure direction: an empty graph makes every
    subject ``FROM_NEITHER``, which is the loudest state the mechanism has, so
    the failure is a flood rather than a silence. This is the layer that knows
    how many Go files the sweep found, so it is the only layer that can tell
    "this package declares nothing" from "the helper stopped answering".

    The control is in the same call and is what stops the guard being a
    tripwire: a tree of Go files that genuinely declare nothing — package
    clauses and imports — is an ANSWER, and must not fault.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens both ways:
    dropping the guard makes the first half green-by-omission, and faulting on
    any empty union reddens the control.
    """
    tree = _package(tmp_path, {"main.go": "package main\n\nfunc main() {}\n"})
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(
            gr, "decode_go_reachability_response",
            lambda stdout: gr.GoReachabilityResponse(
                schema=GO_REACHABILITY_SCHEMA,
                unit=GoUnit(module_path="example.com/tiny", package_dir="p",
                            package_name="main"),
            ),
        )
        with pytest.raises(AnalyzerUnavailable) as refused:
            GoReachabilityAnalyzer().graph(tree)
    finally:
        monkey.undo()
    assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID

    # The control: declaring nothing is an answer.
    nothing = _package(tmp_path, {
        "a.go": 'package main\n\nimport "fmt"\n\nvar _ = fmt.Sprint\n',
    }, name="nothing")
    assert GoReachabilityAnalyzer().graph(nothing) is not None


def test_two_runs_over_one_tree_produce_one_graph(tmp_path):
    """RED at HEAD. A diff between two reports must be a real change.

    Determinism is contracted at three layers and it is load-bearing twice over:
    two runs over one tree must produce equal reports so a diff between them is a
    real change, and ``reachable_from`` breaks equal-length ties on edge order,
    so an unsorted edge list makes the WITNESS PATH nondeterministic even where
    the verdict is not.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green over both the synthetic
    package and the vendored acceptance tree, and it reddens on ranging a Go map
    to produce ``edges``.
    """
    tree = _package(tmp_path, {
        "main.go": (
            "package main\n\n"
            "func a() {}\n\nfunc b() {}\n\nfunc c() {}\n\n"
            "func main() {\n\ta()\n\tb()\n\tc()\n\ta()\n}\n"
        ),
    })
    row = GoReachabilityAnalyzer()
    assert row.graph(tree) == row.graph(tree)
    assert row.roots(tree) == row.roots(tree)


def test_a_key_declared_by_two_units_is_a_fault(tmp_path):
    """RED at HEAD. It should be impossible, which is exactly why it is a fault.

    The qualifier makes keys unique per package, so if two units declare one key
    the sweep sent one package twice or :func:`go_symbol_key` disagrees with
    itself — and both are mechanism bugs. A mechanism bug folded into the graph
    is a duplicate key at whole-tree scale, with the same consequence: one symbol
    whose ``path`` decides whether it is excluded from a subject set.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    ``symbols.update(produced.symbols)``, which is the natural spelling and
    which silently keeps the last writer.
    """
    tree = _package(tmp_path, {"main.go": "package main\n\nfunc main() {}\n"})
    monkey = pytest.MonkeyPatch()
    try:
        monkey.setattr(
            gr, "discover_units",
            lambda t: (
                (GoUnit(module_path="example.com/tiny", package_dir="p",
                        package_name="main"),
                 (GoSourceFile(path="p/main.go",
                               source=(t / "p" / "main.go").read_text()),)),
            ) * 2,
        )
        with pytest.raises(AnalyzerUnavailable) as refused:
            GoReachabilityAnalyzer().graph(tree)
    finally:
        monkey.undo()
    assert refused.value.fault is AnalyzerFault.HELPER_OUTPUT_INVALID


# =========================================================================== #
# Part 11 — the acceptance case
# =========================================================================== #


def test_the_naive_scan_certifies_both_dark_functions_and_still_refuses_an_orphan():
    """The immunity control. GREEN at HEAD — it judges the fixture, not the row.

    This row exists so that no other row in this file can be satisfied by the
    scan that certified B1. Measured PER MODULE over the vendored PRODUCTION
    files, 2026-08-11 — per module because the two packages are two resolution
    scopes and three exported names are declared in both, so a union would let
    one module's mention certify the other module's function:

      * five exported top-level funcs in each module;
      * the naive scan — *"an exported func with no non-test mention"* — flags
        **NONE of the ten**. Go's doc-comment convention opens a comment with
        the name of the thing it documents, and both ``VerifyPreservation`` doc
        comments do (``// VerifyPreservation checks a produced document against
        the original at the …``), so on idiomatic Go the scan has no
        discriminating power at all;
      * the refined scan scores **0 for exactly ``VerifyPreservation``, in each
        module, and for nothing else.** Over ``d5_b1_classify`` the same scan
        scores 0 for seven functions of fourteen, so this fixture is the sharper
        of the two.

    **The POSITIVE CONTROL is what makes the first bullet mean something.** A
    synthetic ``func Orphan()`` with NO doc comment is flagged by the same scan
    in the same call: the scan can still say no, so "it certifies both" is a
    fact about idiomatic Go rather than a scan that has stopped working. That is
    the shape "green on an unproducible input" names, refused here.

    **Measured under** ``feat/D6-seals``, 2026-08-11, in a clone, and the
    measurement corrected this row's first draft: rewriting the DOC COMMENT
    alone leaves the row green, because ``preserve.go`` mentions the name in
    **eight** comments and one is enough to certify. Rewriting **every comment
    mention** in one module's production text reddens that module's naive-scan
    assertion. So the scan is defeated eight times over per module, not once —
    which makes the fixture more robust than the B1 one, where a single doc
    comment carries it, and which is why the count in ``PROVENANCE.md`` is
    comments and not doc comments.
    """
    for module in ("cmd/gates", "cmd/iterate"):
        production = _production_text(module)
        exported = _exported_funcs(production)
        assert len(exported) == 5, (
            f"expected five exported funcs in {module} and found {exported}; "
            "the fixture and this row have drifted"
        )
        assert _SUBJECT_NAME in exported

        assert _naive_scan(production) == [], (
            f"the naive scan flagged something in {module}; on this fixture it "
            "must certify all five, which is what every other row in this file "
            "must be immune to"
        )
        assert _refined_scan(production) == [_SUBJECT_NAME], (
            f"the refined scan must isolate exactly the subject in {module}; if "
            "it scored zero for anything else, 'the mechanism finds what the "
            "scan misses' would be a claim about a set rather than about this "
            "defect"
        )

        orphan = dict(production)
        orphan[f"{module}/orphan.go"] = (
            "package main\n\nfunc Orphan() int { return 0 }\n"
        )
        assert _naive_scan(orphan) == ["Orphan"], (
            "the positive control failed: a func with no doc comment must still "
            "be flagged, or 'the naive scan certifies both' says nothing"
        )


def test_the_acceptance_case_is_seven_seal_subject_pairs_over_two_keys(tmp_path, monkeypatch):
    """RED at HEAD. DISPUTE D1: seven, and the contract's eight is unmeasured.

    ``check_tree`` judges every (seal, subject) PAIR, and a subject with no
    finding is a silent pass — so this is seven findings and not two, over two
    subjects. **Measured under** ``claude-workflow`` @ ``83b0b97``, 2026-08-11,
    by two independent methods that agree (see the fixture's ``PROVENANCE.md``):
    three seals in ``cmd/gates`` and **FOUR** in ``cmd/iterate``, sixteen calls,
    every one lexically inside the seal function's own body. The contract's
    "five seals … nine times" for ``cmd/iterate`` is wrong; its own list names
    four functions and then re-names the first.

    Seven and not two **only because the key is module-qualified**: both modules
    declare ``package main`` and both declare ``func VerifyPreservation``, and
    the row asserts the two keys are distinct so a body that lost the qualifier
    is red here as well as at :func:`test_the_two_acceptance_declarations_get_two_keys_and_an_unqualified_one_collides`.

    **What this row does NOT assert is the VERDICT**, because the verdict is a
    function of the production closure and is measured separately (D2). What it
    asserts is the thing that must hold under every reading and is exactly what
    the naive scan gets wrong: **not one of the seven is ``FROM_PRODUCTION``,
    and not one is adjudicated ``OK``.**

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, at 0.17 s for the first
    ``check_tree`` over the vendored tree and 0.04 s warm. Two mutations redden
    it independently. An import-based subject reader returns ZERO subjects —
    seal and subject are both ``package main`` in one directory and there is no
    import between them, which is the same measurement that killed the import
    reading for B1 — and it reddens **seven** rows across this file, this one
    among them. A row asserting its own ``root_kind`` instead of deriving it
    reddens **six**. Stripping ``package_dir`` from the key collapses the seven
    findings onto one symbol.
    """
    tree = _acceptance_tree(tmp_path)
    _with_go_row(monkeypatch)

    report = csr.check_tree(tree)

    gates_key = f"{_GATES_MODULE}/cmd/gates.{_SUBJECT_NAME}"
    iterate_key = f"{_ITERATE_MODULE}/cmd/iterate.{_SUBJECT_NAME}"
    assert gates_key != iterate_key

    findings = [f for f in report.findings if f.subject.key.endswith(f".{_SUBJECT_NAME}")]
    assert {f.subject.key for f in findings} == {gates_key, iterate_key}, (
        "the two subjects must be two symbols; one key here is one symbol "
        "wearing two declarations, and the findings collapse"
    )
    assert len(findings) == 7, (
        f"expected seven (seal, subject) pairs and found {len(findings)}; see "
        "DISPUTE D1 — the contract's eight is an unmeasured count and "
        "cmd/iterate has four seals, not five"
    )

    by_module: dict[str, set[str]] = {}
    for finding in findings:
        module = finding.seal.test_id.rpartition(".")[0]
        by_module.setdefault(module, set()).add(finding.seal.test_id.rpartition(".")[2])
    assert by_module == {m: set(s) for m, s in _ACCEPTANCE_SEALS.items()}, (
        "the seven must be the seven measured seals by name; a count alone is "
        "satisfiable by seven of the wrong ones"
    )

    assert not [f for f in findings if f.reach is Reach.FROM_PRODUCTION], (
        "production reaches neither: 18 non-test occurrences, 2 declarations "
        "and 16 comments, zero call expressions"
    )
    assert not [f for f in findings if csr.adjudicate(f, None) is Disposition.OK], (
        "this is the whole claim: whatever else the mechanism says about these "
        "seven, it may never say OK — that is what the naive scan says"
    )

    assert report.seals_examined > 7, (
        "the non-vacuity field: zero breaches over zero seals is exactly what "
        "this module exists to stop other people shipping"
    )
    assert any(r.kind is EntrypointKind.GO_MAIN for r in report.roots), (
        "with no production root every subject abstains at step 2 and the "
        "fixture would prove nothing"
    )


def test_the_step_three_abstention_is_measured_and_the_implication_is_total(tmp_path, monkeypatch):
    """RED at HEAD. DISPUTE D2 — no longer a prediction, and the row is total.

    ``check_subject`` reaches step 4 only past step 3, which abstains on ANY
    unresolved call in the production closure. The contract marks this
    *Predicted (unmeasured)* and calls it "the likeliest way this unit fails to
    earn its keep".

    **P4 AMENDED THIS DOCSTRING (D6 adjudication, 2026-08-11). The row's code is
    unchanged and correct; its measurement was not.** The seal author's number
    was 55 unresolved sites in the production closure, of which ~51 were method
    calls through untypeable receivers. **That was a measurement of a
    non-conformant walk, not of the tree.** ``main.go``'s EDGE GRAMMAR files a
    method call on an unresolved receiver as an ``interface`` edge — one per
    in-tree method of that name — and NOT as a hole; ``unresolved[]`` means the
    walk could not NAME the target, never "the target is out of tree". The
    author's own prose did not close either: 51 + 7 > 55.

    **Measured under** ``feat/D6-seals`` @ ``5669cb7``, 2026-08-11, over the
    vendored tree by TWO independent walks written for this adjudication — a
    name-level walk obeying the grammar above, and a full ``go/types`` walk
    using ``importer.ForCompiler(fset, "source", nil)`` under
    ``env -u HOME -u GOCACHE -u XDG_CACHE_HOME GOPROXY=off
    GOMODCACHE=/nonexistent GOPATH=/nonexistent``. **Re-measured under**
    ``feat/D6-adj2``, 2026-08-11, by a THIRD walk written from scratch for the
    round-2 adjudication, which classifies every ``*ast.CallExpr`` by the form
    in its ``Fun`` slot rather than looking at one form: 1,114
    ``SelectorExpr``, 1,000 ``Ident``, 17 ``ArrayType`` (conversions), 1
    ``FuncLit`` (immediately invoked), nothing else. **All three agree on the
    thing this row turns on:**

      * unresolved sites in the production closure: **SEVEN**, not 55 —
        ``cancel`` (``context.CancelFunc``, from ``context.WithTimeout``) twice
        in ``cmd/gates/main.go``, at ``runOne`` and ``runCmd``, and a
        ``setMember`` closure five times in ``cmd/iterate/preserve.go`` at
        ``ApplyRoundRecord``. Same seven sites, same lines;
      * **every one of the seven is a call through a FUNCTION VALUE.** Not one
        is a typing failure. Of the ~50 method-call sites the first walk filed
        as holes, only **2** even name a method that exists in this tree;
        1,054 sites name a target that lives outside the tree, and those are
        answered questions rather than holes;
      * ``reference`` edges move neither number — 41 in-tree references, and
        the closure and the hole count are identical with and without them.

    **The closure size is 104, not 106, and the two are the same measurement.**
    The round-2 walk spells the synthetic package-var initialiser once per
    PACKAGE and the round-1 walks spelled it once per FILE; four files in this
    fixture carry a package-level ``var`` with an initialiser and two packages
    hold them, so the difference is exactly those two synthetic symbols. No
    real declaration and no hole is on either side of it. The number is
    recorded as 104 because ``go_symbol_key``'s synthetic spelling is
    per-package.

    So step 4 is still never reached and **all seven findings still come back
    :attr:`UndecidedReason.DYNAMIC_EDGE`** — the row's conclusion survives, and
    "even the most permissive honest reading leaves the closure holed" is TRUE.
    But the REASON is not the one recorded: it is seven func-value call sites,
    and **type information moved 50 sites and moved the verdict on none of
    them**, because no amount of type information names the target of a call
    through a function value. ``go/types`` gives the value's TYPE, never its
    identity; that is a dataflow question.

    **P4 ROUND 2 (D6 adjudication, 2026-08-11) — THE ARITHMETIC, AND WHY IT IS
    SEVEN OR NONE.** The round-1 ruling recorded that a sound single-assignment
    rule "would clear all four of ``cmd/iterate``'s findings". The rule is now
    ruled and adopted — ``main.go``'s SOLE-BINDING FUNC LITERAL rule, which
    clears exactly the five ``setMember`` sites and declines both ``cancel``
    sites, measured. **The "four" is REFUTED by measurement.**
    :func:`check_subject` computes its hole list as
    ``[h for h in graph.unresolved_calls if h[0].key in production_reach]``,
    over the ONE whole-tree ``production_reach`` :func:`check_tree` builds, so
    the list is identical for every (seal, subject) pair and a hole in
    ``cmd/gates`` abstains ``cmd/iterate``'s findings too. **Measured under**
    ``feat/D6-adj2``, 2026-08-11, by driving :func:`check_subject` directly over
    two modules at four hole-sets: 7 holes → 0 of 7 answered; 2 holes (rule 1
    alone) → **0 of 7**; 5 holes → 0 of 7; 0 holes → 7 of 7. There is no
    partial answer available on this repository. Scoping step 3's hole set to
    the SUBJECT rather than to the tree would make it four, and that is
    ``call_site_reachability.py``, which is on ``FLOOR_GLOBS`` — D5's file and
    D5's ruling. **ESCALATED, not taken here.**

    **This row seals the IMPLICATION and is total over the two states**, because
    the alternatives are both wrong: asserting the abstention seals the failure
    and would go red the day a body improved, and asserting the BREACH demands a
    name-level walk that types ``time.Time``. It survives round 2 untouched in
    code for the same reason it survived round 1, and that is the point of
    having written it that way. Which branch runs today is
    recorded, not required — and the branch that does NOT run today is kept from
    being a dead letter by
    :func:`test_a_fully_resolved_production_closure_reaches_the_tests_only_verdict`,
    which reaches step 4 over a package whose closure is genuinely clean.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone the abstention branch runs and is
    green; forcing the closure's hole list empty while leaving the graph alone
    switches it to the other branch, which then also passes — which is what
    "total over the two states" has to mean.
    """
    tree = _acceptance_tree(tmp_path)
    _with_go_row(monkeypatch)

    report = csr.check_tree(tree)
    findings = [f for f in report.findings if f.subject.key.endswith(f".{_SUBJECT_NAME}")]
    assert len(findings) == 7

    if report.unresolved_call_count:
        assert all(f.reach is Reach.UNDECIDED for f in findings)
        assert all(f.reason is UndecidedReason.DYNAMIC_EDGE for f in findings), (
            "with the production closure holed, one of those calls may be the "
            "missing call site; the abstention is correct and is the measured "
            "state of this tree — SEVEN holes over a 104-symbol closure, every "
            "one a call through a function value"
        )
        assert all(csr.adjudicate(f, None) is Disposition.ABSTAIN for f in findings)
    else:
        assert all(f.reach is Reach.FROM_TESTS_ONLY for f in findings)
        assert all(f.quality is PathQuality.NOT_APPLICABLE for f in findings)
        assert all(csr.adjudicate(f, None) is Disposition.BREACH for f in findings), (
            "a fully resolved production closure is the only state in which "
            "this mechanism may say BREACH about these seven"
        )


def test_a_fully_resolved_production_closure_reaches_the_tests_only_verdict(tmp_path, monkeypatch):
    """RED at HEAD. The row that keeps D2's other branch from being a dead letter.

    A conditional whose consequent nothing can satisfy is a green that measures
    nothing — the "pass condition satisfiable by executing nothing" shape. This
    package is the smallest tree in which every production call resolves: ``main``
    calls ``light`` by name and ``println`` is a builtin, so the closure holds
    **zero** holes and ``check_subject`` reaches step 4.

    ``Dark`` carries a doc comment opening with its own name, exactly as both
    ``VerifyPreservation`` doc comments do, so the naive scan certifies it here
    too and this row is not green for a reason the acceptance rows are not.

    The in-test control is the second finding: ``light`` IS reached from
    production and is adjudicated ``OK`` in the same report, so the BREACH is
    shown to be a discrimination rather than a verdict this mechanism hands
    everything.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green — ``unresolved_call_count``
    0, one BREACH, one OK — and it reddens on emitting a hole for the builtin
    ``println``, which is the mutation that would put every real Go tree back
    into the abstention branch.
    """
    tree = _package(tmp_path, {
        "main.go": (
            "package main\n\n"
            "// Dark reports one more than x.\n"
            "func Dark(x int) int { return x + 1 }\n\n"
            "func light(x int) int { return x * 2 }\n\n"
            "func main() { println(light(1)) }\n"
        ),
        "main_test.go": (
            'package main\n\nimport "testing"\n\n'
            "func TestSeal_Dark(t *testing.T) {\n"
            "\tif Dark(1) != 2 {\n\t\tt.Error(\"red\")\n\t}\n}\n\n"
            "func TestSeal_Light(t *testing.T) {\n"
            "\tif light(1) != 2 {\n\t\tt.Error(\"red\")\n\t}\n}\n"
        ),
    })
    _with_go_row(monkeypatch)

    report = csr.check_tree(tree)

    assert report.unresolved_call_count == 0, (
        "the premise of the row: with a hole in the closure this proves "
        "nothing about step 4"
    )
    dark = [f for f in report.findings if f.subject.key.endswith(".Dark")]
    assert len(dark) == 1
    assert dark[0].reach is Reach.FROM_TESTS_ONLY
    assert dark[0].quality is PathQuality.NOT_APPLICABLE
    assert dark[0].path is None
    assert csr.adjudicate(dark[0], None) is Disposition.BREACH

    control = [f for f in report.findings if f.subject.key.endswith(".light")]
    assert control and control[0].reach is Reach.FROM_PRODUCTION, (
        "the control failed: if nothing in this tree were reached from "
        "production, the BREACH above would be arithmetic rather than a finding"
    )
    assert csr.adjudicate(control[0], None) is Disposition.OK


def test_a_dark_function_nobody_sealed_produces_no_finding_and_is_still_in_the_graph(tmp_path, monkeypatch):
    """RED at HEAD. Limit 8, and the fixture that makes it concrete.

    **Measured under** ``claude-workflow`` @ ``1fe753b`` (``feat/G2-iterate-preserve``),
    2026-08-11, by ``git ls-tree``: ``cmd/iterate`` tracks **no
    ``preserve_seal_test.go`` at all**; ``VerifyPreservation`` is an
    unimplemented stub returning ``errNotImplemented``, and its seven
    occurrences are all in ``preserve.go`` while ``main.go`` and ``main_test.go``
    have zero. **Zero seals name it.** Under D5's limit 8 the correct report is
    therefore **no finding at all** — not a BREACH and not an abstention. D5
    judges the subjects OF SEALS; a dark function nobody sealed is dead-code
    detection, which is a strictly larger set and would bury the B1 shape in it.

    That revision is NOT vendored, and the omission is a decision rather than an
    oversight: it would cost ~100 KB of scaffold text to seal a rule that a
    six-line package states exactly, and the instance is measured and cited
    above rather than frozen. What IS sealed is the discrimination, and the
    second half is what stops it reading as a discovery failure: ``Dark`` must
    be IN ``graph.symbols``. A body that simply failed to find it would pass a
    row that only checked for the absence of a finding.

    **A body author who "fixes" this has widened the subject population without
    a ruling.**

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green, and it reddens on
    sweeping every declared symbol into the subject population instead of
    deriving it from seals.
    """
    tree = _package(tmp_path, {
        "main.go": (
            "package main\n\n"
            "// Dark is dark, and nobody sealed it.\n"
            "func Dark() int { return 7 }\n\n"
            "func light() int { return 1 }\n\n"
            "func main() { _ = light() }\n"
        ),
        "main_test.go": (
            'package main\n\nimport "testing"\n\n'
            "func TestSeal_Light(t *testing.T) {\n"
            "\tif light() != 1 {\n\t\tt.Error(\"red\")\n\t}\n}\n"
        ),
    })
    _with_go_row(monkeypatch)

    report = csr.check_tree(tree)
    graph = GoReachabilityAnalyzer().graph(tree)

    assert not [f for f in report.findings if f.subject.key.endswith(".Dark")], (
        "no seal names Dark, so D5 says nothing about it; reporting it would "
        "be dead-code detection and would bury the B1 shape"
    )
    assert any(key.endswith(".Dark") for key in graph.symbols), (
        "Dark must still be DECLARED in the graph; 'no finding' must mean 'out "
        "of scope' and never 'the sweep did not find it'"
    )
    assert report.seals_examined == 1
    assert report.findings, "the seal that DOES exist must still be judged"


def test_the_subject_reader_cannot_be_import_based_over_this_fixture(tmp_path, monkeypatch):
    """RED at HEAD. The measurement that killed the import reading for B1, twice.

    ``subjects_of_seal``'s rejected alternative — "by the symbol it IMPORTS" —
    fails outright on the case that motivated the unit, and this fixture says so
    twice over: in each module the seal and its subject are both ``package
    main`` in ONE directory, so there is no import between them and an
    import-based reader reports ZERO subjects for the exact defect.

    The row measures the premise rather than asserting it — it reads the two
    seal files and requires that neither imports its own module path — so that
    "an import reader returns zero" is a fact about the fixture and not a claim
    about it.

    **Measured under** ``feat/D6-seals`` @ ``b451cfc``, 2026-08-11: red today by
    ``NotImplementedError``. In the clone it is green.
    """
    for module, path in (("cmd/gates", _GATES_MODULE), ("cmd/iterate", _ITERATE_MODULE)):
        seal_source = (_FIXTURE / module / "preserve_seal_test.go").read_text()
        assert re.search(r"^package main$", seal_source, flags=re.MULTILINE), (
            f"{module}'s seal file is not package main; the no-import premise "
            "is a property of the real text and must be measured, not assumed"
        )
        assert path not in seal_source, (
            f"{module}'s seal file imports its own module; the fixture no "
            "longer demonstrates that an import reader returns zero"
        )

    tree = _acceptance_tree(tmp_path)
    _with_go_row(monkeypatch)
    graph = GoReachabilityAnalyzer().graph(tree)
    roots = GoReachabilityAnalyzer().roots(tree)

    named = 0
    for seal in csr.discover_seals(graph, roots):
        if seal.symbol.key.rpartition(".")[2] in (
            _ACCEPTANCE_SEALS["cmd/gates"] + _ACCEPTANCE_SEALS["cmd/iterate"]
        ):
            subject = csr.subjects_of_seal(seal, graph)
            assert any(s.key.endswith(f".{_SUBJECT_NAME}") for s in subject.symbols), (
                f"{seal.test_id} calls the subject in its own body; a reader "
                "that needed an import returns zero here"
            )
            named += 1
    assert named == 7


# =========================================================================== #
# Part 12 — the cross-package key repair, and the one shape where it is worse
#           than the drop it replaced
#
# P4 (D6 adjudication round 3, 2026-08-11). `main.go`'s contract used to say a
# cross-package callee's KEY is derivable from the import block. It is not:
# `go_symbol_key`'s qualifier is `<module_path>/<TREE-relative package_dir>`
# and a package's import path is `<module_path>/<MODULE-relative directory>`.
# The two differ whenever the module root is not the tree root, which is the
# acceptance fixture's own shape, and the difference costs a real production
# edge — a false accusation of dark code in the mechanism whose whole purpose
# is accusing code of being dark.
#
# The body closed it inside `graph()` with `_import_path_qualifiers` and
# `_join_callee` and flagged it as uncovered. These are the rows.
#
# EVERY TREE HERE PUTS THE MODULE BELOW THE TREE ROOT, and that is not
# decoration: with a module at the tree root the map is the identity, the
# rewrite is a no-op, and a row built that way would pass with the repair
# deleted. The `_MODULE_BELOW_ROOT` control asserts exactly that.
# =========================================================================== #


#: The subdirectory every tree in this part puts its module in. Named once,
#: because a row that spelled it twice could drift into the tree-root shape
#: where these rows measure nothing.
_MODULE_BELOW_ROOT = "sub"


def _below_root_tree(tmp_path: Path, files: dict[str, str], *, name: str) -> Path:
    """A tree whose module lives at ``sub/``, one file per entry.

    Keys are paths relative to ``sub/``. The ``go.mod`` is the caller's, because
    two of these rows turn on what it says.
    """
    tree = tmp_path / name
    for relative, source in files.items():
        path = tree / _MODULE_BELOW_ROOT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return tree


def test_a_cross_package_edge_survives_only_because_the_callee_key_is_rejoined(
    tmp_path,
):
    """The repair, and the control that proves the row can fail.

    ``sub/main.go`` calls ``core.Work`` in ``sub/internal/core``. The helper can
    only name that callee by its IMPORT PATH — ``example.com/app/internal/core``
    — while the callee's own unit keys it ``example.com/app/sub/internal/core``,
    because ``go_symbol_key``'s qualifier keeps the TREE-relative directory. If
    the two are not rejoined, ``CallGraph``'s both-ends rule drops a real
    production edge and ``Work`` reads as uncalled.

    **THE POSITIVE CONTROL IS THE SECOND ASSERTION**, and it is what makes this
    row more than a restatement of the body: it re-derives the pre-repair
    answer by joining against an EMPTY qualifier map — which is the code as it
    stood before ``_import_path_qualifiers`` existed — and asserts that key
    names nothing in the tree. So the row measures the repair rather than the
    call.

    **Measured under** ``feat/D6-adj3``, 2026-08-11: GREEN, mutation-verified,
    two mutations, and each reddens this row plus the two below it and nothing
    else in the file — replacing ``graph``'s ``qualifiers`` with ``{}`` (which
    is the code exactly as it stood before the repair), and computing
    ``_import_path_qualifiers``' ``inside`` from the TREE root instead of the
    module directory (which is the same defect written a second way).
    """
    tree = _below_root_tree(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.21\n",
            "main.go": (
                "package main\n\n"
                'import "example.com/app/internal/core"\n\n'
                "func main() { core.Work() }\n"
            ),
            "internal/core/core.go": "package core\n\nfunc Work() {}\n",
        },
        name="rejoined",
    )
    graph = GoReachabilityAnalyzer().graph(tree)

    callee = go_symbol_key(
        "example.com/app", f"{_MODULE_BELOW_ROOT}/internal/core", "core", None, "Work"
    )
    assert callee in graph.symbols, (
        "the control failed: the callee's own unit did not declare the key "
        "go_symbol_key spells, so the row below is measuring nothing"
    )
    assert [e for e in graph.edges if e.callee.key == callee], (
        "the cross-package call is a real production edge; dropping it makes "
        "core.Work read as uncalled, which is a manufactured BREACH in the "
        "mechanism whose whole purpose is accusing code of being dark"
    )

    # THE POSITIVE CONTROL. The key the helper emitted, joined the way the code
    # joined it before the repair: it names nothing here.
    as_the_helper_spelled_it = "example.com/app/internal/core.Work"
    assert as_the_helper_spelled_it not in graph.symbols, (
        "the row is vacuous if the helper's spelling already matches: then the "
        "module sits at the tree root, the qualifier map is the identity, and "
        "this file would pass with the repair deleted"
    )


def test_the_longest_import_path_wins_when_one_prefixes_another(tmp_path):
    """The one shape in which longest-match is load-bearing, built rather than imagined.

    ``_KEY_PACKAGE_SEPARATOR`` is ``"."`` and an import path may legally contain
    one — ``gopkg.in/yaml.v2`` is the everyday example — so ``example.com/x.``
    is a genuine textual prefix of the KEY ``example.com/x.y.FromY``. Two
    candidates match and the rule must pick the longer.

    **THE TWO MODULES ARE THE POINT AND THIS ROW COST ONE REWRITE TO GET
    RIGHT.** Inside ONE module the two rules are indistinguishable: every
    package of a module gets the SAME prefix inserted, so shortest-match's
    answer for ``…/app/b.v2.FromBV2`` is the correct key by coincidence and a
    row built that way passes under either rule. The candidates must belong to
    units whose qualifiers transform differently, which means two modules in
    two directories. **The first draft of this row was built inside one module
    and was vacuous; it is recorded because a control that cannot fail is the
    defect this file exists to find.**

    Here ``example.com/x`` lives at ``mx/`` and ``example.com/x.y`` at ``my/``,
    so longest-match answers ``example.com/x.y/my.FromY`` and shortest-match
    answers ``example.com/x/mx.y.FromY`` — different strings, and only one of
    them names anything. Getting this backwards costs a DROPPED production edge
    and prints no error at all.

    **Measured under** ``feat/D6-adj3``, 2026-08-11: GREEN, mutation-verified,
    three mutations — dropping ``reverse=True`` from ``_join_callee``'s
    ``sorted(..., key=len)``, which reddens this row and no other; and the two
    the row above lists, which redden this one too.
    """
    tree = tmp_path / "prefix"
    for relative, source in {
        "mx/go.mod": "module example.com/x\n\ngo 1.21\n",
        "mx/x.go": "package x\n\nfunc FromX() {}\n",
        "my/go.mod": "module example.com/x.y\n\ngo 1.21\n",
        "my/y.go": "package y\n\nfunc FromY() {}\n",
        "app/go.mod": (
            "module example.com/app\n\n"
            "go 1.21\n\n"
            "require (\n"
            "\texample.com/x v0.0.0\n"
            "\texample.com/x.y v0.0.0\n"
            ")\n\n"
            "replace example.com/x => ../mx\n\n"
            "replace example.com/x.y => ../my\n"
        ),
        "app/main.go": (
            "package main\n\n"
            "import (\n"
            '\t"example.com/x"\n'
            '\t"example.com/x.y"\n'
            ")\n\n"
            "func main() {\n"
            "\tx.FromX()\n"
            "\ty.FromY()\n"
            "}\n"
        ),
    }.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    graph = GoReachabilityAnalyzer().graph(tree)

    for module, directory, package, name in (
        ("example.com/x", "mx", "x", "FromX"),
        ("example.com/x.y", "my", "y", "FromY"),
    ):
        key = go_symbol_key(module, directory, package, None, name)
        assert key in graph.symbols, (
            f"the control failed: {directory} declared no {name} to reach"
        )
        assert [e for e in graph.edges if e.callee.key == key], (
            f"{name} is called from app/main.go and its edge was lost; under "
            "shortest-match the example.com/x.y callee is rewritten onto "
            "example.com/x's qualifier and lands on nothing"
        )

    # THE POSITIVE CONTROL: the key shortest-match would have produced. It must
    # name nothing, or the row cannot tell the two rules apart.
    x_qualifier = go_symbol_key("example.com/x", "mx", "x", None, "").rpartition(".")[0]
    shortest_match = f"{x_qualifier}.y.FromY"
    correct = go_symbol_key("example.com/x.y", "my", "y", None, "FromY")
    assert shortest_match != correct, (
        "the control failed: the two rules produced the same string, which is "
        "what happens when both candidates live in ONE module. This row is "
        "then vacuous under either rule"
    )
    assert shortest_match not in graph.symbols, (
        "shortest-match's answer must name nothing in the tree"
    )


def test_a_method_key_crosses_a_package_boundary_with_its_receiver_intact(tmp_path):
    """The rewrite moves ``(*T).M`` and ``(T).M`` without touching the member.

    ``go_symbol_key`` gives pointer and value receivers DIFFERENT keys on
    purpose, so a prefix rewrite that reached into the member — or that split on
    the wrong ``.`` — would silently merge two bodies into one symbol, which is
    the collision the qualifier exists to prevent, one level in.

    This row asserts the SPELLING survives the join, over a package-level
    function that returns the receiver type. It deliberately does not assert an
    edge into either method: **a method call on a receiver declared in another
    in-tree package emits no edge at all today** — see the P4 escalation on
    ``classifySelectorCall`` in ``main.go`` — and a row that asserted one here
    would be red for a defect that is P3's, not this repair's.

    **Measured under** ``feat/D6-adj3``, 2026-08-11: GREEN, mutation-verified
    by the two mutations the first row of this Part lists, both of which redden
    it; a join that rewrote past the qualifier's separator would mangle the
    member and redden the ``{pointer, value}`` assertion.
    """
    tree = _below_root_tree(
        tmp_path,
        {
            "go.mod": "module example.com/app\n\ngo 1.21\n",
            "internal/core/core.go": (
                "package core\n\n"
                "type T struct{}\n\n"
                "func (t *T) Ptr()  {}\n"
                "func (t T) Value() {}\n\n"
                "func New() *T { return &T{} }\n"
            ),
            "main.go": (
                "package main\n\n"
                'import "example.com/app/internal/core"\n\n'
                "func main() {\n"
                "\tv := core.New()\n"
                "\tv.Ptr()\n"
                "\t(*v).Value()\n"
                "}\n"
            ),
        },
        name="methods",
    )
    graph = GoReachabilityAnalyzer().graph(tree)

    directory = f"{_MODULE_BELOW_ROOT}/internal/core"
    pointer = go_symbol_key("example.com/app", directory, "core", "*T", "Ptr")
    value = go_symbol_key("example.com/app", directory, "core", "T", "Value")
    assert pointer != value, (
        "the control failed: the two receivers collapsed to one key, and this "
        "row cannot tell a preserved member from a mangled one"
    )
    assert {pointer, value} <= set(graph.symbols), (
        "both methods are declared in the tree and both must be symbols; a "
        "symbol absent from the map cannot be a subject"
    )
    joined = [e for e in graph.edges if e.callee.key.endswith(".New")]
    assert joined and joined[0].callee.key.startswith(f"example.com/app/{directory}"), (
        "the cross-package func edge must land on the callee unit's own "
        "qualifier, which is what makes the method keys above reachable at all"
    )


def test_two_units_claiming_one_import_path_are_never_silently_joined_to_one(
    tmp_path,
):
    """RED at HEAD, and the redness is the finding.

    **P4 (D6 adjudication round 3, 2026-08-11): this is the one measured shape
    in which the repair is WORSE than the drop it replaced, and it ships red so
    that P3 has a row to fix against rather than a paragraph to remember.**

    ``_import_path_qualifiers`` returns a plain ``dict`` keyed on import path
    with no collision check, so when two units in one tree claim one import path
    — two checkouts of a module, or a vendored copy that kept its ``go.mod`` —
    the LAST one written wins, and the winner is decided by ``discover_units``'
    sort order, which is a fact about directory names and nothing else.

    Here ``a/`` and ``b/`` both declare ``module example.com/dup`` and ``app``
    reaches the FIRST through ``replace example.com/dup => ../a``. Measured
    under ``feat/D6-body`` @ ``f4c7c46``: the edge lands on ``b/d.go``. Two
    harms at one site — the real target reads as uncalled, which is a false
    BREACH, and the decoy reads as called, which is a false certification and
    hides dark code. Before the repair the edge was merely dropped, so the
    repair introduced the second harm.

    THE RULING is that a second unit claiming an import path already in the map
    is :attr:`AnalyzerFault.HELPER_OUTPUT_INVALID`, exactly as a duplicate
    symbol key across units already is in ``graph`` and for the same reason: one
    label naming two packages is one symbol wearing two declarations, one layer
    up. Abstaining is the answer a mechanism that cannot tell two packages apart
    is entitled to give; guessing is not.

    The alternative ruling — silently preferring one — was rejected because
    there is no honest tie-break: ``replace`` decides which directory the import
    resolves to and nothing in this map reads ``replace``.

    THE CONTROL is the first assertion: both ``Do``s must be declared, so a
    green from an empty graph is impossible.

    **AND THE SHARPEST MEASUREMENT IN THIS PART: THIS ROW IS GREEN WITH THE
    REPAIR REMOVED.** Measured under ``feat/D6-adj3``, 2026-08-11, replacing
    ``graph``'s ``qualifiers`` with ``{}``: the three rows above redden and this
    one goes green, because with no map the edge is merely dropped and nothing
    is certified. That is "the repair introduced the second harm" as an
    executable fact rather than a claim, and it is why the collision must be
    made loud rather than the repair reverted — reverting would take the three
    rows above with it.
    """
    tree = tmp_path / "collision"
    for relative, source in {
        "a/go.mod": "module example.com/dup\n\ngo 1.21\n",
        "a/d.go": "package dup\n\nfunc Do() {}\n",
        "b/go.mod": "module example.com/dup\n\ngo 1.21\n",
        "b/d.go": "package dup\n\nfunc Do() {}\n",
        "app/go.mod": (
            "module example.com/app\n\n"
            "go 1.21\n\n"
            "require example.com/dup v0.0.0\n\n"
            "replace example.com/dup => ../a\n"
        ),
        "app/main.go": (
            "package main\n\n"
            'import "example.com/dup"\n\n'
            "func main() { dup.Do() }\n"
        ),
    }.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    row = GoReachabilityAnalyzer()
    try:
        graph = row.graph(tree)
    except AnalyzerUnavailable as exc:
        assert exc.fault is AnalyzerFault.HELPER_OUTPUT_INVALID, (
            "two units claiming one import path is the mechanism failing to "
            f"tell two packages apart, not {exc.fault!r}"
        )
        return

    declared = {key for key in graph.symbols if key.endswith(".Do")}
    assert len(declared) == 2, (
        "the control failed: the tree must declare both Do's, or a green here "
        f"means nothing. Declared: {sorted(declared)}"
    )
    landed = [e.callee.key for e in graph.edges if e.callee.key.endswith(".Do")]
    assert not landed, (
        "the map guessed. `replace ... => ../a` resolves the import to a/d.go "
        f"and the edge landed on {landed}; the map cannot read `replace`, so "
        "it has no honest tie-break and must raise HELPER_OUTPUT_INVALID "
        "rather than pick. Picking makes the real target read as uncalled AND "
        "certifies the decoy — a false BREACH and a false certification at one "
        "site. P4 ruled: make the collision loud. See "
        "_import_path_qualifiers' WHAT THIS DOES NOT CLOSE, item 3"
    )
