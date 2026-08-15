r"""DF-2 seals (P2) — a merge authorised for one SHA must not act on another.

Written against ``src/claude_dispatcher/merge_authorization.py`` at
``5d967d2`` by an author who did not write the scaffold (DF-2-1) and will not
write the bodies (DF-2-3), per the DF-4 ruling. Both ladder branches are
sealed — the SELF-APPROVAL path first and hardest, because five of the seven
recorded merges took it and PR #39's ``reviews`` array is ``[]``: an
elevated-only seal set would cover the minority path.

The condemned seal (``tests/test_merge_engine.py:313`` area, DF-1-4: AMENDED)
is not twinned here: **no assertion in this file is a truthiness check over a
recorded SHA.** Every observed value is judged by equality against an
expectation produced in the same call (a same-call ``git rev-parse``, a
same-call fixture oid, or origin's own post-merge answer), and every required
absence is judged beside a same-call presence control.

Measured under: ``5d967d2`` (``feat/DF-2-2-seals-a-merge-authorised-for``),
git 2.51.0, CPython 3.13.7, 2026-08-14, in throwaway repositories under
pytest ``tmp_path``, unless a line says ``Predicted (unmeasured)``.
Citations re-measured for this file rather than carried from the scaffold:

  * Tag-shadowing is REAL: with a tag and a branch both named ``feat-a``,
    ``git rev-parse --verify 'feat-a^{commit}'`` warns ``refname 'feat-a' is
    ambiguous`` and answers the TAG's commit; ``refs/heads/feat-a^{commit}``
    answers the branch tip — re-measured live (git 2.51.0) before this file
    was written, and re-proven as an in-call control on every run of the
    tag rows below. The scaffold's fully-qualified-ref rule is therefore a
    real refusal, not paranoia.
  * ``--match-head-commit`` exists in the installed gh 2.46.0 (scaffold,
    MEASURED; not re-run here — no seal shells out to real gh).
  * gh's refusal MESSAGE for a mismatched pin is Predicted (unmeasured) by
    the scaffold ("Head branch was modified" on the GraphQL error surface).
    The fake gh below emulates that predicted shape; the mismatch rows
    therefore seal the FOLD (fail closed, never the conflict label), and
    each such row proves in-call that the emulated message matches no entry
    of ``pr._CONFLICT_MARKERS`` — so if DF-2-3's live measurement lands a
    different message, the harness constant is one string to update and the
    control names it.

HOW THE RED ROWS ARE COMMITTED RED (DF-4-2 precedent, via DF-1-2's mechanism)
=============================================================================
``authorize_self_approval`` is the P1 stub; the ``--match-head-commit`` argv
leg, the ``commit.oid`` parse, and the engine wiring are DF-2-3's, landing
together in one commit (the scaffold's rule). Rows that drive those seams
CANNOT pass at HEAD and are committed as

    ``xfail(condition=<the seam still shows the P1 shape>,
            raises=<the row's one tolerated exception>, strict=True)``

for the DF-1-2 reasons: the ``.dispatcher.yaml`` test gate runs the whole
suite with exit 0 = green and has no seals-role carve-out, so plain red
would block this branch and poison every concurrent unit's whole-suite
baseline (the DF-5 false-positive shape, deliberately not repeated); and
BODIES is denied ``tests/**``, so each condition is computed by PROBING the
seam and every marker retires ITSELF the commit DF-2-3 lands, with no test
edit and no silent XPASS (``strict=True``). Three probes, one per seam:

  * ``_SELF_STUB``    — ``authorize_self_approval`` still raises the P1 stub;
  * ``_PIN_REFUSED``  — ``merge_pr`` still refuses a pin as data instead of
    passing ``--match-head-commit`` (probed with a gh that accepts, so the
    probe is behavior, not error-string matching);
  * ``_OID_DROPPED``  — ``pr_review_state`` still drops the approving
    review's ``commit.oid``.

If DF-2-3 lands PARTIALLY (a probe flips while a dependent seam lags), the
affected rows run plain and fail loudly — which is the correct signal, since
the scaffold requires the landing to be one commit.

``raises=`` pins the ONE tolerated failure per row: ``NotImplementedError``
for rows that call the stub directly, ``AssertionError`` for rows red by a
contract assertion. In the latter rows the in-call controls use
``pytest.fail`` (``Failed`` is not an ``AssertionError``, so a broken control
reports as a real failure today, never as an expected red); in the former,
controls are plain asserts for the mirrored reason.

NON-VACUITY LEDGER (each row names its defect and its same-call control)
========================================================================
Red rows, each red at HEAD by the specific defect it names:

  * the self-approval engine row (THE ROW) — red because the engine, having
    judged the LOCAL ``feat-a`` tip, merges UNPINNED and origin lands the
    moved head: the unjudged commit really ships into origin's feature
    branch under a journal that says it was judged. Controls in the same
    call: the window is real (origin's branch head ≠ the judged local tip,
    both 40-hex, proven distinct), and while the seams are the P1 shape the
    red is verified to be by the named defect — the row went Merged, no
    merge argv carried a pin, and the unjudged commit IS an ancestor of
    origin's feature branch — not a harness accident.
  * the self-approval happy-path engine row — red because the merge that
    lands carries no ``--match-head-commit`` argv and the ``pr_approved``
    payload carries neither contract key. Control: the merge really landed
    (both at HEAD and post-fix — a row that didn't merge would be red for
    the wrong reason).
  * the elevated engine row — red the same way from the other ladder branch:
    reviewer approved at the judged tree, origin's head moved, the engine
    merges the moved head anyway (today's parse drops the oid it would pin).
  * the direct ``authorize_self_approval`` rows — red at the stub raise,
    after controls proved: the branch tip is resolvable and 40-hex (positive
    row); the tag-shadow temptation is real and distinguishable (tag rows);
    the refusal cases really cannot resolve a branch (refusal rows).
  * the ``pr_review_state`` oid row — red because ``approved_commit_oid`` is
    None while the same call's fixture gh demonstrably returned the oid
    (control runs the fake gh directly and reads it back from the JSON).
  * the pinned-merge rows on ``merge_pr`` — red because no gh invocation
    carrying the pin exists at HEAD (the pin is refused as data). Controls
    run the enforcing fake gh directly and prove both legs (accept on
    match, refuse on mismatch with the emulated message) before the seam
    is asked.

Green rows (the P1-implemented surface), mutation-checked in a /tmp lab
under 5d967d2 (mutation → which row kills it):

  * ``__post_init__`` body → ``pass``  → both unconstructibility rows fail;
  * ``stamp_fields`` → ``return {}``   → the exact-stamp row fails;
  * ``authorize_external_approval`` returning a pin when ``approved_commit_
    oid`` is None (the unpinned-authorization mutation) → the fold-refusal
    rows and the parse-to-fold invariant row fail;
  * ``merge_pr`` dropping the early refusal and merging UNPINNED while a pin
    was passed (the defect wearing the fixed signature) → the never-dropped
    row fails (a merge invocation exists with no adjacent pin pair);
  * a third ``AuthorizedShaSource`` member added silently → the
    members-are-fixed row fails (that row is the loud review surface the
    scaffold promises: a new source must edit a seal, in a seals-owned
    file, as a shared-contract change).

What this file deliberately does NOT seal, each a CHOICE: the pin-then-judge
internal (that ``risk.classify`` receives the SHA, not the name, as
``head_ref``) is not directly observable at a public seam — it is ruled in
the scaffold docstring and its observable consequence (the pin equals the
judged tip) IS sealed by the engine rows; the ``needs_rebase``-vs-new-kind
naming on a mismatch is DF-2-3's measurement and DF-2-4's ruling — these
rows pin only what the scaffold fixes (a mismatch must not wear the conflict
label); and the fake-gh ``_num()`` first-all-digit-token hazard named in the
scaffold is AVOIDED here rather than amended there (this file's harness
parses ``gh pr merge``'s PR number positionally and never scans for digit
tokens; amending ``test_merge_engine.py``'s harness stays with the role
DF-2-3 briefs).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from claude_dispatcher import journal as journal_mod
from claude_dispatcher import merge_engine as me
from claude_dispatcher import notify as notify_mod
from claude_dispatcher import pr as pr_mod
from claude_dispatcher import yaml_io
from claude_dispatcher.merge_authorization import (
    AuthorizationUnavailable,
    AuthorizedShaSource,
    MergeAuthorization,
    authorize_external_approval,
    authorize_self_approval,
)

_HEX40 = re.compile(r"[0-9a-f]{40}")

#: The mismatch refusal the fake gh emulates. Predicted (unmeasured) by the
#: DF-2-1 scaffold (gh's GraphQL error surface for --match-head-commit);
#: DF-2-3 measures the real one. Every row that leans on this proves in-call
#: that it matches no ``pr._CONFLICT_MARKERS`` entry, so a wrong prediction
#: is caught as a named control failure, not a silently-vacuous seal.
_PREDICTED_MISMATCH_STDERR = (
    "GraphQL: Head branch was modified. Review and try the merge again. "
    "(mergePullRequest)"
)


# --------------------------------------------------------------------------- #
# Self-retiring stub probes — one per DF-2-3 seam
# --------------------------------------------------------------------------- #

def _self_approval_is_still_the_stub() -> bool:
    """Does ``authorize_self_approval`` still raise the P1 stub?

    Probed with a branch that cannot exist. While the stub stands this raises
    ``NotImplementedError`` before touching git. The commit DF-2-3 lands the
    body, the same call runs the contract's cheapest refusal leg (one failed
    ``git rev-parse``, no network) and raises ``AuthorizationUnavailable``
    instead — the probe flips to False on its own and every dependent xfail
    retires without a test edit. Any OTHER outcome is treated as not-the-stub
    so a partially-landed body runs the rows plain and fails them loudly.
    """
    try:
        authorize_self_approval(
            cwd=Path(__file__).parent, pr_number=0,
            branch="df-2-seal-probe-branch-that-cannot-exist",
        )
    except NotImplementedError:
        return True
    except Exception:
        return False
    return False


def _probe_p1_shapes() -> tuple[bool, bool]:
    """Probe the two other DF-2-3 seams behaviorally (never by error text).

    ``pin_refused``: ``merge_pr`` given a pin and a gh that ACCEPTS any merge
    — while the P1 refusal-as-data stands, gh is never invoked and ``merged``
    is False; the commit the argv leg lands, the same call merges and the
    probe flips. ``oid_dropped``: ``pr_review_state`` against a gh answering
    the PR-813-measured reviews shape — while the parse drops ``commit.oid``
    the field is None beside ``approved=True``; the commit the parse lands it
    equals the fixture oid and the probe flips. Any unexpected shape → False
    (rows run plain and fail loudly). Probe scripts live in a throwaway
    tempdir removed before returning.
    """
    oid = "cd" * 20
    tmp = Path(tempfile.mkdtemp(prefix="df2-seal-probe-"))
    try:
        ok_gh = tmp / "gh-accepts.py"
        ok_gh.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n",
                         encoding="utf-8")
        ok_gh.chmod(0o755)
        reviews_gh = tmp / "gh-reviews.py"
        reviews_gh.write_text(
            '#!/usr/bin/env python3\n'
            'import json, sys\n'
            'print(json.dumps({"reviews": [{"author": {"login": "r"},'
            f' "state": "APPROVED", "commit": {{"oid": "{oid}"}}}}]}}))\n'
            'sys.exit(0)\n',
            encoding="utf-8")
        reviews_gh.chmod(0o755)

        pin_refused = False
        try:
            res = pr_mod.merge_pr(
                cwd=tmp, number=1, gh_bin=str(ok_gh),
                match_head_commit="ab" * 20,
            )
            pin_refused = not res.merged
        except Exception:
            pin_refused = False

        oid_dropped = False
        try:
            st = pr_mod.pr_review_state(cwd=tmp, number=1,
                                        gh_bin=str(reviews_gh))
            if st.error is None and st.approved:
                oid_dropped = st.approved_commit_oid is None
        except Exception:
            oid_dropped = False
        return pin_refused, oid_dropped
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_SELF_STUB = _self_approval_is_still_the_stub()
_PIN_REFUSED, _OID_DROPPED = _probe_p1_shapes()

_RED_SELF = ("DF-2 P1 stub still in place: authorize_self_approval raises; "
             "DF-2-3's body turns this row green")
_RED_PIN = ("DF-2 P1 shape still in place: merge_pr refuses a pin as data "
            "instead of passing --match-head-commit; DF-2-3's argv leg turns "
            "this row green")
_RED_ENGINE = ("DF-2 P1 shape still in place: the engine merges unpinned "
               "(and pr_review_state drops the approving review's oid); "
               "DF-2-3's one-commit wiring turns this row green")


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


def _commit_on_branch(repo: Path, branch: str, filename: str,
                      *, base: str) -> str:
    """One commit on ``branch`` (created off ``base`` if absent) via a temp
    worktree, so the repo's own checkout never moves. Returns the new tip."""
    wt = repo.parent / f"wt-{repo.name}-{branch.replace('/', '-')}"
    if subprocess.run(
        ["git", "rev-parse", "--verify", "-q", f"refs/heads/{branch}"],
        cwd=str(repo), capture_output=True, text=True, timeout=60,
    ).returncode == 0:
        _git(repo, "worktree", "add", "-q", str(wt), branch)
    else:
        _git(repo, "worktree", "add", "-q", "-b", branch, str(wt), base)
    (wt / filename).write_text(f"# {filename}\n", encoding="utf-8")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-q", "-m", f"work on {branch}: {filename}")
    tip = _git(wt, "rev-parse", "HEAD")
    _git(repo, "worktree", "remove", "--force", str(wt))
    return tip


