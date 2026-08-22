r"""D3 seals (P2) — fixture reachability.

Written against ``src/claude_dispatcher/fixture_reachability.py`` at ``57cf6a9``
by an author who did not write the scaffold and does not write the bodies.

AMENDED BY P4, 2026-08-10, RULING ON THE FOUR DISPUTES THIS FILE RAISED
=======================================================================
Each amendment is named at the row it changed. In summary:

  1. **The two never-observable COLLECTOR rows are REMOVED** from
     ``BOUNDARIES``. The row that inventoried them is replaced by
     :func:`test_no_collector_row_calls_its_own_producer`, which asserts the
     INVARIANT (no row is like that) over the same AST sweep, plus a positive
     control proving the sweep can still find one — because an inventory that
     becomes an empty set is passed by a sweep that has stopped working.
  2. **No replay handle.** ``ObservedFixture`` keeps its five strings.
     ``check_observation`` instead gains a ``differential`` a caller supplies,
     and ``(DIVERGED, NOT_MEASURED)`` — the state when nobody can supply one —
     joins the ruling grid as ABSTAIN rather than raising. The claim ticket
     this file wrote is redeemed at
     :func:`test_check_observation_abstains_when_no_differential_is_supplied`
     and its new partner row.
  3. **The property was the right thing to seal.** ``observe``'s contract now
     names the ``sys.modules`` sweep; the seal is unchanged, which is the
     point of having sealed the property.
  4. **The over-call is confirmed and corrected.** Exactly ONE stub file has a
     gap. The scaffold's instance-(B) narrative and ``StubGap``'s docstring now
     say so.

And on the two items this file sealed around rather than disputing: no
``extract_value`` was added (reasons on ``Boundary.extract_outcome``, with the
coupling made loud instead, in
:func:`test_observe_raises_when_extract_outcome_has_gone_stale`); and
``classify_value`` no longer discriminates on prose at all, because ``Witness``
gained a typed ``gap``
(:func:`test_classify_value_reads_the_gap_and_not_the_prose`).

WHAT A READER SHOULD CHECK FIRST
================================
This module is about seals that cannot fail. A vacuous row *here* is
self-refuting, so every row below is either red at HEAD (the twelve contracts
raise :class:`NotImplementedError`) or, for the four rows that pin the parts of
the scaffold that ARE implemented (:data:`BOUNDARIES`, :func:`boundary_for`),
mutation-verified in a clone and named as such in its own docstring.

THE FLAGSHIP IS ALREADY FIXED, AND THIS FILE DOES NOT PRETEND OTHERWISE
-----------------------------------------------------------------------
``263298d`` put ``role_protocol._unquote_git_path`` into ``risk.collect_diff``,
so over a repository containing ``.github/workflows/ci<LF>x.yml`` the collector
emits the DECODED name and the check's honest answer for instance (A) today is
``REACHED``. The scaffold warns that this is where these seals are most likely
to go vacuous, on the very defect they are written against.

So the flagship appears here TWICE, as a matched pair:

  * :func:`test_flagship_is_reached_against_the_landed_collector` — the real,
    fixed producer. REACHED. This is the row that would go red if someone
    "helpfully" made :func:`classify_value` tolerant of quoting.
  * :func:`test_flagship_pre_fix_collector_is_a_breach` — the SAME witness
    repository, with ``risk.collect_diff`` swapped for
    :func:`_collect_diff_before_263298d`, a local reconstruction of the
    undecoded numstat split. DIVERGED, OPPOSITE_DISPOSITION, BREACH, and no
    declaration touches it.

The pair is the evidence. One row alone proves nothing: a mechanism that
answered REACHED unconditionally passes the first, and a mechanism that
answered BREACH unconditionally passes the second.

WHAT THESE SEALS DELIBERATELY DO NOT CLAIM
-------------------------------------------
Nothing here reads an assertion. The scaffold rules an assertion-side reader
out of scope in as many words, so a tautological row, a comment-inclusive
substring match, and a completeness sweep that omits an outcome are all outside
this unit and are NOT sealed here. Claiming them would be the same shape of lie
the module exists to close.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_dispatcher import fixture_reachability as fr
from claude_dispatcher import repo_config, risk, role_protocol
from claude_dispatcher.fixture_reachability import (
    BOUNDARIES,
    Boundary,
    BoundaryKind,
    Consequence,
    FindingDisposition,
    FixtureReachabilityError,
    GateDisposition,
    ObservedFixture,
    Reachability,
    ReachabilityDeclaration,
    ValueKind,
    Witness,
    WitnessGap,
    adjudicate,
    boundary_for,
    check_observation,
    check_suite,
    classify_value,
    construct_witness,
    gate_disposition,
    git_subcommand,
    measure_consequence,
    modelled_subcommands,
    observe,
    stub_gaps,
)

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_SRC = _REPO_ROOT / "src" / "claude_dispatcher"

#: The path whose rendering defeated four seals and every ``.github/**`` deny
#: rule. A REAL line feed, exactly as instance (A) describes it.
_LF_PATH = ".github/workflows/ci\nx.yml"

#: What ``git diff --numstat --no-renames`` actually prints for that file.
#: Measured against a real repository on this worktree; the quotes and the
#: two-character ``\n`` are literal.
_LF_RENDERING = '".github/workflows/ci\\nx.yml"'


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )


def _witness_repo(root: Path, filename: str) -> Path:
    """A repo on ``main`` with a seed commit and, on ``feat/x``, ``filename``.

    The same recipe :func:`construct_witness` is contracted to build, written
    out here so the seals that do NOT go through the mechanism (the two
    disposition probes of the flagship pair) rest on a repository built the same
    way, and so a reader can reproduce it by hand.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main", ".")
    _git(root, "config", "user.email", "seal@example.invalid")
    _git(root, "config", "user.name", "seal")
    (root / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "seed")
    _git(root, "checkout", "-qb", "feat/x")
    target = root / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "add")
    return root


def _collect_diff_before_263298d(
    worktree, base_ref: str, head_ref: str = "HEAD"
) -> list[risk.FileDiff]:
    r"""``risk.collect_diff`` as it stood BEFORE ``263298d`` — no decoder.

    The scaffold is explicit that the flagship cannot be a live red row without
    this, and that budgeting for it is the difference between a seal about the
    mechanism and a seal about nothing. It is the same numstat split the landed
    function performs, with the one line that matters removed: the path field is
    passed on as git rendered it.

    Kept deliberately small and local. It is a fixture, not a second
    implementation: nothing outside the flagship pair may import it.
    """
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--numstat",
            "--no-renames",
            f"{base_ref}...{head_ref}",
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )
    out: list[risk.FileDiff] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ins = 0 if parts[0] == "-" else int(parts[0])
        dels = 0 if parts[1] == "-" else int(parts[1])
        out.append(risk.FileDiff(path=parts[2], insertions=ins, deletions=dels))
    return out


def _risk_level(path: str) -> str:
    """``risk.evaluate``'s level for a one-file diff at ``path``.

    Everything except the path is held identical between the two calls of the
    differential, which is the obligation :func:`measure_consequence`'s contract
    puts on its caller in as many words.
    """
    return risk.evaluate(
        size_label="S",
        labels=[],
        changed_files=[risk.FileDiff(path=path, insertions=1, deletions=0)],
        verified=True,
        verification_iterations=0,
    ).level


def _witness(*, produced=(), gap=None, detail="") -> Witness:
    return Witness(
        recipe="hand-built for a pure-decision seal",
        produced=tuple(produced),
        environment={"sys.platform": sys.platform},
        gap=gap,
        detail=detail,
    )


def _observed(
    boundary: Boundary,
    value: str,
    outcome: str,
    *,
    test_id: str = "tests/test_x.py::test_row",
    cut: tuple[str, ...] | None = None,
) -> ObservedFixture:
    return ObservedFixture(
        boundary=boundary,
        value=value,
        outcome=outcome,
        test_id=test_id,
        call_site="tests/test_x.py:1",
        cut_boundaries=cut if cut is not None else (boundary.producer,),
    )


def _finding(
    reachability: Reachability,
    consequence: Consequence,
    *,
    observed: ObservedFixture | None = None,
    neighbour: str | None = None,
) -> fr.Finding:
    obs = observed if observed is not None else _observed(_RISK_ROW, "p.py", "low")
    return fr.Finding(
        observed=obs,
        reachability=reachability,
        consequence=consequence,
        neighbour=neighbour,
        witness=_witness(produced=("p.py",)),
        detail="",
    )


def _row(producer: str) -> Boundary:
    found = boundary_for(producer)
    assert found is not None, f"BOUNDARIES no longer names {producer!r}"
    return found


_RISK_ROW = _row("claude_dispatcher.risk.collect_diff")
_PATHS_ROW = _row("claude_dispatcher.role_protocol.changed_paths_between")
_BLOB_SEAM_ROW = _row("git via claude_dispatcher.repo_config._run_git")
_BRANCH_SEAM_ROW = _row("git via claude_dispatcher.role_protocol._run_git_capture")


# --------------------------------------------------------------------------- #
# Part 1 — the boundary table and its one implemented lookup
#
# These four rows are GREEN at HEAD, because BOUNDARIES and boundary_for are
# implemented in the scaffold. Each names the mutation that reddens it.
# --------------------------------------------------------------------------- #


def test_every_boundary_row_is_well_formed():
    """Both outcome sets non-empty and disjoint, on every row.

    The scaffold makes this a load-bearing invariant rather than tidiness: the
    differential compares BY DISPOSITION, so an outcome appearing on both sides
    would make ``gate_disposition`` answer according to which set is consulted
    first and would let two opposed outcomes compare equal.

    Reddens on: emptying either set on any row; moving ``"skipped"`` from
    ``proceed_outcomes`` to ``refuse_outcomes`` without removing it from the
    first (measured in a clone).
    """
    assert BOUNDARIES, "an empty table is a check that observes nothing"
    for b in BOUNDARIES:
        assert b.proceed_outcomes, f"{b.consumer}: no proceed outcomes"
        assert b.refuse_outcomes, f"{b.consumer}: no refuse outcomes"
        overlap = set(b.proceed_outcomes) & set(b.refuse_outcomes)
        assert not overlap, f"{b.consumer}: {overlap} is on both sides of the gate"
        assert b.rationale.strip(), f"{b.consumer}: a row with no rationale"
        assert "." in b.consumer, f"{b.consumer} is not fully qualified"


def test_every_named_consumer_and_in_repo_producer_resolves():
    """Every name in the table is a real callable in the package today.

    A written-out table drifts silently when the code moves under it; this is
    the cheapest half of the two-way pin. SEAM producers are spelled
    ``git via <injection point>`` and the injection point is resolved.

    Reddens on: renaming any of the six consumers, or the four collector
    producers, in ``src/`` (measured in a clone by renaming
    ``risk.collect_diff``).
    """
    for b in BOUNDARIES:
        for qualified in (b.producer, b.consumer):
            name = qualified.split(" via ")[-1]
            module_name, _, attr = name.rpartition(".")
            module = importlib.import_module(module_name)
            assert callable(
                getattr(module, attr)
            ), f"{qualified} does not resolve to a callable"


def test_boundary_for_is_keyed_on_the_fully_qualified_name():
    """The lookup answers on qualified names and refuses bare ones.

    The scaffold's reason, verbatim, is that a seal must not be able to get an
    answer by passing a bare function name. That is a property of the lookup and
    it is the reason SEAM producers carry their injection point.

    Reddens on: keying the comprehension on ``b.producer.rpartition('.')[2]``.
    """
    assert boundary_for("claude_dispatcher.risk.collect_diff") is _RISK_ROW
    assert boundary_for("collect_diff") is None
    assert boundary_for("claude_dispatcher.risk.evaluate") is None
    assert boundary_for("git") is None
    assert _BLOB_SEAM_ROW is not _BRANCH_SEAM_ROW


