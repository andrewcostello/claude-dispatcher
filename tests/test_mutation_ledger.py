"""Seals for unit W2-3 — the mutation-coverage ledger (:mod:`mutation_ledger`).

The property this file exists for: **A LEDGER ENTRY THAT NO LONGER REPRODUCES
IS RED.** A docstring cannot have it, and neither can a row that checks an
entry EXISTS, that the ledger holds N of them, that every clause has a
companion record, or that a field is non-empty — each of those is satisfied by
typing, which is the refusal this unit inherits.

So the load-bearing rows RUN the recorded mutation and compare the recorded
result, against real claims rather than fixtures:

  * The struck clause on
    ``test_discover_roots_refuses_a_tree_it_cannot_sweep`` — "Reddens under a
    body on: ... swallowing an ``AnalyzerError``". RE-MEASURED for this file at
    ``4e66a01`` on 2026-08-18 (:func:`_measured`): that mutation reddens the
    six parametrisations of
    ``test_discover_roots_raises_on_a_fault_without_help_from_the_graph_builder``
    and NOTHING else in the file — not the row whose own clause names it. The
    claim was never true. The same pair of runs carries the control that says
    the mutation does bite, and both are judged in one call.
  * One of the 31 clauses whose evidence expired with the discarded reference
    implementation: recorded as a :class:`Prediction`, which never reads as
    coverage.

:func:`_swallow` applies the mutation here rather than
:func:`mutation_ledger.apply_mutation`: a seal that measured through the
harness it seals would be reporting that harness's opinion of itself. The
measurement is this file's; every VERDICT below is the module's own fold.

RED until W2-3-3 fills the four folds and the harness. The rows that are pure
measurement or pure arithmetic over implemented seams are green today, and are
marked as such — this file is not a set of stubs waiting for a body.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_dispatcher import mutation_ledger as ml
from claude_dispatcher.mutation_ledger import (
    ClauseFate, Drift, Freshness, MutationOperator, MutationSite, NonDerivable,
    Observation, RederiveMode, RowResult, Status,
)
from claude_dispatcher.scratch_clone import scrubbed_git_env

# --------------------------------------------------------------------------- #
# The measured claim. Every constant here was re-derived on 2026-08-18 by
# running the procedure in `_measured`; none is carried from the P4 report.
# --------------------------------------------------------------------------- #

#: `feat/D5-seals2`, the revision the P4 injected into. Immutable, so the
#: measurement below is repeatable rather than a claim about "now".
REVISION = "4e66a01da37c5ea4d480cc2aa3bca84728a2a4da"
MEASURED_ON = "2026-08-18"

SUBJECT = "src/claude_dispatcher/call_site_reachability.py"
SEAL_FILE = "tests/test_call_site_reachability.py"

#: The row whose clause names the mutation. It does not redden under it.
CLAIMING_ROW = f"{SEAL_FILE}::test_discover_roots_refuses_a_tree_it_cannot_sweep"
#: The row that actually reddens — six parametrisations, folded to one row.
REDDENED_ROW = (f"{SEAL_FILE}::test_discover_roots_raises_on_a_fault"
                "_without_help_from_the_graph_builder")

SITE = MutationSite(subject=SUBJECT, anchor="discover_roots",
                    operator=MutationOperator.RAISE_TO_CONTINUE,
                    argument="AnalyzerError")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(("git", *args), cwd=cwd, env=scrubbed_git_env(),
                          capture_output=True, check=True)


def _swallow(source: bytes, site: MutationSite) -> bytes:
    """``site``'s RAISE_TO_CONTINUE applied to ``source``, resolved by ast.

    Not a re-implementation of :func:`mutation_ledger.apply_mutation` for the
    seals to lean on — it is the independent measurement those seals judge, so
    it must not import its answer from the thing under seal.
    """
    fn = next(n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.FunctionDef) and n.name == site.anchor)
    handler = next(h for node in ast.walk(fn) if isinstance(node, ast.Try)
                   for h in node.handlers
                   if isinstance(h.type, ast.Name) and h.type.id == site.argument)
    stmt = handler.body[0]
    assert isinstance(stmt, ast.Raise), "the recorded site is not a raise handler"
    lines = source.decode().splitlines(keepends=True)
    lines[stmt.lineno - 1:stmt.end_lineno] = [" " * stmt.col_offset + "continue\n"]
    return "".join(lines).encode()


def _run_rows(tree: Path, seal_file: str, junit: Path) -> dict[str, RowResult]:
    """Node-id-level results for ``seal_file`` in ``tree``.

    junit-xml rather than stdout: a row that was collected and then not
    reported must come back ABSENT, and short-summary parsing cannot see the
    difference between "not reported" and "passed".
    """
    env = dict(os.environ, PYTHONPATH=str(tree / "src"))
    subprocess.run(
        (sys.executable, "-m", "pytest", seal_file, "-q", "--tb=no",
         "-p", "no:randomly", "-p", "no:cacheprovider", f"--junitxml={junit}"),
        cwd=tree, env=env, capture_output=True)
    outcome = {"failure": RowResult.FAILED, "error": RowResult.ERRORED}
    results: dict[str, RowResult] = {}
    for case in ET.parse(junit).iter("testcase"):
        kinds = {child.tag for child in case}
        if "skipped" in kinds:
            continue
        result = RowResult.PASSED
        for tag, member in outcome.items():
            if tag in kinds:
                result = member
        results[f"{seal_file}::{case.get('name')}"] = result
    return results


@dataclass(frozen=True)
class _Pair:
    control: dict[str, RowResult]
    mutant: dict[str, RowResult]
    subject_sha256: str
    mutant_sha256: str
    population_sha256: str


@pytest.fixture(scope="session")
def measured(tmp_path_factory: pytest.TempPathFactory) -> _Pair:
    """The control/mutant pair at :data:`REVISION`, run once per session.

    ``git archive`` rather than ``git worktree add``: this row must not write
    repository metadata to take a measurement, which is the accident DF-4
    exists for.
    """
    root = _repo_root()
    tree = tmp_path_factory.mktemp("d5")
    archive = tree.parent / "d5.tar"
    with archive.open("wb") as fh:
        subprocess.run(("git", "archive", REVISION), cwd=root, stdout=fh,
                       env=scrubbed_git_env(), check=True)
    with tarfile.open(archive) as tar:
        # `.claude/workflow` is a symlink out of the tree; extracting it is
        # refused, and the harness contract drops it for the same reason.
        tar.extractall(tree, filter="data", members=[
            m for m in tar if not m.name.startswith(".claude/")])

    subject = tree / SUBJECT
    original = subject.read_bytes()
    mutated = _swallow(original, SITE)
    assert mutated != original, "the mutation changed nothing"

    control = ml.fold_row_results(_run_rows(tree, SEAL_FILE, tree / "c.xml"))
    subject.write_bytes(mutated)
    mutant = ml.fold_row_results(_run_rows(tree, SEAL_FILE, tree / "m.xml"))

    return _Pair(
        control=control, mutant=mutant,
        subject_sha256=ml.source_digest(original),
        mutant_sha256=ml.source_digest(mutated),
        population_sha256=ml.population_digest(tuple(control)))


def _entry(pair: _Pair, *, claiming_row: str, reddened: tuple[str, ...]):
    return ml.new_entry(
        seal_file=SEAL_FILE, claiming_row=claiming_row, site=SITE,
        revision=REVISION, subject_sha256=pair.subject_sha256,
        mutant_sha256=pair.mutant_sha256,
        population_sha256=pair.population_sha256, reddened=reddened,
        control_green=pair.control[claiming_row] is RowResult.PASSED,
        observed_on=MEASURED_ON)


def _verdict(pair: _Pair, entry) -> Status:
    return ml.fold(
        ml.freshness_of(()),
        ml.classify_observation(control=pair.control, mutant=pair.mutant,
                                claiming_row=entry.claiming_row,
                                recorded_reddened=entry.reddened))


# --------------------------------------------------------------------------- #
# A real repository with a real baseline-red row. Built rather than found: no
# revision of THIS repository carries a red row at a site the recorded
# mutation reaches, and the two readings of `reddened_observed` coincide on
# every tree that has none.
# --------------------------------------------------------------------------- #

_SUBJECT_SRC = '''"""The mutated module."""


def answer():
    """Body replaced by ``return None`` under BODY_TO_NO_OP."""
    return 41


def other():
    return 7
'''

#: The same module under the recorded operator, written out rather than
#: generated: `mutant_sha256` is provenance on the observation id and no drift
#: member compares it, so deriving it through the applier under seal would buy
#: nothing and couple the record to it.
_MUTANT_SRC = _SUBJECT_SRC.replace("    return 41", "    return None")

_CONFTEST_SRC = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
"""