#: An enforcing gh for the merge_pr rows: compares an argv pin against
#: $FAKE_GH_HEAD exactly as the scaffold says origin does — atomically with
#: the merge, refusing with the predicted message on mismatch. Logs each
#: invocation's argv as one JSON line to $FAKE_GH_LOG.
_ENFORCING_GH = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\\n")
if args[:2] == ["pr", "merge"]:
    pin = None
    if "--match-head-commit" in args:
        pin = args[args.index("--match-head-commit") + 1]
    if pin is not None and pin != os.environ["FAKE_GH_HEAD"]:
        sys.stderr.write(
            "GraphQL: Head branch was modified. Review and try the merge "
            "again. (mergePullRequest)\\n")
        sys.exit(1)
    sys.exit(0)
sys.exit(0)
'''

#: The engine-row gh: a real origin repository behind it. ``pr merge <n>``
#: resolves origin's CURRENT branch head, enforces an argv pin against it
#: (refusing with the predicted message), and on acceptance REALLY merges the
#: branch into origin's checked-out feature branch, writing a receipt.
#: ``pr view --json reviews`` answers $FAKE_GH_REVIEWS (default: none — the
#: self-approval path's measured reality, PR #39). The PR number is parsed
#: POSITIONALLY (``args[2]`` of ``pr merge <n>`` / ``pr view <n>``), never by
#: scanning for digit tokens — the scaffold-named ``_num()`` hazard cannot
#: arise in this harness.
_ORIGIN_GH = '''#!/usr/bin/env python3
import json, os, subprocess, sys
args = sys.argv[1:]
log = os.environ.get("FAKE_GH_LOG")
if log:
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(args) + "\\n")
origin = os.environ["FAKE_GH_ORIGIN"]
receipts_path = os.environ["FAKE_GH_RECEIPTS"]
branches = json.loads(os.environ["FAKE_GH_BRANCHES"])