def test_boundary_for_raises_when_one_producer_owns_two_rows(monkeypatch):
    """Two rows for one producer is a table error, never a lookup outcome.

    The scaffold spells out the harm: returning the first match would give one
    consumer the other's PROCEED set, and a differential run under the wrong
    vocabulary reports agreement — the permissive answer.

    Reddens on: ``return found[0] if found else None`` without the length guard.
    """
    twinned = BOUNDARIES + (
        Boundary(
            producer=_RISK_ROW.producer,
            consumer="claude_dispatcher.risk.something_else",
            kind=BoundaryKind.COLLECTOR,
            value_kind=ValueKind.GIT_PATH,
            proceed_outcomes=("low",),
            refuse_outcomes=("elevated",),
            extract_outcome="level",
            rationale="a second row for the same producer",
        ),
    )
    monkeypatch.setattr(fr, "BOUNDARIES", twinned)
    with pytest.raises(FixtureReachabilityError) as exc:
        boundary_for(_RISK_ROW.producer)
    assert _RISK_ROW.producer in str(exc.value)
    assert "claude_dispatcher.risk.something_else" in str(exc.value)


def _consumer_calls_producer(producer: str, consumer: str) -> bool:
    """Does ``consumer``'s own body call ``producer``? Read from ``src/`` by AST.

    The one measurement behind :func:`test_no_collector_row_calls_its_own_producer`
    and behind its positive control, so both run the identical sweep and a sweep
    that stops working cannot pass one while the other covers for it.
    """
    _, _, prod_name = producer.rpartition(".")
    cons_mod, _, cons_name = consumer.rpartition(".")
    source = Path(importlib.import_module(cons_mod).__file__).read_text(
        encoding="utf-8"
    )
    fn = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == cons_name
    )
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if called == prod_name:
            return True
    return False


#: Two pairs in ``src/`` in which the consumer calls its own producer inside its
#: own body. NOT boundaries — they were ``BOUNDARIES`` rows until P4 removed
#: them on dispute 1, and the code is still there, which is what makes them the
#: positive control the invariant below needs.
_SELF_CALLING_PAIRS = (
    (
        "claude_dispatcher.seal_verify.partition_changed",
        "claude_dispatcher.seal_verify.run_seal_inversion",
    ),
    (
        "claude_dispatcher.blast_radius.changed_files",
        "claude_dispatcher.blast_radius.build_blast_radius",
    ),
)


def test_no_collector_row_calls_its_own_producer():
    """No COLLECTOR row's consumer calls its own producer. An INVARIANT.

    P4, 2026-08-10, dispute 1. This file's earlier version INVENTORIED the two
    rows that were like that and pinned the inventory. P4 removed both rows
    instead — a consumer that calls its own producer takes no argument a fixture
    can be substituted at, so the row can never fire, and :class:`Boundary`'s own
    contract says such a row "will be read as coverage". Keeping them behind a
    "never observable" marker was refused because it would put two permanent
    members into ``boundaries_never_observed``, which the report designates as
    its non-vacuity field.

    So the assertion is now that the measured set is EMPTY, which is a stronger
    claim than the inventory was: every COLLECTOR row in the table is a row a
    fixture can really be substituted at, and a new row that isn't — or a
    consumer refactored to call its producer inline — reddens on the commit that
    does it.

    **An empty-set assertion is passed by a sweep that has stopped working**,
    which is this module's own subject matter turned on its own seal. Hence the
    positive control: the same sweep, over the two pairs the removed rows named,
    which are still in ``src/`` and must still be detected.

    Reddens on: re-adding either removed row to ``BOUNDARIES``; a sweep that
    only looks at ``ast.Name`` and not ``ast.Attribute``, or that does not walk
    nested bodies (both measured in a clone — the control goes red and the
    invariant stays green, which is exactly the pair that catches it).
    """
    measured = {
        b.producer
        for b in BOUNDARIES
        if b.kind is BoundaryKind.COLLECTOR
        and _consumer_calls_producer(b.producer, b.consumer)
    }
    assert measured == set(), (
        f"{sorted(measured)}: a COLLECTOR row whose consumer calls its own "
        "producer can never be observed and is permanently 'never observed'. "
        "Either the row names the wrong pair, or there is no substitution here "
        "and the row does not belong in BOUNDARIES; see dispute 1."
    )
    assert [b for b in BOUNDARIES if b.kind is BoundaryKind.COLLECTOR], (
        "the sweep ran over no COLLECTOR rows at all, so the empty set above "
        "means nothing"
    )
    for producer, consumer in _SELF_CALLING_PAIRS:
        assert _consumer_calls_producer(producer, consumer), (
            f"the positive control failed: {consumer} no longer calls "
            f"{producer}, so the sweep above proves nothing. Either the sweep "
            "broke, or that pair became substitutable — in which case it is a "
            "candidate BOUNDARIES row and this control needs replacing."
        )


# --------------------------------------------------------------------------- #
# Part 2 — gate_disposition: the enum member that exists to be named, not
# returned
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("boundary", "outcome", "expected"),
    [
        pytest.param(b, o, exp, id=f"{b.consumer.rpartition('.')[2]}-{o}")
        for b in BOUNDARIES
        for o, exp in (
            [(x, GateDisposition.PROCEED) for x in b.proceed_outcomes]
            + [(x, GateDisposition.REFUSE) for x in b.refuse_outcomes]
        )
    ],
)
def test_gate_disposition_reads_the_two_written_out_sets(boundary, outcome, expected):
    """Every outcome the table names lands on the side the table puts it.

    Parametrized over the table rather than written out, so a row that gains an
    outcome gains a seal, and every one of the eleven outcome strings in
    ``BOUNDARIES`` is exercised. Note in particular ``"absent"`` on the blob
    seam row: ``None`` means "the tree does not contain it", which suppresses
    every signature change in the file, so it is a PROCEED.

    Eleven and not seventeen since P4 removed two rows on dispute 1; the
    ``"skipped"`` example this docstring used to give lived on one of them.
    """
    assert gate_disposition(boundary, outcome) is expected


def test_gate_disposition_raises_on_an_outcome_neither_set_names():
    """An unclassified outcome RAISES; UNKNOWN is never returned.

    The scaffold's reason is the engine: defaulting an unclassified outcome to
    either side would make it compare EQUAL to an already-classified one, and
    ``measure_consequence`` would then report SAME_DISPOSITION for a pair that
    differs. The differential silently reporting agreement is the same shape as
    the seals this module is written against.

    The error must name the outcome and BOTH sets, so the human editing
    BOUNDARIES can see what it has to be disjoint from.
    """
    with pytest.raises(FixtureReachabilityError) as exc:
        gate_disposition(_RISK_ROW, "moderate")
    message = str(exc.value)
    assert "moderate" in message
    assert "low" in message and "elevated" in message


def test_gate_disposition_does_not_fold_case_or_whitespace():
    """``"LOW"`` and ``" low"`` are not ``"low"``.

    A tolerance here is the same failure as a tolerance in ``classify_value``:
    it makes an outcome the consumer never emits compare equal to one it does.
    """
    for near_miss in ("LOW", " low", "low ", "Low", "elevated\n"):
        with pytest.raises(FixtureReachabilityError):
            gate_disposition(_RISK_ROW, near_miss)


def test_gate_disposition_never_returns_unknown_for_a_named_outcome():
    """Sweep: no row, no outcome, ever yields UNKNOWN."""
    for b in BOUNDARIES:
        for outcome in (*b.proceed_outcomes, *b.refuse_outcomes):
            assert gate_disposition(b, outcome) is not GateDisposition.UNKNOWN


# --------------------------------------------------------------------------- #
# Part 3 — classify_value: string EQUALITY, and nothing that resembles it
# --------------------------------------------------------------------------- #


def test_classify_value_reached_when_the_producer_emitted_exactly_it():
    assert (
        classify_value(
            value="src/app.py", witness=_witness(produced=("a.py", "src/app.py"))
        )
        is Reachability.REACHED
    )


def test_classify_value_diverged_when_the_producer_emitted_something_else():
    assert (
        classify_value(value="src/app.py", witness=_witness(produced=("src/other.py",)))
        is Reachability.DIVERGED
    )


@pytest.mark.parametrize(
    ("value", "produced"),
    [
        pytest.param(_LF_PATH, (_LF_RENDERING,), id="flagship-decoded-vs-rendering"),
        pytest.param(_LF_RENDERING, (_LF_PATH,), id="flagship-rendering-vs-decoded"),
        pytest.param("tests/a b.py", ('"tests/a b.py"',), id="quote-wrapped"),
        pytest.param("tests/a\tb.py", ('"tests/a\\tb.py"',), id="tab-escape"),
        pytest.param("src/app.py", ("src/app.py\n",), id="trailing-newline"),
        pytest.param("src/app.py", (" src/app.py",), id="leading-space"),
        pytest.param(
            "tests/tést.py", ('"tests/t\\303\\251st.py"',), id="octal-escape"
        ),
    ],
)
def test_classify_value_is_equality_and_admits_no_normalisation(value, produced):
    """A value that is NEARLY the produced value is DIVERGED, never REACHED.

    The scaffold says this in as many words and asks for a seal on it: every
    instance of this defect class is a value that is nearly the right value, and
    "a 'helpful' normaliser added by a later author is the single most likely way
    this check is silently disabled".

    Seven pairs, each a real rendering git emits for a real name. The first two
    ARE instance (A), in both directions.

    Reddens on: ``classify_value`` comparing through ``_unquote_git_path``,
    through ``strip('"')``, through ``.strip()``, or case-insensitively.
    """
    assert (
        classify_value(value=value, witness=_witness(produced=produced))
        is Reachability.DIVERGED
    )


def test_classify_value_refuses_a_witness_that_says_nothing_or_two_things():
    """Both contradictions are ERRORS, not states.

    "A witness that neither produced nor explained is a non-judgement, and the
    whole point is that a non-judgement must not read as an answer." Note which
    direction the harm runs on the first: the tempting default is NO_STRATEGY,
    which is at least an abstention — but it would report an abstention the
    checker never made, and the abstention count is this mechanism's own
    coverage figure.

    P4, 2026-08-10, added the opposite contradiction with
    :class:`WitnessGap`: a witness that BOTH produced values and carries a gap
    was assembled by something that did not know which had happened, and a body
    that resolves it either way (produced wins / gap wins) is picking one of two
    answers to a question the witness cannot be asked.
    """
    with pytest.raises(FixtureReachabilityError):
        classify_value(
            value="src/app.py", witness=_witness(produced=(), gap=None, detail="")
        )
    with pytest.raises(FixtureReachabilityError):
        classify_value(
            value="src/app.py",
            witness=_witness(
                produced=("src/app.py",),
                gap=WitnessGap.NO_STRATEGY,
                detail="produced values AND a gap",
            ),
        )


