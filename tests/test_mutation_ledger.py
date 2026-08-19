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
    ``4e66a01`` on 2026-08-18 (:func:`measured`): that mutation reddens the
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

RED until W2-3-3 fills the four folds and the harness. Which sensitivity
vocabulary a row carries follows from that, and is not a stylistic choice:

  * ``Measured under:`` — the five rows green today over implemented seams.
    Each named mutation was applied to :mod:`mutation_ledger` and the row
    observed to go PASSED->FAILED on 2026-08-18.
  * ``Predicted (unmeasured) under:`` — the sixteen rows red against a
    declared hole (the four folds, the harness, the applier, the
    provisioner/collector/runner, the reader/writer, the citation check and
    the CLI). They are red under control as well as mutant, so no transition
    is derivable and ``Measured under:`` on them would assert a run nobody
    made. W2-3-3 is owed the re-measurement when it greens them.

The measurement in the flagship's BODY is a different thing and was taken: the
mutant/control maps above are real runs of ``call_site_reachability``. What is
unmeasured is only this file's own sensitivity to a wrong ``mutation_ledger``.

:data:`REVISION` and :data:`SUBJECT_MOVED_AT` are object-database
dependencies, and their absence FAILS. A clone without them cannot take the
flagship measurement, and the outcome this file cannot detect from its own
exit status is the one where it silently did not: a shallow checkout would
otherwise drop the flagship, the rederive oracle, the applier row and the
one green prediction-staleness row, and report a green seal suite having
compared nothing. ``MLSEAL_ALLOW_MISSING_HISTORY=1`` turns the absence back
into a skip for a clone that genuinely cannot fetch — see
:func:`_require_revisions`.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import os
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import pytest

from claude_dispatcher import mutation_ledger as ml
from claude_dispatcher import role_protocol
from claude_dispatcher.mutation_ledger import (
    ClauseFate, Drift, Freshness, LedgerEntry, MutationOperator, MutationSite,
    NonDerivable, Observation, RederiveMode, RowResult, Status,
)
from claude_dispatcher.scratch_clone import scrubbed_git_env

# --------------------------------------------------------------------------- #
# The measured claim. Every constant here was re-derived on 2026-08-18 by
# running the procedure in `measured`; none is carried from the P4 report.
# --------------------------------------------------------------------------- #

#: `feat/D5-seals2`, the revision the P4 injected into. Immutable, so the
#: measurement below is repeatable rather than a claim about "now".
REVISION = "4e66a01da37c5ea4d480cc2aa3bca84728a2a4da"
#: The last revision that touched the subject, and it is AFTER `REVISION`.
#: Also immutable, which is what lets the prediction row show a judgement
#: going stale without comparing against a working tree that anyone can edit.
SUBJECT_MOVED_AT = "2e0dc89d4953baeb9cbcaac4354abcd97e82ffc5"
MEASURED_ON = "2026-08-18"

SUBJECT = "src/claude_dispatcher/call_site_reachability.py"
SEAL_FILE = "tests/test_call_site_reachability.py"

#: The row whose clause names the mutation. It does not redden under it.
CLAIMING_ROW = f"{SEAL_FILE}::test_discover_roots_refuses_a_tree_it_cannot_sweep"
#: The row that actually reddens — six parametrisations, folded to one row.
REDDENED_ROW = (f"{SEAL_FILE}::test_discover_roots_raises_on_a_fault"
                "_without_help_from_the_graph_builder")

#: What the seal file collects and folds to at :data:`REVISION`. Pinned, so
#: "the whole file was green" is a statement about all 53 rows and not about
#: the two this claim names.
NODE_IDS = 95
ROWS = 53

SITE = MutationSite(subject=SUBJECT, anchor="discover_roots",
                    operator=MutationOperator.RAISE_TO_CONTINUE,
                    argument="AnalyzerError")

#: Every subprocess here is bounded. An unbounded nested pytest hangs the
#: session fixture and therefore CI, and the failure reads as a stall rather
#: than as anything about the claim.
TIMEOUT_SECONDS = 600

#: pytest exit codes that mean the RUN itself completed: 0 all passed, 1 tests
#: failed. INTERRUPTED, INTERNAL_ERROR, USAGE_ERROR and NO_TESTS_COLLECTED are
#: broken runs — and a broken run still leaves a well-formed junit file, one
#: that can hold the two rows asserted on while the rest never ran.
RAN = frozenset({0, 1})

#: Loaded into the measurement run to record its COLLECTED population. A
#: plugin rather than parsing ``--collect-only -q``, whose output format is
#: not stable across pytest majors (9 prints a count where 8 printed the ids),
#: and loaded into the SAME run as the results, so no second collection can
#: disagree with the one that was measured.
_COLLECT_PLUGIN = '''import os


def pytest_collection_finish(session):
    with open(os.environ["MLSEAL_COLLECTED"], "w", encoding="utf-8") as fh:
        for item in session.items:
            fh.write(item.nodeid + "\\n")
'''


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(("git", *args), cwd=cwd, env=scrubbed_git_env(),
                          capture_output=True, check=True,
                          timeout=TIMEOUT_SECONDS)


def _object_present(root: Path, name: str) -> bool:
    """Whether ``name``'s object is in this clone — and nothing else.

    ``git cat-file -e <sha>``, with no ``^{commit}`` peel, is the only probe
    that separates the two answers: an object this clone does not have exits
    **1 with an empty stderr**, while no repository, an unreadable object
    database, or a git that will not start exits 128 with a message. (Peeled,
    ``<sha>^{commit}`` reports the absence as 128 too, and the two become
    indistinguishable.) Every non-absence failure is RAISED: laundering one
    into "not measured in this clone" is how a green run comes to mean
    nothing, which is the opposite of the distinction the skip exists for.
    """
    proc = subprocess.run(("git", "cat-file", "-e", name), cwd=root,
                          env=scrubbed_git_env(), capture_output=True,
                          text=True, timeout=TIMEOUT_SECONDS)
    if proc.returncode == 0:
        return True
    if proc.returncode == 1 and not proc.stderr.strip():
        return False
    raise AssertionError(
        f"git could not answer whether {name} is in this clone, which is not "
        f"the same as its absence — reported rather than skipped over\n"
        f"exit: {proc.returncode}\nstdout:\n{proc.stdout}"
        f"\nstderr:\n{proc.stderr}")


def _require_revisions(root: Path, *revisions: str) -> None:
    """FAIL when a recorded revision is not in this clone.

    Absence is a failure by default and the skip is the opt-out, which is the
    way round it has to be. The alternative fails open in every environment
    that has not been told otherwise: no workflow in this repository sets an
    opt-in variable, ``actions/checkout`` defaults to ``fetch-depth: 1``, and
    a clone without these objects would drop the flagship, the rederive
    oracle, the applier row and the prediction-staleness row TOGETHER — every
    row that takes a measurement — and still exit 0. "A green suite that
    compared nothing" is precisely the reading this unit exists to make
    impossible, so this file must not produce one about itself.

    ``MLSEAL_ALLOW_MISSING_HISTORY=1`` restores the skip, for a clone that
    genuinely cannot fetch the history. It is a deliberate, named act:
    whoever sets it is saying "this run does not measure", and the message
    says so.

    Two things this must not do, both of which turn "we did not look" into
    "we looked and it was fine":

      * treat anything but the absence itself as absence. The repository is
        proved usable first (a check that raises), and :func:`_object_present`
        classifies the rest.
      * answer for ONE revision while another row needs a different one.
        Every revision a row will reach is named here, so a clone carrying
        :data:`REVISION` but not :data:`SUBJECT_MOVED_AT` is caught here
        rather than raising ``CalledProcessError`` out of ``git show``.
    """
    # Raises rather than reporting absence: if this fails, git or the
    # repository is broken, and no conclusion about the revisions is
    # available at all.
    _git("rev-parse", "--verify", "HEAD^{commit}", cwd=root)

    absent = [r for r in revisions if not _object_present(root, r)]
    if not absent:
        return
    message = (
        f"{', '.join(absent)} not in this clone, so the recorded measurement "
        "cannot be re-derived here; fetch the full history "
        "(git fetch --unshallow) to run it")
    if os.environ.get("MLSEAL_ALLOW_MISSING_HISTORY") == "1":
        pytest.skip(f"MLSEAL_ALLOW_MISSING_HISTORY is set and {message}; this "
                    "run took no measurement")
    raise AssertionError(message)


def _at_revision(root: Path, revision: str, path: str) -> bytes:
    return _git("show", f"{revision}:{path}", cwd=root).stdout


def _tree(source: bytes) -> str:
    """``source`` as a parsed program, with formatting discarded.

    What two mutants have to agree on is the PROGRAM. Comparing bytes would
    make the harness answerable to :func:`_swallow`'s indentation.
    """
    return ast.dump(ast.parse(source))