def _receipts():
    try:
        with open(receipts_path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}

if args[:2] == ["pr", "view"]:
    if "reviews" in args:
        print(json.dumps(
            {"reviews": json.loads(os.environ.get("FAKE_GH_REVIEWS", "[]"))}))
        sys.exit(0)
    if "mergeCommit" in args:
        sha = _receipts().get(args[2])
        print(json.dumps({"mergeCommit": ({"oid": sha} if sha else None)}))
        sys.exit(0)
    print("{}")
    sys.exit(0)
if args[:2] == ["pr", "merge"]:
    num = args[2]
    branch = branches[num]
    head = subprocess.run(
        ["git", "-C", origin, "rev-parse", "refs/heads/%s" % branch],
        capture_output=True, text=True, check=True).stdout.strip()
    pin = None
    if "--match-head-commit" in args:
        pin = args[args.index("--match-head-commit") + 1]
    if pin is not None and pin != head:
        sys.stderr.write(
            "GraphQL: Head branch was modified. Review and try the merge "
            "again. (mergePullRequest)\\n")
        sys.exit(1)
    proc = subprocess.run(
        ["git", "-C", origin, "merge", "--no-ff", "-m",
         "Merge pull request #%s from %s" % (num, branch), branch],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        sys.exit(1)
    merged = subprocess.run(
        ["git", "-C", origin, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    receipts = _receipts()
    receipts[num] = merged
    with open(receipts_path, "w", encoding="utf-8") as fh:
        json.dump(receipts, fh)
    sys.exit(0)
sys.exit(0)
'''


def _invocations(log: Path) -> list[list[str]]:
    """Every gh invocation's argv, in order (JSON lines from the fake gh)."""
    if not log.exists():
        return []
    return [json.loads(line)
            for line in log.read_text(encoding="utf-8").splitlines() if line]


def _merge_invocations(log: Path) -> list[list[str]]:
    return [a for a in _invocations(log) if a[:2] == ["pr", "merge"]]


def _pinned_to(argv: list[str], sha: str) -> bool:
    """Does ``argv`` carry the adjacent pair ``--match-head-commit <sha>``?
    Judged by equality of the following token — never by substring."""
    return any(
        argv[i] == "--match-head-commit"
        and i + 1 < len(argv) and argv[i + 1] == sha
        for i in range(len(argv))
    )


def _review_state(*, approved: bool = True, oid: str | None = None,
                  error: str | None = None) -> pr_mod.ReviewState:
    return pr_mod.ReviewState(
        approved=approved,
        latest={"reviewer-bot": "APPROVED" if approved else "COMMENTED"},
        approver="reviewer-bot" if approved else None,
        approved_commit_oid=oid,
        error=error,
    )


def _pr_row(key: str, *, pr_number: int, branch: str,
            labels: list[str] | None = None) -> dict:
    return {
        "key": key,
        "summary": f"summary {key}",
        "description": f"desc {key}",
        "type": "Task",
        "labels": labels or ["size:S", "area:x"],
        "status": "Awaiting Review",
        "branch": branch,
        "pr_number": pr_number,
        "pr_url": f"https://github.com/test/repo/pull/{pr_number}",
        "verified": True,
        "verification_iterations": 0,
    }


def _engine_fixture(tmp_path: Path, monkeypatch, *,
                    move_origin_head: bool,
                    labels: list[str] | None = None):
    """The pr-mode configuration the defect was measured in: a real origin
    with ``feature/x`` checked out, a clone as ``repo_root`` (feature/x
    checked out there too), one task branch ``feat-a`` whose LOCAL tip is the
    tree the engine will judge — and, when ``move_origin_head``, one more
    commit landed directly on ORIGIN's ``feat-a`` afterward, so origin's head
    is a tree nobody judged. Returns (cfg, journal_path, journal, gh_log,
    judged_tip, origin_head)."""
    origin = _init_repo(tmp_path / "origin")
    _git(origin, "checkout", "-q", "-b", "feature/x")
    repo = tmp_path / "repo_root"
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(repo)],
        check=True, capture_output=True, text=True, timeout=60,
    )
    _git(repo, "config", "user.email", "seal@example.invalid")
    _git(repo, "config", "user.name", "seal")
    _git(repo, "checkout", "-q", "feature/x")

    judged_tip = _commit_on_branch(repo, "feat-a", "a.py", base="feature/x")
    _git(repo, "push", "-q", "origin", "feat-a")
    origin_head = judged_tip
    if move_origin_head:
        origin_head = _commit_on_branch(
            origin, "feat-a", "pushed_after_judgement.py", base="feature/x")

    gh = _script(repo / "fake_gh.py", _ORIGIN_GH)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_ORIGIN", str(origin))
    monkeypatch.setenv("FAKE_GH_RECEIPTS", str(tmp_path / "receipts.json"))
    monkeypatch.setenv("FAKE_GH_BRANCHES", json.dumps({"101": "feat-a"}))
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    monkeypatch.delenv("FAKE_GH_REVIEWS", raising=False)

    tasks = repo / "tasks.yaml"
    yaml_io.dump({"project": "T", "epic": "X", "tasks": [
        _pr_row("A", pr_number=101, branch="feat-a", labels=labels),
    ]}, tasks)
    jpath = repo / "journal.jsonl"
    journal = journal_mod.Journal.create(
        jpath, tasks_yaml_path=tasks, reviewer_prompts_dir=repo,
        run_id="run-df2")
    cfg = me.MergeEngineConfig(
        tasks_path=tasks, repo_root=repo, feature_branch="feature/x",
        gh_bin=str(gh), run_id="run-df2")
    return cfg, jpath, journal, gh_log, judged_tip, origin_head


def _rowof(cfg: me.MergeEngineConfig, key: str) -> dict:
    doc = yaml_io.load(cfg.tasks_path)
    return next(t for t in doc["tasks"] if t["key"] == key)


def _events(jpath: Path, event_type) -> list:
    return [e for e in journal_mod.read_events(jpath)
            if e.event_type == event_type]


def _is_ancestor(repo: Path, sha: str, ref: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, ref], cwd=str(repo),
        capture_output=True, text=True, timeout=60,
    ).returncode == 0


# --------------------------------------------------------------------------- #
# Green rows — the record type (question 1's structural half)
# --------------------------------------------------------------------------- #

def test_an_authorization_that_cannot_name_a_judgeable_sha_is_unconstructible() -> None:
    """A pin origin cannot compare — None, empty, abbreviated, uppercase,
    over-long, decorated, non-hex, non-str — must refuse to construct, so a
    value that never named a tree can never travel to ``--match-head-commit``.

    Control, judged first in the same call: the legal 40-hex lower shape
    constructs and holds exactly its answer — the refusals below are refusals
    of the illegal values, not a constructor that rejects everything.

    Mutation-verified (lab under 5d967d2): ``__post_init__`` → ``pass`` →
    every ``pytest.raises`` block below fails.
    """
    sha = "ab" * 20
    legal = MergeAuthorization(
        pr_number=7, head_sha=sha,
        source=AuthorizedShaSource.LOCAL_CLASSIFIED_TIP,
    )
    assert legal.head_sha == sha  # control: the legal shape holds its answer

    for bad in (None, "", "4a2e73df", "AB" * 20, "ab" * 20 + "ab",
                ("ab" * 20)[:-1], f"{'ab' * 20}\n", "not-a-sha-" * 4,
                b"ab" * 20, 42):
        with pytest.raises(ValueError):
            MergeAuthorization(
                pr_number=7, head_sha=bad,
                source=AuthorizedShaSource.LOCAL_CLASSIFIED_TIP,
            )


def test_an_authorization_without_a_named_source_is_unconstructible() -> None:
    """A SHA without provenance is a pin nobody can audit: ``source`` must be
    a named ``AuthorizedShaSource`` member — not None, not the member's string
    VALUE (a string wearing the name), not a member of some other enum.

    Control: BOTH real members construct — each ladder branch's provenance is
    expressible, so the refusals are about naming, not about one branch being
    unrepresentable.

    Mutation-verified (lab under 5d967d2): ``__post_init__`` → ``pass`` →
    the raises blocks fail.
    """
    sha = "ab" * 20
    for member in AuthorizedShaSource:
        assert MergeAuthorization(
            pr_number=7, head_sha=sha, source=member,
        ).source is member  # control

    from claude_dispatcher.merge_record import ShaSource as _OtherEnum
    for bad in (None, "local_classified_tip", "external_review_commit",
                _OtherEnum.ORIGIN_PR_MERGE_COMMIT):
        with pytest.raises(ValueError):
            MergeAuthorization(pr_number=7, head_sha=sha, source=bad)


def test_the_authorization_stamp_is_exactly_the_contracted_key_shape() -> None:
    """The ``pr_approved`` audit keys, fixed now so these seals and DF-2-3's
    wiring write against the same names. Judged by equality of the WHOLE dict
    per source — a row probing one key would stay green while the fold grew
    or lost keys. There is no keys-absent state: an authorization that cannot
    name a SHA never constructs (the fold rows below), so BOTH keys are
    always present, for BOTH ladder branches.

    Mutation-verified (lab under 5d967d2): ``stamp_fields`` → ``return {}``
    → both equalities fail.
    """
    sha_low = "ab" * 20
    sha_ext = "cd" * 20
    assert MergeAuthorization(
        pr_number=7, head_sha=sha_low,
        source=AuthorizedShaSource.LOCAL_CLASSIFIED_TIP,
    ).stamp_fields() == {
        "authorized_head_sha": sha_low,
        "authorized_head_source": "local_classified_tip",
    }
    assert MergeAuthorization(
        pr_number=9, head_sha=sha_ext,
        source=AuthorizedShaSource.EXTERNAL_REVIEW_COMMIT,
    ).stamp_fields() == {
        "authorized_head_sha": sha_ext,
        "authorized_head_source": "external_review_commit",
    }


def test_the_rejected_sha_sources_are_refusals_not_members() -> None:
    """The scaffold's two rejected sources (the branch name; origin's tip
    read at merge time) are documented refusals, not enum members — and the
    scaffold promises a future source arrives as a REVIEWED shared-contract
    change, never a silent widening. This row is that promise made loud: the
    member set is pinned exactly, so adding a source means editing a seal in
    a seals-owned file, where the DF-2 review surface is.

    Mutation-verified (lab under 5d967d2): a third member added → the
    name-set equality fails.
    """
    assert {m.name: m.value for m in AuthorizedShaSource} == {
        "LOCAL_CLASSIFIED_TIP": "local_classified_tip",
        "EXTERNAL_REVIEW_COMMIT": "external_review_commit",
    }


# --------------------------------------------------------------------------- #
# Green rows — the external-approval fold (the elevated ladder branch)
# --------------------------------------------------------------------------- #

def test_an_approved_review_folds_to_a_pin_on_the_tree_the_reviewer_saw() -> None:
    """Question 1, elevated branch: the authorization names the approving
    review's ``commit.oid`` — exactly, by equality — with the external
    provenance and the PR number carried, and the stamp is the full
    contracted shape.
    """
    oid = "4a2e73dfc8b52f6b73781ab7e869fad8f6ea7c86"  # PR 813's measured oid
    auth = authorize_external_approval(
        pr_number=813, review=_review_state(approved=True, oid=oid))
    assert auth.pr_number == 813
    assert auth.head_sha == oid
    assert auth.source is AuthorizedShaSource.EXTERNAL_REVIEW_COMMIT
    assert auth.stamp_fields() == {
        "authorized_head_sha": oid,
        "authorized_head_source": "external_review_commit",
    }


@pytest.mark.parametrize(
    ("case", "review"),
    [
        pytest.param(
            "read-error-wins",
            _review_state(approved=True, oid="ab" * 20,
                          error="HTTP 502: upstream error"),
            id="read-error-wins",
        ),
        pytest.param(
            "not-approved",
            _review_state(approved=False, oid="ab" * 20),
            id="not-approved",
        ),
        pytest.param(
            "no-oid-todays-parse",
            _review_state(approved=True, oid=None),
            id="no-oid-todays-parse",
        ),
        pytest.param(
            "abbreviated-oid",
            _review_state(approved=True, oid="4a2e73df"),
            id="abbreviated-oid",
        ),
        pytest.param(
            "uppercase-oid",
            _review_state(approved=True, oid="AB" * 20),
            id="uppercase-oid",
        ),
    ],
)
def test_a_review_that_cannot_name_a_judged_tree_authorizes_nothing(
    case: str, review: pr_mod.ReviewState,
) -> None:
    """Question 3, elevated branch, fail closed: an unreadable state, a
    missing approval, and an approval whose judged tree cannot be named (the
    no-oid case is TODAY'S REAL SHAPE — the parse drops the oid) each raise
    ``AuthorizationUnavailable``. Never a pin from another source; the
    refusal happens BEFORE the irreversible action, so it cannot be ignored.

    Mutation-verified (lab under 5d967d2): the fold returning a
    LOCAL_CLASSIFIED_TIP-sourced pin for the no-oid case (the fallback-source
    mutation) → this row fails on the non-raise.
    """
    with pytest.raises(AuthorizationUnavailable):
        authorize_external_approval(pr_number=39, review=review)


def test_a_real_parse_never_yields_an_unpinned_external_authorization(
    tmp_path: Path,
) -> None:
    """The parse→fold invariant, durable across DF-2-3: feeding
    ``authorize_external_approval`` what ``pr_review_state`` ACTUALLY returns
    for gh's measured PR-813 reviews shape yields either a fail-closed
    refusal (today: the parse drops the oid — asserted as the reason in the
    same call) or an authorization pinned by equality to the very oid the
    fixture returned (after DF-2-3). There is no third outcome — never an
    authorization naming some other tree.

    Control, judged first: the fake gh, invoked directly with the documented
    argv, really returns the APPROVED review carrying ``commit.oid``.
    """
    oid = "4a2e73dfc8b52f6b73781ab7e869fad8f6ea7c86"
    gh = _script(tmp_path / "gh.py", f'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args[:2] == ["pr", "view"] and "reviews" in args:
    print(json.dumps({{"reviews": [{{"author": {{"login": "reviewer-bot"}},
        "state": "APPROVED", "commit": {{"oid": "{oid}"}}}}]}}))
sys.exit(0)
''')
    probe = subprocess.run(
        [str(gh), "pr", "view", "813", "--json", "reviews"],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0  # control: the harness answers
    fixture_reviews = json.loads(probe.stdout)["reviews"]
    assert fixture_reviews[0]["commit"]["oid"] == oid  # control

    state = pr_mod.pr_review_state(cwd=tmp_path, number=813, gh_bin=str(gh))
    assert state.error is None and state.approved  # control: approval readable

    try:
        auth = authorize_external_approval(pr_number=813, review=state)
    except AuthorizationUnavailable:
        # Today's leg: refused BECAUSE the parse dropped the oid — any other
        # reason for the refusal would be a different defect.
        assert state.approved_commit_oid is None
    else:
        # DF-2-3's leg: pinned to exactly the tree the reviewer saw.
        assert auth.head_sha == oid
        assert auth.source is AuthorizedShaSource.EXTERNAL_REVIEW_COMMIT


# --------------------------------------------------------------------------- #
# Green row — a pin handed to merge_pr is NEVER dropped (durable invariant)
# --------------------------------------------------------------------------- #

def test_a_pin_passed_to_merge_pr_is_never_accepted_and_dropped(
    tmp_path: Path, monkeypatch,
) -> None:
    """The scaffold's signature rule, sealed as an invariant that holds on
    BOTH sides of DF-2-3: when a caller passes ``match_head_commit``, either
    no merge is attempted at all (today's loud refusal-as-data — the error
    must be non-empty) or every ``gh pr merge`` invocation carries the
    adjacent argv pair ``--match-head-commit <that exact sha>``. A merge
    invocation without the pin, or a ``merged=True`` with no pinned
    invocation on record, is the DF-2 defect wearing the fixed signature.

    Mutation-verified (lab under 5d967d2): the early refusal deleted and the
    argv built WITHOUT the flag (accept-and-drop) → the per-invocation pin
    assert fails.
    """
    sha = "ab" * 20
    gh = _script(tmp_path / "gh.py", _ENFORCING_GH)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    monkeypatch.setenv("FAKE_GH_HEAD", sha)  # accepts this pin, refuses others

    result = pr_mod.merge_pr(
        cwd=tmp_path, number=7, gh_bin=str(gh), match_head_commit=sha)

    merges = _merge_invocations(gh_log)
    for argv in merges:
        assert _pinned_to(argv, sha), (
            f"gh pr merge was invoked WITHOUT the pin ({argv!r}) while the "
            "caller passed match_head_commit — the pin was accepted and "
            "dropped, which is the DF-2 defect wearing the fixed signature")
    if result.merged:
        assert any(_pinned_to(argv, sha) for argv in merges), (
            "merged=True was reported with no pinned gh invocation on record")
    else:
        assert result.error, (
            "the pin was neither acted on nor refused LOUDLY — a silent "
            "no-merge is not the contracted refusal shape")


# --------------------------------------------------------------------------- #
# Red rows — authorize_self_approval (the majority ladder branch, P1 stub)
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_SELF_STUB, reason=_RED_SELF, raises=NotImplementedError,
                   strict=True)
def test_self_approval_names_the_local_branch_tip_it_judges(
    tmp_path: Path,
) -> None:
    """Question 1, self-approval branch: the authorization names the local
    ``refs/heads/<branch>`` tip — judged by EQUALITY against a same-call
    ``git rev-parse`` of that exact qualified ref — with the local provenance,
    the PR number carried, and the full contracted stamp.

    Controls (plain asserts — ``AssertionError`` is not this row's tolerated
    exception, so a control break fails today): the tip is resolvable from
    the same ``cwd`` the seam gets, and is 40-hex lower.
    """
    repo = _init_repo(tmp_path / "repo", branch="feature/x")
    tip = _commit_on_branch(repo, "feat-a", "a.py", base="feature/x")
    expected = _git(repo, "rev-parse", "--verify", "refs/heads/feat-a^{commit}")
    assert expected == tip  # control: the judged tree is well-defined
    assert _HEX40.fullmatch(expected)  # control

    auth = authorize_self_approval(cwd=repo, pr_number=5, branch="feat-a")
    assert auth.head_sha == expected
    assert auth.source is AuthorizedShaSource.LOCAL_CLASSIFIED_TIP
    assert auth.pr_number == 5
    assert auth.stamp_fields() == {
        "authorized_head_sha": expected,
        "authorized_head_source": "local_classified_tip",
    }


@pytest.mark.xfail(_SELF_STUB, reason=_RED_SELF, raises=NotImplementedError,
                   strict=True)
def test_a_tag_of_the_same_name_cannot_answer_for_the_branch(
    tmp_path: Path,
) -> None:
    """The fully-qualified-ref rule, sealed against a live temptation: with a
    TAG named ``feat-a`` pointing at a different commit than the branch, the
    authorization must name the BRANCH tip. Measured (git 2.51.0, re-proven
    below as this row's control): the unqualified name resolves to the TAG
    (``refname is ambiguous`` — tags outrank heads in rev-parse
    disambiguation), so a body that dropped the ``refs/heads/`` prefix would
    pin a tree nobody judged.
    """
    repo = _init_repo(tmp_path / "repo", branch="feature/x")
    base = _git(repo, "rev-parse", "HEAD")
    tip = _commit_on_branch(repo, "feat-a", "a.py", base="feature/x")
    _git(repo, "tag", "feat-a", base)  # the shadow, at a DIFFERENT commit

    shadow = subprocess.run(
        ["git", "rev-parse", "--verify", "feat-a^{commit}"], cwd=str(repo),
        capture_output=True, text=True, timeout=60,
    )
    # controls: the temptation is real (unqualified answers the TAG) and
    # distinguishable (tag commit != branch tip)
    assert shadow.returncode == 0
    assert shadow.stdout.strip() == base
    assert base != tip
    assert _git(repo, "rev-parse", "--verify",
                "refs/heads/feat-a^{commit}") == tip  # control: qualified works

    auth = authorize_self_approval(cwd=repo, pr_number=5, branch="feat-a")
    assert auth.head_sha == tip
    assert auth.head_sha != base


@pytest.mark.xfail(_SELF_STUB, reason=_RED_SELF, raises=NotImplementedError,
                   strict=True)
@pytest.mark.parametrize("case", ["missing-branch", "tag-but-no-branch",
                                  "not-a-repo"])
def test_a_branch_that_cannot_be_resolved_authorizes_nothing(
    tmp_path: Path, case: str,
) -> None:
    """Question 3, self-approval branch, fail closed: no resolvable
    ``refs/heads/<branch>`` → ``AuthorizationUnavailable``, never a pin from
    a lookalike source. The tag-but-no-branch case is the sharp one: the
    unqualified name RESOLVES (to the tag — control below), so an
    under-qualified body would find a value to smuggle; the contract refuses.
    """
    if case == "not-a-repo":
        cwd = tmp_path / "empty"
        cwd.mkdir()
    else:
        cwd = _init_repo(tmp_path / "repo", branch="feature/x")
        if case == "tag-but-no-branch":
            _git(cwd, "tag", "feat-a", "HEAD")
            # control: the unqualified temptation really resolves...
            assert subprocess.run(
                ["git", "rev-parse", "--verify", "feat-a^{commit}"],
                cwd=str(cwd), capture_output=True, text=True, timeout=60,
            ).returncode == 0
        # control: ...and the qualified branch ref really does not
        assert subprocess.run(
            ["git", "rev-parse", "--verify", "refs/heads/feat-a^{commit}"],
            cwd=str(cwd), capture_output=True, text=True, timeout=60,
        ).returncode != 0

    with pytest.raises(AuthorizationUnavailable):
        authorize_self_approval(cwd=cwd, pr_number=5, branch="feat-a")


# --------------------------------------------------------------------------- #
# Red row — the parse owes the oid (elevated branch's input, P1 shape)
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_OID_DROPPED, reason=_RED_ENGINE, raises=AssertionError,
                   strict=True)
@pytest.mark.parametrize(
    ("case", "reviews", "expected_oid"),
    [
        pytest.param(
            "single-approval",
            [{"author": {"login": "reviewer-bot"}, "state": "APPROVED",
              "commit": {"oid": "4a" + "2e" * 19 + "7c"}}],
            "4a" + "2e" * 19 + "7c",
            id="single-approval",
        ),
        pytest.param(
            "latest-approval-wins",
            [{"author": {"login": "reviewer-bot"}, "state": "APPROVED",
              "commit": {"oid": "ab" * 20}},
             {"author": {"login": "reviewer-bot"}, "state": "APPROVED",
              "commit": {"oid": "cd" * 20}}],
            "cd" * 20,
            id="latest-approval-wins",
        ),
    ],
)
def test_pr_review_state_carries_the_tree_the_approving_reviewer_saw(
    tmp_path: Path, case: str, reviews: list, expected_oid: str,
) -> None:
    """The elevated pin's input: ``approved_commit_oid`` must equal the
    ``commit.oid`` of the review that made ``approved`` True — the latest
    APPROVED one, matching the fold ``pr_review_state`` already applies to
    ``state``/``approver``. RED AT HEAD: the parse keeps only ``state`` and
    ``author.login`` and drops the oid (scaffold, MEASURED against PR 813).

    Controls (plain asserts, fail today if broken): the fake gh really
    returns the oid in its JSON, and the state parses as approved with no
    read error — so the None below is the parse dropping a value it was
    given, not a harness that never supplied one.
    """
    gh = _script(tmp_path / "gh.py", f'''#!/usr/bin/env python3
import json, sys
args = sys.argv[1:]
if args[:2] == ["pr", "view"] and "reviews" in args:
    print(json.dumps({{"reviews": {json.dumps(reviews)}}}))
sys.exit(0)
''')
    probe = subprocess.run(
        [str(gh), "pr", "view", "813", "--json", "reviews"],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.returncode == 0  # control
    returned = json.loads(probe.stdout)["reviews"]
    assert [r["commit"]["oid"] for r in returned] == \
        [r["commit"]["oid"] for r in reviews]  # control: the oid was supplied

    state = pr_mod.pr_review_state(cwd=tmp_path, number=813, gh_bin=str(gh))
    assert state.error is None and state.approved  # control: approval parsed

    assert state.approved_commit_oid == expected_oid, (
        "pr_review_state dropped (or mis-picked) the approving review's "
        f"commit.oid: expected {expected_oid!r}, got "
        f"{state.approved_commit_oid!r} — the elevated pin has no input")


# --------------------------------------------------------------------------- #
# Red rows — merge_pr's argv leg (question 2, P1 refusal-as-data)
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_PIN_REFUSED, reason=_RED_PIN, raises=AssertionError,
                   strict=True)
def test_a_pinned_merge_lands_when_origins_head_is_the_judged_tree(
    tmp_path: Path, monkeypatch,
) -> None:
    """Question 2's positive leg: with origin's head EQUAL to the pin, the
    pinned merge lands — exactly one ``gh pr merge`` invocation, carrying the
    adjacent ``--match-head-commit <sha>`` pair.

    Controls (``pytest.fail``, never this row's tolerated
    ``AssertionError``): the enforcing fake gh, run directly, really accepts
    the matching pin and really refuses a mismatched one with the emulated
    refusal — both legs proven before the seam is asked.
    """
    sha = "ab" * 20
    other = "cd" * 20
    gh = _script(tmp_path / "gh.py", _ENFORCING_GH)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_HEAD", sha)
    monkeypatch.setenv("FAKE_GH_LOG", str(tmp_path / "control.log"))
    ok = subprocess.run(
        [str(gh), "pr", "merge", "7", "--merge", "--match-head-commit", sha],
        capture_output=True, text=True, timeout=30)
    refused = subprocess.run(
        [str(gh), "pr", "merge", "7", "--merge", "--match-head-commit", other],
        capture_output=True, text=True, timeout=30)
    if ok.returncode != 0 or refused.returncode == 0 \
            or "Head branch was modified" not in refused.stderr:
        pytest.fail("CONTROL: the enforcing fake gh does not enforce "
                    f"(ok rc={ok.returncode}, refused rc={refused.returncode})")
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))

    result = pr_mod.merge_pr(
        cwd=tmp_path, number=7, gh_bin=str(gh), match_head_commit=sha)

    assert result.merged, (
        f"the pinned merge did not land (error={result.error!r}) though "
        "origin's head IS the judged tree")
    assert result.error is None and result.conflict is False
    merges = _merge_invocations(gh_log)
    assert len(merges) == 1
    assert _pinned_to(merges[0], sha)