def test_classify_value_reads_the_gap_and_not_the_prose(tmp_path):
    """The two empty-``produced`` states are told apart by ``gap``, ONLY.

    P4 ruling, 2026-08-10, on this file's second smaller item. The complaint
    was that ``classify_value``'s discrimination between an OS refusal and a
    missing strategy rested on ``Witness.detail`` wording that no contract
    fixed — two functions in one module agreeing on a prose format, written by
    the same author, green whatever the strings are, and one reworded error
    message away from moving an unsuppressible abstention into a DECLARABLE
    REPORT. The ruling was not to specify the wording but to stop deciding on
    prose: :class:`Witness` carries a typed ``gap``, and ``detail`` is evidence
    for a human that no decision reads.

    The seal has three parts and needs all three:

      1. the round trip — the two states as :func:`construct_witness` really
         builds them still classify as they should, so the contract and the
         constructor agree;
      2. the CROSS — a witness carrying the refusal's ``detail`` prose beside
         the NO_STRATEGY ``gap``, and the reverse. The gap must win both times.
         This is the row a body that sniffs ``detail`` fails, and it is why
         this is not a tautological read-back of a field;
      3. a hand-built witness classifies identically to the real one, which
         forbids a body smuggling the answer through an attribute that is not
         one of the Witness's five declared fields.
    """
    unrepresentable = construct_witness(
        _RISK_ROW, "bad\0name.py", workspace=tmp_path / "ws-unrep"
    )
    assert unrepresentable.produced == ()
    assert unrepresentable.gap is WitnessGap.REFUSED
    assert unrepresentable.detail.strip(), "an unrepresentable witness must explain"
    assert (
        classify_value(value="bad\0name.py", witness=unrepresentable)
        is Reachability.UNREPRESENTABLE
    )

    no_strategy = construct_witness(
        _BLOB_SEAM_ROW, "tests.test_x._run_stub", workspace=tmp_path / "ws-nostrat"
    )
    assert no_strategy.produced == ()
    assert no_strategy.gap is WitnessGap.NO_STRATEGY
    assert no_strategy.detail.strip(), "an abstention must say what it abstained on"
    assert (
        classify_value(value="tests.test_x._run_stub", witness=no_strategy)
        is Reachability.NO_STRATEGY
    )

    # The cross. Each prose string is paired with the OTHER state's gap, using
    # the exact details the constructor emitted, so a body that discriminates on
    # wording gets both of these backwards.
    assert (
        classify_value(
            value="bad\0name.py",
            witness=_witness(
                gap=WitnessGap.NO_STRATEGY, detail=unrepresentable.detail
            ),
        )
        is Reachability.NO_STRATEGY
    ), "detail is prose; the gap decides"
    assert (
        classify_value(
            value="tests.test_x._run_stub",
            witness=_witness(gap=WitnessGap.REFUSED, detail=no_strategy.detail),
        )
        is Reachability.UNREPRESENTABLE
    ), "detail is prose; the gap decides"

    # Hand-built witnesses agree with the real ones, field for field.
    assert (
        classify_value(
            value="bad\0name.py",
            witness=_witness(gap=WitnessGap.REFUSED, detail=unrepresentable.detail),
        )
        is Reachability.UNREPRESENTABLE
    )
    assert (
        classify_value(
            value="tests.test_x._run_stub",
            witness=_witness(gap=WitnessGap.NO_STRATEGY, detail=no_strategy.detail),
        )
        is Reachability.NO_STRATEGY
    )


# --------------------------------------------------------------------------- #
# Part 4 — measure_consequence: the differential, compared by DISPOSITION
# --------------------------------------------------------------------------- #


def test_measure_consequence_without_a_neighbour_is_not_measured():
    """No neighbour is NOT_MEASURED — a named state, never a blank."""
    assert (
        measure_consequence(_RISK_ROW, fixture_outcome="low", neighbour_outcome=None)
        is Consequence.NOT_MEASURED
    )


def test_measure_consequence_compares_by_disposition_not_by_string():
    """Two DIFFERENT refusals are still SAME_DISPOSITION.

    ``"violation"`` and ``"undetermined"`` are different strings and the same
    side of the gate. The scaffold: "it is the crossing of the gate that
    matters, and it is the only thing that distinguishes the two cases the brief
    asked to separate."

    Reddens on: ``fixture_outcome == neighbour_outcome``.
    """
    assert (
        measure_consequence(
            _PATHS_ROW, fixture_outcome="violation", neighbour_outcome="undetermined"
        )
        is Consequence.SAME_DISPOSITION
    )
    # And on the PROCEED side, which needs a row with two of them. This used to
    # be the seal-verify row's ``passed``/``skipped``; P4 removed that row on
    # dispute 1, and the blob seam's ``text``/``absent`` is the surviving pair —
    # a better one, in fact, since ``absent`` proceeding is the whole reason
    # instance (B) mattered: None means "the tree does not contain it", which
    # suppresses every signature change in the file.
    assert (
        measure_consequence(
            _BLOB_SEAM_ROW, fixture_outcome="text", neighbour_outcome="absent"
        )
        is Consequence.SAME_DISPOSITION
    )


def test_measure_consequence_names_the_crossing():
    """PROCEED against REFUSE, either way round, is OPPOSITE_DISPOSITION."""
    assert (
        measure_consequence(
            _RISK_ROW, fixture_outcome="elevated", neighbour_outcome="low"
        )
        is Consequence.OPPOSITE_DISPOSITION
    )
    assert (
        measure_consequence(
            _RISK_ROW, fixture_outcome="low", neighbour_outcome="elevated"
        )
        is Consequence.OPPOSITE_DISPOSITION
    )
    assert (
        measure_consequence(
            _RISK_ROW, fixture_outcome="low", neighbour_outcome="low"
        )
        is Consequence.SAME_DISPOSITION
    )


@pytest.mark.parametrize(
    ("fixture_outcome", "neighbour_outcome"),
    [("moderate", "low"), ("low", "moderate")],
)
def test_measure_consequence_propagates_an_unclassifiable_outcome(
    fixture_outcome, neighbour_outcome
):
    """An outcome in neither set aborts the differential, on either side.

    Not SAME_DISPOSITION, not NOT_MEASURED: a differential the mechanism could
    not carry out is an error, and "the check could not run" and "the check ran
    and found nothing" must not be the same value.
    """
    with pytest.raises(FixtureReachabilityError):
        measure_consequence(
            _RISK_ROW,
            fixture_outcome=fixture_outcome,
            neighbour_outcome=neighbour_outcome,
        )


# --------------------------------------------------------------------------- #
# Part 5 — adjudicate: total over the grid, and what a declaration cannot buy
# --------------------------------------------------------------------------- #

_RULING_TABLE = {
    (Reachability.REACHED, Consequence.NOT_MEASURED): (
        FindingDisposition.OK,
        FindingDisposition.OK,
    ),
    (Reachability.DIVERGED, Consequence.OPPOSITE_DISPOSITION): (
        FindingDisposition.BREACH,
        FindingDisposition.BREACH,
    ),
    (Reachability.DIVERGED, Consequence.SAME_DISPOSITION): (
        FindingDisposition.REPORT,
        FindingDisposition.ACCEPTED,
    ),
    # P4, 2026-08-10, dispute 2. This pair used to raise, because nothing could
    # produce it. It is now the ordinary outcome of a DIVERGED finding whose
    # caller supplied no ``differential``, and it is UNDECLARABLE: a declaration
    # that could silence it would buy silence on a measurement never taken.
    (Reachability.DIVERGED, Consequence.NOT_MEASURED): (
        FindingDisposition.ABSTAIN,
        FindingDisposition.ABSTAIN,
    ),
    (Reachability.UNREPRESENTABLE, Consequence.NOT_MEASURED): (
        FindingDisposition.REPORT,
        FindingDisposition.ACCEPTED,
    ),
    (Reachability.NO_STRATEGY, Consequence.NOT_MEASURED): (
        FindingDisposition.ABSTAIN,
        FindingDisposition.ABSTAIN,
    ),
}


def _matching_declaration(finding: fr.Finding) -> ReachabilityDeclaration:
    return ReachabilityDeclaration(
        test_id=finding.observed.test_id,
        producer=finding.observed.boundary.producer,
        value=finding.observed.value,
        reason="pinned defensive branch",
        guard="tests/test_fixture_reachability.py::test_ruling_table_is_total",
    )


@pytest.mark.parametrize(
    ("reachability", "consequence"),
    [
        pytest.param(r, c, id=f"{r.value}-{c.value}")
        for r in Reachability
        for c in Consequence
    ],
)
def test_ruling_table_is_total_over_the_whole_grid(reachability, consequence):
    """Every one of the twelve (Reachability x Consequence) pairs is answered.

    SIX are named in the scaffold's ruling table; the other SIX must RAISE.
    This is the row that stops a new enum member falling through to the
    permissive answer — the failure the module docstring warns about twice and
    ``skills/explicit-state.md`` warns about generally.

    Both declaration states are exercised on every pair, because what a
    declaration may and may not buy is part of the ruling and not a separate
    question: it may turn REPORT into ACCEPTED and it may do nothing else.

    P4, 2026-08-10, dispute 2: ``(DIVERGED, NOT_MEASURED)`` moved from the
    raising six to the ruled six, as ABSTAIN under both declaration states. It
    is the state a DIVERGED finding lands in when its caller supplied no
    ``differential``, which is every caller that holds only an observation list.

    Reddens on: a body with an ``else: return FindingDisposition.OK``; a body
    that lets a declaration touch BREACH or ABSTAIN; a body that rules
    ``DIVERGED, NOT_MEASURED`` as REPORT (the tempting reading — it is not a
    report, nothing was measured to report) or that still raises on it.
    """
    finding = _finding(
        reachability,
        consequence,
        neighbour="src/other.py" if reachability is Reachability.DIVERGED else None,
    )
    expected = _RULING_TABLE.get((reachability, consequence))
    if expected is None:
        with pytest.raises(FixtureReachabilityError):
            adjudicate(finding, None)
        with pytest.raises(FixtureReachabilityError):
            adjudicate(finding, _matching_declaration(finding))
        return
    undeclared, declared = expected
    assert adjudicate(finding, None) is undeclared
    assert adjudicate(finding, _matching_declaration(finding)) is declared


def test_a_breach_is_unappealable():
    """No declaration accepts OPPOSITE_DISPOSITION. Stated on its own row.

    The grid row above covers it, and it is repeated here alone because it is
    the single ruling the whole design turns on: "Either the fixture becomes the
    neighbour, or the producer is fixed so it emits the fixture. There is no
    third resolution and no annotation."
    """
    finding = _finding(
        Reachability.DIVERGED,
        Consequence.OPPOSITE_DISPOSITION,
        neighbour=_LF_RENDERING,
    )
    assert adjudicate(finding, _matching_declaration(finding)) is (
        FindingDisposition.BREACH
    )


def test_an_abstention_is_not_suppressible():
    """NO_STRATEGY is ABSTAIN with or without a declaration.

    "An abstention is not a pass and must not be suppressible: the count of
    abstentions is the mechanism's own coverage figure and a run that hides it
    is reporting a judgement it did not make."
    """
    finding = _finding(Reachability.NO_STRATEGY, Consequence.NOT_MEASURED)
    assert adjudicate(finding, None) is FindingDisposition.ABSTAIN
    assert adjudicate(finding, _matching_declaration(finding)) is (
        FindingDisposition.ABSTAIN
    )


@pytest.mark.parametrize("wrong_key", ["test_id", "producer", "value"])
def test_a_declaration_that_misses_any_of_its_three_keys_buys_nothing(wrong_key):
    """All three keys must match exactly, or the declaration is ignored.

    "Silently ignoring it would let a typo look like an accepted state." Each
    key is missed on its own, so a body that checks two of the three reddens on
    exactly the third.
    """
    finding = _finding(Reachability.UNREPRESENTABLE, Consequence.NOT_MEASURED)
    good = _matching_declaration(finding)
    fields = {
        "test_id": good.test_id,
        "producer": good.producer,
        "value": good.value,
    }
    fields[wrong_key] = fields[wrong_key] + "-typo"
    stale = ReachabilityDeclaration(
        reason=good.reason, guard=good.guard, **fields
    )
    assert adjudicate(finding, stale) is FindingDisposition.REPORT


# --------------------------------------------------------------------------- #
# Part 6 — construct_witness: the state is derived FROM the value
# --------------------------------------------------------------------------- #


