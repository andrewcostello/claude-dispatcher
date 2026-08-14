r"""DF-1 seals (P2) — a merge record that cannot be checked against origin is red.

Written against ``src/claude_dispatcher/merge_record.py`` at ``60789ab`` by an
author who did not write the scaffold (DF-1-1) and will not write the bodies
(DF-1-3). The condemned seal this file must not twin —
``tests/test_merge_engine.py:313``, ``assert merged[0].payload
["feature_branch_sha"]``, truthiness of a value measured wrong seven times —
is DF-1-4's to amend or strike (its ``disputed_paths`` claims that file); no
row here touches it, and no row here repeats its shape: **no assertion in this
file is a truthiness check over a recorded SHA.** Every observed value is
judged by equality against an origin-derived expectation produced in the same
call, and every absence is judged as key-absence beside a same-call presence
control.

Measured under: ``60789ab`` (``feat/DF-1-2-seals-a-merge-record-that``),
git 2.51.0, CPython 3.13.7, gh 2.46.0, 2026-08-13, in throwaway repositories
under pytest ``tmp_path``, unless a line says ``Predicted (unmeasured)
under:``. Two citations used below, re-measured for this file rather than
carried from the scaffold:

  * ``git fetch origin feature/x:feature/x`` from a worktree where
    ``feature/x`` is checked out exits 128 with ``refusing to fetch into
    branch`` and leaves the local ref untouched — re-measured LIVE inside
    :func:`test_two_prs_merged_in_one_run_cannot_record_the_same_post_merge_sha`
    on every suite run, as that row's mechanism control.
  * ``mergeCommit`` is a real ``gh pr view --json`` field name — Measured
    under: gh 2.46.0 (the field list gh prints on an unknown ``--json`` field
    names it). The VALUE shape ``{"mergeCommit": {"oid": <sha>}}`` is
    Predicted (unmeasured) under: gh 2.46.0 — reading it needs a live GitHub
    PR; the fake-gh harness below emulates that documented shape, and DF-1-3
    measures against a real run. The witness's TIMEOUT failure is likewise
    Predicted (unmeasured): sealing it needs a hanging gh plus the body's
    chosen bound, and a sleep-based row would buy that seal with suite
    wall-clock; DF-1-3 must demonstrate it instead.

HOW THE RED ROWS ARE COMMITTED RED (the DF-4-2 precedent, kept deliberately)
============================================================================
``witness_merged_sha`` is the P1 stub and the call-site rewiring is DF-1-3's,
so the rows below that drive them CANNOT pass at HEAD. They are committed as

    ``xfail(condition=<the seam still raises the P1 stub>,
            raises=<the row's one tolerated exception>, strict=True)``

not as plain red, for the reasons DF-4-2 recorded and this run re-confirmed:
``.dispatcher.yaml``'s test gate runs the whole suite with exit 0 = green and
has no seals-role carve-out, so plain red blocks this branch and poisons every
concurrent unit's whole-suite baseline; and BODIES is denied ``tests/**``, so
no marker requiring a later human edit could ever be removed — the condition
is computed by probing the seam, and the marker retires ITSELF the commit the
body lands, with no test edit and no silent XPASS (``strict=True``).

``raises=`` pins the ONE tolerated failure per row: ``NotImplementedError``
(the stub's raise) for the rows that call the seam directly, and
``AssertionError`` (the contract assertions) for the engine-level row, whose
in-call controls therefore use ``pytest.fail`` — ``Failed`` is not an
``AssertionError``, so a broken control reports as a real suite failure today,
never as an expected red. In the direct-call rows the controls are plain
asserts for the mirrored reason: an ``AssertionError`` there is not the
tolerated ``NotImplementedError`` and also reports today.

The panel row (added under the operator adjudication of 2026-08-14, which
sanctioned this one extension) retires the same way but off its OWN probe:
its condition is "``__post_init__`` still accepts a non-SHA", not "the seam
is still the stub" — its defect is in the IMPLEMENTED record type, not the
stub — so it xfails while the DF-1-1 panel's truthy-sha hole stands and runs
plain (and must pass) the commit a guard lands, with no test edit.

NON-VACUITY LEDGER (each row names its defect and its same-call control)
========================================================================
Red rows, each red at HEAD by the specific defect it names:

  * the engine row — red because both YAML rows record the SAME
    ``merged_sha`` (the frozen local tip) and neither journal payload carries
    the contract keys. Controls in the same call: origin really created two
    DISTINCT merge commits (receipts cross-checked against ``git cat-file``
    in origin), the freeze mechanism is re-measured live (fetch exits
    non-zero, ``refusing to fetch``, ref unmoved), and while the seam is
    still the stub the red is verified to be by the named defect — both
    records sharing exactly the frozen tip — not by a harness accident.
  * the relay row — red at the stub raise, after its control proved the
    fake gh answers the documented argv with the expected oid.
  * the wrong-question row — red at the stub raise, after its control proved
    origin's branch tip is readable from ``cwd`` and differs from the merge
    commit, so the temptation is reachable and distinguishable.
  * the gh-missing row — red at the stub raise, after its controls proved the
    binary is really absent (exec raises ``FileNotFoundError``) and the local
    ref is really readable (the temptation exists).
  * the four not-an-answer rows — red at the stub raise, after each control
    ran the fake gh directly and confirmed the advertised failure shape
    (exit 0 with no field / null field / exit 1 / an oid that is not a SHA).
  * the panel row — red because ``__post_init__`` judges ``not self.sha``
    (truthiness) only — the DF-1-1 review panel's three-family finding — so
    ``"not-a-sha"`` and whitespace wear the OBSERVED state and the stamp
    emits them under ``merged_sha``. Controls in the same call: the legal
    40-hex shape constructs and stamps exactly its answer, and while the
    hole stands the red is verified to be by the named defect (the garbage
    value really reaches the stamp), not a harness accident.

Green rows (the P1-implemented record type and stamp fold), each
mutation-verified in a ``/tmp`` lab under 60789ab — the mutations and which
row kills each are named in the row docstrings:

  * observed-shape unconstructibility; unavailable-shape unconstructibility
    (kill: ``__post_init__`` body replaced with ``pass``);
  * the observed stamp's exact key shape; the unavailable stamp's key-absence
    (kill: ``stamp_fields`` returning ``{}``; and separately, the unavailable
    branch emitting ``"merged_sha": None``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import merge_engine as me
from claude_dispatcher import merge_record as mr
from claude_dispatcher import notify as notify_mod
from claude_dispatcher import yaml_io
from claude_dispatcher.merge_record import (
    MergedShaWitness,
    ShaSource,
    WitnessState,
    witness_merged_sha,
)

_HEX40 = re.compile(r"[0-9a-f]{40}")


# --------------------------------------------------------------------------- #
# The self-retiring stub probe
# --------------------------------------------------------------------------- #

def _seam_is_still_the_stub() -> bool:
    """Does ``witness_merged_sha`` still raise the P1 stub?

    Probed by calling it with a gh that cannot exist. While the stub stands
    this raises ``NotImplementedError`` before touching anything. The moment
    DF-1-3 lands the body, the same call exercises the TOTAL contract's
    cheapest failure leg (gh missing → an UNAVAILABLE witness, no subprocess
    beyond one failed exec, no network) and returns — so the probe flips to
    False on its own and every ``xfail`` below retires without a test edit.
    Any OTHER exception is treated as not-the-stub, so a partially-landed body
    that crashes runs the rows plain and fails them loudly rather than
    xfailing forever.
    """
    try:
        witness_merged_sha(
            cwd=Path(__file__).parent,
            pr_number=0,
            target="feature/x",
            gh_bin=str(Path(__file__).parent / "no-such-gh-binary"),
        )
    except NotImplementedError:
        return True
    except Exception:
        return False
    return False


_STUB = _seam_is_still_the_stub()

_RED = "DF-1 P1 stub still in place: witness_merged_sha raises and the engine still stamps the frozen local tip; DF-1-3 turns this row green"


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #

def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True,
        text=True, timeout=60,
    ).stdout.strip()


def _init_repo(path: Path, *, branch: str = "main") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", branch, ".")
    _git(path, "config", "user.email", "seal@example.invalid")
    _git(path, "config", "user.name", "seal")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _answering_gh(path: Path, *, oid: str) -> Path:
    """A gh that answers ``pr view <n> --json mergeCommit`` with ``oid``.

    Emits the documented value shape (Predicted (unmeasured) under gh 2.46.0,
    see module docstring) and nothing else; any other invocation exits 0 with
    empty output so an over-curious body gets no accidental data from it.
    """
    return _script(path, f'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if "view" in args and "mergeCommit" in args:
    print(json.dumps({{"mergeCommit": {{"oid": "{oid}"}}}}))
sys.exit(0)
''')


#: The fake gh for the engine row. ``pr merge <n>`` REALLY merges the PR's
#: branch into the feature branch inside the ORIGIN repository (--no-ff, so a
#: merge commit exists per PR) and writes the resulting SHA to a receipts
#: file; ``pr view <n> --json mergeCommit`` answers from the receipts —
#: GitHub's own record of the merge, emulated. ``pr view ... --json reviews``
#: answers no-reviews so the engine's low-risk self-approval path is
#: undisturbed.
_MERGING_GH = '''#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[1:]
origin = os.environ["FAKE_GH_ORIGIN"]
receipts_path = os.environ["FAKE_GH_RECEIPTS"]
branches = json.loads(os.environ["FAKE_GH_BRANCHES"])

def _num():
    for a in args:
        if a.isdigit():
            return a
    return ""

def _receipts():
    try:
        with open(receipts_path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}

if "view" in args and "reviews" in args:
    print(json.dumps({"reviews": []}))
    sys.exit(0)
if "view" in args and "mergeCommit" in args:
    sha = _receipts().get(_num())
    print(json.dumps({"mergeCommit": ({"oid": sha} if sha else None)}))
    sys.exit(0)
if "merge" in args:
    num = _num()
    branch = branches[num]
    proc = subprocess.run(
        ["git", "-C", origin, "merge", "--no-ff", "-m",
         "Merge pull request #%s from %s" % (num, branch), branch],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(1)
    head = subprocess.run(
        ["git", "-C", origin, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    receipts = _receipts()
    receipts[num] = head
    with open(receipts_path, "w", encoding="utf-8") as fh:
        json.dump(receipts, fh)
    sys.exit(0)
sys.exit(0)
'''


def _pr_row(key: str, *, pr_number: int, branch: str) -> dict:
    return {
        "key": key,
        "summary": f"summary {key}",
        "description": f"desc {key}",
        "type": "Task",
        "labels": ["size:S", "area:x"],
        "status": "Awaiting Review",
        "branch": branch,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/test/repo/pull/{pr_number}",
        "verified": True,
        "verification_iterations": 0,
    }


def _feature_branch_off(repo: Path, branch: str, filename: str) -> None:
    """One commit on ``branch`` off ``feature/x``, via a temp worktree so the
    repo's own checkout (feature/x — the pr-mode configuration under seal)
    never moves."""
    wt = repo.parent / f"wt-{branch}"
    _git(repo, "worktree", "add", "-q", "-b", branch, str(wt), "feature/x")
    (wt / filename).write_text("x = 1\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", f"work on {branch}")
    _git(repo, "worktree", "remove", "--force", str(wt))


# --------------------------------------------------------------------------- #
# Green rows — the P1-implemented record type
# --------------------------------------------------------------------------- #

def test_an_observed_witness_without_its_answer_is_unconstructible() -> None:
    """Question 3's structural half: OBSERVED cannot exist without a SHA and a
    named source, so a stale stamp cannot wear the success state.

    Control, judged first in the same call: the LEGAL observed shape
    constructs — so the three refusals below are refusals of the illegal
    shapes, not a constructor that rejects everything.

    Mutation-verified (lab under 60789ab): ``__post_init__`` body replaced
    with ``pass`` → the three ``pytest.raises`` blocks fail. Not a twin of
    the condemned seal: nothing here asserts truthiness of a recorded value.
    """
    sha = "ab" * 20
    legal = MergedShaWitness(
        pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
        sha=sha, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
    )
    assert legal.sha == sha  # control: the legal shape holds its answer

    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
            sha=None, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
        )
    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
            sha="", source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
        )
    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
            sha=sha, source=None,
        )


def test_an_unavailable_witness_cannot_smuggle_a_value_or_leave_absence_unexplained() -> None:
    """Question 3's other half: UNAVAILABLE cannot carry a value from anywhere
    (a smuggled SHA is the silently stale stamp wearing a failure label) and
    cannot omit its reason (an unexplained absence is not checkable).

    Control, judged first: the legal unavailable shape constructs, and its
    ``sha`` really is None — so the refusals below are about the smuggling,
    not about UNAVAILABLE being unconstructible outright.

    Mutation-verified (lab under 60789ab): ``__post_init__`` → ``pass`` →
    all three ``pytest.raises`` blocks fail.
    """
    legal = MergedShaWitness(
        pr_number=7, target="feature/x", state=WitnessState.UNAVAILABLE,
        detail="gh binary not found",
    )
    assert legal.sha is None and legal.source is None  # control

    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.UNAVAILABLE,
            sha="ab" * 20, detail="gh timed out",
        )
    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.UNAVAILABLE,
            source=ShaSource.ORIGIN_PR_MERGE_COMMIT, detail="gh timed out",
        )
    with pytest.raises(ValueError):
        MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.UNAVAILABLE,
            detail="",
        )


def test_the_observed_stamp_is_exactly_the_contracted_key_shape() -> None:
    """Question 2: the stamp fold fixes the YAML/journal key names NOW, so
    these seals and DF-1-3's body write against the same shape. Judged by
    equality of the WHOLE dict — a row that only probed one key would stay
    green while the fold grew or lost keys.

    ``feature_branch_sha`` must not be among the keys: the retired key must
    not survive under the new fold in either state.

    Mutation-verified (lab under 60789ab): ``stamp_fields`` → ``return {}``
    → the equality fails.
    """
    sha = "cd" * 20
    stamp = MergedShaWitness(
        pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
        sha=sha, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
    ).stamp_fields()
    assert stamp == {
        "merged_sha": sha,
        "merged_sha_source": "origin_pr_merge_commit",
        "merged_sha_state": "observed",
    }
    assert "feature_branch_sha" not in stamp


def test_the_unavailable_stamp_has_no_merged_sha_key_for_truthiness_to_pass_on() -> None:
    """Question 3's stamp half, and the anti-twin of the condemned seal: an
    unavailable witness contributes NO ``merged_sha`` key at all, so the
    ``assert payload["merged_sha"]`` shape of check cannot even be written
    against it — it KeyErrors rather than passing on a smuggled value.

    Control, judged in the same call: the observed twin's stamp DOES carry the
    key — so the absence below is a decision of the fold, not a fold that
    emits nothing (that vacuous twin is also killed by the exact-dict
    equality).

    Mutation-verified (lab under 60789ab): ``stamp_fields`` → ``return {}``
    → the exact-dict equality fails; unavailable branch emitting
    ``"merged_sha": None`` → the key-absence assert fails.
    """
    observed_twin = MergedShaWitness(
        pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
        sha="ef" * 20, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
    ).stamp_fields()
    assert "merged_sha" in observed_twin  # control: presence is expressible

    stamp = MergedShaWitness(
        pr_number=9, target="feature/x", state=WitnessState.UNAVAILABLE,
        detail="no mergeCommit in gh answer",
    ).stamp_fields()
    assert stamp == {
        "merged_sha_state": "unavailable",
        "merged_sha_detail": "no mergeCommit in gh answer",
    }
    assert "merged_sha" not in stamp
    assert "feature_branch_sha" not in stamp
    with pytest.raises(KeyError):
        stamp["merged_sha"]


# --------------------------------------------------------------------------- #
# The panel row — red at HEAD by the DF-1-1 review panel's finding
# --------------------------------------------------------------------------- #

def _observed_still_accepts_a_non_sha() -> bool:
    """Does ``__post_init__`` still accept any truthy ``sha`` for OBSERVED?

    The DF-1-1 panel's hole, probed directly: while it stands, constructing
    OBSERVED around ``"not-a-sha"`` succeeds and this returns True. The
    commit a guard lands, the same construction raises ``ValueError`` — the
    type's one refusal exception — the probe flips to False on its own, and
    the panel row below runs plain and must pass. Any OTHER exception is
    treated as not-the-hole, so a guard with the wrong shape runs the row
    plain and fails it loudly rather than xfailing forever.
    """
    try:
        MergedShaWitness(
            pr_number=0, target="feature/x", state=WitnessState.OBSERVED,
            sha="not-a-sha", source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
        )
    except ValueError:
        return False
    except Exception:
        return False
    return True


_TRUTHY_HOLE = _observed_still_accepts_a_non_sha()

_RED_HOLE = (
    "DF-1-1 panel finding (one defect, three reviewer families): "
    "__post_init__ accepts any truthy sha, so a non-SHA wears the OBSERVED "
    "state; the guard that closes it turns this row green"
)


@pytest.mark.xfail(_TRUTHY_HOLE, reason=_RED_HOLE, raises=AssertionError,
                   strict=True)
def test_an_observed_witness_refuses_an_answer_that_is_not_a_sha() -> None:
    """Question 2's missing structural half: OBSERVED must be unconstructible
    around a value no auditor can re-ask origin about — ``"not-a-sha"`` and
    whitespace must refuse to construct, exactly as OBSERVED-without-a-sha
    already does.

    Added under the operator adjudication of 2026-08-14, which sanctioned
    this one extension: DF-1-1's review panel recorded this hole three times
    independently (codex HIGH at merge_record.py:205, claude MEDIUM at :214
    "verified by direct execution", grok LOW at :218) — ``__post_init__``
    judges ``not self.sha`` (truthiness) only. The seam-level near-twin above
    (the ``not-a-sha`` case) constrains only ``witness_merged_sha``'s answer;
    once DF-1-3 validates inside the seam that row goes green while the TYPE
    still accepts garbage from any other caller. This row pins the type — the
    audit record for merge authority itself.

    RED AT HEAD by that finding. Measured under: 0a6ae4a (this branch),
    CPython 3.13.7, 2026-08-14: both values below constructed as well-formed
    OBSERVED witnesses and ``stamp_fields()`` emitted each under
    ``merged_sha``.

    Controls (``pytest.fail``, never the tolerated ``AssertionError``),
    judged in the same call: the legal 40-hex shape constructs and its stamp
    carries exactly its answer — so the refusals below are refusals of the
    illegal values, not a constructor that rejects everything; and while the
    hole stands, the red is verified to be by the named defect — the non-SHA
    really reaches the stamp under ``merged_sha`` — not a harness accident.

    Not a twin of the condemned seal: the judgments are constructibility
    refusals and same-call equality; nothing asserts truthiness of a recorded
    value. Wider well-formedness (uppercase hex, abbreviated SHAs) is
    deliberately not pinned — the panel named this hole and this row pins
    exactly it; tightening further is the guard author's choice to propose.
    """
    sha = "ab" * 20
    try:
        legal = MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
            sha=sha, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
        )
    except ValueError:
        pytest.fail("CONTROL: the legal 40-hex observed shape must construct")
    if legal.stamp_fields().get("merged_sha") != sha:
        pytest.fail("CONTROL: the legal stamp must carry exactly its answer")

    if _TRUTHY_HOLE:
        # While the hole stands the red below must be by the NAMED defect:
        # the non-SHA constructs AND the stamp emits it under merged_sha.
        smuggled = MergedShaWitness(
            pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
            sha="not-a-sha", source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
        ).stamp_fields()
        if smuggled.get("merged_sha") != "not-a-sha":
            pytest.fail(
                "CONTROL: red for the wrong reason — the truthy-sha hole "
                f"did not reach the stamp (stamp: {smuggled!r})")

    for bad in ("not-a-sha", "   "):
        constructed = None
        try:
            constructed = MergedShaWitness(
                pr_number=7, target="feature/x", state=WitnessState.OBSERVED,
                sha=bad, source=ShaSource.ORIGIN_PR_MERGE_COMMIT,
            )
        except ValueError:
            pass
        assert constructed is None, (
            f"OBSERVED accepted {bad!r} as its answer — __post_init__ judges "
            "truthiness only, so a value no auditor can re-ask origin about "
            "wears the success state and the stamp emits it under merged_sha")


# --------------------------------------------------------------------------- #
# THE ROW THAT MATTERS — red at HEAD by the measured defect itself
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_STUB, reason=_RED, raises=AssertionError, strict=True)
def test_two_prs_merged_in_one_run_cannot_record_the_same_post_merge_sha(
    tmp_path: Path, monkeypatch,
) -> None:
    """Two PRs merged in one ``merge_pass``, in the pr-mode configuration
    (the feature branch checked out at ``repo_root``, a real origin the
    merges actually land on), must record DISTINCT ``merged_sha`` values —
    each equal to origin's merge commit for THAT PR, with the provenance and
    state keys the contract fixes, and with ``feature_branch_sha`` retired
    from the journal payload.

    RED AT HEAD by the named defect: the engine stamps
    ``_feature_branch_sha`` — the frozen local tip — so both YAML rows
    record the SAME ``merged_sha`` and the first contract assert below fails
    on exactly the many-merges-one-SHA shape measured seven times in the run
    journals. Controls (``pytest.fail``, never the tolerated
    ``AssertionError``) judged in the same call:

      * origin really created two DISTINCT merge commits (receipts written by
        the merging fake gh, cross-checked against ``git cat-file`` in
        origin) — so distinctness is available to be recorded;
      * the freeze mechanism is re-measured live: ``git fetch origin
        feature/x:feature/x`` from ``repo_root`` exits non-zero with
        ``refusing to fetch`` and the local ref has not moved (Measured
        under: 60789ab, git 2.51.0 — the scaffold's exit-128 citation,
        re-observed here on every suite run);
      * while the seam is still the stub, the red must be by the named
        defect: both rows and both payloads carry exactly the frozen tip —
        any other red is a harness accident and fails the row today.
    """
    # -- a real origin, merged on for real, and a pr-mode clone -------------
    origin = _init_repo(tmp_path / "origin")
    _git(origin, "checkout", "-q", "-b", "feature/x")
    repo = tmp_path / "repo_root"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(repo)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    _git(repo, "config", "user.email", "seal@example.invalid")
    _git(repo, "config", "user.name", "seal")
    _git(repo, "checkout", "-q", "feature/x")  # pr-mode: fb IS the checkout
    _feature_branch_off(repo, "feat-a", "a.py")
    _feature_branch_off(repo, "feat-b", "b.py")
    _git(repo, "push", "-q", "origin", "feat-a", "feat-b")

    gh = _script(repo / "fake_gh.py", _MERGING_GH)
    receipts_path = tmp_path / "receipts.json"
    monkeypatch.setenv("FAKE_GH_ORIGIN", str(origin))
    monkeypatch.setenv("FAKE_GH_RECEIPTS", str(receipts_path))
    monkeypatch.setenv(
        "FAKE_GH_BRANCHES", json.dumps({"1": "feat-a", "2": "feat-b"}))

    tasks = repo / "tasks.yaml"
    yaml_io.dump({"project": "T", "epic": "X", "tasks": [
        _pr_row("A", pr_number=1, branch="feat-a"),
        _pr_row("B", pr_number=2, branch="feat-b"),
    ]}, tasks)
    jpath = repo / "journal.jsonl"
    journal = journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo,
        run_id="run-df1")
    cfg = me.MergeEngineConfig(
        tasks_path=tasks, repo_root=repo, feature_branch="feature/x",
        gh_bin=str(gh), run_id="run-df1")

    frozen_before = _git(repo, "rev-parse", "feature/x")
    result = me.merge_pass(cfg, journal=journal,
                           notifier=notify_mod.NullNotifier())

    # -- controls: pytest.fail, so a broken control is never the expected red
    if result.merged != ["A", "B"]:
        pytest.fail(f"CONTROL: both PRs must merge in this one pass; "
                    f"merged={result.merged!r} errors={result.errors!r}")
    receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
    origin_a, origin_b = receipts.get("1"), receipts.get("2")
    if not origin_a or not origin_b or origin_a == origin_b:
        pytest.fail(
            "CONTROL: origin must hold two DISTINCT merge commits for the "
            f"two PRs, else distinctness is not recordable: {receipts!r}")
    for sha in (origin_a, origin_b):
        if _git(origin, "cat-file", "-t", sha) != "commit":
            pytest.fail(f"CONTROL: receipt {sha!r} is not a commit origin knows")
    probe = subprocess.run(
        ["git", "fetch", "origin", "feature/x:feature/x"], cwd=str(repo),
        capture_output=True, text=True, timeout=60,
    )
    if probe.returncode == 0 or "refusing to fetch" not in probe.stderr:
        pytest.fail(
            "CONTROL: the measured freeze mechanism is gone — the checked-out "
            f"fetch was not refused (rc={probe.returncode}, "
            f"stderr={probe.stderr.strip()[:200]!r}); these seals need "
            "re-measurement before they can accuse the stamp")
    frozen = _git(repo, "rev-parse", "feature/x")
    if frozen != frozen_before:
        pytest.fail("CONTROL: the local feature ref moved; the frozen-tip "
                    "premise of this row's red does not hold in this harness")

    doc = yaml_io.load(tasks)
    row_a = next(t for t in doc["tasks"] if t["key"] == "A")
    row_b = next(t for t in doc["tasks"] if t["key"] == "B")
    merged_events = {
        e.task_key: e.payload
        for e in journal_mod.read_events(jpath)
        if e.event_type == journal_mod.EventType.pr_merged
    }
    if set(merged_events) != {"A", "B"}:
        pytest.fail(f"CONTROL: expected pr_merged for A and B, "
                    f"got {sorted(merged_events)!r}")
    pay_a, pay_b = merged_events["A"], merged_events["B"]

    if _STUB:
        # While the seam is the stub the red below must be by the NAMED
        # defect — both records sharing exactly the frozen local tip — not
        # some other accident of this harness.
        if not (row_a.get("merged_sha") == row_b.get("merged_sha") == frozen
                and pay_a.get("feature_branch_sha") == frozen
                and pay_b.get("feature_branch_sha") == frozen):
            pytest.fail(
                "CONTROL: red for the wrong reason — the engine did not "
                "exhibit the measured frozen-tip stamp this row is written "
                f"against (rows: {row_a.get('merged_sha')!r}/"
                f"{row_b.get('merged_sha')!r}, frozen {frozen!r})")

    # -- the contract (the red): distinct, origin's own, named, retired -----
    assert row_a.get("merged_sha") != row_b.get("merged_sha"), (
        "two PRs merged in one run recorded the SAME post-merge SHA — the "
        "measured defect: the stamp reads a frozen local tip, not origin's "
        "record of each merge")
    assert row_a.get("merged_sha") == origin_a
    assert row_b.get("merged_sha") == origin_b
    for row in (row_a, row_b):
        assert row.get("merged_sha_source") == "origin_pr_merge_commit"
        assert row.get("merged_sha_state") == "observed"
    for pay, want in ((pay_a, origin_a), (pay_b, origin_b)):
        assert pay.get("merged_sha") == want
        assert pay.get("merged_sha_source") == "origin_pr_merge_commit"
        assert pay.get("merged_sha_state") == "observed"
        assert "feature_branch_sha" not in pay


# --------------------------------------------------------------------------- #
# Red rows driving witness_merged_sha — red at the stub raise
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_STUB, reason=_RED, raises=NotImplementedError, strict=True)
def test_the_witness_relays_origins_answer_for_the_pr_it_was_asked_about(
    tmp_path: Path,
) -> None:
    """Question 1's positive leg: the witness names the merge commit origin
    reports for THIS pr_number — observed state, the one named source, and
    the question's identifiers carried so an auditor can re-ask it.

    Control, judged first in the same call (plain asserts — ``AssertionError``
    is NOT this row's tolerated exception, so a control break fails today):
    the fake gh, invoked with the documented argv
    (``pr view 7 --json mergeCommit``), answers exactly the expected oid —
    proving the harness answers before the seam is asked to relay it.
    """
    oid = "0d" * 20
    gh = _answering_gh(tmp_path / "gh.py", oid=oid)
    probe = subprocess.run(
        [str(gh), "pr", "view", "7", "--json", "mergeCommit"],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0  # control: the harness answers
    assert json.loads(probe.stdout)["mergeCommit"]["oid"] == oid  # control

    w = witness_merged_sha(
        cwd=tmp_path, pr_number=7, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.OBSERVED
    assert w.sha == oid
    assert w.source is ShaSource.ORIGIN_PR_MERGE_COMMIT
    assert (w.pr_number, w.target) == (7, "feature/x")
    assert w.stamp_fields() == {
        "merged_sha": oid,
        "merged_sha_source": "origin_pr_merge_commit",
        "merged_sha_state": "observed",
    }


@pytest.mark.xfail(_STUB, reason=_RED, raises=NotImplementedError, strict=True)
def test_origins_branch_tip_is_not_the_question_the_witness_answers(
    tmp_path: Path,
) -> None:
    """Question 1's rejected source #2: origin's BRANCH TIP races — two
    truthful records can share it, which is the measured defect's shape — so
    the witness must name the per-PR merge commit even when the tip has moved
    past it.

    Control, judged first: from ``cwd``, ``git ls-remote origin`` really
    answers the tip, and the tip really differs from the merge commit gh
    reports — the wrong answer is reachable AND distinguishable, so relaying
    the right one is a decision, not an accident.
    """
    origin = _init_repo(tmp_path / "origin", branch="feature/x")
    merge_commit = _git(origin, "rev-parse", "HEAD")
    (origin / "later.txt").write_text("tip moved\n", encoding="utf-8")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "a sibling merge moved the tip")
    tip = _git(origin, "rev-parse", "HEAD")

    cwd = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(cwd)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    remote_tip = _git(
        cwd, "ls-remote", "origin", "refs/heads/feature/x").split()[0]
    assert remote_tip == tip  # control: the racing answer is reachable
    assert tip != merge_commit  # control: ...and distinguishable

    gh = _answering_gh(tmp_path / "gh.py", oid=merge_commit)
    w = witness_merged_sha(
        cwd=cwd, pr_number=4, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.OBSERVED
    assert w.sha == merge_commit
    assert w.sha != tip
    assert tip not in w.stamp_fields().values()


@pytest.mark.xfail(_STUB, reason=_RED, raises=NotImplementedError, strict=True)
def test_a_gh_that_cannot_run_is_a_named_absence_not_a_raise_and_not_a_local_read(
    tmp_path: Path,
) -> None:
    """Question 3, and the TOTAL contract: gh missing → the call RETURNS an
    UNAVAILABLE witness whose detail says why. It does not raise (the merge
    already landed on origin; an exception here strands a merged row), and it
    does not fall back to the local ref — the frozen tip must appear nowhere
    in the record.

    Controls, judged first: the gh path really does not exist and executing
    it really raises ``FileNotFoundError`` (the failure is the advertised
    one); and the local feature-branch tip really is readable from ``cwd``
    (the temptation exists — a body that reached for it would have found a
    value to smuggle).
    """
    repo = _init_repo(tmp_path / "repo", branch="feature/x")
    local_tip = _git(repo, "rev-parse", "feature/x")
    assert _HEX40.fullmatch(local_tip)  # control: the temptation is readable

    gh = tmp_path / "no-such-gh"
    assert not gh.exists()  # control
    with pytest.raises(FileNotFoundError):  # control: the advertised failure
        subprocess.run([str(gh), "pr", "view", "7", "--json", "mergeCommit"],
                       capture_output=True, timeout=30)

    w = witness_merged_sha(
        cwd=repo, pr_number=7, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.UNAVAILABLE
    assert w.sha is None and w.source is None
    assert w.detail  # non-empty; the wording is the body's, not this seal's
    stamp = w.stamp_fields()
    assert "merged_sha" not in stamp
    assert stamp["merged_sha_state"] == "unavailable"
    assert local_tip not in stamp.values()


@pytest.mark.xfail(_STUB, reason=_RED, raises=NotImplementedError, strict=True)
@pytest.mark.parametrize(
    ("case", "script", "advertised"),
    [
        pytest.param(
            "field-missing",
            '#!/usr/bin/env python3\nprint("{}")\n',
            "exit 0, valid JSON, no mergeCommit key",
            id="field-missing",
        ),
        pytest.param(
            "field-null",
            '#!/usr/bin/env python3\nprint(\'{"mergeCommit": null}\')\n',
            "exit 0, mergeCommit present but null (gh's shape for an "
            "unmerged PR)",
            id="field-null",
        ),
        pytest.param(
            "non-zero-exit",
            '#!/usr/bin/env python3\nimport sys\n'
            'sys.stderr.write("HTTP 502: upstream error\\n")\nsys.exit(1)\n',
            "exit 1 with stderr",
            id="non-zero-exit",
        ),
        pytest.param(
            "not-a-sha",
            '#!/usr/bin/env python3\nprint(\'{"mergeCommit": '
            '{"oid": "merge-commit-is-not-a-sha"}}\')\n',
            "exit 0, an oid that is not 40 hex characters",
            id="not-a-sha",
        ),
    ],
)
def test_an_answer_that_is_not_an_answer_is_unavailable_with_the_partiality_named(
    tmp_path: Path, case: str, script: str, advertised: str,
) -> None:
    """Question 3's enumerated failure legs, one red row each: an answer
    without the field, gh's null for the field, a non-zero exit, and an oid
    that is not a SHA all return WitnessState.UNAVAILABLE with a non-empty
    detail — never a raise, never a value under ``merged_sha``, never another
    source consulted.

    Control, judged first in each call: the fake gh is run DIRECTLY and its
    output confirmed to be the advertised failure shape — so the row is red
    for its own leg, not for a broken script.
    """
    gh = _script(tmp_path / f"gh-{case}.py", script)
    probe = subprocess.run(
        [str(gh), "pr", "view", "7", "--json", "mergeCommit"],
        capture_output=True, text=True, timeout=30,
    )
    # control: the advertised shape, per case
    if case == "field-missing":
        assert probe.returncode == 0
        assert "mergeCommit" not in json.loads(probe.stdout)
    elif case == "field-null":
        assert probe.returncode == 0
        assert json.loads(probe.stdout)["mergeCommit"] is None
    elif case == "non-zero-exit":
        assert probe.returncode == 1
    else:
        oid = json.loads(probe.stdout)["mergeCommit"]["oid"]
        assert not _HEX40.fullmatch(oid)

    w = witness_merged_sha(
        cwd=tmp_path, pr_number=7, target="feature/x", gh_bin=str(gh))
    assert w.state is WitnessState.UNAVAILABLE, advertised
    assert w.sha is None and w.source is None
    assert w.detail
    assert "merged_sha" not in w.stamp_fields()