@pytest.mark.xfail(_PIN_REFUSED, reason=_RED_PIN, raises=AssertionError,
                   strict=True)
def test_a_pinned_merge_on_a_moved_head_fails_closed_with_no_retry_and_no_conflict_label(
    tmp_path: Path, monkeypatch,
) -> None:
    """Question 3 at the argv seam: origin refuses the mismatched pin →
    ``merged=False`` with the detail carried, ``conflict=False`` (a moved
    head is NOT a rebase's problem — a rebase does not re-judge a tree), and
    EXACTLY ONE pinned invocation: no retry against the moved head, no
    fallback unpinned re-invocation.

    Controls (``pytest.fail``): the emulated refusal message matches no
    ``pr._CONFLICT_MARKERS`` entry under the fold's own case-insensitive
    containment rule — so if DF-2-3's live measurement replaces the predicted
    message with one that DOES collide, this row's premise breaks loudly here
    rather than sealing vacuously.
    """
    judged = "ab" * 20
    gh = _script(tmp_path / "gh.py", _ENFORCING_GH)
    gh_log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_HEAD", "cd" * 20)  # origin's head has moved
    monkeypatch.setenv("FAKE_GH_LOG", str(gh_log))
    lowered = _PREDICTED_MISMATCH_STDERR.lower()
    if any(marker in lowered for marker in pr_mod._CONFLICT_MARKERS):
        pytest.fail(
            "CONTROL: the emulated mismatch refusal collides with "
            "pr._CONFLICT_MARKERS — the not-a-conflict premise needs "
            "re-measurement before this row can seal the fold")

    result = pr_mod.merge_pr(
        cwd=tmp_path, number=7, gh_bin=str(gh), match_head_commit=judged)

    merges = _merge_invocations(gh_log)
    assert len(merges) == 1, (
        f"expected exactly one pinned attempt, saw {len(merges)} — either "
        "the pin never reached gh (the P1 refusal) or the seam retried "
        "against a head that has never been judged")
    assert _pinned_to(merges[0], judged)
    assert result.merged is False
    assert result.conflict is False, (
        "a mismatched pin folded to conflict=True — the moved head would "
        "wear the needs_rebase label, and a rebase does not re-judge a tree")
    assert result.error, "the refusal must carry origin's detail, loudly"