def test_construct_witness_runs_the_real_collector_over_a_built_repository(tmp_path):
    """An ordinary path: build the state, run the producer, get it back.

    Also pins the two things that make a Witness usable as evidence — a recipe a
    human can follow, and an environment fingerprint, without which limit 5
    (UNREPRESENTABLE is a property of THIS machine) has nothing to rest on.
    """
    witness = construct_witness(_RISK_ROW, "src/app.py", workspace=tmp_path)
    assert "src/app.py" in witness.produced
    assert classify_value(value="src/app.py", witness=witness) is Reachability.REACHED
    assert witness.recipe.strip(), "a finding whose recipe cannot be followed is dead"
    assert set(witness.environment) >= {"git", "platform", "filesystem_encoding"}
    assert witness.gap is None, "a witness that produced values has no gap"
    assert witness.detail == "", "REACHED explains nothing"
    assert any(tmp_path.iterdir()), "the witness repo must live under workspace"


def test_construct_witness_covers_the_second_collector_row(tmp_path):
    """``changed_paths_between`` is interrogated over a real repo too.

    Two collector rows exercised, not one: a body that special-cases
    ``risk.collect_diff`` and abstains on everything else would pass every other
    dynamic row in this file.
    """
    witness = construct_witness(_PATHS_ROW, "src/app.py", workspace=tmp_path)
    assert witness.produced, "changed_paths_between emitted nothing over its witness"
    assert classify_value(value="src/app.py", witness=witness) is Reachability.REACHED


@pytest.mark.parametrize(
    ("value", "why"),
    [
        pytest.param("bad\0name.py", "embedded NUL", id="nul"),
        pytest.param("", "the empty path", id="empty"),
        pytest.param("x" * 300 + ".py", "a component over NAME_MAX", id="name-max"),
    ],
)
def test_construct_witness_reports_unrepresentable_with_the_refusing_layer(
    tmp_path, value, why
):
    """A name the machine cannot hold is UNREPRESENTABLE, with a reason.

    This is where a genuinely defensive row lands, and it is the only state a
    declaration is load-bearing for — so the detail must name the refusing
    layer, or the human writing the declaration has nothing to read.

    Reddens on: a body that catches ``OSError`` and returns an empty Witness
    with no gap (which ``classify_value`` then has to raise on), and on a body
    that lets an unrepresentable name fall through to NO_STRATEGY — the gap
    assertion below is what separates those two, since P4 made the gap and not
    the prose the thing ``classify_value`` reads.
    """
    witness = construct_witness(_RISK_ROW, value, workspace=tmp_path / "ws")
    assert witness.produced == ()
    assert witness.gap is WitnessGap.REFUSED
    assert witness.detail.strip(), f"{why} must name the layer that refused"
    assert classify_value(value=value, witness=witness) is (
        Reachability.UNREPRESENTABLE
    )


@pytest.mark.parametrize(
    "boundary",
    [b for b in BOUNDARIES if b.kind is BoundaryKind.SEAM],
    ids=lambda b: b.consumer.rpartition(".")[2],
)
def test_git_response_has_no_dynamic_strategy_and_says_so(tmp_path, boundary):
    """Every SEAM row abstains on the collector face. THE contract, not a gap.

    ``ValueKind.GIT_RESPONSE`` gets a witness only when the row supplies a
    repository recipe, and no row does. So both seam rows resolve to NO_STRATEGY
    dynamically and are carried entirely by :func:`stub_gaps` — which means the
    first real report is dominated by abstentions, and a reader has to be able
    to tell that from a clean run.

    Reddens on: a body that quietly returns a REACHED witness for a seam row,
    which is the exact degradation ("green on everything it does not
    understand") the fourth Reachability state exists to prevent.
    """
    witness = construct_witness(
        boundary, "tests.test_x._run_stub", workspace=tmp_path / boundary.consumer[-8:]
    )
    assert witness.produced == ()
    assert witness.gap is WitnessGap.NO_STRATEGY
    # The detail is prose and nothing decides on it (P4, 2026-08-10) — but a
    # human reading an abstention has to be told WHICH value kind abstained, so
    # it is still required to name one.
    assert ValueKind.GIT_RESPONSE.value in witness.detail or "GIT_RESPONSE" in (
        witness.detail
    )
    assert (
        classify_value(value="tests.test_x._run_stub", witness=witness)
        is Reachability.NO_STRATEGY
    )


def test_construct_witness_raises_on_a_value_kind_it_does_not_handle(tmp_path):
    """Total over ValueKind, and RAISES rather than fabricating a Witness.

    "an empty produced list would classify as DIVERGED against a neighbour that
    does not exist, which is a fabricated finding, and fabricated findings are
    how a mechanism gets switched off."
    """
    bogus = Boundary(
        producer=_RISK_ROW.producer,
        consumer=_RISK_ROW.consumer,
        kind=BoundaryKind.COLLECTOR,
        value_kind="a-kind-that-does-not-exist",  # type: ignore[arg-type]
        proceed_outcomes=("low",),
        refuse_outcomes=("elevated",),
        extract_outcome="level",
        rationale="a row with a value kind no strategy names",
    )
    with pytest.raises(FixtureReachabilityError):
        construct_witness(bogus, "src/app.py", workspace=tmp_path)


# --------------------------------------------------------------------------- #
# Part 7 — INSTANCE (A), the flagship, as a matched pair
# --------------------------------------------------------------------------- #


def test_flagship_is_reached_against_the_landed_collector(tmp_path):
    """Instance (A) is REACHED today, and that is the CORRECT answer.

    ``263298d`` decodes, so over a repository containing
    ``.github/workflows/ci<LF>x.yml`` the collector emits the decoded name and
    the fixture the four ``test_glob_newline.py`` rows use is a value production
    really does produce. Reporting a breach here would be the mechanism
    fabricating a finding on a fixed defect — the loudest possible way to be
    switched off.

    Half of the pair. Alone it is satisfied by a mechanism that answers REACHED
    unconditionally; the other half is the discriminator.
    """
    witness = construct_witness(_RISK_ROW, _LF_PATH, workspace=tmp_path)
    assert _LF_PATH in witness.produced
    assert _LF_RENDERING not in witness.produced, (
        "the landed collector must emit the decoded name, not git's rendering"
    )
    assert classify_value(value=_LF_PATH, witness=witness) is Reachability.REACHED
    finding = _finding(
        Reachability.REACHED,
        Consequence.NOT_MEASURED,
        observed=_observed(_RISK_ROW, _LF_PATH, "elevated"),
    )
    assert adjudicate(finding, None) is FindingDisposition.OK


def test_flagship_pre_fix_collector_is_a_breach(tmp_path, monkeypatch):
    """Instance (A) reconstructed: DIVERGED, OPPOSITE_DISPOSITION, BREACH.

    The scaffold requires this row and says why: without the pre-``263298d``
    collector the flagship cannot be a live red row, and "it is the single most
    likely place these seals go vacuous, on the very defect they are written
    against".

    So the producer is swapped for :func:`_collect_diff_before_263298d` — the
    undecoded numstat split — over a real witness repository, and the whole
    engine is driven end to end:

      1. the producer emits git's RENDERING, not the fixture;
      2. ``classify_value`` says DIVERGED and the rendering is the neighbour;
      3. ``risk.evaluate`` REFUSES the fixture (``.github/**`` matches the
         decoded name) and PROCEEDS on the neighbour (the rendering matches no
         glob — the quotes push the anchored pattern off both ends);
      4. the differential is OPPOSITE_DISPOSITION;
      5. the ruling is BREACH, and a declaration does not touch it.

    Step 3 is measured here rather than asserted from the docstring, because it
    is the fact the entire incident rests on.

    The monkeypatch also pins something a body could otherwise get wrong for
    free: the producer must be resolved from ``BOUNDARIES`` at CALL time, by
    module attribute, not bound by value at import.
    """
    monkeypatch.setattr(risk, "collect_diff", _collect_diff_before_263298d)

    witness = construct_witness(_RISK_ROW, _LF_PATH, workspace=tmp_path)
    assert witness.produced == (_LF_RENDERING,), (
        "the pre-fix collector emits git's rendering; if this is the decoded "
        "name the swap did not take and the row below proves nothing"
    )
    assert classify_value(value=_LF_PATH, witness=witness) is Reachability.DIVERGED

    fixture_outcome = _risk_level(_LF_PATH)
    neighbour_outcome = _risk_level(_LF_RENDERING)
    assert fixture_outcome == "elevated"
    assert neighbour_outcome == "low"
    assert gate_disposition(_RISK_ROW, fixture_outcome) is GateDisposition.REFUSE
    assert gate_disposition(_RISK_ROW, neighbour_outcome) is GateDisposition.PROCEED

    consequence = measure_consequence(
        _RISK_ROW,
        fixture_outcome=fixture_outcome,
        neighbour_outcome=neighbour_outcome,
    )
    assert consequence is Consequence.OPPOSITE_DISPOSITION

    finding = fr.Finding(
        observed=_observed(_RISK_ROW, _LF_PATH, fixture_outcome),
        reachability=Reachability.DIVERGED,
        consequence=consequence,
        neighbour=_LF_RENDERING,
        witness=witness,
        detail="pre-263298d collect_diff",
    )
    assert adjudicate(finding, None) is FindingDisposition.BREACH
    assert adjudicate(finding, _matching_declaration(finding)) is (
        FindingDisposition.BREACH
    )


# --------------------------------------------------------------------------- #
# Part 8 — check_observation: the composition, and the multi-cut abstention
# --------------------------------------------------------------------------- #


def test_check_observation_judges_a_multi_cut_first_and_abstains(tmp_path):
    """Two cuts is ABSTAIN, and the detail names every one of them.

    Judged FIRST: "a multi-cut observation's near hop is answerable and
    answering it would imply the far one was checked."

    The value below is perfectly producible — it is an ordinary path — so a body
    that judges the near hop and forgets ``cut_boundaries`` answers OK and
    reddens here. That is what makes the rule seal-able at all: the harm is
    ANSWERING the near hop, not the order in which the work is done, and the
    mutation sweep confirmed the distinction (merely constructing the witness
    early changes nothing and this row correctly does not object to it).
    """
    observed = _observed(
        _PATHS_ROW,
        "src/app.py",
        "clean",
        cut=(_BRANCH_SEAM_ROW.producer, _PATHS_ROW.producer),
    )
    finding = check_observation(observed, workspace=tmp_path)
    assert finding.reachability is Reachability.NO_STRATEGY
    assert finding.consequence is Consequence.NOT_MEASURED
    assert _BRANCH_SEAM_ROW.producer in finding.detail
    assert _PATHS_ROW.producer in finding.detail
    assert adjudicate(finding, None) is FindingDisposition.ABSTAIN


def test_check_observation_on_a_producible_value_is_ok(tmp_path):
    """The ordinary case, end to end, with no second consumer call."""
    finding = check_observation(
        _observed(_RISK_ROW, "src/app.py", "low"), workspace=tmp_path
    )
    assert finding.reachability is Reachability.REACHED
    assert finding.consequence is Consequence.NOT_MEASURED
    assert finding.neighbour is None
    assert finding.witness is not None
    assert adjudicate(finding, None) is FindingDisposition.OK


def test_check_observation_neighbour_is_none_unless_diverged(tmp_path):
    """``neighbour`` is set exactly when the reachability is DIVERGED.

    Pinned on the two states that are cheapest to get wrong: an UNREPRESENTABLE
    with a neighbour would invite a differential against a value nothing
    produced, and a NO_STRATEGY with one would be an abstention that quietly
    answered.
    """
    unrep = check_observation(
        _observed(_RISK_ROW, "bad\0name.py", "elevated"), workspace=tmp_path / "a"
    )
    assert unrep.reachability is Reachability.UNREPRESENTABLE
    assert unrep.neighbour is None
    assert unrep.consequence is Consequence.NOT_MEASURED

    seam = check_observation(
        _observed(_BLOB_SEAM_ROW, "tests.test_x._run_stub", "text"),
        workspace=tmp_path / "b",
    )
    assert seam.reachability is Reachability.NO_STRATEGY
    assert seam.neighbour is None
    assert adjudicate(seam, None) is FindingDisposition.ABSTAIN