_SEAL_SRC = """from subject import answer, other


def test_reddens_under_the_mutation():
    assert answer() == 41


def test_red_before_anything_was_mutated():
    assert other() == 8


def test_untouched():
    assert other() == 7
"""


def _tiny_repo(tmp_path: Path, *, over_claim: bool = False,
               revision: str | None = None):
    """A one-commit repository, an entry against it, and its row names."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "subject.py").write_text(_SUBJECT_SRC)
    (repo / "tests" / "conftest.py").write_text(_CONFTEST_SRC)
    (repo / "tests" / "test_seal.py").write_text(_SEAL_SRC)
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=seal", "-c", "user.email=seal@example.invalid",
         "commit", "-qm", "the tree the entry names", cwd=repo)
    head = _git("rev-parse", "HEAD", cwd=repo).stdout.decode().strip()

    seal = "tests/test_seal.py"
    rows = {
        "reddens": f"{seal}::test_reddens_under_the_mutation",
        "baseline_red": f"{seal}::test_red_before_anything_was_mutated",
        "untouched": f"{seal}::test_untouched",
    }
    entry = ml.new_entry(
        seal_file=seal, claiming_row=rows["reddens"],
        site=MutationSite(subject="src/subject.py", anchor="answer",
                          operator=MutationOperator.BODY_TO_NO_OP),
        revision=revision or head,
        subject_sha256=ml.source_digest(_SUBJECT_SRC.encode()),
        mutant_sha256=ml.source_digest(_MUTANT_SRC.encode()),
        population_sha256=ml.population_digest(tuple(rows.values())),
        reddened=((rows["baseline_red"], rows["reddens"]) if over_claim
                  else (rows["reddens"],)),
        control_green=True, observed_on=MEASURED_ON)
    return repo, entry, rows


# --------------------------------------------------------------------------- #
# The property: a claim that does not reproduce is red, and the control that
# does reproduce is judged in the same call so nothing constant can pass.
# --------------------------------------------------------------------------- #

def test_a_claim_that_does_not_reproduce_is_red_and_its_control_holds(
        measured: _Pair) -> None:
    """The flagship, over a real struck clause and a real surviving one.

    Both entries name the SAME mutation at the SAME revision and are judged
    from ONE pair of runs, so the two verdicts differ only in what was
    claimed. That is what makes this row unsatisfiable by a constant fold: a
    ``fold`` that always answers HELD fails on the expired claim, and one that
    always answers BROKEN fails on the control.

    The measurement, re-derived here rather than quoted: swallowing the
    ``AnalyzerError`` in ``discover_roots`` reddens the six parametrisations of
    the gap-4 row and nothing else in the file. The clause on
    ``test_discover_roots_refuses_a_tree_it_cannot_sweep`` says it reddens THAT
    row; it does not, and never did — the row never hands ``discover_roots`` a
    raising analyzer.

    Measured under: read the mutant map alone and the expired claim reads as
    coverage; drop the control comparison and the surviving claim reads as
    broken; give ``fold`` a default arm and the two verdicts collapse together.
    """
    assert measured.control[CLAIMING_ROW] is RowResult.PASSED
    assert measured.control[REDDENED_ROW] is RowResult.PASSED
    assert measured.mutant[CLAIMING_ROW] is RowResult.PASSED, (
        "the recorded mutation now reddens the row whose clause names it; the "
        "struck clause would be true and this seal's subject is gone")
    assert measured.mutant[REDDENED_ROW] is RowResult.FAILED, (
        "the control failed: the mutation reddened nothing, so nothing below "
        "distinguishes a false claim from a mutation that does not bite")

    expired = _entry(measured, claiming_row=CLAIMING_ROW,
                     reddened=(CLAIMING_ROW,))
    control = _entry(measured, claiming_row=REDDENED_ROW,
                     reddened=(REDDENED_ROW,))

    assert _verdict(measured, expired) is Status.BROKEN
    assert _verdict(measured, control) is Status.HELD

    assert ml.proposed_fate(_verdict(measured, expired)) is ClauseFate.STRIKE
    assert ml.proposed_fate(_verdict(measured, control)) is ClauseFate.CITE_CLAIM
    assert not ml.counts_as_coverage(_verdict(measured, expired))
    assert ml.counts_as_coverage(_verdict(measured, control))


def test_rederive_is_the_oracle_and_must_reproduce_the_measurement(
        measured: _Pair) -> None:
    """The harness must reach the same two verdicts from the record alone.

    Without this the folds could be right while nothing ever fed them a real
    run — the ledger would be a decision table with no measurement behind it.
    ``AT_RECORDED`` because that is the mode in which BROKEN is reachable: the
    tree the entry names is the tree that is run, so a survival has no
    innocent explanation.

    Measured under: return a canned ``Rederivation`` from ``rederive`` and the
    two statuses stop disagreeing; trust ``entry.reddened`` instead of running
    the mutant and the expired claim reads as HELD.
    """
    root = str(_repo_root())
    expired = _entry(measured, claiming_row=CLAIMING_ROW,
                     reddened=(CLAIMING_ROW,))
    control = _entry(measured, claiming_row=REDDENED_ROW,
                     reddened=(REDDENED_ROW,))

    got = {e.claiming_row: ml.rederive(e, repo_root=root,
                                       mode=RederiveMode.AT_RECORDED)
           for e in (expired, control)}

    assert got[CLAIMING_ROW].freshness is Freshness.ANCHORED
    assert got[CLAIMING_ROW].observation is Observation.SURVIVED
    assert got[CLAIMING_ROW].status is Status.BROKEN
    assert got[REDDENED_ROW].status is Status.HELD
    # The mutation DID bite — it reddened a row the clause never named. A
    # harness reporting "nothing reddened" would be wrong in the other
    # direction and would read as a mutation that does not apply.
    assert got[CLAIMING_ROW].reddened_observed == (REDDENED_ROW,)


def test_the_reddened_set_drops_a_row_that_was_red_before_the_mutation(
        tmp_path: Path) -> None:
    """``reddened_observed`` is the PASSED-to-FAILED TRANSITION set.

    ``Rederivation.reddened_observed`` is documented as "Rows red under the
    mutant in THIS run", which is the other reading and contradicts
    ``LedgerEntry.reddened`` and ``classify_observation``. The two coincide on
    any tree with no baseline-red row, so this row is run against a tree that
    HAS one — a real repository with a real failing row, built here because no
    revision of this repository carries one at a site the recorded mutation
    reaches.

    Under the transition reading the baseline-red row is not observed, the
    record over-claimed, and the clause is AMENDED. Under the other reading
    the observed set equals the recorded one and the entry reads as HELD — so
    the two readings give opposite dispositions and this row separates them.

    Measured under: define ``reddened_observed`` as the mutant's red rows and
    every assertion below flips; compute ``missing_rows`` from the observed
    set instead of the recorded one and the two set assertions cross over.
    """
    repo, entry, rows = _tiny_repo(tmp_path, over_claim=True)

    r = ml.rederive(entry, repo_root=str(repo), mode=RederiveMode.AT_RECORDED)

    assert rows["baseline_red"] not in r.reddened_observed
    assert r.reddened_observed == (rows["reddens"],)
    assert r.missing_rows == (rows["baseline_red"],)
    assert r.unexpected_rows == ()
    # The structural invariant, independent of which rows these are.
    assert set(r.missing_rows) == set(entry.reddened) - set(r.reddened_observed)
    assert set(r.unexpected_rows) == set(r.reddened_observed) - set(entry.reddened)

    assert r.observation is Observation.REDDENED_SCOPE_DIVERGED
    assert r.status is Status.SCOPE_BROKEN
    assert ml.proposed_fate(r.status) is ClauseFate.AMEND_SCOPE


def test_rederive_returns_a_verdict_when_the_recorded_revision_is_gone(
        tmp_path: Path) -> None:
    """A rebased-away revision is a disposition, not an exception.

    ``rederive`` promises a :class:`Rederivation` in every terminating case.
    Note what is NOT asserted: ``revision_run``. It is mandatory and
    documented as "the revision actually provisioned and run", and nothing was
    provisioned here — there is no truthful value, which is a contract defect
    reported rather than sealed to a guess.

    Measured under: raise instead of returning and this row errors; report the
    absence as ``HARNESS_FAULT`` and the clause parks on ``AWAIT_RERUN``
    forever, which no re-run can clear.
    """
    repo, entry, _ = _tiny_repo(tmp_path, revision="0" * 40)

    r = ml.rederive(entry, repo_root=str(repo), mode=RederiveMode.AT_RECORDED)

    assert isinstance(r, ml.Rederivation)
    assert Drift.REVISION_ABSENT in r.drift
    assert r.observation is Observation.NOT_ATTEMPTED
    assert r.status is Status.UNDERIVABLE
    assert ml.proposed_fate(r.status) is ClauseFate.RELABEL_PREDICTED


# --------------------------------------------------------------------------- #
# The other half of the population: clauses that can never yield an
# observation. GREEN today — arithmetic over implemented seams plus one real
# digest comparison.
# --------------------------------------------------------------------------- #

def test_a_clause_whose_evidence_expired_is_predicted_and_never_cited() -> None:
    """One of the 31, recorded as what it is.

    ``test_no_undecided_reason_is_actionable_as_a_pass`` carries "Reddens
    under a body on: ... letting a declaration touch an abstention", measured
    only against the reference implementation that was discarded. Copying it
    into the ledger as an observation would make it true again by
    transcription, which is the defect this unit closes; the honest record is
    a prediction, and its fate is ``RELABEL_PREDICTED`` and nothing else.

    The measured half: the subject's bytes at the revision the judgement was
    made against are NOT the bytes it has now, so a reader can see the
    prediction is owed another look without re-reading the clause.

    Measured under: fold ``PREDICTION_FATE`` in with ``proposed_fate`` and a
    prediction becomes citable; drop ``subject_sha256`` from ``Prediction``
    and the staleness below is unrepresentable.
    """
    root = _repo_root()
    at_revision = subprocess.run(
        ("git", "show", f"{REVISION}:{SUBJECT}"), cwd=root, check=True,
        env=scrubbed_git_env(), capture_output=True).stdout

    predicted = ml.new_prediction(
        seal_file=SEAL_FILE,
        claiming_row=f"{SEAL_FILE}::test_no_undecided_reason_is_actionable_as_a_pass",
        subject=SUBJECT,
        described="letting a declaration touch an abstention",
        reason=NonDerivable.REFERENCE_IMPLEMENTATION_DISCARDED,
        revision=REVISION, subject_sha256=ml.source_digest(at_revision),
        recorded_on=MEASURED_ON)

    assert ml.PREDICTION_FATE is ClauseFate.RELABEL_PREDICTED
    assert predicted.reason is NonDerivable.REFERENCE_IMPLEMENTATION_DISCARDED
    assert predicted.subject_sha256 != ml.source_digest(
        (root / SUBJECT).read_bytes()), (
        "the subject has not moved since the judgement, so this row can no "
        "longer show that a prediction goes stale")


# --------------------------------------------------------------------------- #
# The folds. Arithmetic, and disclosed as such: they cannot tell us the
# mutation ran, which is why the rows above exist.
# --------------------------------------------------------------------------- #

def test_no_combination_leaves_a_clause_as_it_was_and_only_a_broken_run_waits(
) -> None:
    """``fold`` is total over 7x7 and ``AWAIT_RERUN``'s preimage is exact.

    The one fate that does not dispose of a clause must be reachable ONLY from
    a fault in the RUN. Every fact about the clause, the mutation or the
    tree's content that reached it would strand that clause un-relabelled and
    un-struck forever — "kept as it was" under another name.

    Measured under: route ``MUTANT_UNEVALUABLE`` or ``CONTROL_RED`` to
    ``FAULTED`` and the preimage assertion reddens; give ``fold`` or
    ``proposed_fate`` a default arm and the totality sweep reddens on the
    member it silently swallowed.
    """
    waits, seen = set(), set()
    for freshness in Freshness:
        for observation in Observation:
            status = ml.fold(freshness, observation)
            assert isinstance(status, Status)
            seen.add(status)
            if ml.proposed_fate(status) is ClauseFate.AWAIT_RERUN:
                waits.add((freshness, observation))

    assert waits == {(f, Observation.HARNESS_FAULT) for f in Freshness} | {
        (f, o) for f in (Freshness.SUBJECT_GONE, Freshness.SITE_GONE,
                         Freshness.ROW_GONE)
        for o in (Observation.REDDENED_AS_RECORDED,
                  Observation.REDDENED_SCOPE_DIVERGED, Observation.SURVIVED)}
    assert {ml.proposed_fate(s) for s in Status} == set(ClauseFate)
    # No member of Status is dead: each has a combination that produces it.
    assert seen == set(Status)

    for bad in (None, "anchored", Freshness):
        with pytest.raises(ml.MutationLedgerError):
            ml.fold(bad, Observation.SURVIVED)  # type: ignore[arg-type]
        with pytest.raises(ml.MutationLedgerError):
            ml.fold(Freshness.ANCHORED, bad)  # type: ignore[arg-type]
        with pytest.raises(ml.MutationLedgerError):
            ml.proposed_fate(bad)  # type: ignore[arg-type]


def test_a_deleted_row_is_disposed_of_rather_than_parked_forever() -> None:
    """The precedence argued hardest in the contract, pinned as a row.

    A deleted row, a deleted subject and an unresolvable anchor arrive as
    absence drift carrying ``NOT_ATTEMPTED``. Ranked under the absence arm
    they fold to ``FAULTED`` and wait on a re-run that can never restore what
    the tree no longer has.

    Measured under: check the absence arm before the "no comparison possible"
    arm and every assertion in the first block flips to ``FAULTED``.
    """
    for freshness in (Freshness.SUBJECT_GONE, Freshness.SITE_GONE,
                      Freshness.ROW_GONE):
        for observation in (Observation.NOT_ATTEMPTED, Observation.CONTROL_RED,
                            Observation.MUTANT_UNEVALUABLE):
            status = ml.fold(freshness, observation)
            assert status is Status.UNDERIVABLE
            assert ml.proposed_fate(status) is ClauseFate.RELABEL_PREDICTED

    # A completed comparison alongside a row the tree does not have is a
    # record contradicting itself, and that IS a fault in the run.
    assert ml.fold(Freshness.ROW_GONE,
                   Observation.REDDENED_AS_RECORDED) is Status.FAULTED


def test_freshness_reports_the_strongest_fact_about_the_tree() -> None:
    """Absence of the thing being compared outranks a difference in it.

    ``PROVENANCE_GONE`` sits between: it blocks the audit of the record, not
    the comparison, so a claim whose revision was rebased away is still
    refutable and is owed a fresh observation rather than a permanent wait.

    Measured under: rank ``REVISION_ABSENT`` with the hard absences and a
    rebased-away claim can never be re-observed; rank it below
    ``SUBJECT_BYTES`` and a moved body hides a missing provenance.
    """
    assert ml.freshness_of(()) is Freshness.ANCHORED
    assert ml.freshness_of((Drift.SUBJECT_BYTES,)) is Freshness.SUBJECT_MOVED
    assert ml.freshness_of((Drift.POPULATION,)) is Freshness.POPULATION_MOVED
    assert ml.freshness_of((Drift.REVISION_ABSENT,)) is Freshness.PROVENANCE_GONE

    strongest = (
        ((Drift.SUBJECT_ABSENT, Drift.SUBJECT_BYTES), Freshness.SUBJECT_GONE),
        ((Drift.SITE_ABSENT, Drift.POPULATION), Freshness.SITE_GONE),
        ((Drift.ROW_ABSENT, Drift.POPULATION), Freshness.ROW_GONE),
        ((Drift.SUBJECT_ABSENT, Drift.SITE_ABSENT), Freshness.SUBJECT_GONE),
        ((Drift.REVISION_ABSENT, Drift.SUBJECT_BYTES), Freshness.PROVENANCE_GONE),
        ((Drift.SUBJECT_BYTES, Drift.POPULATION), Freshness.SUBJECT_MOVED),
    )
    for drift, expected in strongest:
        assert ml.freshness_of(drift) is expected, drift


def test_one_red_parametrisation_reddens_the_row_and_a_missing_one_does_not(
) -> None:
    """``fold_row_results``, over the shape a real run produces.

    A clause names ROWS; a parametrisation added to a row must not read as the
    file growing. GREEN today — this seam is implemented.

    The second block pins a CHOICE rather than a property: ABSENT ranks BELOW
    PASSED, so a row whose ``[b]`` was never reported folds to PASSED. A panel
    finding on W2-3-1 calls that a false green (a partially collected row
    reads as fully run) and it is not answered here — the row exists so that
    changing the ranking is a visible diff and not a silent one, and W2-3-4
    owns the ruling.

    Measured under: rank FAILED below PASSED and the first block reddens; drop
    the ``[param]`` split and every parametrised id becomes its own row, which
    is the population digest reporting a file that grew.
    """
    assert ml.fold_row_results({
        "t.py::r[a]": RowResult.PASSED, "t.py::r[b]": RowResult.FAILED,
    }) == {"t.py::r": RowResult.FAILED}
    assert ml.fold_row_results({
        "t.py::r[a]": RowResult.FAILED, "t.py::r[b]": RowResult.ERRORED,
    }) == {"t.py::r": RowResult.ERRORED}
    assert ml.fold_row_results({
        "t.py::r[a]": RowResult.ABSENT, "t.py::r[b]": RowResult.ABSENT,
    }) == {"t.py::r": RowResult.ABSENT}

    assert ml.fold_row_results({
        "t.py::r[a]": RowResult.PASSED, "t.py::r[b]": RowResult.ABSENT,
    }) == {"t.py::r": RowResult.PASSED}