# --------------------------------------------------------------------------- #
# THE ROWS THAT MATTER — the engine, both ladder branches, red at HEAD
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(_SELF_STUB or _PIN_REFUSED, reason=_RED_ENGINE,
                   raises=AssertionError, strict=True)
def test_a_self_approved_merge_authorised_for_one_sha_does_not_act_on_another(
    tmp_path: Path, monkeypatch,
) -> None:
    """THE seal, on the majority path (five of seven recorded merges): a
    low-risk PR is judged at the LOCAL ``feat-a`` tip, but origin's head has
    moved (a commit landed after the judgement — the measured window). The
    merge MUST NOT act: the row stays Awaiting Review, no ``pr_merged`` is
    journaled, the unjudged commit never becomes part of origin's feature
    branch, any merge attempt is pinned by equality to the judged tip, and
    the failure does not wear the conflict label.

    RED AT HEAD by the measured defect: the engine self-approves off the
    local diff and merges UNPINNED, so origin lands the moved head — the
    unjudged tree ships under a journal that says it was judged.

    Controls (``pytest.fail``, never the tolerated ``AssertionError``),
    judged in the same call: the window is real (origin's branch head and
    the judged local tip are distinct 40-hex commits); and while the seams
    are still the P1 shape, the red must be by the NAMED defect — the row
    went Merged, no gh merge argv carried any pin, and the unjudged commit
    IS an ancestor of origin's feature branch — not a harness accident.
    """
    cfg, jpath, journal, gh_log, judged_tip, origin_head = _engine_fixture(
        tmp_path, monkeypatch, move_origin_head=True)
    if judged_tip == origin_head or not (_HEX40.fullmatch(judged_tip)
                                         and _HEX40.fullmatch(origin_head)):
        pytest.fail("CONTROL: the authorization/action window is not real "
                    f"(judged {judged_tip!r}, origin head {origin_head!r})")

    me.merge_pass(cfg, journal=journal, notifier=notify_mod.NullNotifier())

    row = _rowof(cfg, "A")
    merges = _merge_invocations(gh_log)
    origin_repo = tmp_path / "origin"

    if _SELF_STUB or _PIN_REFUSED:
        # While the P1 shape stands the red below must be by the NAMED
        # defect: an UNPINNED merge that landed the moved head.
        if not (row.get("status") == "Merged"
                and merges
                and all("--match-head-commit" not in argv for argv in merges)
                and _is_ancestor(origin_repo, origin_head, "feature/x")):
            pytest.fail(
                "CONTROL: red for the wrong reason — the engine did not "
                "exhibit the measured unpinned-merge defect (status="
                f"{row.get('status')!r}, merges={merges!r})")

    assert row.get("status") == "Awaiting Review", (
        "a merge authorised for the judged tip acted on origin's moved head "
        "— the row went Merged while origin's branch held a tree nobody "
        "judged")
    assert _events(jpath, journal_mod.EventType.pr_merged) == []
    assert not _is_ancestor(origin_repo, origin_head, "feature/x"), (
        "the unjudged commit shipped into origin's feature branch")
    for argv in merges:
        assert _pinned_to(argv, judged_tip), (
            f"a merge attempt was not pinned to the judged tip: {argv!r}")
    assert row.get("needs_rebase") is not True, (
        "the mismatch wore the conflict label — a rebase does not re-judge "
        "a tree")
    for e in _events(jpath, journal_mod.EventType.pr_merge_failed):
        assert e.payload.get("needs_rebase") is False