def test_check_observation_abstains_when_no_differential_is_supplied(
    tmp_path, monkeypatch
):
    """DIVERGED is found and named; with no differential it is an ABSTENTION.

    **THE CLAIM TICKET THIS FILE WROTE FOR DISPUTE 2, REDEEMED.** The dispute:
    ``check_observation``'s step 3 said to "re-run the consumer with the
    neighbour substituted and nothing else changed", which is not performable
    from this function's inputs — :class:`ObservedFixture` records five strings
    and nothing that can replay the original call. This row used to assert that
    :func:`adjudicate` RAISES on the resulting ``(DIVERGED, NOT_MEASURED)``,
    because that pair was not in the ruling grid.

    P4 ruled, 2026-08-10:

      * **No replay handle**, and the reason is not cost — it is that a handle
        invoked by ``check_suite`` runs after the ``observe`` block has exited,
        in a world where the row's ``tmp_path`` is gone and its monkeypatches
        are undone, so the second call would differ in everything except the
        one value. ``measure_consequence``'s contract says what that produces:
        SAME_DISPOSITION, the permissive answer. A handle would manufacture it
        while appearing to meet the obligation.
      * **Step 3 is delegated**, to a ``differential`` a caller supplies —
        the same placement, and the same stated reason, that
        ``measure_consequence`` already uses for not running the consumer
        itself. The partner row below seals that half.
      * **``(DIVERGED, NOT_MEASURED)`` is ABSTAIN**, not a raise. The
        reachability axis was measured and the consequence axis was not, and
        that half-measured state is what the two-enum split exists to be able
        to say. Raising would abort the whole run on the first divergence and
        leave no report, which for a suite-wide sweep is the same as not having
        the check.

    So what is sealed here is: the two determinate halves, the abstention, and
    that the abstention is NOT suppressible by a declaration — because an
    abstention that a declaration could silence is a coverage figure that lies.
    """
    monkeypatch.setattr(risk, "collect_diff", _collect_diff_before_263298d)
    finding = check_observation(
        _observed(_RISK_ROW, _LF_PATH, "elevated"), workspace=tmp_path
    )
    assert finding.reachability is Reachability.DIVERGED
    assert finding.neighbour == _LF_RENDERING
    assert finding.consequence is Consequence.NOT_MEASURED
    assert finding.detail.strip(), "an unmeasured differential must say so"
    assert adjudicate(finding, None) is FindingDisposition.ABSTAIN
    assert adjudicate(finding, _matching_declaration(finding)) is (
        FindingDisposition.ABSTAIN
    )


def test_check_observation_runs_a_supplied_differential_and_can_reach_breach(
    tmp_path, monkeypatch
):
    """The other half of the dispute-2 ruling: the delegated differential works.

    Without this row the ``differential`` parameter is a contract nothing
    checks, and a body that ignored it entirely would pass every other row in
    this file while making OPPOSITE_DISPOSITION — and therefore BREACH —
    unreachable from ``check_observation``. That is the module's headline
    finding, so it gets a row.

    The closure below is what "everything else held identical" looks like when
    it is really held: it calls the SAME consumer through
    :func:`_risk_level`, with the same size label, labels, verification state
    and file count, and changes the path and nothing else. Its obligation
    cannot be enforced by the mechanism — that is stated on the parameter — but
    it can be written out, and it is.

    Note the pair with the row above: the identical observation, over the
    identical pre-fix collector, is ABSTAIN with no differential and BREACH with
    one. A body that ignores the parameter fails the second; a body that
    fabricates a differential when none was given fails the first. Neither row
    alone is satisfiable by both answers.
    """
    monkeypatch.setattr(risk, "collect_diff", _collect_diff_before_263298d)

    calls: list[str] = []

    def _held_identical(observed: ObservedFixture, neighbour: str) -> str:
        calls.append(neighbour)
        return _risk_level(neighbour)

    observed = _observed(_RISK_ROW, _LF_PATH, "elevated")
    finding = check_observation(
        observed, workspace=tmp_path, differential=_held_identical
    )
    assert calls == [_LF_RENDERING], (
        "the differential must be called exactly once, with the neighbour"
    )
    assert finding.reachability is Reachability.DIVERGED
    assert finding.neighbour == _LF_RENDERING
    assert finding.consequence is Consequence.OPPOSITE_DISPOSITION
    assert adjudicate(finding, None) is FindingDisposition.BREACH
    assert adjudicate(finding, _matching_declaration(finding)) is (
        FindingDisposition.BREACH
    )


def test_a_supplied_differential_is_not_called_unless_diverged(tmp_path):
    """A REACHED observation runs no second call, differential or not.

    "Every other reachability yields NOT_MEASURED without a second call." A body
    that calls the differential unconditionally would put a neighbour outcome
    against a fixture that has no neighbour, and
    :func:`measure_consequence` would then compare a value against itself and
    report SAME_DISPOSITION — a DIVERGED-shaped answer for a REACHED value.
    """
    called: list[str] = []

    def _must_not_run(observed: ObservedFixture, neighbour: str) -> str:
        called.append(neighbour)
        return "low"

    finding = check_observation(
        _observed(_RISK_ROW, "src/app.py", "low"),
        workspace=tmp_path,
        differential=_must_not_run,
    )
    assert finding.reachability is Reachability.REACHED
    assert finding.consequence is Consequence.NOT_MEASURED
    assert called == [], "no neighbour, no second call"
    assert adjudicate(finding, None) is FindingDisposition.OK


def test_check_observation_lets_a_mechanism_error_propagate(tmp_path):
    """An unclassifiable outcome is not converted into a finding.

    "'the check could not run' and 'the check ran and found nothing' must not be
    the same value, which is the rule this whole effort turns on."
    """
    with pytest.raises(FixtureReachabilityError):
        check_observation(
            _observed(_RISK_ROW, "src/app.py", "moderate"), workspace=tmp_path
        )


# --------------------------------------------------------------------------- #
# Part 9 — observe: boundaries are found by watching the suite
# --------------------------------------------------------------------------- #


def test_observe_records_one_fixture_per_value_with_the_consumers_outcome():
    """A call carrying two paths yields two observations, with one outcome.

    "reachability is a property of a value, and a list that is half producible
    would otherwise get one verdict."
    """
    with observe([_RISK_ROW]) as seen:
        verdict = risk.evaluate(
            size_label="S",
            labels=[],
            changed_files=[
                risk.FileDiff("src/app.py", 1, 0),
                risk.FileDiff(".github/workflows/ci.yml", 1, 0),
            ],
            verified=True,
            verification_iterations=0,
        )
    assert verdict.level == "elevated"
    assert [o.value for o in seen] == [
        "src/app.py",
        ".github/workflows/ci.yml",
    ]
    assert {o.outcome for o in seen} == {"elevated"}
    assert all(o.boundary is _RISK_ROW for o in seen)
    assert all(o.cut_boundaries == (_RISK_ROW.producer,) for o in seen)


def test_observe_records_values_verbatim():
    """No decoding, no stripping, no tidying at observation time.

    "The entire defect class is a value that is nearly the right value, and any
    tidying at this point erases the finding." The value fed in below is git's
    RENDERING — precisely the thing a well-meaning observer would decode, and
    precisely the thing that must arrive at ``check_suite`` undecoded or
    instance (A) becomes invisible to the mechanism written for it.
    """
    with observe([_RISK_ROW]) as seen:
        risk.evaluate(
            size_label="S",
            labels=[],
            changed_files=[risk.FileDiff(_LF_RENDERING, 1, 0)],
            verified=True,
            verification_iterations=0,
        )
    assert [o.value for o in seen] == [_LF_RENDERING]
    assert seen[0].outcome == "low"


def test_observe_is_transparent_to_the_consumer():
    """Same return value, same arity, same exception. Instrument, not a filter."""
    kwargs = dict(
        size_label="S",
        labels=[],
        changed_files=[risk.FileDiff("src/app.py", 1, 0)],
        verified=True,
        verification_iterations=0,
    )
    before = risk.evaluate(**kwargs)
    with observe([_RISK_ROW]):
        during = risk.evaluate(**kwargs)
    after = risk.evaluate(**kwargs)
    assert before == during == after

    with observe([_PATHS_ROW]):
        with pytest.raises(TypeError):
            role_protocol.evaluate_changed_paths()  # type: ignore[call-arg]


def test_observe_maps_an_empty_violation_tuple_to_clean():
    """``evaluate_changed_paths`` has ``extract_outcome=""``: () is 'clean'.

    Written into the row's rationale — "the observer maps () to 'clean' and a
    non-empty tuple to 'violation' — the mapping check_branch itself performs".
    A body that recorded ``str(())`` would produce an outcome
    ``gate_disposition`` has to raise on, which is at least loud; a body that
    recorded ``"violation"`` for both is silent and is what this row stops.
    """
    rule = role_protocol.RoleRule(
        role=role_protocol.Role.SEALS,
        kind=role_protocol.RuleKind.DENY_GLOBS,
        globs=("src/**",),
        rationale="seal fixture",
    )
    with observe([_PATHS_ROW]) as seen:
        role_protocol.evaluate_changed_paths(rule, ["docs/readme.md"])
        role_protocol.evaluate_changed_paths(rule, ["src/app.py"])
    assert [(o.value, o.outcome) for o in seen] == [
        ("docs/readme.md", "clean"),
        ("src/app.py", "violation"),
    ]


def test_observe_records_the_test_and_the_substitution_site():
    """A finding must name a row a human can open, and the line to change.

    ``call_site`` is the frame that CALLED the consumer, which is where the
    fixture is written — not the test's own first line, and not the consumer's.
    """
    with observe([_RISK_ROW]) as seen:
        line = inspect.currentframe().f_lineno + 1
        risk.evaluate(
            size_label="S",
            labels=[],
            changed_files=[risk.FileDiff("src/app.py", 1, 0)],
            verified=True,
            verification_iterations=0,
        )
    assert len(seen) == 1
    assert "test_observe_records_the_test_and_the_substitution_site" in seen[0].test_id
    assert seen[0].call_site.endswith(f":{line}"), seen[0].call_site
    assert "test_fixture_reachability.py" in seen[0].call_site


def test_observe_covers_a_consumer_imported_by_value():
    """A caller holding its own reference to the consumer is still observed.

    Reason 2 in the scaffold: observation "cannot be fooled by indirection". The
    alias below is bound at import time, exactly as a helper module's
    ``from ... import evaluate`` would be, and a body that only rebinds the
    defining module's attribute misses it.

    Dispute 3: the contract's stated MECHANISM ("wrapped in the module that
    defines it, so callers that imported it by value are covered") does not
    achieve its stated PROPERTY. Rebinding one module attribute cannot reach a
    name another module already bound. The property is achievable — sweep
    ``sys.modules`` for aliases — and it is the property that is sealed.
    """
    with observe([_RISK_ROW]) as seen:
        _EVALUATE_BOUND_AT_IMPORT(
            size_label="S",
            labels=[],
            changed_files=[risk.FileDiff("src/app.py", 1, 0)],
            verified=True,
            verification_iterations=0,
        )
    assert [o.value for o in seen] == ["src/app.py"]


def test_observe_restores_every_consumer_on_the_way_out():
    """Including on an exception, or the package stays patched for the suite."""
    original = risk.evaluate
    with observe([_RISK_ROW]):
        pass
    assert risk.evaluate is original

    with pytest.raises(ZeroDivisionError):
        with observe([_RISK_ROW]):
            raise ZeroDivisionError("a failing run must still unwrap")
    assert risk.evaluate is original
    assert _EVALUATE_BOUND_AT_IMPORT is original