def _bodies(source: bytes) -> dict[str, str]:
    """Top-level function name to its parsed body, for locating an edit."""
    return {n.name: ast.dump(ast.Module(body=n.body, type_ignores=[]))
            for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


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


def _nested_env(tree: Path, plugins: Path, collected: Path) -> dict[str, str]:
    """The environment for a nested measurement run, scrubbed of the host's.

    Drop-by-prefix rather than an allowlist of the known routing variables,
    the choice :func:`scratch_clone.scrubbed_git_env` documents on the git
    side and for the same reason: the enumeration is what falls out of date.
    ``PYTEST_ADDOPTS`` carrying ``-k``, ``--lf`` or ``--maxfail``, a
    ``PYTEST_PLUGINS`` entry, a ``COVERAGE_*`` wrapper or an inherited
    ``PYTHONPATH`` each change what this run observes — and this run is the
    oracle the flagship rests on, so a measurement that is right in a clean
    shell and different under CI addopts is the failure to prevent.

    Scrubbing the environment is only half of it: a ``pytest11`` entry point
    INSTALLED in this interpreter is loaded with no environment variable
    naming it, so ``cov``, ``timeout``, ``rerunfailures``, ``testmon`` and
    ``xdist`` each still reach collection and reporting here. That is the
    same "a clean shell is not CI" class the scrub exists to close, so
    autoload is disabled and the one plugin this measurement needs is named
    with ``-p``. ``PYTEST_DISABLE_PLUGIN_AUTOLOAD`` is set AFTER the
    prefix scrub, which would otherwise drop it.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PYTEST_", "COVERAGE_", "PYTHON", "GIT_",
                                "TOX_", "NOSE_"))}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(tree / "src"), str(plugins)))
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MLSEAL_COLLECTED"] = str(collected)
    return env


def _unusable(what: str, proc: subprocess.CompletedProcess) -> str:
    return (f"the nested measurement run is unusable ({what}); this file's "
            f"claim rests on it, so it is reported rather than parsed around"
            f"\ncommand: {proc.args}\nstdout:\n{proc.stdout}"
            f"\nstderr:\n{proc.stderr}")


def _junit_node_id(seal_file: str, case: ET.Element,
                   proc: subprocess.CompletedProcess) -> str:
    """The collected node id ``case`` reports on.

    junit splits an id in two: ``name`` is the function, and ``classname``
    carries the dotted module PLUS any enclosing classes. Reading ``name``
    alone reconstructs ``file.py::test_m`` for a row that was collected as
    ``file.py::TestC::test_m``, which is not in the collected set, so a
    class-based row anywhere in the seal file would report as unreported.
    The seal file this measurement runs has none today; it is not a file
    this unit owns, and the flagship must not turn amber when it grows one.

    A ``classname`` that is not the module or one of its classes is REPORTED,
    not mapped: it means the run reached a file this measurement did not ask
    for, and every result parsed out of it is about something else.
    """
    module = seal_file[:-len(".py")].replace("/", ".")
    classname = case.get("classname") or ""
    if classname == module:
        enclosing: tuple[str, ...] = ()
    elif classname.startswith(f"{module}."):
        enclosing = tuple(classname[len(module) + 1:].split("."))
    else:
        raise AssertionError(_unusable(
            f"reported classname {classname!r}, which is not {module!r} nor a "
            f"class in it", proc))
    return "::".join((seal_file, *enclosing, case.get("name") or ""))


def _run_rows(tree: Path, seal_file: str, work: Path,
              tag: str) -> dict[str, RowResult]:
    """Node-id-level results for ``seal_file`` in ``tree``, over the COLLECTED
    population.

    Three things this cannot do without, each of which silently manufactures a
    measurement when it is missing:

      * the COLLECTED ids, from the run itself. A row that was collected and
        then not reported is ABSENT, and neither the short summary nor the
        junit file can tell "not reported" from "passed" — the junit file
        simply has no element for it.
      * the EXIT CODE. pytest writes a junit file for an interrupted or
        internally-failed run too, and a partial one holding the rows this
        file asserts on reads as a complete measurement.
      * a bound, and the OUTPUT when the bound or the code says no. A hang or
        an import error otherwise surfaces as ``ET.parse`` on a missing file.
    """
    plugins = work / f"{tag}-plugins"
    plugins.mkdir()
    (plugins / "mlseal_collect.py").write_text(_COLLECT_PLUGIN)
    collected, junit = work / f"{tag}.ids", work / f"{tag}.xml"

    proc = subprocess.run(
        (sys.executable, "-m", "pytest", seal_file, "-q", "--tb=no",
         "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "mlseal_collect",
         f"--junitxml={junit}"),
        cwd=tree, env=_nested_env(tree, plugins, collected),
        capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if proc.returncode not in RAN:
        raise AssertionError(_unusable(f"exit {proc.returncode}", proc))
    if not collected.exists():
        raise AssertionError(_unusable("collection never finished", proc))

    # `splitlines`, never `split`: a parametrised id routinely carries spaces
    # (`test_seal[a plain property]`) and splitting on whitespace tears one row
    # into several that match nothing.
    results = dict.fromkeys(
        (i for i in collected.read_text().splitlines() if i), RowResult.ABSENT)
    if not results:
        raise AssertionError(_unusable("collected nothing", proc))
    outcome = {"failure": RowResult.FAILED, "error": RowResult.ERRORED}
    for case in ET.parse(junit).iter("testcase"):
        node = _junit_node_id(seal_file, case, proc)
        if node not in results:
            raise AssertionError(_unusable(
                f"reported {node!r}, which it did not collect", proc))
        kinds = {child.tag for child in case}
        if "skipped" in kinds:
            # `RowResult` has no SKIPPED member (a W2-3-1 finding). ABSENT is
            # the fail-closed reading of one: it ranks below PASSED, so a skip
            # cannot manufacture a PASSED->FAILED transition either way.
            continue
        result = RowResult.PASSED
        for tag_name, member in outcome.items():
            if tag_name in kinds:
                result = member
        results[node] = result
    return results


@dataclass(frozen=True)
class _Pair:
    #: Node-id level, before folding: the population these rows pin.
    control_nodes: dict[str, RowResult]
    mutant_nodes: dict[str, RowResult]
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
    _require_revisions(root, REVISION)
    work = tmp_path_factory.mktemp("d5")
    tree = work / "tree"
    tree.mkdir()
    archive = work / "d5.tar"
    with archive.open("wb") as fh:
        subprocess.run(("git", "archive", REVISION), cwd=root, stdout=fh,
                       env=scrubbed_git_env(), check=True,
                       timeout=TIMEOUT_SECONDS)
    with tarfile.open(archive) as tar:
        # `.claude/workflow` is a symlink out of the tree; extracting it is
        # refused, and the harness contract drops it for the same reason.
        tar.extractall(tree, filter="data", members=[
            m for m in tar if not m.name.startswith(".claude/")])

    subject = tree / SUBJECT
    original = subject.read_bytes()
    mutated = _swallow(original, SITE)
    assert mutated != original, "the mutation changed nothing"

    control_nodes = _run_rows(tree, SEAL_FILE, work, "control")
    subject.write_bytes(mutated)
    mutant_nodes = _run_rows(tree, SEAL_FILE, work, "mutant")

    control = ml.fold_row_results(control_nodes)
    return _Pair(
        control_nodes=control_nodes, mutant_nodes=mutant_nodes,
        control=control, mutant=ml.fold_row_results(mutant_nodes),
        subject_sha256=ml.source_digest(original),
        mutant_sha256=ml.source_digest(mutated),
        population_sha256=ml.population_digest(tuple(control)))


@pytest.fixture(scope="session")
def repo_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A throwaway clone of this repository for :func:`rederive` to work in.

    ``rederive`` provisions with ``git worktree add --detach`` in the
    ``repo_root`` it is handed, and then removes ``.claude/workflow`` from the
    staging worktree. Handing it the developer's checkout would have running
    this file write — and delete — inside the tree under measurement, once per
    entry. ``--shared`` so the copy costs an alternates file rather than the
    object database.
    """
    root = _repo_root()
    _require_revisions(root, REVISION)
    dest = tmp_path_factory.mktemp("repo") / "clone"
    _git("clone", "--shared", "--no-checkout", "-q", str(root), str(dest),
         cwd=root)
    return dest


def _entry(pair: _Pair, *, claiming_row: str,
           reddened: tuple[str, ...]) -> LedgerEntry:
    return ml.new_entry(
        seal_file=SEAL_FILE, claiming_row=claiming_row, site=SITE,
        revision=REVISION, subject_sha256=pair.subject_sha256,
        mutant_sha256=pair.mutant_sha256,
        population_sha256=pair.population_sha256, reddened=reddened,
        control_green=pair.control[claiming_row] is RowResult.PASSED,
        observed_on=MEASURED_ON)


def _verdict(pair: _Pair, entry: LedgerEntry) -> Status:
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


def choose(flag):
    """Returns a value based on a flag; no default case."""
    if flag:
        return "yes"
'''

#: The same module under the recorded operator, written out rather than
#: generated: `mutant_sha256` is provenance on the observation id and no drift
#: member compares it, so deriving it through the applier under seal would buy
#: nothing and couple the record to it.
_MUTANT_SRC = _SUBJECT_SRC.replace("    return 41", "    return None")
_MUTANT_WITH_DEFAULT_SRC = _SUBJECT_SRC.replace(
    '''def choose(flag):
    """Returns a value based on a flag; no default case."""
    if flag:
        return "yes"''',
    '''def choose(flag):
    """Returns a value based on a flag; no default case."""
    if flag:
        return "yes"
    else:
        return None''')

_CONFTEST_SRC = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))
"""

#: The tiny repository's seal file, named once: the row names below, the
#: recorded population and every collector assertion all have to agree on it.
_TINY_SEAL = "tests/test_seal.py"

_SEAL_SRC = """import pytest

from subject import answer, other


def test_reddens_under_the_mutation():
    assert answer() == 41


def test_red_before_anything_was_mutated():
    assert other() == 8


def test_untouched():
    assert other() == 7


@pytest.mark.parametrize("case", ["a", "b"])
def test_parametrised(case):
    assert other() == 7
"""


def _tiny_repo(tmp_path: Path, *, over_claim: bool = False,
               revision: str | None = None, deleted_row: bool = False):
    """A one-commit repository, an entry against it, and its row names.

    ``deleted_row`` records the entry against a claiming row the tree does
    not collect, and puts that row in the recorded population too — the shape
    a DELETED row leaves behind, where the absence and the population change
    arrive together.
    """
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

    seal = _TINY_SEAL
    # Function-level, which is what `population_digest` and `collect_rows`
    # take. `parametrised` is collected as ONE row and RUN as two node ids —
    # the only place the two levels differ, and therefore the only place a
    # runner that folded them would show.
    rows = {
        "reddens": f"{seal}::test_reddens_under_the_mutation",
        "baseline_red": f"{seal}::test_red_before_anything_was_mutated",
        "untouched": f"{seal}::test_untouched",
        "parametrised": f"{seal}::test_parametrised",
    }
    gone = f"{seal}::test_a_row_this_tree_no_longer_has"
    claiming = gone if deleted_row else rows["reddens"]
    population = (tuple(rows.values()) + (gone,) if deleted_row
                  else tuple(rows.values()))
    entry = ml.new_entry(
        seal_file=seal, claiming_row=claiming,
        site=MutationSite(subject="src/subject.py", anchor="answer",
                          operator=MutationOperator.BODY_TO_NO_OP),
        revision=revision or head,
        subject_sha256=ml.source_digest(_SUBJECT_SRC.encode()),
        mutant_sha256=ml.source_digest(_MUTANT_SRC.encode()),
        population_sha256=ml.population_digest(population),
        reddened=((rows["baseline_red"], rows["reddens"]) if over_claim
                  else (claiming,)),
        control_green=True, observed_on=MEASURED_ON)
    # `gone` is in the map only when it is in the record: `rows` is otherwise
    # exactly the tree's population, which is what the collector rows compare
    # against.
    return repo, entry, (dict(rows, gone=gone) if deleted_row else rows), head


def _recommit(repo: Path, path: str, source: str) -> str:
    """Replace ``path`` in ``repo``, commit, and return the new revision."""
    (repo / path).write_text(source)
    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=seal", "-c", "user.email=seal@example.invalid",
         "commit", "-qm", f"rewrite {path}", cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo).stdout.decode().strip()


#: A record with no measurement behind it, for the rows about IDENTITY and the
#: WIRE — those answer "can this file be misread", which is a question about
#: bytes and not about a run.
_WIRE_SEAL = "tests/test_seal.py"
_WIRE_ROW = f"{_WIRE_SEAL}::test_row"
_WIRE_SITE = MutationSite(subject="src/pkg/subject.py", anchor="answer",
                          operator=MutationOperator.BODY_TO_NO_OP)


#: Sentinel for "this key is absent", distinct from a key present and null —
#: which is a difference `_parse_observation` is required to keep.
_DROP = object()


def _wire_entry(**over) -> LedgerEntry:
    fields = dict(
        seal_file=_WIRE_SEAL, claiming_row=_WIRE_ROW, site=_WIRE_SITE,
        revision="a" * 40, subject_sha256=ml.source_digest(b"before"),
        mutant_sha256=ml.source_digest(b"after"),
        population_sha256=ml.population_digest((_WIRE_ROW,)),
        reddened=(_WIRE_ROW,), control_green=True, observed_on=MEASURED_ON)
    fields.update(over)
    return ml.new_entry(**fields)


def _wire_prediction(**over) -> ml.Prediction:
    fields = dict(
        seal_file=_WIRE_SEAL, claiming_row=_WIRE_ROW,
        subject=_WIRE_SITE.subject, described="a whole alternative body",
        reason=NonDerivable.NO_APPLICABLE_OPERATOR, revision="a" * 40,
        subject_sha256=ml.source_digest(b"before"), recorded_on=MEASURED_ON)
    fields.update(over)
    return ml.new_prediction(**fields)


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

    The first block asserts over the WHOLE population rather than the two rows
    the claim is about. "Exactly one row transitioned" is the fact both entries
    below rest on, and deriving it through ``classify_observation`` would have
    the implementation under seal certify its own measurement.

    Predicted (unmeasured) under: read the mutant map alone and the expired
    claim reads as coverage; drop the control comparison and the surviving
    claim reads as broken; give ``fold`` a default arm and the two verdicts
    collapse together.
    """
    assert len(measured.control_nodes) == NODE_IDS
    assert set(measured.mutant_nodes) == set(measured.control_nodes)
    assert set(measured.control.values()) == {RowResult.PASSED}, (
        "the file was not green before the mutation, so any red row below "
        "could be a baseline failure credited to the mutation")
    assert len(measured.control) == ROWS

    transitioned = {row for row, result in measured.mutant.items()
                    if result is RowResult.FAILED
                    and measured.control[row] is RowResult.PASSED}
    assert transitioned == {REDDENED_ROW}, (
        "the mutation's blast radius is not the one recorded; the two entries "
        "below no longer name the run that was taken")
    assert measured.mutant[CLAIMING_ROW] is RowResult.PASSED, (
        "the recorded mutation now reddens the row whose clause names it; the "
        "struck clause would be true and this seal's subject is gone")

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
        measured: _Pair, repo_copy: Path) -> None:
    """The harness must reach the same two verdicts from the record alone.

    Without this the folds could be right while nothing ever fed them a real
    run — the ledger would be a decision table with no measurement behind it.
    ``AT_RECORDED`` because that is the mode in which BROKEN is reachable: the
    tree the entry names is the tree that is run, so a survival has no
    innocent explanation.

    ``repo_copy``, not this checkout: ``rederive`` provisions by adding a
    worktree and deleting a path inside it.

    Predicted (unmeasured) under: return a canned ``Rederivation`` from
    ``rederive`` and the two statuses stop disagreeing; trust
    ``entry.reddened`` instead of running the mutant and the expired claim
    reads as HELD.
    """
    expired = _entry(measured, claiming_row=CLAIMING_ROW,
                     reddened=(CLAIMING_ROW,))
    control = _entry(measured, claiming_row=REDDENED_ROW,
                     reddened=(REDDENED_ROW,))

    got = {e.claiming_row: ml.rederive(e, repo_root=str(repo_copy),
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


def test_classify_observation_answers_one_pair_of_runs_in_a_fixed_order(
) -> None:
    """The fold that decides whether a mutation REPRODUCED, swept directly.

    It is the only one of the four the rows above reach through another
    function, and a table that is right on the flagship's single pair can be
    wrong on every arm that pair does not visit. The ORDER of the arms is the
    contract rather than an implementation detail: each case naming two facts
    at once is there because ranking them the other way turns a broken run or
    a baseline failure into coverage.

    The reddened set is the PASSED-to-FAILED TRANSITION set, and the last two
    cases are where that stops agreeing with "rows red under the mutant":
    ``S`` is red in both runs, so it is not a transition, and a record that
    names it has over-claimed.

    A ``claiming_row`` absent from a non-empty map is deliberately NOT swept:
    :func:`rederive` resolves the row against the tree before calling this, so
    the contract does not define it and a row here would invent one.

    Predicted (unmeasured) under: check the mutant before the control and
    ``control-red-under-a-red-mutant`` reads as REDDENED_AS_RECORDED — a row
    that was red anyway becomes evidence; read ABSENT under the mutant as a
    failure and ``mutant-absent`` becomes coverage; compare the mutant's red
    rows instead of the transition set and the last two cases swap.
    """
    P, F, E, A = (RowResult.PASSED, RowResult.FAILED, RowResult.ERRORED,
                  RowResult.ABSENT)
    R, S = "t.py::r", "t.py::s"
    cases = (
        ("neither-run-reported", {}, {}, (), Observation.NOT_ATTEMPTED),
        ("control-empty", {}, {R: F}, (R,), Observation.HARNESS_FAULT),
        ("mutant-empty", {R: P}, {}, (R,), Observation.HARNESS_FAULT),
        ("control-errored", {R: E}, {R: F}, (R,), Observation.HARNESS_FAULT),
        ("control-absent", {R: A}, {R: F}, (R,), Observation.HARNESS_FAULT),
        ("control-red-under-a-red-mutant",
         {R: F}, {R: F}, (R,), Observation.CONTROL_RED),
        ("control-red-under-an-errored-mutant",
         {R: F}, {R: E}, (R,), Observation.CONTROL_RED),
        ("mutant-errored", {R: P}, {R: E}, (R,),
         Observation.MUTANT_UNEVALUABLE),
        ("mutant-absent", {R: P}, {R: A}, (R,),
         Observation.MUTANT_UNEVALUABLE),
        ("survived", {R: P}, {R: P}, (R,), Observation.SURVIVED),
        ("survived-with-collateral",
         {R: P, S: P}, {R: P, S: F}, (R,), Observation.SURVIVED),
        ("reddened", {R: P}, {R: F}, (R,),
         Observation.REDDENED_AS_RECORDED),
        ("order-is-not-a-fact-about-a-run",
         {R: P, S: P}, {R: F, S: F}, (S, R),
         Observation.REDDENED_AS_RECORDED),
        ("understated-scope", {R: P, S: P}, {R: F, S: F}, (R,),
         Observation.REDDENED_SCOPE_DIVERGED),
        ("overstated-scope", {R: P, S: P}, {R: F, S: P}, (R, S),
         Observation.REDDENED_SCOPE_DIVERGED),
        ("a-baseline-red-row-is-not-a-transition",
         {R: P, S: F}, {R: F, S: F}, (R,),
         Observation.REDDENED_AS_RECORDED),
        ("a-baseline-red-row-recorded-as-reddened",
         {R: P, S: F}, {R: F, S: F}, (R, S),
         Observation.REDDENED_SCOPE_DIVERGED),
    )

    seen = set()
    for label, control, mutant, recorded, expected in cases:
        got = ml.classify_observation(control=control, mutant=mutant,
                                      claiming_row=R,
                                      recorded_reddened=recorded)
        assert got is expected, label
        seen.add(got)
    # Surjective: no member of Observation is unreachable, so none of them is
    # a state the harness can never report and nobody has to handle.
    assert seen == set(Observation)


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

    Predicted (unmeasured) under: define ``reddened_observed`` as the
    mutant's red rows and every assertion below flips; compute
    ``missing_rows`` from the observed set instead of the recorded one and the
    two set assertions cross over.
    """
    repo, entry, rows, _ = _tiny_repo(tmp_path, over_claim=True)

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

    ``revision_run`` is the W2-3-1 contract defect this row can only pin one
    side of: it is mandatory, must be a 40-char sha, and is documented as
    "the revision actually provisioned and run" — and nothing was provisioned
    here, so no truthful value exists. What DOES have a truth value is the
    one answer that would be a lie, and it is the cheapest one for a body to
    reach for: echoing the recorded revision back. That is refused. The null
    sha, or the revision of whatever tree was in fact stood up, both remain
    open, and W2-3-4 owns the ruling that closes them.

    Predicted (unmeasured) under: raise instead of returning and this row
    errors; report the absence as ``HARNESS_FAULT`` and the clause parks on
    ``AWAIT_RERUN`` forever, which no re-run can clear; echo
    ``entry.revision`` into ``revision_run`` and the provenance block
    reddens.
    """
    repo, entry, _, _ = _tiny_repo(tmp_path, revision="9" * 40)

    r = ml.rederive(entry, repo_root=str(repo), mode=RederiveMode.AT_RECORDED)

    assert isinstance(r, ml.Rederivation)
    assert Drift.REVISION_ABSENT in r.drift
    assert r.observation is Observation.NOT_ATTEMPTED
    assert r.status is Status.UNDERIVABLE
    assert ml.proposed_fate(r.status) is ClauseFate.RELABEL_PREDICTED

    assert r.revision_run != entry.revision, (
        "the recorded revision is not in this repository, so reporting it as "
        "the revision provisioned and run is fabricated provenance")
    assert r.detail, "an unprovisioned re-derivation must say why"


def test_a_deleted_claiming_row_is_resolved_before_anything_is_classified(
        tmp_path: Path) -> None:
    """``rederive`` reports a row the tree does not have as DRIFT, not as a
    classification.

    :func:`classify_observation` is entitled to assume the claiming row was
    COLLECTED in both runs — its ABSENT arm means "collected and then not
    reported", which is a broken run. That entitlement is a promise made HERE
    and nowhere else, and the sweep of ``classify_observation`` deliberately
    leaves the missing-row case out because the contract does not define it.
    Without this row, "``rederive`` resolves the row first" is asserted by no
    test at all, and a harness that let a deleted row reach the classifier
    would report ``HARNESS_FAULT`` — parking a clause on a re-run that can
    never collect a row somebody deleted.

    The recorded population carries the deleted row too, so ``ROW_ABSENT``
    and ``POPULATION`` drift arrive together and the hard absence must win.
    No result map is consulted for the verdict: ``NOT_ATTEMPTED`` is the
    observation, and no other row's transition may stand in for the missing
    one.

    Predicted (unmeasured) under: classify before resolving the row and this
    reads ``HARNESS_FAULT``/``FAULTED``; fold ``POPULATION`` above
    ``ROW_ABSENT`` and the freshness reads ``POPULATION_MOVED``; let another
    row's transition answer for the claiming row and ``reddened_observed``
    stops being empty.
    """
    repo, entry, rows, _ = _tiny_repo(tmp_path, deleted_row=True)

    # AT_TARGET, not AT_RECORDED: a well-formed observation cannot show a row
    # missing at its own revision — the row was collected when it was taken —
    # so the deleted row is only observable against the target tree, which is
    # also the mode W2-3-3 and W2-3-5 will run in.
    r = ml.rederive(entry, repo_root=str(repo), mode=RederiveMode.AT_TARGET)

    assert Drift.ROW_ABSENT in r.drift
    assert r.freshness is Freshness.ROW_GONE
    assert r.observation is Observation.NOT_ATTEMPTED
    assert r.reddened_observed == (), (
        "nothing was compared, so no row may be reported as reddened by a "
        "comparison that did not happen")
    assert r.status is Status.UNDERIVABLE
    assert ml.proposed_fate(r.status) is ClauseFate.RELABEL_PREDICTED

    # The row really is not there — checked against the seal file's source,
    # not through `collect_rows`, so this row reddens on `rederive` alone.
    assert rows["gone"].rpartition("::")[2] not in _SEAL_SRC


# --------------------------------------------------------------------------- #
# The other half of the population: clauses that can never yield an
# observation. GREEN today — arithmetic over implemented seams plus two real
# digests taken from two immutable revisions.
# --------------------------------------------------------------------------- #

def test_a_clause_whose_evidence_expired_is_predicted_and_never_cited() -> None:
    """One of the 31, recorded as what it is.

    ``test_no_undecided_reason_is_actionable_as_a_pass`` carries "Reddens
    under a body on: ... letting a declaration touch an abstention", measured
    only against the reference implementation that was discarded. Copying it
    into the ledger as an observation would make it true again by
    transcription, which is the defect this unit closes; the honest record is
    a prediction.

    The measured half is that the judgement has gone stale, and it is taken
    between two IMMUTABLE revisions rather than against the working tree: the
    subject's bytes at :data:`REVISION` are not its bytes at
    :data:`SUBJECT_MOVED_AT`. A comparison against the checkout would pass for
    every state except one and would move under an uncommitted edit.

    The identity half is what makes re-examination possible at all: the id
    names the CLAUSE — row, subject, and the sentence judged unmeasurable —
    and not the judgement, so looking again lands on the same record while
    judging a different sentence does not.

    Measured under: drop ``subject_sha256`` from ``Prediction`` and the
    staleness below is unrepresentable; put the judgement's ``reason`` into
    ``prediction_id`` and re-examining a clause forks the record instead of
    replacing it; drop ``described`` from it and two clauses on one row
    collide; let ``observations`` return every record and a prediction reads
    as evidence.
    """
    root = _repo_root()
    _require_revisions(root, REVISION, SUBJECT_MOVED_AT)
    at_revision = _at_revision(root, REVISION, SUBJECT)
    at_later = _at_revision(root, SUBJECT_MOVED_AT, SUBJECT)

    row = f"{SEAL_FILE}::test_no_undecided_reason_is_actionable_as_a_pass"
    described = "letting a declaration touch an abstention"
    predicted = ml.new_prediction(
        seal_file=SEAL_FILE, claiming_row=row, subject=SUBJECT,
        described=described,
        reason=NonDerivable.REFERENCE_IMPLEMENTATION_DISCARDED,
        revision=REVISION, subject_sha256=ml.source_digest(at_revision),
        recorded_on=MEASURED_ON)

    assert predicted.subject_sha256 == ml.source_digest(at_revision)
    assert predicted.subject_sha256 != ml.source_digest(at_later), (
        "the subject did not move between the two recorded revisions, so "
        "this row can no longer show a prediction going stale")

    re_examined = ml.new_prediction(
        seal_file=SEAL_FILE, claiming_row=row, subject=SUBJECT,
        described=described, reason=NonDerivable.NO_APPLICABLE_OPERATOR,
        revision=SUBJECT_MOVED_AT, subject_sha256=ml.source_digest(at_later),
        recorded_on="2026-08-19")
    assert re_examined.prediction_id == predicted.prediction_id
    assert re_examined.subject_sha256 != predicted.subject_sha256

    other_clause = ml.new_prediction(
        seal_file=SEAL_FILE, claiming_row=row, subject=SUBJECT,
        described="a whole alternative body",
        reason=NonDerivable.NO_APPLICABLE_OPERATOR, revision=REVISION,
        subject_sha256=ml.source_digest(at_revision), recorded_on=MEASURED_ON)
    assert other_clause.prediction_id != predicted.prediction_id

    # NEVER CITED, which is the half of this row's name the ids do not carry:
    # a prediction is not evidence, so it is not in the observation set the
    # citation check resolves against and no `ml-` id resolves to it. A
    # reader that returned it among the observations would let "we could not
    # measure this" be cited as "we measured this".
    ledger = (predicted, other_clause)
    assert ml.observations(ledger) == ()
    assert ml.current_observations(ledger) == {}
    assert ml.predictions(ledger) == ledger


# --------------------------------------------------------------------------- #
# The folds. Arithmetic, and disclosed as such: they cannot tell us the
# mutation ran, which is why the rows above exist.
# --------------------------------------------------------------------------- #

def test_every_cell_of_the_fold_and_every_fate_has_a_pinned_value() -> None:
    """The 7x7 table and the fate of each :class:`Status`, by VALUE.

    The invariants in the row below — totality, ``AWAIT_RERUN``'s preimage,
    surjectivity over :class:`Status` and over :class:`ClauseFate`, and
    ``citable == {CITE_CLAIM}`` — are all satisfied by an INVERTED table. A
    panel demonstrated two independent inversions that keep every one of them
    green: swapping the drifted-tree arm (``REDDENED_AS_RECORDED`` to
    EXPIRED, ``SURVIVED`` to REANCHORED), and swapping the two fates
    (``REANCHORED`` to STRIKE, ``EXPIRED`` to REOBSERVE_THEN_CITE). Under
    either, a clause whose mutation still reddens exactly as recorded is
    proposed for STRIKE, and a clause that SURVIVED — an entry that no longer
    reproduces, which is this file's whole subject — stays citable pending a
    re-run.

    So the arms are pinned as values rather than as constraints. Arm 6 in
    particular is the COMMON path for W2-3-3/W2-3-5, which re-derive 41
    clauses against subjects whose bytes have moved since the clause was
    written; the flagship reaches only ANCHORED.

    The table is the contract's precedence list read out, in its order:
    HARNESS_FAULT first, then the three no-comparison observations, then the
    hard absences, then a diverged scope, then ANCHORED, then the rest.

    Predicted (unmeasured) under: swap either half of the drifted-tree arm
    and twelve cells redden; give ``fold`` a default arm and the cell it
    swallows reddens; swap ``REANCHORED``/``EXPIRED`` in ``proposed_fate``
    and the fate block reddens.
    """
    HELD, REANCH, SCOPE = Status.HELD, Status.REANCHORED, Status.SCOPE_BROKEN
    BROKEN, EXPIRED = Status.BROKEN, Status.EXPIRED
    UND, FAULT = Status.UNDERIVABLE, Status.FAULTED

    columns = (Observation.REDDENED_AS_RECORDED,
               Observation.REDDENED_SCOPE_DIVERGED, Observation.SURVIVED,
               Observation.CONTROL_RED, Observation.MUTANT_UNEVALUABLE,
               Observation.NOT_ATTEMPTED, Observation.HARNESS_FAULT)
    table = {
        Freshness.ANCHORED:         (HELD,   SCOPE, BROKEN,  UND, UND, UND, FAULT),
        Freshness.SUBJECT_MOVED:    (REANCH, SCOPE, EXPIRED, UND, UND, UND, FAULT),
        Freshness.POPULATION_MOVED: (REANCH, SCOPE, EXPIRED, UND, UND, UND, FAULT),
        Freshness.PROVENANCE_GONE:  (REANCH, SCOPE, EXPIRED, UND, UND, UND, FAULT),
        Freshness.SUBJECT_GONE:     (FAULT,  FAULT, FAULT,   UND, UND, UND, FAULT),
        Freshness.SITE_GONE:        (FAULT,  FAULT, FAULT,   UND, UND, UND, FAULT),
        Freshness.ROW_GONE:         (FAULT,  FAULT, FAULT,   UND, UND, UND, FAULT),
    }
    # Every member on both axes, so a member added to either enum arrives
    # here unruled rather than defaulting.
    assert set(table) == set(Freshness)
    assert set(columns) == set(Observation)
    for freshness, expected in table.items():
        for observation, want in zip(columns, expected):
            assert ml.fold(freshness, observation) is want, (
                freshness, observation)

    assert {s: ml.proposed_fate(s) for s in Status} == {
        Status.HELD: ClauseFate.CITE_CLAIM,
        Status.REANCHORED: ClauseFate.REOBSERVE_THEN_CITE,
        Status.SCOPE_BROKEN: ClauseFate.AMEND_SCOPE,
        Status.BROKEN: ClauseFate.STRIKE,
        Status.EXPIRED: ClauseFate.STRIKE,
        Status.UNDERIVABLE: ClauseFate.RELABEL_PREDICTED,
        Status.FAULTED: ClauseFate.AWAIT_RERUN,
    }


def test_no_combination_leaves_a_clause_as_it_was_and_only_a_broken_run_waits(
) -> None:
    """``fold`` is total over 7x7 and ``AWAIT_RERUN``'s preimage is exact.

    The INVARIANTS only. Every one of them is satisfied by an inverted table,
    so the values themselves are pinned in
    :func:`test_every_cell_of_the_fold_and_every_fate_has_a_pinned_value`;
    this row is what survives once they are, and it is the part that keeps
    holding when a member is added to either enum.

    The one fate that does not dispose of a clause must be reachable ONLY from
    a fault in the RUN. Every fact about the clause, the mutation or the
    tree's content that reached it would strand that clause un-relabelled and
    un-struck forever — "kept as it was" under another name.

    The last block is where the prediction row stops: a prediction is never
    evidence, checked against the fate of the statuses that ARE rather than by
    restating :data:`PREDICTION_FATE`'s value back to itself.

    Predicted (unmeasured) under: route ``MUTANT_UNEVALUABLE`` or
    ``CONTROL_RED`` to ``FAULTED`` and the preimage assertion reddens; give
    ``fold`` or ``proposed_fate`` a default arm and the totality sweep reddens
    on the member it silently swallowed; add a second member to
    ``READS_AS_COVERAGE`` and the last block reddens.
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

    citable = {ml.proposed_fate(s) for s in Status if ml.counts_as_coverage(s)}
    assert citable == {ClauseFate.CITE_CLAIM}
    assert ml.PREDICTION_FATE not in citable

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
    absence drift carrying no completed comparison. They must fold to
    ``UNDERIVABLE`` and be RELABELLED: ranking the absence arm above the
    "no comparison possible" arm folds them to ``FAULTED`` instead, which
    parks the clause on a re-run that can never restore what the tree no
    longer has.

    Predicted (unmeasured) under: check the absence arm before the "no
    comparison possible" arm and every assertion in the first block flips to
    ``FAULTED``.
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

    ``REVISION_ABSENT`` is declared FIRST in :class:`Drift` and ranks FOURTH
    here, and that gap is what the sweep below is for. Scanning ``Drift`` in
    declaration order and taking the first match — which is also the order
    ``Rederivation.__post_init__`` forces the drift tuple into, so it is the
    natural misreading — passes a table of named pairs while answering
    ``PROVENANCE_GONE`` for ``(REVISION_ABSENT, SUBJECT_ABSENT)`` and
    ``(REVISION_ABSENT, ROW_ABSENT)``, where the contract says the hard
    absence wins. Every one of the 64 subsets is swept instead, against the
    contract's numbered precedence list transcribed as ``PRECEDENCE``.

    Predicted (unmeasured) under: rank ``REVISION_ABSENT`` with the hard
    absences and a rebased-away claim can never be re-observed; rank it below
    ``SUBJECT_BYTES`` and a moved body hides a missing provenance; scan
    ``Drift`` in declaration order and the two subsets above redden.
    """
    #: :func:`freshness_of`'s numbered precedence list, in its order. First
    #: match wins; no match is ANCHORED.
    PRECEDENCE = (
        (Drift.SUBJECT_ABSENT, Freshness.SUBJECT_GONE),
        (Drift.SITE_ABSENT, Freshness.SITE_GONE),
        (Drift.ROW_ABSENT, Freshness.ROW_GONE),
        (Drift.REVISION_ABSENT, Freshness.PROVENANCE_GONE),
        (Drift.SUBJECT_BYTES, Freshness.SUBJECT_MOVED),
        (Drift.POPULATION, Freshness.POPULATION_MOVED),
    )
    assert {d for d, _ in PRECEDENCE} == set(Drift)
    assert {f for _, f in PRECEDENCE} | {Freshness.ANCHORED} == set(Freshness)

    order = list(Drift)
    seen = set()
    for mask in range(1 << len(order)):
        # Declaration order and unique: the shape `Rederivation` accepts.
        drift = tuple(d for i, d in enumerate(order) if mask >> i & 1)
        expected = next((f for d, f in PRECEDENCE if d in drift),
                        Freshness.ANCHORED)
        assert ml.freshness_of(drift) is expected, drift
        seen.add(expected)
    assert seen == set(Freshness)

    # The two the sweep exists for, named so a failure reads as itself.
    assert ml.freshness_of(
        (Drift.REVISION_ABSENT, Drift.SUBJECT_ABSENT)) is Freshness.SUBJECT_GONE
    assert ml.freshness_of(
        (Drift.REVISION_ABSENT, Drift.ROW_ABSENT)) is Freshness.ROW_GONE


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

    Measured under: rank FAILED below PASSED and the first block reddens;
    drop the ``[param]`` split and every block reddens — ``_NODE_ID`` refuses
    the bracketed id, so nothing folds at all.
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


# --------------------------------------------------------------------------- #
# The implemented surface that decides WHERE a ledger may be written, WHETHER
# a line may be read, and WHICH record answers for a claim. None of it is a
# fold, and all of it fails silently when it is wrong. GREEN today.
# --------------------------------------------------------------------------- #

def test_a_ledger_path_no_role_could_create_is_refused_before_it_is_used(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """``refuse_unwritable_ledger_path`` is fail-closed, and reads live tables.

    Deleting any one of its three checks leaves a green diff today, because
    nothing else refuses a ledger written where W2-3-3 could not create it —
    and a ledger the body role cannot write is one that gets written somewhere
    it can, outside every reader.

    Two of the cases are the ones a cheaper implementation gets wrong:

      * ``x_test.jsonl`` is denied to BODIES only through
        ``role_protocol.SEAL_VERIFY_TEST_PATHS``, which carries no wildcard —
        the second block asserts that NO glob in the rule matches it, so a
        gate that scanned ``DENY_GLOBS`` itself would let it through.
      * the floor is read at CALL time. No ``FLOOR_GLOBS`` entry matches a
        ledger path today, so that branch is exercised by putting one there;
        without the third block, dropping the floor check outright passes
        every other case here.

    Measured under: drop the ``first_matching_glob`` floor check and the third
    block reddens; scan ``rule.globs`` instead of calling
    ``evaluate_changed_paths`` and ``x_test.jsonl`` is accepted; drop the
    dot-in-segment refusal in ``ledger_path_for`` and the two colliding
    modules below get one file.
    """
    assert ml.ledger_path_for(SUBJECT) == (
        f"{ml.LEDGER_DIR}/claude_dispatcher.call_site_reachability.jsonl")
    accepted = f"{ml.LEDGER_DIR}/claude_dispatcher.subject.jsonl"
    ml.refuse_unwritable_ledger_path(accepted)

    for path in ("docs/other.jsonl",
                 f"{ml.LEDGER_DIR}/nested/x.jsonl",
                 f"{ml.LEDGER_DIR}/x.json",
                 f"{ml.LEDGER_DIR}/../x.jsonl",
                 f"/{ml.LEDGER_DIR}/x.jsonl",
                 f"{ml.LEDGER_DIR}/x.test.jsonl",
                 f"{ml.LEDGER_DIR}/x_test.jsonl"):
        with pytest.raises(ml.MutationLedgerError):
            ml.refuse_unwritable_ledger_path(path)

    bodies = role_protocol.built_in_policy().rule_for(role_protocol.Role.BODIES)
    assert role_protocol.first_matching_glob(
        f"{ml.LEDGER_DIR}/x_test.jsonl", bodies.globs) is None

    monkeypatch.setattr(
        role_protocol, "FLOOR_GLOBS",
        role_protocol.FLOOR_GLOBS + (f"**/{ml.LEDGER_DIR}/**",))
    with pytest.raises(ml.MutationLedgerError, match="floor"):
        ml.refuse_unwritable_ledger_path(accepted)
    monkeypatch.undo()

    # INJECTIVE, or two modules share a file `validate_ledger` then refuses
    # for holding two subjects.
    assert ml.ledger_path_for("src/pkg/a/b.py") == f"{ml.LEDGER_DIR}/pkg.a.b.jsonl"
    with pytest.raises(ml.MutationLedgerError):
        ml.ledger_path_for("src/pkg/a.b.py")


def test_a_ledger_line_round_trips_and_a_damaged_one_is_refused_not_guessed(
) -> None:
    """The wire, where a record stops being a Python object.

    Every refusal here is a way a ledger file could be read as saying
    something nobody measured: a truncated observation read as a prediction, a
    ``"false"`` coerced to ``True``, a hand-edited digest accepted because the
    id was not re-derived, a ``NaN`` cost that no budget comparison can ever
    exceed, an unknown key dropped so the fact it carried is lost.

    Measured under: derive the record kind from which keys are present rather
    than from ``kind`` and the truncated-observation case is read as a
    prediction; coerce a string to a bool in ``_typed`` and the ``"false"``
    case is accepted; drop BOTH id re-derivations from
    ``LedgerEntry.__post_init__`` and the forged-digest case is accepted —
    either one alone still catches it, which is why the pair is the mutation;
    drop ``_refuse_unknown_keys`` and the unknown-key case is accepted; drop
    ``parse_constant=`` from ``json.loads`` and the three JSON-constant tokens
    are refused by the field check instead, under a different message.
    """
    entry = _wire_entry(cost_seconds=1.5, note="prose")
    prediction = _wire_prediction()
    assert ml.parse_line(ml.canonical_line(entry)) == entry
    assert ml.parse_line(ml.canonical_line(prediction)) == prediction

    payload = json.loads(ml.canonical_line(entry))
    assert payload["kind"] == ml.OBSERVATION_KIND

    def refused(**over) -> None:
        damaged = dict(payload)
        for key, value in over.items():
            if value is _DROP:
                damaged.pop(key)
            else:
                damaged[key] = value
        with pytest.raises(ml.MutationLedgerError):
            ml.parse_line(json.dumps(damaged))

    refused(kind=_DROP)
    refused(kind=ml.PREDICTION_KIND)
    refused(reddened=_DROP)          # truncated, and not a prediction either
    refused(supersedes=_DROP)        # present-and-null is not the same as gone
    refused(control_green="false")   # no coercion: this one flips a verdict
    refused(cost_seconds="1.5")
    refused(version=ml.LEDGER_FORMAT_VERSION + 1)
    refused(operator="not-an-operator")
    refused(surprise="a fact nobody records")
    refused(subject_sha256=ml.source_digest(b"forged"))
    refused(observation_id="mlo-" + "0" * 16)

    # Refused at the DECODER, which is what the match pins. `_require_cost`
    # refuses a non-finite cost too, so without this guard the line is still
    # rejected — but by the field check, and `Infinity` would have travelled
    # through `json` first either way.
    for token in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ml.MutationLedgerError, match="JSON constant"):
            ml.parse_line(ml.canonical_line(entry).replace(
                '"cost_seconds":1.5', f'"cost_seconds":{token}'))
    for line in ("", "[]", "{", '{"version":1}'):
        with pytest.raises(ml.MutationLedgerError):
            ml.parse_line(line)


def test_a_claim_with_two_live_observations_has_no_answer_and_is_refused(
) -> None:
    """``validate_ledger`` and the reader that makes it more than advisory.

    An observation is replaced by a later one that NAMES it; the superseded
    entry stays, because it is the record of what was believed and when. Two
    entries for one claim with no link between them is not a merge conflict to
    resolve by file order — there is no rule by which one of them is the
    answer, and ``current_observations`` refuses rather than picking, which is
    what stops "is this clause covered" having two answers.

    The last block is about the W2-3-1 finding that an observation and a
    prediction for one clause are both permitted, so a citation can select
    whichever supports it. Half of that is a defect and half of it is the
    contract, and this row is careful to pin only the half that is:

      * ONE ROW carrying both kinds is correct and must stay accepted. The
        rows in this population name several clauses each — a whole
        alternative body, which no operator reaches, beside an edit to
        existing bytes, which one does. Refusing at row granularity makes
        such a row unrecordable, and the way out of a hard refusal is to drop
        the prediction, which leaves the unmeasurable clause unrecorded and
        reading as coverage. That is the defect this unit exists to close, so
        asserting acceptance here is asserting the contract, not blessing an
        ambiguity. The pair used is the legitimate one, and the row says so
        by checking that the two records name DIFFERENT clauses.
      * ONE CLAUSE carrying both is the real hole, and it is not expressible:
        ``claim_id`` keys a clause by ``(row, site)`` and ``prediction_id``
        by ``(row, described)``, so the two kinds share no clause key to
        compare. THAT is what the last assertions pin — as the missing key
        itself rather than as an acceptance — so a future clause key is a
        visible diff and a correct refusal built on it does not have to
        redden this row to land.

    Measured under: pick the last entry by file order in
    ``current_observations`` instead of refusing and the rival-entries block
    goes green; drop the ``target.claim_id`` check and an entry may supersede
    another claim's evidence; drop the ``superseders`` check and two entries
    both claim to replace one; resolve ``supersedes`` against later entries
    and a cycle validates.
    """
    first = _wire_entry()
    second = _wire_entry(observed_on="2026-08-19",
                         supersedes=first.observation_id)
    ml.validate_ledger((first, second))
    assert ml.current_observations((first, second)) == {first.claim_id: second}
    assert ml.observations((first, second, _wire_prediction())) == (first, second)
    assert ml.predictions((first, second)) == ()

    rival = _wire_entry(observed_on="2026-08-19")
    assert rival.claim_id == first.claim_id
    assert rival.observation_id != first.observation_id
    with pytest.raises(ml.MutationLedgerError, match="two current"):
        ml.validate_ledger((first, rival))
    with pytest.raises(ml.MutationLedgerError, match="two current"):
        ml.current_observations((first, rival))

    # `supersedes` must resolve BACKWARDS: a link read forwards makes the
    # replacement order a property of how the file was sorted.
    with pytest.raises(ml.MutationLedgerError, match="earlier"):
        ml.validate_ledger((second, first))

    third = _wire_entry(observed_on="2026-08-20",
                        supersedes=first.observation_id)
    with pytest.raises(ml.MutationLedgerError, match="superseded twice"):
        ml.validate_ledger((first, second, third))

    # A link across claims would let one clause's evidence be retired by
    # another clause's run.
    cross = _wire_entry(claiming_row=f"{_WIRE_SEAL}::test_other_row",
                        supersedes=first.observation_id)
    assert cross.claim_id != first.claim_id
    with pytest.raises(ml.MutationLedgerError, match="different claim"):
        ml.validate_ledger((first, cross))

    elsewhere = _wire_entry(site=MutationSite(
        subject="src/pkg/elsewhere.py", anchor="answer",
        operator=MutationOperator.BODY_TO_NO_OP))
    with pytest.raises(ml.MutationLedgerError, match="one ledger per subject"):
        ml.validate_ledger((first, elsewhere))

    duplicate = _wire_prediction()
    with pytest.raises(ml.MutationLedgerError, match="duplicate prediction"):
        ml.validate_ledger((duplicate, duplicate))

    # One ROW, two clauses: the contract's own example, and it is accepted.
    # `described` names a whole alternative body; `first` names a mutation
    # site. Nothing here is two dispositions of one sentence.
    both_kinds = _wire_prediction()
    assert both_kinds.claiming_row == first.claiming_row
    assert both_kinds.reason is NonDerivable.NO_APPLICABLE_OPERATOR
    ml.validate_ledger((first, both_kinds))

    # The hole, pinned as the MISSING KEY rather than as an acceptance: the
    # two kinds share these five field names and NO OTHER, and not one of
    # them is a clause identity. `seal_file`/`claiming_row` name the ROW, and
    # the accepted pair above is the proof that a row carries several
    # clauses; `revision`/`subject_sha256` are provenance, equal between an
    # observation and a prediction taken at the same commit and therefore
    # unable to tell one clause from two; `note` is prose no fold reads.
    #
    # Written as an exact set on purpose. Any W2-3-4 ruling that adds a
    # shared clause key reddens this line WHATEVER IT IS NAMED — `clause_id`,
    # `clause`, a reused `claim_id` — where a comparison of the two existing
    # ids could not: `ml-`/`mlp-` prefixes make those unequal under every
    # possible implementation, so such a comparison asserts nothing about
    # this module at all. The refusal the key would enable is not blocked by
    # a row demanding the pair stay accepted; it just has to arrive as a
    # visible diff here.
    shared = ({f.name for f in dataclasses.fields(LedgerEntry)}
              & {f.name for f in dataclasses.fields(ml.Prediction)})
    assert shared == {"seal_file", "claiming_row", "revision",
                      "subject_sha256", "note"}
    for name in sorted(shared):
        assert getattr(both_kinds, name) == getattr(first, name), (
            f"{name} is equal across the legitimate pair, so it cannot be "
            f"the key that separates one clause from two")


# --------------------------------------------------------------------------- #
# The harness itself. Seven of the module's declared holes had no row anywhere
# in the repository, and this is the only SEALS task in the unit — W2-3-3 and
# W2-3-5 fill bodies, W2-3-4 adjudicates — so nothing later would have closed
# them. Three are FAIL-OPEN by shape: `check_citations` returning `()` reports
# a clean tree and exits 0, `collect_rows` returning a short tuple reports a
# file that shrank, and `run_rows` omitting a row reports it ABSENT. A body
# that does nothing must not read as a body that found nothing.
#
# RED until W2-3-3, like the folds above.
# --------------------------------------------------------------------------- #

def test_the_applier_reproduces_an_independent_mutation_and_refuses_a_miss(
) -> None:
    """``apply_mutation`` against the one oracle this file already carries.

    :func:`_swallow` resolves the recorded site by :mod:`ast` without
    importing the module under seal, so it is an independent answer to "what
    does RAISE_TO_CONTINUE at ``discover_roots`` produce" — and it is the
    answer the flagship's whole measurement was taken through. If the harness
    disagrees with it, every re-derivation runs a different mutation from the
    one the ledger records, and the record's ``mutant_sha256`` names bytes
    nothing produced.

    The refusals are the other half, and the contract states them as "refuse,
    do not no-op": an anchor that does not resolve, an ``argument`` naming a
    handler that is not there, and an operator that does not fit what is at
    the anchor. A returned copy of the input reddens nothing and is recorded
    as a mutation that was survived — a false STRIKE against a true clause.

    The comparison is over PARSED TREES, not bytes. The contract for
    ``apply_mutation`` says "resolve the anchor with ``ast``, refuse rather
    than no-op" and says nothing about the emitted text; ``mutant_sha256`` is
    provenance on the observation id and no :class:`Drift` member compares
    it, so a mutation that is the same program with different whitespace
    breaks nothing in the ledger. Pinning bytes would lock the harness to the
    formatting of a private helper in this file, which is not a contract
    anyone agreed to.

    What is pinned is stronger than "something changed": the mutated tree
    equals the independently-derived one, and the ONE function whose body
    moved is the recorded anchor. An applier that produced the right bytes at
    the site while also rewriting something else would satisfy neither.

    Predicted (unmeasured) under: return ``source`` unchanged when the anchor
    does not resolve and the three refusals redden; resolve the anchor by
    line number and the first assertion reddens against a moved body; mutate
    a second handler of the same type elsewhere in the file and the
    untouched-elsewhere assertion reddens.
    """
    root = _repo_root()
    _require_revisions(root, REVISION)
    source = _at_revision(root, REVISION, SUBJECT)

    mutated = ml.apply_mutation(source, SITE)
    assert _tree(mutated) == _tree(_swallow(source, SITE)), (
        "the harness applies a different mutation from the one this file "
        "measured through, so the ledger would record bytes nothing produced")
    assert _tree(mutated) != _tree(source)
    assert ml.source_digest(mutated) != ml.source_digest(source)

    # The blast radius of the edit itself. `_bodies` is anchor -> dumped
    # body, so a mutation that also touched another function, or that
    # rewrote the whole module into something equivalent at the site, shows
    # here rather than passing the equality above.
    before, after = _bodies(source), _bodies(mutated)
    assert set(before) == set(after)
    assert {a for a in before if before[a] != after[a]} == {SITE.anchor}

    for label, site in (
            ("no such anchor",
             MutationSite(subject=SUBJECT, anchor="no_such_function",
                          operator=MutationOperator.RAISE_TO_CONTINUE,
                          argument="AnalyzerError")),
            ("no such handler",
             MutationSite(subject=SUBJECT, anchor=SITE.anchor,
                          operator=MutationOperator.RAISE_TO_CONTINUE,
                          argument="NoSuchErrorIsCaughtHere")),
            ("operator does not fit",
             MutationSite(subject=SUBJECT, anchor=SITE.anchor,
                          operator=MutationOperator.ADD_DEFAULT_BRANCH,
                          argument="None")),
    ):
        with pytest.raises(ml.MutationLedgerError):
            ml.apply_mutation(source, site)


def test_the_applier_positively_exercises_add_default_branch() -> None:
    """ADD_DEFAULT_BRANCH applied to a conditional statement that has none.

    The applier test covers RAISE_TO_CONTINUE directly and BODY_TO_NO_OP
    indirectly, but ADD_DEFAULT_BRANCH only appeared as a refused refusal at
    an anchor that was not a conditional, so an implementation that always
    refuses it would pass. This test applies the mutation where it should
    succeed and verifies the tree changed by the right amount.
    """
    source = _SUBJECT_SRC.encode()
    site = MutationSite(subject="src/subject.py", anchor="choose",
                        operator=MutationOperator.ADD_DEFAULT_BRANCH,
                        argument="None")
    mutated = ml.apply_mutation(source, site)
    assert mutated != source, (
        "the applier applied the mutation and returned something different")
    expected = _MUTANT_WITH_DEFAULT_SRC.encode()
    assert _tree(mutated) == _tree(expected), (
        "the mutated tree matches the expected mutation")
    assert ml.source_digest(mutated) != ml.source_digest(source)

    before, after = _bodies(source), _bodies(mutated)
    assert set(before) == set(after), (
        "the mutation does not introduce new functions")
    assert {a for a in before if before[a] != after[a]} == {"choose"}, (
        "the ONE function whose body moved is the anchor")


def test_the_provisioner_stands_up_the_whole_population_and_runs_it(
        tmp_path: Path) -> None:
    """``provision_subject_tree``, ``collect_rows`` and ``run_rows``, over a
    real repository with a real red row.

    These three are what turn a ledger record back into a run, and each fails
    OPEN when it is wrong: a short collection reads as a file that shrank
    (and shifts :func:`population_digest`, so the clause reports drift it
    does not have), and a row omitted from the results reads as ABSENT rather
    than as unreported. So both are asserted as WHOLE sets, not by membership.

    A runner that reported PASSED for everything would satisfy every
    membership check ever written against it, so the baseline-red row is
    pinned to FAILED by value.

    The provisioned tree is a copy: the assertion that the source repository
    still holds the unmutated bytes is what stops a provisioner that mutates
    in place from passing, which is the accident DF-4 exists for.

    ``run_rows`` is node-id level and ``collect_rows`` is function-level, and
    the tiny repo carries one parametrised row so that the difference is
    observable: a runner that folded would hide a parametrisation that never
    ran behind one that passed, and a collector that did not fold would move
    ``population_digest`` every time a case is added to a row.

    Predicted (unmeasured) under: fold parametrisations inside ``run_rows``
    and the node-id assertion reddens; return node ids from ``collect_rows``
    and the population assertion reddens; report only what pytest printed and
    the whole-set assertions redden; provision by checking out into
    ``repo_root`` and the last assertion reddens; ignore the requested
    revision and provision HEAD anyway.
    """
    repo, entry, rows, head = _tiny_repo(tmp_path)
    collected = set(rows.values())

    _git("add", "-A", cwd=repo)
    _git("-c", "user.name=seal", "-c", "user.email=seal@example.invalid",
         "commit", "-qm", "a second commit after the subject entry was created",
         cwd=repo)

    clone = ml.provision_subject_tree(str(repo), head, str(tmp_path / "dest"))
    assert ml.collect_rows(clone, _TINY_SEAL) == tuple(sorted(collected)), (
        "function-level and sorted by contract, so a re-ordering or a "
        "parametrisation cannot move population_digest")

    results = ml.run_rows(clone, _TINY_SEAL)
    assert set(results) == (collected - {rows["parametrised"]}) | {
        f"{rows['parametrised']}[a]", f"{rows['parametrised']}[b]"}, (
        "node-id level and pre-fold by contract: folding here would hide a "
        "parametrisation that never ran behind one that passed")
    assert results[rows["baseline_red"]] is RowResult.FAILED
    assert results[rows["reddens"]] is RowResult.PASSED
    assert results[rows["untouched"]] is RowResult.PASSED
    assert ml.fold_row_results(results)[rows["parametrised"]] is (
        RowResult.PASSED)

    # Provisioning adds a worktree inside `repo_root` and deletes a path in
    # it. The source tree it provisions FROM must come back untouched, or a
    # re-derivation edits the repository it is measuring. Verify that the
    # source was provisioned from the REQUESTED revision, not HEAD: the
    # repository now sits at a different commit.
    assert (repo / "src" / "subject.py").read_text() == _SUBJECT_SRC
    assert _git("status", "--porcelain", cwd=repo).stdout == b""
    current_head = _git("rev-parse", "HEAD", cwd=repo).stdout.decode().strip()
    assert current_head != head, (
        "the repository moved to a new HEAD after the entry was created; the "
        "provisioner was asked for the old one and must have honored it")
    # The entry recorded its population in the order the fixture built it and
    # the collector returns it sorted. The two agree because
    # `population_digest` sorts and de-duplicates before hashing — pinned
    # here, because if it did not, every entry in this file would be
    # comparing a digest against a different ordering of the same rows.
    assert entry.population_sha256 == ml.population_digest(
        ml.collect_rows(clone, _TINY_SEAL))
    shuffled = tuple(reversed(sorted(collected))) + (rows["untouched"],)
    assert ml.population_digest(shuffled) == entry.population_sha256


def test_a_collection_that_broke_refuses_rather_than_reporting_a_short_file(
        tmp_path: Path) -> None:
    """``collect_rows`` raises on a collection error.

    The contract states it in one line and it is the single fail-open shape
    in this module that nothing else catches: a seal file that no longer
    IMPORTS collects zero rows, which is a legal tuple. Returned, it moves
    :func:`population_digest`, so every entry against that file reports
    POPULATION drift, folds to REANCHORED or EXPIRED, and the whole file's
    coverage is quietly relabelled by an ImportError.

    Predicted (unmeasured) under: swallow the collection error and return
    what was collected, and this row reddens on both branches.
    """
    repo, _, _, head = _tiny_repo(tmp_path)
    broken = _recommit(repo, _TINY_SEAL,
                       "from subject import no_such_name  # noqa\n\n\n"
                       "def test_x():\n    assert True\n")
    assert broken != head

    clone = ml.provision_subject_tree(str(repo), broken,
                                      str(tmp_path / "broken"))
    with pytest.raises(ml.MutationLedgerError):
        ml.collect_rows(clone, _TINY_SEAL)


def test_a_run_that_did_not_complete_is_refused_and_not_reported_as_results(
        tmp_path: Path) -> None:
    """``run_rows`` on three runs that produce a well-formed result and no
    measurement.

    The contract states ``run_rows``'s fail-closed rule for one case — a row
    collected and then not reported is ABSENT, never PASSED — and is silent
    on the case that produces the SAME map for a different reason: the run
    stopped. Its signature carries no channel for "there is no measurement
    here", so refusing is the only way to say it, and these three are where
    a body that trusts pytest's exit code says the opposite:

      * the seal file no longer IMPORTS. Every recorded row comes back
        ABSENT, which folds to ``MUTANT_UNEVALUABLE`` or ``HARNESS_FAULT``
        and parks the clause on a re-run that will never collect anything.
      * a row KILLS the interpreter mid-run. ``os._exit(0)`` is the shape
        that defeats an exit-code check specifically: pytest never reaches
        its reporting hook, so the run has no results and every row is
        unreported, while the process exits 0 — "all tests passed". A body
        checking only the code accepts an empty run as a green file.
      * the file collects NOTHING. An empty map is a legal ``Mapping[str,
        RowResult]`` and reads downstream as a population that vanished.

    The healthy tree is run FIRST and in the same call, so a ``run_rows``
    that raises on everything fails here rather than passing three refusals.

    The ``os._exit`` case must be isolated in a subprocess: if ``run_rows``
    is implemented to run pytest in-process, the nested test's ``os._exit(0)``
    will terminate the seal interpreter itself before any handler can run.
    This isolation demonstrates that the requirement for a subprocess
    implementation is necessary, not just convenient.

    Predicted (unmeasured) under: return the partial map instead of raising
    and all three blocks redden; gate on pytest's exit code alone and the
    ``os._exit`` block reddens; treat "no rows" as an empty result and the
    third block reddens; refuse every run and the control block reddens;
    run the nested pytest in-process and the os._exit block kills the seal.
    """
    repo, _, rows, head = _tiny_repo(tmp_path)

    healthy = ml.provision_subject_tree(str(repo), head,
                                        str(tmp_path / "healthy"))
    assert ml.run_rows(healthy, _TINY_SEAL)[rows["untouched"]] is (
        RowResult.PASSED), "the control run is refused, so nothing below means"

    for label, source in (
            ("the seal file stops importing",
             "from subject import no_such_name  # noqa\n\n\n"
             "def test_x():\n    assert True\n"),
            ("the file collects nothing",
             "from subject import other  # noqa\n\nNOT_A_TEST = other\n"),
    ):
        revision = _recommit(repo, _TINY_SEAL, source)
        clone = ml.provision_subject_tree(
            str(repo), revision, str(tmp_path / f"dest-{revision[:8]}"))
        returned = None
        try:
            returned = ml.run_rows(clone, _TINY_SEAL)
        except ml.MutationLedgerError:
            pass
        assert returned is None, (
            f"{label}: run_rows returned {returned!r} for a run that took no "
            f"measurement")


def test_a_run_interrupted_by_os_exit_is_refused_and_isolated(
        tmp_path: Path) -> None:
    """``run_rows`` on a run where a test calls ``os._exit(0)`` mid-execution.

    This is the ``os._exit`` case from
    ``test_a_run_that_did_not_complete_is_refused_and_not_reported_as_results``,
    isolated in its own test to ensure the seal process is protected.

    If ``run_rows`` is implemented to run pytest in-process (using
    ``pytest.main()`` or similar), the nested test's ``os._exit(0)`` will
    terminate the Python interpreter immediately, bypassing any exception
    handler and killing the seal process itself. This test must run the nested
    pytest as a subprocess to prevent that termination from propagating.

    A provisioned tree with a seal file that calls ``os._exit(0)`` in a test
    must result in a refused run, not a crashed seal process.
    """
    repo, _, rows, head = _tiny_repo(tmp_path)

    source = ("import os\n\nfrom subject import other\n\n\n"
              "def test_a_reported():\n    assert other() == 7\n\n\n"
              "def test_b_kills_the_run():\n    os._exit(0)\n\n\n"
              "def test_c_never_runs():\n    assert other() == 7\n")
    revision = _recommit(repo, _TINY_SEAL, source)
    clone = ml.provision_subject_tree(
        str(repo), revision, str(tmp_path / f"dest-{revision[:8]}"))

    returned = None
    try:
        returned = ml.run_rows(clone, _TINY_SEAL)
    except ml.MutationLedgerError:
        pass

    assert returned is None, (
        "a run that did not complete (os._exit(0) mid-run): run_rows returned "
        f"{returned!r} instead of refusing")


def test_a_ledger_is_written_only_where_it_can_be_read_back_unchanged(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``write_ledger`` and ``load_ledger``, the pair that has to agree.

    A reader that drops a line it cannot parse turns a corrupted ledger into
    a smaller one, and a smaller ledger is a clause with no evidence, which
    reads as never measured. A writer that skips
    :func:`refuse_unwritable_ledger_path` puts the file where W2-3-3's role
    cannot create it, so it lands somewhere outside every reader — and a
    writer that skips :func:`validate_ledger` commits a state no reader can
    answer from.

    The round trip is asserted on the RECORDS, not on the bytes: equality of
    dataclasses is what a later re-derivation actually depends on, and both
    ids are re-derived by ``__post_init__`` on the way back in.

    A refused write is asserted on the FILE, not only on the exception. "It
    raised" is satisfied by a writer that truncates the ledger, streams the
    rival records out, validates last and then raises — the file is
    destroyed and the caller is told the write was refused, which is the
    worse of the two failures and the one an exception check cannot see. So
    each refusal below is followed by the bytes that were there before, and
    the refused PATH is checked for not having been created at all.

    Predicted (unmeasured) under: drop the ``validate_ledger`` call from
    ``write_ledger`` and the rival-entry block reddens; validate AFTER
    writing and the surviving-bytes assertions redden while the ``raises``
    blocks stay green; drop the ``refuse_unwritable_ledger_path`` call and
    the misplaced-path block reddens; skip an unparseable line instead of
    refusing the file and the last block reddens.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ml.LEDGER_DIR).mkdir(parents=True)
    path = ml.ledger_path_for(_WIRE_SITE.subject)

    first = _wire_entry()
    second = _wire_entry(observed_on="2026-08-19",
                         supersedes=first.observation_id)
    records = (first, second, _wire_prediction())
    ml.write_ledger(path, records)
    assert ml.load_ledger(path) == records
    committed = Path(path).read_bytes()

    with pytest.raises(ml.MutationLedgerError):
        ml.write_ledger("docs/other.jsonl", records)
    assert not Path("docs/other.jsonl").exists(), (
        "a path the body role cannot create was refused and written anyway")

    with pytest.raises(ml.MutationLedgerError):
        ml.write_ledger(path, (first, _wire_entry(observed_on="2026-08-19")))
    assert Path(path).read_bytes() == committed, (
        "the invalid records were committed over a valid ledger before the "
        "refusal; the exception says nothing was written and the file says "
        "otherwise")
    assert ml.load_ledger(path) == records

    # A blank line is not a record; a damaged one is not a missing one.
    Path(path).write_text(
        "\n".join((ml.canonical_line(first), "", ml.canonical_line(second)))
        + "\n")
    assert ml.load_ledger(path) == (first, second)
    Path(path).write_text(
        ml.canonical_line(first) + "\n{not json\n"
        + ml.canonical_line(second) + "\n")
    with pytest.raises(ml.MutationLedgerError):
        ml.load_ledger(path)


def test_a_citation_to_evidence_that_is_gone_is_reported_and_exits_non_zero(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``check_citations`` and the CLI verb that exits on its length.

    The fail-open one, and the loudest: a body of ``return ()`` reports every
    tree clean and every ``citations`` run exits 0 — which is exactly the
    state this whole unit exists to make impossible, a clause that cites
    evidence nobody can produce. So the first thing asserted is a DIRTY tree,
    with the id in the message; the clean tree comes second.

    Three problems are pinned, and they are the three the recorded fields can
    answer: an id that resolves to nothing, an id that resolves to a
    SUPERSEDED observation, and an ``mlo-`` observation id cited where a
    claim id belongs. The fourth in the contract — "a claim whose live
    observation does not :func:`counts_as_coverage`" — is NOT pinned here: a
    W2-3-1 panel finding is that no stored record carries a
    :class:`Status`, so that predicate is not computable from a ledger file
    and W2-3-4 owns what replaces it. Sealing it to a guess would fix the
    wrong answer in place.

    ``main(("citations",))`` reads the tree from the process CWD. The
    contract names three verbs and says nothing about where the tree comes
    from, so something has to fix it and this row does — in the direction
    that invents no argument. An optional path argument defaulting to the CWD
    keeps this green; only a MANDATORY one reddens it, and a verb whose
    helper takes ``repo_root`` should not require the caller to say twice
    where they already are.

    The LEDGER FILES are not citations to themselves. A record naming its
    own ids is the evidence; a check that grepped them as citations would
    report every superseded entry in every ledger and no tree could ever be
    clean, so the clean-tree assertion below fails a body that scans
    :data:`LEDGER_DIR`. That is stated here because the contract says "every
    ledger citation in the TREE" and leaves it open.

    Predicted (unmeasured) under: return ``()`` unconditionally and every
    dirty block reddens; report the count instead of the id and the message
    assertions redden; exit 0 on a non-empty result and the ``main`` block
    reddens; grep the ledger directory too and the clean-tree assertion
    reddens.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ml.LEDGER_DIR).mkdir(parents=True)
    (tmp_path / "tests").mkdir()

    superseded = _wire_entry(observed_on="2026-08-01")
    live_over = _wire_entry(observed_on="2026-08-19",
                            supersedes=superseded.observation_id)
    # Written with `canonical_line`, not `write_ledger`: the writer is a
    # separate hole, and a row that needed it would redden for its reasons
    # rather than for the citation check's.
    (tmp_path / ml.ledger_path_for(_WIRE_SITE.subject)).write_text(
        "".join(ml.canonical_line(r) + "\n" for r in (superseded, live_over)))

    def cite(clause: str) -> None:
        """Put ``clause`` on :data:`_WIRE_ROW`, where a citation lives."""
        (tmp_path / _WIRE_SEAL).write_text(
            f'def test_row():\n    """{clause}"""\n')

    dangling = ml.CLAIM_ID_PREFIX + "0" * 12
    for label, cited in (("unresolved", dangling),
                         ("superseded", superseded.observation_id),
                         ("an observation id where a claim id belongs",
                          live_over.observation_id)):
        cite(f"Reddens under a body on: swallowing it ({cited}).")
        problems = ml.check_citations(str(tmp_path))
        assert problems, label
        assert any(cited in line for line in problems), label
        assert ml.main(("citations",)) != 0, label

    cite(f"Reddens under a body on: swallowing it ({live_over.claim_id}).")
    assert ml.check_citations(str(tmp_path)) == ()
    assert ml.main(("citations",)) == 0

    # A verb the CLI does not have is not a clean tree.
    assert ml.main(("no-such-verb",)) != 0