@pytest.mark.xfail(_SELF_STUB or _PIN_REFUSED, reason=_RED_ENGINE,
                   raises=AssertionError, strict=True)
def test_a_self_approved_merge_on_an_unmoved_head_lands_pinned_and_stamped(
    tmp_path: Path, monkeypatch,
) -> None:
    """The majority path's positive leg: origin's head IS the judged local
    tip, so the self-approved merge lands — pinned (the one merge invocation
    carries ``--match-head-commit <judged tip>``, judged by equality against
    a same-call rev-parse) and stamped (the ``pr_approved`` payload carries
    BOTH contract keys, with the local provenance). A pin that only ever
    refuses would be a denial-of-service wearing the fix's name; this row
    seals that the pinned path still merges.

    RED AT HEAD: the merge lands (control — in both states of the world this
    row's merge succeeds) but unpinned and unstamped.
    """
    cfg, jpath, journal, gh_log, judged_tip, origin_head = _engine_fixture(
        tmp_path, monkeypatch, move_origin_head=False)
    if judged_tip != origin_head:
        pytest.fail("CONTROL: this row's premise is an UNMOVED head; the "
                    "fixture disagrees")

    result = me.merge_pass(cfg, journal=journal,
                           notifier=notify_mod.NullNotifier())

    if result.merged != ["A"] or _rowof(cfg, "A").get("status") != "Merged":
        pytest.fail(
            "CONTROL: the unmoved-head merge must land in BOTH states of "
            f"the world (merged={result.merged!r}) — a pin that refuses a "
            "matching head is a different defect than the one this row seals")

    merges = _merge_invocations(gh_log)
    approved = _events(jpath, journal_mod.EventType.pr_approved)

    if _SELF_STUB or _PIN_REFUSED:
        # The named defect: merged, yes — but unpinned and unstamped.
        if not (merges
                and all("--match-head-commit" not in argv for argv in merges)
                and approved
                and "authorized_head_sha" not in approved[0].payload):
            pytest.fail(
                "CONTROL: red for the wrong reason — expected the measured "
                "unpinned/unstamped merge at HEAD "
                f"(merges={merges!r}, approved={approved!r})")

    assert len(merges) == 1
    assert _pinned_to(merges[0], judged_tip), (
        "the self-approved merge landed WITHOUT being pinned to the tree "
        f"the classifier judged: {merges[0]!r}")
    assert len(approved) == 1
    assert approved[0].payload.get("authorized_head_sha") == judged_tip, (
        "pr_approved carries no authorized_head_sha — the authorization "
        "is not auditable")
    assert approved[0].payload.get("authorized_head_source") == \
        "local_classified_tip"
    assert approved[0].payload.get("risk_level") == "low"