def test_observe_refuses_to_nest():
    """Two live wrappers double-record and the second unwrap restores a wrapper.

    And the failure must not leave the package patched, which is the half a body
    forgets: the outer block still has to unwrap.
    """
    original = risk.evaluate
    with observe([_RISK_ROW]):
        with pytest.raises(FixtureReachabilityError):
            with observe([_RISK_ROW]):
                pass
    assert risk.evaluate is original


def test_observe_refuses_a_boundary_whose_consumer_cannot_be_wrapped():
    """An unwrappable consumer is an ERROR, not a silently unobserved row.

    A row that cannot be instrumented and reports nothing is indistinguishable
    from a row nothing crossed — this module's own subject matter, one level in.
    """
    unwrappable = Boundary(
        producer="claude_dispatcher.risk.collect_diff",
        consumer="claude_dispatcher.risk.no_such_function",
        kind=BoundaryKind.COLLECTOR,
        value_kind=ValueKind.GIT_PATH,
        proceed_outcomes=("low",),
        refuse_outcomes=("elevated",),
        extract_outcome="level",
        rationale="a consumer that is not there",
    )
    with pytest.raises(FixtureReachabilityError):
        with observe([unwrappable]):
            pass
    assert not hasattr(risk, "no_such_function")


def test_observe_raises_when_extract_outcome_has_gone_stale():
    """A table path that does not resolve on the return value is an ERROR.

    P4, 2026-08-10, on this file's first smaller item. The complaint was that
    ``Boundary`` has ``extract_outcome`` but no ``extract_value``, so the
    observer still holds per-row knowledge — the coupling ``extract_outcome``
    was introduced to remove. P4 declined to add ``extract_value`` (an honest
    one is a parameter name plus a per-element attribute plus a per-element
    rule, i.e. a small expression language, and a parser for it is more surface
    than the coupling it removes) and ruled instead that the coupling must be
    LOUD: a row the observer cannot extract from raises, and never silently
    contributes nothing.

    This is the determinate half of that rule. The row below names a real,
    wrappable consumer and an outcome path that does not resolve on what it
    returns — which is what a table row looks like the day after a consumer
    changes shape.

    A body that records ``""``, or the repr, or ``getattr(..., default)``
    instead of raising, defers the failure to :func:`gate_disposition` one
    frame later, where the message can only say "this outcome is in neither
    set" and cannot say that the TABLE is stale. Reddens on exactly that.
    """
    stale = Boundary(
        producer=_RISK_ROW.producer,
        consumer=_RISK_ROW.consumer,
        kind=BoundaryKind.COLLECTOR,
        value_kind=ValueKind.GIT_PATH,
        proceed_outcomes=("low",),
        refuse_outcomes=("elevated",),
        extract_outcome="verdict.level",  # RiskVerdict has .level, not .verdict
        rationale="a row whose outcome path went stale under the consumer",
    )
    with pytest.raises(FixtureReachabilityError):
        with observe([stale]) as _seen:
            risk.evaluate(
                size_label="S",
                labels=[],
                changed_files=[risk.FileDiff("src/app.py", 1, 0)],
                verified=True,
                verification_iterations=0,
            )
    assert risk.evaluate is _EVALUATE_BOUND_AT_IMPORT, (
        "the failing observe block must still unwrap on the way out"
    )


def test_observe_records_a_seam_only_when_a_substitute_was_supplied(tmp_path):
    """At a SEAM the fixture IS the callable; ``run=None`` substitutes nothing.

    So a real-git call across a seam produces no observation, and a stubbed one
    produces an observation whose value names the stub. A body that recorded
    every ``blob_text_at`` call would put a boundary that nothing was
    substituted at into the findings, and a REACHED/OK on it would be a
    judgement about a value nobody replaced.
    """
    repo = _witness_repo(tmp_path / "repo", "src/app.py")

    def _stub(cmd, *_a, **_k):
        argv = [str(c) for c in cmd]
        if "ls-tree" in argv:
            return (0, f"100644 blob 0123456789abcdef\t{argv[-1]}\0", "")
        if "cat-file" in argv:
            return (0, "X = 1\n", "")
        raise AssertionError(f"unscripted git command: {argv}")

    with observe([_BLOB_SEAM_ROW]) as seen:
        assert repo_config.blob_text_at(repo, "main", "seed.txt") == "seed\n"
        assert repo_config.blob_text_at(repo, "main", "src/app.py", run=_stub) == (
            "X = 1\n"
        )

    assert len(seen) == 1, f"expected one substituted seam call, got {seen}"
    assert seen[0].value.endswith("_stub")
    assert seen[0].outcome == "text"


def test_observe_records_a_raise_as_the_boundarys_spelling_for_it(tmp_path):
    """A consumer that RAISES still produces an observation, spelled 'raised'.

    "a fixture that makes the consumer raise is exactly the defensive shape this
    module has to judge, and dropping it would make every such row invisible."
    """
    repo = _witness_repo(tmp_path / "repo", "src/app.py")

    def _always_raises(cmd, *_a, **_k):
        raise AssertionError(f"unscripted git command: {[str(c) for c in cmd]}")

    with observe([_BLOB_SEAM_ROW]) as seen:
        with pytest.raises(Exception):
            repo_config.blob_text_at(repo, "main", "src/app.py", run=_always_raises)

    assert len(seen) == 1
    assert seen[0].outcome == "raised"
    assert gate_disposition(_BLOB_SEAM_ROW, seen[0].outcome) is GateDisposition.REFUSE


def test_observe_names_both_cuts_when_a_value_arrives_through_a_stubbed_seam(
    tmp_path,
):
    """A path that reached the path gate through a stubbed git is TWO cuts deep.

    ``check_branch(run=stub)`` substitutes git; the paths the real
    ``changed_paths_between`` then derives from the stub's answer arrive at
    ``evaluate_changed_paths`` having crossed two boundaries. Its reachability
    "is not decidable one hop at a time, and the mechanism must say so rather
    than answer the easy hop and imply it answered the question".

    This is instance (B)'s own shape, seen from the collector face, and it is
    why the two faces are not interchangeable.
    """

    def _stub(cmd, *_a, **_k):
        argv = [str(c) for c in cmd]
        if "diff" in argv:
            return (0, "src/app.py\n", "")
        if "merge-base" in argv:
            return (0, "main\n", "")
        raise AssertionError(f"unscripted git command: {argv}")

    repo = _witness_repo(tmp_path / "repo", "src/app.py")
    with observe([_BRANCH_SEAM_ROW, _PATHS_ROW]) as seen:
        role_protocol.check_branch(
            repo, "main", "feat/x", role_protocol.Role.SEALS, run=_stub
        )

    inner = [o for o in seen if o.boundary is _PATHS_ROW]
    assert inner, "the path gate's own observation was not recorded"
    assert all(len(o.cut_boundaries) > 1 for o in inner)
    assert all(_BRANCH_SEAM_ROW.producer in o.cut_boundaries for o in inner)
    assert all(_PATHS_ROW.producer in o.cut_boundaries for o in inner)


# --------------------------------------------------------------------------- #
# Part 10 — git_subcommand
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        pytest.param(["git", "diff", "--numstat"], "diff", id="plain"),
        pytest.param(
            ["git", "-c", "core.quotePath=false", "diff", "--name-only"],
            "diff",
            id="the-real-changed_paths_between-argv",
        ),
        pytest.param(
            ["git", "ls-tree", "-z", "main:", "--", "src/app.py"],
            "ls-tree",
            id="the-real-ls-tree-argv",
        ),
        pytest.param(
            ["git", "cat-file", "blob", "main:src/app.py"],
            "cat-file",
            id="the-real-cat-file-argv",
        ),
        pytest.param(["git", "-C", "/tmp/x", "status"], "status", id="dash-C"),
        pytest.param(["git", "--git-dir", "/x/.git", "log"], "log", id="git-dir"),
        pytest.param(["git", "--work-tree", "/x", "add"], "add", id="work-tree"),
        pytest.param(["git", "--namespace", "ns", "push"], "push", id="namespace"),
        pytest.param(["git", "--exec-path", "/x", "show"], "show", id="exec-path"),
        pytest.param(["git", "--git-dir=/x/.git", "log"], "log", id="joined-value"),
        pytest.param(["git", "--no-pager", "diff"], "diff", id="valueless-option"),
        pytest.param(["git"], None, id="bare-git"),
        pytest.param(["git", "--version"], None, id="version"),
        pytest.param(["git", "-c", "a=b"], None, id="options-only"),
    ],
)
def test_git_subcommand_skips_global_options(argv, expected):
    """Not ``argv[1]``. The repo's own argvs are in the table.

    ``changed_paths_between`` really does run
    ``git -c core.quotePath=false diff ...``, so a body that takes ``argv[1]``
    reports ``-c`` as the subcommand of the single most-issued command in the
    suite and every stub looks under-declared at once.

    ``None`` for an argv with no subcommand is a DISTINCT answer from "a
    subcommand I do not know": an argv with no subcommand cannot be a modelling
    gap, and an unrecognised one is precisely what a gap looks like.
    """
    assert git_subcommand(argv) == expected


def test_git_subcommand_pins_the_current_global_option_list():
    """An option the rule does NOT know eats the next token. Pinned, not hidden.

    The scaffold records this limitation and asks for exactly this seal: "the fix
    is to add it to the list, and a seal should pin the current list so a new
    global option in an argv reddens rather than mis-parses". So the known five
    consume a value and an unknown one does not, and a body that broadens the
    list — or narrows it — reddens here and has to say so.
    """
    assert git_subcommand(["git", "--future-option", "value", "diff"]) == "value"
    assert git_subcommand(["git", "-c", "a=b", "-c", "c=d", "diff"]) == "diff"


# --------------------------------------------------------------------------- #
# Part 11 — INSTANCE (B): the seam face, over the real stubs
# --------------------------------------------------------------------------- #

_STUB_FILES = {
    "diff": _TESTS_DIR / "test_role_protocol_diff.py",
    "floor": _TESTS_DIR / "test_role_protocol_floor.py",
    "provenance": _TESTS_DIR / "test_role_protocol_provenance.py",
}

#: What each ``_run_stub`` NAMES. Measured, 2026-08-10, against the three files
#: at HEAD. ``test_role_protocol_diff.py``'s two are the finding: ``ls-tree``
#: and ``cat-file`` are both answered by its ``":" in a`` branch and neither
#: appears here.
_MODELLED_AT_HEAD = {
    "diff": frozenset({"diff", "merge-base"}),
    "floor": frozenset({"diff", "merge-base"}),
    "provenance": frozenset({"diff", "merge-base", "ls-tree", "cat-file"}),
}


@pytest.mark.parametrize("which", sorted(_STUB_FILES))
def test_modelled_subcommands_over_the_three_real_stubs(which):
    """The vocabulary each stub declares, read from its own source.

    This is the acceptance measurement for instance (B). The claim every
    ``_run_stub`` docstring makes — "an unscripted command raises, so a seal
    cannot pass on a read it never modelled" — is a property of this set and of
    the dispatch shape, and for ``test_role_protocol_diff.py`` it is false: the
    set below is two names wide and the stub answers four commands.

    A body that counted a shape predicate as a declaration would put ``":"`` in
    the ``diff`` row; a body that counted every string constant in the function
    would put ``"blob"`` there too (from ``raise_on == "blob"``, which is not
    argv-derived). Both reddens.
    """
    source = _STUB_FILES[which].read_text(encoding="utf-8")
    assert modelled_subcommands(source, "_run_stub") == _MODELLED_AT_HEAD[which]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        pytest.param(
            'def s():\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        if "diff" in argv:\n'
            '            return 0\n'
            '        raise AssertionError(argv)\n'
            '    return run\n',
            frozenset({"diff"}),
            id="membership-in-the-argv-list",
        ),
        pytest.param(
            'def s():\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        if argv[1] == "cat-file":\n'
            '            return 0\n'
            '        raise AssertionError(argv)\n'
            '    return run\n',
            frozenset({"cat-file"}),
            id="equality-against-an-argv-element",
        ),
        pytest.param(
            'def s():\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        subcmd = argv[1]\n'
            '        if subcmd in ("show", "ls-tree"):\n'
            '            return 0\n'
            '        raise AssertionError(argv)\n'
            '    return run\n',
            frozenset({"show", "ls-tree"}),
            id="membership-in-a-literal-tuple",
        ),
        pytest.param(
            'def s():\n'
            '    table = {"diff": 1, "show": 2}\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        return table[argv[1]]\n'
            '    return run\n',
            frozenset({"diff", "show"}),
            id="dict-keys-indexed-by-argv",
        ),
        pytest.param(
            'def s():\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        spec = next((a for a in argv if ":" in a), None)\n'
            '        if spec is not None:\n'
            '            return 0\n'
            '        if argv[1].startswith("-"):\n'
            '            return 1\n'
            '        if len(argv) > 3:\n'
            '            return 2\n'
            '        raise AssertionError(argv)\n'
            '    return run\n',
            frozenset(),
            id="shape-predicates-name-nothing",
        ),
        pytest.param(
            'def s(raise_on=None):\n'
            '    def run(cmd):\n'
            '        argv = [str(c) for c in cmd]\n'
            '        if raise_on == "blob":\n'
            '            raise OSError\n'
            '        if raise_on == "rev-parse":\n'
            '            raise OSError\n'
            '        raise AssertionError(argv)\n'
            '    return run\n',
            frozenset(),
            id="constants-not-compared-against-argv",
        ),
    ],
)
def test_modelled_subcommands_counts_names_and_not_shapes(body, expected):
    """What counts as NAMING a subcommand, and what deliberately does not.

    The last two rows are the whole finding. A predicate over argv SHAPE answers
    commands without naming them, so a stub whose last branch before the raise
    is one of them "has no totality property at all — which is what the nineteen
    seals were resting on". And a constant compared against something that is
    not argv-derived declares nothing about git.
    """
    assert modelled_subcommands(body, "s") == expected


def test_modelled_subcommands_raises_on_a_name_that_is_not_a_function():
    """Not the empty set: "an analyzer that quietly returns the empty set would
    make every stub look maximally under-declared and the resulting flood is how
    a check gets turned off"."""
    source = _STUB_FILES["diff"].read_text(encoding="utf-8")
    with pytest.raises(FixtureReachabilityError):
        modelled_subcommands(source, "_no_such_function")


@pytest.fixture(scope="module")
def issued_argv(tmp_path_factory) -> tuple[tuple[str, ...], ...]:
    """The argvs ``blob_text_at`` REALLY issues, recorded over a real repository.

    ``stub_gaps`` takes this rather than deriving it, and the contract says why:
    "an argv list derived from the same source the stub was written against
    would agree with the stub by construction". The stub's docstring is the
    artifact that was wrong in instance (B), so nothing here is read off a
    docstring — a recording seam delegates to real git over a real repo and the
    argvs are whatever the consumer chose to run.

    Measured, 2026-08-10::

        git ls-tree -z main: -- seed.txt
        git cat-file blob main:seed.txt
    """
    repo = _witness_repo(tmp_path_factory.mktemp("issued") / "repo", "src/app.py")
    recorded: list[tuple[str, ...]] = []

    def _recording(cmd, *_a, **_k):
        argv = [str(c) for c in cmd]
        recorded.append(tuple(argv))
        proc = subprocess.run(argv, cwd=str(repo), capture_output=True, text=True)
        return (proc.returncode, proc.stdout, proc.stderr)

    assert repo_config.blob_text_at(repo, "main", "seed.txt", run=_recording) == (
        "seed\n"
    )
    assert [a[1] for a in recorded] == ["ls-tree", "cat-file"], recorded
    return tuple(recorded)


def test_the_diff_stub_answers_two_commands_it_never_names(issued_argv):
    """INSTANCE (B), as the acceptance row: ``ls-tree`` AND ``cat-file``.

    Both fall into the ``":" in a`` blob-spec branch of a stub that names
    neither, because the tree-ish token ``main:`` satisfies a shape predicate
    that was written for a blob spec. The scaffold's correction to the brief is
    sealed here: "the gap is two subcommands wide, not one, and the fix is the
    branch rather than a missing case".

    The gap stands whatever the answers were — ``ls-tree`` gets an rc-128
    ``fatal: path '' does not exist in 'main'`` that no git anywhere prints for
    that argv, and ``cat-file`` gets a plausible blob — because "the stub's
    totality claim is either true or it is a lie in a docstring that the next
    author will rely on, as nineteen seals did".
    """
    gaps = stub_gaps(
        stub_source=_STUB_FILES["diff"].read_text(encoding="utf-8"),
        stub_name="_run_stub",
        issued_argv=issued_argv,
        consumer=_BLOB_SEAM_ROW.consumer,
    )
    assert {g.subcommand for g in gaps} == {"ls-tree", "cat-file"}
    assert all(g.modelled == frozenset({"diff", "merge-base"}) for g in gaps)
    assert all(g.stub == "_run_stub" for g in gaps)
    assert all(g.consumer == _BLOB_SEAM_ROW.consumer for g in gaps)
    assert all(g.answered_as.strip() for g in gaps), (
        "answered_as must name the branch that swallowed it, or the fix is not "
        "local"
    )
    assert all(g.argv in {tuple(a) for a in issued_argv} for g in gaps)


@pytest.mark.parametrize("which", ["floor", "provenance"])
def test_the_other_two_stubs_are_clean(which, issued_argv):
    """No gap in the sibling files, and they are clean for DIFFERENT reasons.

    "A check that reported all three would be over-calling, and an over-calling
    check is one nobody runs twice."

      * ``provenance`` NAMES ``ls-tree`` and ``cat-file`` — answered and
        modelled, a stub doing its job.
      * ``floor`` names neither and REFUSES both — unmodelled and refused, which
        is the totality claim holding. Measured 2026-08-10: its ``_run_stub``
        raises ``AssertionError: unscripted git command`` on both real argvs.

    That second reason was a MEASURED DISAGREEMENT with the scaffold, which said
    "Only two of the three files are affected". Under ``stub_gaps``'s own
    definition — unmodelled AND answered — exactly ONE is. Raised as dispute 4;
    the seal followed the measurement, because the measurement is what a body
    has to reproduce.

    **P4 CONFIRMED IT, 2026-08-10**, by running all three ``_run_stub``
    factories against the two argvs ``blob_text_at`` really issues: ``diff``
    answered both (rc 128 both times), ``floor`` raised ``AssertionError:
    unscripted git command`` on both, ``provenance`` answered both while naming
    both. The scaffold's instance-(B) narrative and ``StubGap``'s docstring now
    both say ONE, and both name the reason the earlier count was wrong — it
    applied half the definition ("does not name it") as though it were the
    whole of it.
    """
    gaps = stub_gaps(
        stub_source=_STUB_FILES[which].read_text(encoding="utf-8"),
        stub_name="_run_stub",
        issued_argv=issued_argv,
        consumer=_BLOB_SEAM_ROW.consumer,
    )
    assert gaps == ()


# Each synthetic substitute is a FACTORY returning the seam callable, the shape
# every ``_run_stub`` in this repo has. The trailing ``return run`` is
# load-bearing and was missing in the first draft of this file: without it the
# factory returns None, every argv "raises", and the three gap rows below pass
# for the wrong reason. Found by the joint-satisfiability probe, which is what
# it is for.
_ANSWERS_EVERYTHING = (
    'def s():\n'
    '    def run(cmd):\n'
    '        argv = [str(c) for c in cmd]\n'
    '        if "diff" in argv:\n'
    '            return (0, "", "")\n'
    '        return (0, "", "")\n'
    '    return run\n'
)

_REFUSES_EVERYTHING_UNMODELLED = (
    'def s():\n'
    '    def run(cmd):\n'
    '        argv = [str(c) for c in cmd]\n'
    '        if "diff" in argv:\n'
    '            return (0, "", "")\n'
    '        raise AssertionError(argv)\n'
    '    return run\n'
)

_REFUSES_EVERYTHING = (
    'def s():\n'
    '    def run(cmd):\n'
    '        raise AssertionError(cmd)\n'
    '    return run\n'
)


def test_the_synthetic_substitutes_below_really_answer_and_really_refuse():
    """The anti-vacuity guard for the three ``stub_gaps`` rows that expect NONE.

    A row whose expected gap set is empty passes just as well when the fixture
    is broken — a factory that returns None makes every argv "raise", and
    "unmodelled and refused" then looks like the totality claim holding when in
    fact nothing was tested. That is this unit's own defect class, in this
    unit's own seals, and it is exactly what the first draft did.

    So the fixtures are exercised here directly, without going through the
    mechanism at all: each factory must return a callable, and each callable
    must answer or refuse the argv the row below relies on.
    """
    made = {}
    for name, source in (
        ("answers", _ANSWERS_EVERYTHING),
        ("refuses-unmodelled", _REFUSES_EVERYTHING_UNMODELLED),
        ("refuses-all", _REFUSES_EVERYTHING),
    ):
        namespace: dict = {}
        exec(compile(source, f"<{name}>", "exec"), namespace)
        run = namespace["s"]()
        assert callable(run), f"{name}: the factory returned {run!r}, not a seam"
        made[name] = run

    ls_tree = ["git", "ls-tree", "-z", "main:", "--", "x"]
    assert made["answers"](ls_tree) == (0, "", "")
    assert made["answers"](["git", "diff", "--numstat"]) == (0, "", "")
    assert made["refuses-unmodelled"](["git", "diff"]) == (0, "", "")
    with pytest.raises(AssertionError):
        made["refuses-unmodelled"](ls_tree)
    with pytest.raises(AssertionError):
        made["refuses-all"](["git", "diff"])


@pytest.mark.parametrize(
    ("source", "argvs", "expected"),
    [
        pytest.param(
            _ANSWERS_EVERYTHING,
            [["git", "diff", "--numstat"]],
            set(),
            id="answered-and-modelled-is-fine",
        ),
        pytest.param(
            _REFUSES_EVERYTHING_UNMODELLED,
            [["git", "ls-tree", "-z", "main:", "--", "x"]],
            set(),
            id="unmodelled-and-refused-is-the-claim-holding",
        ),
        pytest.param(
            _ANSWERS_EVERYTHING,
            [["git", "ls-tree", "-z", "main:", "--", "x"]],
            {"ls-tree"},
            id="unmodelled-and-answered-is-a-gap",
        ),
        pytest.param(
            _REFUSES_EVERYTHING,
            [["git", "diff"], ["git", "ls-tree", "main:"]],
            set(),
            id="a-stub-that-refuses-everything-yields-no-gaps",
        ),
        pytest.param(
            _ANSWERS_EVERYTHING,
            [["git", "--version"], ["git"]],
            set(),
            id="an-argv-with-no-subcommand-is-never-a-gap",
        ),
    ],
)
def test_stub_gaps_requires_both_halves(source, argvs, expected):
    """Unmodelled is not enough, and answered is not enough. Both, or nothing.

    The three-line table in the contract, one row each, plus the two edges it
    names: a stub that refuses everything "yields no gaps and is a different
    (and louder) problem", and an argv with no subcommand at all cannot be a
    modelling gap because ``git_subcommand`` returns None rather than a name.
    """
    gaps = stub_gaps(
        stub_source=source,
        stub_name="s",
        issued_argv=argvs,
        consumer="claude_dispatcher.repo_config.blob_text_at",
    )
    assert {g.subcommand for g in gaps} == expected