@pytest.mark.xfail(_OID_DROPPED or _PIN_REFUSED, reason=_RED_ENGINE,
                   raises=AssertionError, strict=True)
def test_an_externally_approved_merge_does_not_act_past_the_reviewed_tree(
    tmp_path: Path, monkeypatch,
) -> None:
    """The elevated twin of THE seal: the reviewer approved at the pushed tip
    (the review's ``commit.oid`` — the tree they actually saw), then origin's
    head moved. The merge MUST NOT act on the moved head: the row stays
    Awaiting Review, nothing lands on origin's feature branch, any attempt is
    pinned by equality to the REVIEWED oid, and the ``pr_approved`` payload —
    when the contract keys are present — names the external provenance.

    RED AT HEAD: today's parse drops the oid the pin needs, and the engine
    merges origin's moved head under the external approval.

    Controls (``pytest.fail``): the window is real, and while the P1 shape
    stands the red is by the named defect (Merged, unpinned, moved head
    shipped).
    """
    cfg, jpath, journal, gh_log, judged_tip, origin_head = _engine_fixture(
        tmp_path, monkeypatch, move_origin_head=True,
        labels=["size:S", "financial"])  # forbidden label → elevated
    monkeypatch.setenv("FAKE_GH_REVIEWS", json.dumps([{
        "author": {"login": "reviewer-bot"}, "state": "APPROVED",
        "commit": {"oid": judged_tip},  # the tree the reviewer saw
    }]))
    if judged_tip == origin_head:
        pytest.fail("CONTROL: the reviewed-tree/moved-head window is not real")

    me.merge_pass(cfg, journal=journal, notifier=notify_mod.NullNotifier())

    row = _rowof(cfg, "A")
    merges = _merge_invocations(gh_log)
    origin_repo = tmp_path / "origin"

    if _OID_DROPPED or _PIN_REFUSED:
        if not (row.get("status") == "Merged"
                and merges
                and all("--match-head-commit" not in argv for argv in merges)
                and _is_ancestor(origin_repo, origin_head, "feature/x")):
            pytest.fail(
                "CONTROL: red for the wrong reason — the elevated path did "
                "not exhibit the measured unpinned-merge defect (status="
                f"{row.get('status')!r}, merges={merges!r})")

    assert row.get("status") == "Awaiting Review", (
        "an externally-approved merge acted past the reviewed tree — origin "
        "held a head the reviewer never saw, and it merged anyway")
    assert _events(jpath, journal_mod.EventType.pr_merged) == []
    assert not _is_ancestor(origin_repo, origin_head, "feature/x")
    for argv in merges:
        assert _pinned_to(argv, judged_tip), (
            "an elevated merge attempt was not pinned to the reviewed "
            f"commit.oid: {argv!r}")
    for e in _events(jpath, journal_mod.EventType.pr_approved):
        if "authorized_head_sha" in e.payload:
            assert e.payload["authorized_head_sha"] == judged_tip
            assert e.payload.get("authorized_head_source") == \
                "external_review_commit"
    assert row.get("needs_rebase") is not True