def test_stub_gaps_says_nothing_about_whether_a_modelled_answer_is_right():
    """Limit 9, sealed: a stub that DECLARES ``ls-tree`` and lies is clean here.

    The seam face checks totality and "deliberately not correctness". The source
    below names ``ls-tree`` and returns a mode git never writes for a regular
    file. No gap. Saying so is the difference between a check with a stated
    scope and one that will be asked why it missed something.
    """
    source = (
        'def s():\n'
        '    def run(cmd):\n'
        '        argv = [str(c) for c in cmd]\n'
        '        if "ls-tree" in argv:\n'
        '            return (0, "123456 blob deadbeef\\tx\\0", "")\n'
        '        raise AssertionError(argv)\n'
        '    return run\n'
    )
    gaps = stub_gaps(
        stub_source=source,
        stub_name="s",
        issued_argv=[["git", "ls-tree", "-z", "main:", "--", "x"]],
        consumer="claude_dispatcher.repo_config.blob_text_at",
    )
    assert gaps == ()


# --------------------------------------------------------------------------- #
# Part 12 — check_suite: the report, and the fields that stop it lying
# --------------------------------------------------------------------------- #


def test_an_empty_run_is_distinguishable_from_a_clean_one(tmp_path):
    """Zero findings because nothing ran, versus zero findings because clean.

    THE non-vacuity seal, and this module's own subject matter turned on itself.
    "a check that reports zero findings because nothing calls it is
    indistinguishable from a check that reports zero findings because the repo
    is clean". Both halves are asserted, so a body cannot satisfy this by
    returning an empty ``boundaries_never_observed`` in both cases.
    """
    empty = check_suite([], workspace=tmp_path / "empty")
    assert empty.findings == ()
    assert set(empty.boundaries_never_observed) == set(BOUNDARIES)
    assert all(count == 0 for count in empty.dispositions.values())

    clean = check_suite(
        [_observed(_RISK_ROW, "src/app.py", "low")], workspace=tmp_path / "clean"
    )
    assert len(clean.findings) == 1
    assert _RISK_ROW not in clean.boundaries_never_observed
    assert set(clean.boundaries_never_observed) == set(BOUNDARIES) - {_RISK_ROW}
    assert clean.dispositions[FindingDisposition.OK] == 1


def test_the_report_counts_every_disposition_including_the_zeros(tmp_path):
    """All five keys present, always. The abstention count is the coverage figure.

    "a report that omits ABSTAIN because there were none is indistinguishable
    from one that omits it because nobody counted". A body using a
    ``Counter`` passes the sums and reddens here, which is the point.
    """
    report = check_suite(
        [_observed(_RISK_ROW, "src/app.py", "low")], workspace=tmp_path
    )
    assert set(report.dispositions) == set(FindingDisposition)
    assert sum(report.dispositions.values()) == len(report.findings)


def test_abstentions_are_counted_apart_from_passes(tmp_path):
    """A seam observation is an ABSTAIN and must never land in the OK column.

    Every SEAM observation resolves to NO_STRATEGY on the collector face, so the
    first real report over this suite is dominated by abstentions. That is the
    contract, not a failure — and it is only readable if ABSTAIN and OK are
    separate counts.
    """
    report = check_suite(
        [
            _observed(_RISK_ROW, "src/app.py", "low"),
            _observed(_BLOB_SEAM_ROW, "tests.test_x._run_stub", "text"),
            _observed(_BLOB_SEAM_ROW, "tests.test_y._run_stub", "absent"),
        ],
        workspace=tmp_path,
    )
    assert report.dispositions[FindingDisposition.OK] == 1
    assert report.dispositions[FindingDisposition.ABSTAIN] == 2
    assert [f.reachability for f in report.findings] == [
        Reachability.REACHED,
        Reachability.NO_STRATEGY,
        Reachability.NO_STRATEGY,
    ]


def test_check_suite_judges_every_observation_in_observation_order(tmp_path):
    """One finding per observation, in order. "An observation with no finding is
    a silent pass", and byte-identical reports across two runs are what make a
    diff between them a real change."""
    observations = [
        _observed(_RISK_ROW, "src/app.py", "low"),
        _observed(_PATHS_ROW, "docs/readme.md", "clean"),
        _observed(_RISK_ROW, "src/other.py", "low"),
    ]
    report = check_suite(observations, workspace=tmp_path)
    assert [f.observed for f in report.findings] == observations


def test_check_suite_dedupes_before_constructing(tmp_path, monkeypatch):
    """One witness per distinct ``(producer, value)``, reused. The cost driver.

    "Over a suite of this size the distinct set is small and the repeated set is
    not; without this the check costs a repository per row." Six observations,
    three distinct pairs, three constructions — and the same value at a
    DIFFERENT producer is a different pair, because the two producers can emit
    different things for the same repository.
    """
    calls: list[tuple[str, str]] = []
    real = fr.construct_witness

    def counting(boundary, value, *, workspace):
        calls.append((boundary.producer, value))
        return real(boundary, value, workspace=workspace)

    monkeypatch.setattr(fr, "construct_witness", counting)
    report = check_suite(
        [
            _observed(_RISK_ROW, "src/app.py", "low"),
            _observed(_RISK_ROW, "src/app.py", "low"),
            _observed(_RISK_ROW, "src/app.py", "elevated"),
            _observed(_RISK_ROW, "src/other.py", "low"),
            _observed(_PATHS_ROW, "src/app.py", "clean"),
            _observed(_PATHS_ROW, "src/app.py", "clean"),
        ],
        workspace=tmp_path,
    )
    assert len(report.findings) == 6
    assert sorted(calls) == sorted(
        [
            (_RISK_ROW.producer, "src/app.py"),
            (_RISK_ROW.producer, "src/other.py"),
            (_PATHS_ROW.producer, "src/app.py"),
        ]
    )


def test_check_suite_reports_a_declaration_that_matched_nothing(tmp_path):
    """A stale declaration is reported, never silent.

    "a stale declaration is how an accepted state outlives the reason for it".
    Both halves: the live one accepts and does not appear as stale, the stale
    one appears and accepts nothing.
    """
    observed = _observed(_RISK_ROW, "bad\0name.py", "elevated")
    live = ReachabilityDeclaration(
        test_id=observed.test_id,
        producer=_RISK_ROW.producer,
        value="bad\0name.py",
        reason="no filesystem holds a NUL in a name",
        guard="tests/test_fixture_reachability.py",
    )
    stale = ReachabilityDeclaration(
        test_id="tests/test_gone.py::test_removed",
        producer=_RISK_ROW.producer,
        value="a value nothing observed",
        reason="left behind",
        guard="nothing",
    )
    report = check_suite(
        [observed], workspace=tmp_path, declarations=[live, stale]
    )
    assert report.dispositions[FindingDisposition.ACCEPTED] == 1
    assert report.stale_declarations == (stale,)


def test_check_suite_lets_a_mechanism_error_propagate_rather_than_part_report(
    tmp_path,
):
    """A partial report is not a report.

    "a caller that receives one cannot tell a clean run from an aborted one."
    The second observation carries an outcome no set names; the run must abort
    rather than return a one-finding report.
    """
    with pytest.raises(FixtureReachabilityError):
        check_suite(
            [
                _observed(_RISK_ROW, "src/app.py", "low"),
                _observed(_RISK_ROW, "src/other.py", "moderate"),
            ],
            workspace=tmp_path,
        )


def test_check_suite_builds_nothing_inside_the_repository_under_check(tmp_path):
    """Witnesses live under ``workspace``, which is not the repo under check.

    A witness repository created inside the tree would be picked up by the very
    collectors being interrogated. Sealed by measurement: the worktree's git
    status is byte-identical either side of a run that constructs three
    witnesses.
    """
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout
    check_suite(
        [
            _observed(_RISK_ROW, "src/app.py", "low"),
            _observed(_RISK_ROW, _LF_PATH, "elevated"),
            _observed(_PATHS_ROW, "docs/readme.md", "clean"),
        ],
        workspace=tmp_path,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    ).stdout
    assert before == after
    assert any(tmp_path.iterdir())


# --------------------------------------------------------------------------- #
# Part 13 — scope, stated as a seal rather than as prose
# --------------------------------------------------------------------------- #


def test_no_assertion_side_reader_is_smuggled_in(tmp_path):
    """A REACHED fixture with a wrong expectation is OK here, on purpose.

    Limit 6, and it is the honest answer to three of the five instances this
    unit was measured against: a tautological parametrize row, a
    comment-inclusive substring match, and a completeness sweep that omits an
    outcome are properties of the ASSERTION, and the scaffold rules an
    assertion-side reader out of scope explicitly. This module asks whether the
    input can occur and never whether the seal is right about what should
    happen.

    Sealed rather than written in prose so that a later author who builds the
    assertion-side reader has to come here and say so, instead of quietly
    widening a check whose scope nobody re-read.
    """
    finding = check_observation(
        _observed(_RISK_ROW, "src/app.py", "low"), workspace=tmp_path
    )
    assert adjudicate(finding, None) is FindingDisposition.OK
    assert not [
        name
        for name in fr.__all__
        if any(word in name.lower() for word in ("assert", "expect", "tautolog"))
    ]


def test_the_two_faces_disagreeing_is_the_design(issued_argv):
    """The same defect is DIVERGED/SAME_DISPOSITION dynamically and a BREACH
    structurally, and both answers are correct.

    Instance (B) lands here today: the diff stub answers ``ls-tree`` with a
    response git cannot produce, and ``blob_text_at`` reaches the same text
    either way, so nothing hinged on it — DIVERGED with SAME_DISPOSITION is
    declarable and is not a breach. The structural face makes it a BREACH
    regardless, because "one asks whether it mattered this time, the other asks
    whether the stub's totality claim is true, and only the second is a
    property".

    A body that reconciled the two faces — by suppressing the StubGap when the
    outcome was unchanged, which is the tempting simplification — reddens here.
    """
    dynamic = _finding(
        Reachability.DIVERGED,
        Consequence.SAME_DISPOSITION,
        observed=_observed(_BLOB_SEAM_ROW, "tests.test_x._run_stub", "text"),
        neighbour="tests.test_y._run_stub",
    )
    assert adjudicate(dynamic, None) is FindingDisposition.REPORT
    assert adjudicate(dynamic, _matching_declaration(dynamic)) is (
        FindingDisposition.ACCEPTED
    )

    gaps = stub_gaps(
        stub_source=_STUB_FILES["diff"].read_text(encoding="utf-8"),
        stub_name="_run_stub",
        issued_argv=issued_argv,
        consumer=_BLOB_SEAM_ROW.consumer,
    )
    assert gaps, "the structural face must find it whatever the outcome was"


def test_making_the_stubs_total_is_not_a_body_authors_fix():
    """``tests/**`` is immutable to P1 and P3; this file detects and names.

    Recorded as a seal because the scaffold asks for it to be stated and because
    the tempting resolution of
    :func:`test_the_diff_stub_answers_two_commands_it_never_names` is to edit
    the stub. It is not available: the three stub files are not this
    unit's to change, and a body author who "fixed" the finding by editing
    ``test_role_protocol_diff.py`` would have deleted the evidence rather than
    the defect.

    So the shape of the fixture is pinned: the ``":" in a`` branch is still
    there, still after the two names, and still the last thing before the raise.
    """
    source = _STUB_FILES["diff"].read_text(encoding="utf-8")
    stub = source[source.index("def _run_stub(") :]
    stub = stub[: stub.index("\ndef ", 1)]
    assert '":" in a' in stub, (
        "the shape predicate that swallows ls-tree and cat-file is gone — if "
        "that was a deliberate repair, this seal and the acceptance row above "
        "are what tell P4 the finding was closed rather than lost"
    )
    assert stub.index('"merge-base"') < stub.index('":" in a')
    assert "unscripted git command" in stub


# Bound at import time, deliberately: see
# test_observe_covers_a_consumer_imported_by_value.
_EVALUATE_BOUND_AT_IMPORT = risk.evaluate
