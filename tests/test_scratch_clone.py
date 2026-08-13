"""Unit DF-4 — P2 seals: the helper refuses rather than producing a dangerous clone.

**P2. Written by an author who did not write the scaffold and will not write
the bodies — the same separation whose absence produced this project's 24
vacuous seals.** Every row seals a PROPERTY of the finished clone or a NAMED
refusal from `src/claude_dispatcher/scratch_clone.py`'s contract; no row
asserts "the helper was called", and no row pins a transient
unimplementedness (this codebase's measured trap).

Every citation is ``Measured under:`` `24e72f0` (tip of
`feat/DF-4-2-...`'s base, carrying the DF-4-1 scaffold), git 2.51.0,
CPython 3.13.7, 2026-08-13, in throwaway repositories under `/tmp` — never
near a real checkout, because taking these measurements near one is the
incident this unit exists to end. Nothing below is carried from the
scaffold's docstring on trust; all eight mechanisms were RE-DERIVED for this
file, and one correction to the scaffold's record fell out (channel 2,
below).

The incident, re-measured for this file
=======================================
A linked worktree's ``.git`` is a FILE (measured: 50 bytes,
``gitdir: <repo>/.git/worktrees/<name>``). After ``cp -a`` of the worktree:

  * ``git -C copy rev-parse --absolute-git-dir`` answered the REAL repo's
    private worktree dir;
  * ``git -C copy revert --no-commit HEAD`` exited 0 and left the ORIGINAL
    worktree — untouched by any command — with exactly ``MM f.txt``, a
    cached diff of 1 file, and a pending ``REVERT_HEAD``;
  * recovery was not clean: ``git revert --abort`` from the real worktree
    then FAILED — ``error: Entry 'f.txt' not uptodate. Cannot merge.`` /
    ``fatal: Could not reset index file`` — exit 128.

And the fix the briefs kept prescribing is insufficient alone: with the
``.git`` file removed and the copy parked under an ancestor repository,
``rev-parse --absolute-git-dir`` answered the ANCESTOR's ``.git`` and
``git update-ref refs/heads/df4probe HEAD`` inside the copy CREATED A BRANCH
IN THE ANCESTOR (exit 0). Removal changes which wrong repo gets mutated.
With ``git init --template=`` at the copy root, both rev-parse flags
answered in-clone from the root and from the deepest directory
(``--git-common-dir`` RELATIVE — ``.git`` at the root, ``../../.git`` two
levels down — which is why every probe below resolves before comparing),
and the incident command died loudly: ``fatal: bad revision 'HEAD'``, 128.

Escape channels, re-measured; one correction to the scaffold's record
=====================================================================
  1. **Inherited ``GIT_DIR``**: pointed at a sentinel repo, ``git init`` at
     a fresh directory created NO ``.git`` there and answered
     ``Reinitialized existing Git repository in <sentinel>/.git/``; inside a
     git-init'd quarantine, ``rev-parse --absolute-git-dir`` answered the
     SENTINEL.
  2. **Nested ``.git`` DIRECTORY carrying ``commondir``**: CORRECTION — a
     directory holding ONLY ``commondir`` is walked past (measured:
     discovery proceeded to the quarantine root and ``--git-common-dir``
     answered ``../.git``). With a ``HEAD`` file beside it — the shape a
     real submodule checkout carries — the scaffold's measurement
     reproduces exactly: ``--absolute-git-dir`` answered INSIDE the clone,
     ``--git-common-dir`` answered the SENTINEL, and ``git update-ref``
     created a branch IN THE SENTINEL. The correction changes no safety
     conclusion (the sever removes every ``.git`` whatever its innards);
     it changes what a NON-VACUOUS control must construct, so the control
     in row 4 builds the honored form.
  3. **Alternates**: ``objects/info/alternates`` in the quarantine's own
     ``.git`` made ``git cat-file -t <sentinel commit>`` answer ``commit``
     (it was exit 128 before the line was written) while
     ``--absolute-git-dir`` still answered in-clone.
  4. **A symlink not named ``.git``**: ``clone/notgit → <sentinel>/.git``
     accepted a file write that landed inside the sentinel's git dir.
  5. **A nested ``.git`` FILE**: ``pkg/.git`` containing
     ``gitdir: <sentinel>/.git`` routed ``update-ref`` into the sentinel
     (branch created, exit 0).

Hazard B, re-measured: a same-size (33-byte) rewrite of ``mod.py`` given the
ORIGINAL's exact ``st_mtime_ns`` imported as the ORIGINAL — the mutant never
ran; the same rewrite with mtime advanced 2 s imported as the mutant.

Baseline, measured here rather than taken on trust
===================================================
Measured under `24e72f0`, ``PYTHONPATH=src python -m pytest tests/ -q
-o addopts=""`` (the ``-o addopts=""`` per unit D8-guard's header; the
vendored TypeScript parser fetched first — without it 87 rows of
`test_ts_comparator.py` fail on the gitignored ``typescript.js``, exactly
as that unit's header warns a fresh worktree):

  * WITHOUT this file: **2532 passed + 13 skipped, 0 failed**, 152.17 s.
  * WITH this file: **2534 passed + 13 skipped + 8 xfailed, 0 failed**,
    exit 0, 153.50 s — exactly this file's two green rows and eight
    conditioned-red rows added, and no row in any other file moved.

Expected state of these rows TODAY, stated so nobody infers vacuity
===================================================================
Rows 1–7 and 10 exercise the five P1 STUBS and are RED at the stub's
``NotImplementedError``; rows 8 and 9 seal the tables the scaffold
implemented (``scrubbed_git_env``, the refusal message fold, the records)
and are GREEN. Every red row runs its in-call CONTROL first — the control
re-derives the danger live, so the row cannot go red for a stale reason and
cannot later go green vacuously — and reaches the stub raise as its LAST
event. DF-4-3 turns rows 1–7 and 10 green by writing bodies, never by
editing this file.

CHOICE — how "committed RED" meets a gate with no seals carve-out. The
repo's own test gate (`.dispatcher.yaml`) runs the whole suite and treats
exit 0 as green, with no role carve-out; concurrent units measure
whole-suite baselines (unit D8-guard's header is such a measurement); and
BODIES is DENIED ``tests/**`` (`role_protocol.py`: "P3 makes the seals pass
by implementing them, never by editing them"), so no marker requiring a P3
edit can ever be removed. Therefore every red row carries
``pytest.mark.xfail(condition=<the seam still raises the P1 stub>,
raises=NotImplementedError, strict=True)``:

  * the condition is computed at import time by CALLING the seam — the
    marker exists exactly as long as the stub does and self-retires the
    commit a body lands, with no test edit and no silent XPASS;
  * ``raises=NotImplementedError`` pins the ONLY tolerated failure to the
    stub raise — a control assertion failing today reports as a real
    failure, not an xfail;
  * rejected: plain red (fails the gate this repo actually runs, and
    poisons every concurrent unit's baseline until DF-4-3); unconditional
    xfail (unremovable — P3 may not edit tests, and DF-4-4's
    ``disputed_paths`` is ``roles/coder.md`` alone); ``pytest.skip`` on
    stub detection (a skipped row runs NO control; these controls are live
    re-measurements and must run on every suite invocation).

Harness note: this file builds its fixtures under its OWN environment scrub
(``_env`` below) rather than through ``scrubbed_git_env`` — a harness that
reached through the module under seal would go green and red with that
module. ``scrubbed_git_env`` is sealed by row 8 against the contract text,
not used as plumbing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import dataclasses
from pathlib import Path

import pytest

from claude_dispatcher import scratch_clone as sc


# --------------------------------------------------------------------------
# Harness: fixture-building git, under the harness's OWN scrub (see header).
# --------------------------------------------------------------------------

def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Env for HARNESS git calls: GIT_* dropped, config pinned, identity set.

    Deliberately not :func:`sc.scrubbed_git_env` — independence, see header.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "df4-seal",
        "GIT_AUTHOR_EMAIL": "df4-seal@test",
        "GIT_COMMITTER_NAME": "df4-seal",
        "GIT_COMMITTER_EMAIL": "df4-seal@test",
    })
    if extra:
        env.update(extra)
    return env


def _git(*args: str, cwd: Path, env: dict[str, str] | None = None,
         check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, env=env or _env(),
        capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            f"harness git {' '.join(args)} in {cwd} failed "
            f"rc={proc.returncode}: {proc.stderr}"
        )
    return proc


def _mk_repo(base: Path, name: str) -> Path:
    """A plain repository with one commit (sentinel / umbrella roles)."""
    repo = base / name
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "seed.txt").write_text("seed\n")
    _git("add", "seed.txt", cwd=repo)
    _git("commit", "-qm", "seed", cwd=repo)
    return repo


def _mk_source(base: Path, name: str) -> tuple[Path, Path]:
    """A repository plus a LINKED WORKTREE shaped like the incident's.

    c1 adds ``f.txt`` ("one") and ``sub/g.txt``; c2 changes ONLY ``f.txt``
    ("two"), so ``git revert --no-commit HEAD`` stages exactly one path —
    the measured incident produced exactly ``MM f.txt``. The worktree also
    carries an UNTRACKED file and inherited bytecode, because the guarantee
    speaks about the worktree's TREE CONTENT, not about what is committed —
    a body built on ``git archive`` would drop ``notes.txt`` and row 1
    would catch it.
    """
    repo = base / f"{name}-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "f.txt").write_text("one\n")
    (repo / "sub").mkdir()
    (repo / "sub" / "g.txt").write_text("g\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "c1", cwd=repo)
    (repo / "f.txt").write_text("two\n")
    _git("add", "f.txt", cwd=repo)
    _git("commit", "-qm", "c2", cwd=repo)
    wt = base / f"{name}-wt"
    _git("worktree", "add", "--detach", str(wt), "HEAD", cwd=repo)
    (wt / "notes.txt").write_text("untracked travels with the tree\n")
    (wt / "__pycache__").mkdir()
    (wt / "__pycache__" / "junk.cpython-313.pyc").write_bytes(b"\x00junk")
    (wt / "stray.pyc").write_bytes(b"\x00stray")
    return repo, wt


def _cp_a(src: Path, dst: Path) -> Path:
    """The naive copy the incident was made of (``cp -a`` semantics)."""
    shutil.copytree(src, dst, symlinks=True)
    return dst


def _hand_quarantine(wt: Path, dest: Path) -> Path:
    """A compliant clone built BY THE GUARANTEE'S RECIPE, not by the helper.

    Rows sealing :func:`sc.assert_isolated` and the swap seams need a
    conforming tree while :func:`sc.make_scratch_clone` is a stub; building
    it through the helper would chain every probe row's verdict to the
    builder's. Copy, remove every ``.git`` of every kind, purge bytecode,
    ``git init --template=`` under the harness scrub.
    """
    shutil.copytree(wt, dest, symlinks=True)
    for entry in sorted(dest.rglob(".git"), reverse=True):
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        else:
            shutil.rmtree(entry)
    for d in sorted(dest.rglob("__pycache__"), reverse=True):
        shutil.rmtree(d)
    for f in dest.rglob("*.pyc"):
        f.unlink()
    _git("init", "-q", "--template=", cwd=dest)
    return dest


def _abs_git_dir(cwd: Path, env: dict[str, str] | None = None) -> Path:
    out = _git("rev-parse", "--absolute-git-dir", cwd=cwd, env=env)
    return Path(out.stdout.strip()).resolve()


def _common_dir(cwd: Path) -> Path:
    """``--git-common-dir`` answers RELATIVE to cwd (measured); resolve it."""
    raw = Path(_git("rev-parse", "--git-common-dir", cwd=cwd).stdout.strip())
    return (raw if raw.is_absolute() else cwd / raw).resolve()


def _dirty(wt: Path) -> list[str]:
    """Non-untracked status lines — the incident's signature lives here."""
    out = _git("status", "--porcelain=v1", cwd=wt).stdout.splitlines()
    return [line for line in out if not line.startswith("??")]


def _refs(repo: Path) -> str:
    return _git("for-each-ref", cwd=repo).stdout


# --------------------------------------------------------------------------
# Stub detection for the conditioned xfail markers (header CHOICE block).
# Each probe hands the seam an input its CONTRACT refuses cheaply, so an
# implemented body answers with ScratchCloneError (→ not stubbed) and never
# touches the filesystem beyond a stat of a nonexistent path.
# --------------------------------------------------------------------------

def _is_stub(thunk) -> bool:
    try:
        thunk()
    except NotImplementedError:
        return True
    except BaseException:
        return False
    return False


_NOWHERE = Path("/nonexistent/df4-seal")
_PROBE_RECEIPT = sc.ScratchClone(
    path=_NOWHERE / "clone", source=_NOWHERE / "src",
    git_dir=_NOWHERE / "clone" / ".git",
)
_STUB_MAKE = _is_stub(
    lambda: sc.make_scratch_clone(_NOWHERE / "src", _NOWHERE / "dst"))
_STUB_ISOLATED = _is_stub(lambda: sc.assert_isolated(_NOWHERE / "clone"))
_STUB_SWAP_IN = _is_stub(
    lambda: sc.swap_in(_PROBE_RECEIPT, "../escape", b""))
_STUB_SWAP_BACK = _is_stub(
    lambda: sc.swap_back(_PROBE_RECEIPT, sc.SwapToken(
        relpath="../escape", original=b"", mutated_mtime_ns=0)))
_STUB_MAIN = _is_stub(lambda: sc.main([]))

_RED_TODAY = (
    "RED by design at P2: the seam under seal still raises the P1 stub's "
    "NotImplementedError. The marker is conditioned on that stub and "
    "self-retires when DF-4-3 lands the body — no test edit. Any failure "
    "other than the stub raise reports as a real failure even today."
)

_NS = 10 ** 9


# --------------------------------------------------------------------------
# Row 1 — THE row: a scratch clone of a linked worktree cannot reach the
# source repository, proven by running the INCIDENT COMMAND inside it.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_MAKE, raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_clone_of_linked_worktree_cannot_reach_the_source_repo(tmp_path):
    """git inside the finished clone must not mutate the source repository.

    CONTROL (pair A, judged first, live on every run): a naive ``cp -a`` of
    an IDENTICAL construction reaches the real repo — rev-parse answers
    under it, and ``git revert --no-commit HEAD`` inside the copy exits 0
    and leaves the ORIGINAL worktree ``MM f.txt`` with a pending
    ``REVERT_HEAD``. Measured under 24e72f0 and re-derived here in-call.

    FALSIFY: implement :func:`sc.make_scratch_clone` as ``cp -a`` and the
    helper half of this row fails at the rev-parse assertion and again at
    the untouched-original assertions — the control half proves those
    outcomes on this exact construction, so this row CANNOT pass a naive
    copy. Implement it as ``git archive`` (tracked files only) and the
    ``notes.txt`` assertion fails. Skip the bytecode purge and the
    ``*.pyc`` assertion fails.
    """
    # -- CONTROL: the incident, re-derived live -------------------------
    repo_a, wt_a = _mk_source(tmp_path, "a")
    copy_a = _cp_a(wt_a, tmp_path / "copy-a")
    assert _abs_git_dir(copy_a).is_relative_to(repo_a.resolve()), (
        "control broke: a cp -a copy no longer resolves to the real repo; "
        "every conclusion below would be about a world that changed"
    )
    assert _git("revert", "--no-commit", "HEAD", cwd=copy_a).returncode == 0
    assert _dirty(wt_a) == ["MM f.txt"], (
        "control broke: the incident no longer reproduces (expected the "
        "measured 'MM f.txt' in the ORIGINAL worktree)"
    )
    assert list((repo_a / ".git").rglob("REVERT_HEAD")), (
        "control broke: no pending REVERT_HEAD in the real repo"
    )

    # -- HELPER: same construction, fresh pair, full guarantee ----------
    repo_b, wt_b = _mk_source(tmp_path, "b")
    refs_before = _refs(repo_b)
    dest = tmp_path / "clone-b"
    clone = sc.make_scratch_clone(wt_b, dest)

    # The receipt names what it must (contract: ScratchClone fields).
    assert clone.path == dest
    assert clone.git_dir == dest / ".git"
    assert clone.source == wt_b

    # Guarantee 4: quarantine at the root; discovery terminates in-clone
    # from the root AND from a deep directory, on BOTH rev-parse answers.
    assert (dest / ".git").is_dir()
    quarantine = (dest / ".git").resolve()
    for probe_cwd in (dest, dest / "sub"):
        assert _abs_git_dir(probe_cwd) == quarantine
        assert _common_dir(probe_cwd) == quarantine

    # THE incident command, inside the finished clone. Its exit code is
    # not the property (in quarantine it dies: measured ``fatal: bad
    # revision 'HEAD'``); the property is that the source repository is
    # bit-for-bit UNTOUCHED afterwards.
    _git("revert", "--no-commit", "HEAD", cwd=dest, check=False)
    assert _dirty(wt_b) == []
    assert _git("diff", "--cached", cwd=wt_b).stdout == ""
    assert not list((repo_b / ".git").rglob("REVERT_HEAD"))
    assert _refs(repo_b) == refs_before

    # Guarantee 1: tree content equals the source worktree's, minus git
    # metadata and bytecode — untracked files INCLUDED.
    assert (dest / "f.txt").read_bytes() == (wt_b / "f.txt").read_bytes()
    assert (dest / "sub" / "g.txt").read_bytes() == b"g\n"
    assert (dest / "notes.txt").read_bytes() == (
        wt_b / "notes.txt").read_bytes()
    assert not list(dest.rglob("__pycache__"))
    assert not list(dest.rglob("*.pyc"))

    # Guarantee 2: the only .git under the clone is the quarantine's own.
    assert list(dest.rglob(".git")) == [dest / ".git"]


# --------------------------------------------------------------------------
# Row 2 — the clone parked under an ANCESTOR repo still terminates in-clone:
# removing the gitdir pointer alone only changes which wrong repo bleeds.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_MAKE, raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_discovery_under_an_ancestor_repo_terminates_in_the_clone(tmp_path):
    """The quarantine — not the sever — is what stops the upward walk.

    CONTROL: the briefs' old fix ("remove the .git FILE first") applied to
    a copy parked under an umbrella repository: rev-parse resolves to the
    UMBRELLA and ``git update-ref`` inside the copy creates a branch there
    (measured under 24e72f0, re-derived here in-call).

    FALSIFY: implement make_scratch_clone as copy-plus-sever with no
    ``git init`` — this row's rev-parse assertions fail exactly the way the
    control half proves.
    """
    umbrella = _mk_repo(tmp_path, "umbrella")
    inner = umbrella / "inner"
    inner.mkdir()
    _, wt = _mk_source(tmp_path, "src")

    # -- CONTROL: sever-only copy under the ancestor ---------------------
    naive = _cp_a(wt, inner / "naive")
    (naive / ".git").unlink()
    assert _abs_git_dir(naive) == (umbrella / ".git").resolve(), (
        "control broke: discovery no longer walks up to the ancestor"
    )
    _git("update-ref", "refs/heads/df4probe", "HEAD", cwd=naive)
    assert "refs/heads/df4probe" in _refs(umbrella), (
        "control broke: the ancestor mutation no longer reproduces"
    )
    _git("update-ref", "-d", "refs/heads/df4probe", cwd=umbrella)
    refs_before = _refs(umbrella)

    # -- HELPER: clone at the same depth under the same ancestor ---------
    dest = inner / "clone"
    sc.make_scratch_clone(wt, dest)
    quarantine = (dest / ".git").resolve()
    for probe_cwd in (dest, dest / "sub"):
        assert _abs_git_dir(probe_cwd) == quarantine
        assert _common_dir(probe_cwd) == quarantine
    # Whatever a ref write inside the clone does (in quarantine it dies on
    # an unresolvable HEAD), the ancestor must not absorb it.
    _git("update-ref", "refs/heads/df4probe", "HEAD", cwd=dest, check=False)
    assert _refs(umbrella) == refs_before
    assert _dirty(umbrella) == []


# --------------------------------------------------------------------------
# Row 3 — the standalone probe: refuses a naive copy, passes a compliant
# quarantine. Both halves in ONE call, so "refuses everything" and "passes
# everything" both redden it.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_ISOLATED, raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_assert_isolated_refuses_a_naive_copy_and_passes_a_quarantine(
        tmp_path):
    """assert_isolated is the checkable half of "the helper succeeded".

    The compliant tree is built by :func:`_hand_quarantine` — the
    guarantee's own recipe, NOT the helper — so this row's verdict does not
    chain to :func:`sc.make_scratch_clone`'s stub.

    FALSIFY: a probe that only checks ``--absolute-git-dir`` still refuses
    the cp -a copy here, but row 4's commondir channel catches it; a probe
    that refuses unconditionally fails this row's second half; one that
    passes unconditionally fails the first.
    """
    repo, wt = _mk_source(tmp_path, "s")
    copy = _cp_a(wt, tmp_path / "naive")
    # Control: this copy genuinely reaches the real repository.
    assert _abs_git_dir(copy).is_relative_to(repo.resolve())
    with pytest.raises(sc.ScratchCloneError) as excinfo:
        sc.assert_isolated(copy)
    assert excinfo.value.refusal is sc.Refusal.ISOLATION_UNVERIFIED

    good = _hand_quarantine(wt, tmp_path / "good")
    assert sc.assert_isolated(good) is None


# --------------------------------------------------------------------------
# Row 4 — the probe refuses each measured escape channel, and passes again
# once the injection is removed (cause attribution, not coincidence).
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_ISOLATED, raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_assert_isolated_refuses_each_measured_escape_channel(tmp_path):
    """Each injection is proven LIVE to reach the sentinel before the probe
    is asked about it — a control per channel, in-call, so no refusal below
    is about a hazard that stopped existing.

    Channels (header, re-measured under 24e72f0): nested ``.git`` dir with
    ``HEAD`` + ``commondir`` (ref write lands in the sentinel); nested
    ``.git`` FILE gitdir pointer (same); alternates in the quarantine's own
    ``.git`` (sentinel objects readable in-clone while --absolute-git-dir
    answers in-clone); a symlink under ANY name resolving outside the clone
    (write through it lands in the sentinel); and the CHOICE that a benign
    out-of-tree symlink is refused too — unprovable gets the same answer as
    unsafe.
    """
    _, wt = _mk_source(tmp_path, "s")
    sentinel = _mk_repo(tmp_path, "sentinel")
    sentinel_head = _git(
        "rev-parse", "HEAD", cwd=sentinel).stdout.strip()
    clone = _hand_quarantine(wt, tmp_path / "clone")
    sc.assert_isolated(clone)  # control: the base tree is compliant

    def _refused() -> None:
        with pytest.raises(sc.ScratchCloneError) as excinfo:
            sc.assert_isolated(clone)
        assert excinfo.value.refusal is sc.Refusal.ISOLATION_UNVERIFIED

    # (2) nested .git DIRECTORY: HEAD + commondir → the sentinel.
    nested = clone / "sub" / ".git"
    nested.mkdir()
    (nested / "HEAD").write_text("ref: refs/heads/main\n")
    (nested / "commondir").write_text(f"{sentinel / '.git'}\n")
    _git("update-ref", "refs/heads/df4-escaped", "HEAD", cwd=clone / "sub")
    assert "refs/heads/df4-escaped" in _refs(sentinel), (
        "control broke: the commondir channel no longer reaches the "
        "sentinel"
    )
    _git("update-ref", "-d", "refs/heads/df4-escaped", cwd=sentinel)
    _refused()
    shutil.rmtree(nested)
    sc.assert_isolated(clone)

    # (5) nested .git FILE: a gitdir pointer at any depth.
    pkg = clone / "pkg"
    pkg.mkdir()
    (pkg / ".git").write_text(f"gitdir: {sentinel / '.git'}\n")
    assert _abs_git_dir(pkg) == (sentinel / ".git").resolve(), (
        "control broke: the gitfile channel no longer reaches the sentinel"
    )
    _refused()
    shutil.rmtree(pkg)
    sc.assert_isolated(clone)

    # (3) alternates inside the quarantine's own .git.
    assert _git("cat-file", "-t", sentinel_head, cwd=clone,
                check=False).returncode != 0  # control, before
    info = clone / ".git" / "objects" / "info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "alternates").write_text(f"{sentinel / '.git' / 'objects'}\n")
    assert _git("cat-file", "-t", sentinel_head,
                cwd=clone).stdout.strip() == "commit", (
        "control broke: the alternates channel no longer reads the "
        "sentinel's objects"
    )
    _refused()
    (info / "alternates").unlink()
    sc.assert_isolated(clone)

    # (4) a symlink not named .git, resolving outside the clone.
    link = clone / "notgit"
    link.symlink_to(sentinel / ".git")
    (link / "df4-probe").write_text("landed\n")
    assert (sentinel / ".git" / "df4-probe").exists(), (
        "control broke: a write through the symlink no longer lands in "
        "the sentinel"
    )
    (sentinel / ".git" / "df4-probe").unlink()
    _refused()
    link.unlink()
    sc.assert_isolated(clone)

    # (4b) CHOICE sealed: even a benign-looking out-of-tree target refuses.
    benign_target = tmp_path / "benign.txt"
    benign_target.write_text("harmless\n")
    (clone / "benign-link").symlink_to(benign_target)
    _refused()
    (clone / "benign-link").unlink()
    sc.assert_isolated(clone)


# --------------------------------------------------------------------------
# Row 5 — preflight refusals: named states, nothing destroyed, no byte
# copied before the check that owns it.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_MAKE, raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_preflight_refusals_are_named_and_destroy_nothing(tmp_path):
    """Every refusal carries exactly the contract's member, and the helper
    neither creates the destination on a refused preflight nor deletes
    anything it did not create.

    The source-inside-destination direction is asserted as EITHER
    ``DEST_COLLISION`` or ``NESTED_PATHS``: with an existing source inside
    it the destination necessarily exists, so both named refusals are
    reachable depending on step order, both are refusals-before-any-byte,
    and pinning the tiebreak would seal the contract's step ORDER — which
    no measured defect demands.
    """
    repo, wt = _mk_source(tmp_path, "s")

    def _refuses(source: Path, dest: Path,
                 *members: sc.Refusal) -> sc.ScratchCloneError:
        with pytest.raises(sc.ScratchCloneError) as excinfo:
            sc.make_scratch_clone(source, dest)
        assert excinfo.value.refusal in members
        return excinfo.value

    # SOURCE_UNUSABLE: a missing path.
    _refuses(tmp_path / "absent", tmp_path / "d1", sc.Refusal.SOURCE_UNUSABLE)
    assert not (tmp_path / "d1").exists()

    # SOURCE_UNUSABLE: an existing directory that is NOT a git worktree —
    # the CHOICE row: accepting any directory is cp -a wearing the
    # helper's name.
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "x.txt").write_text("x\n")
    _refuses(plain, tmp_path / "d2", sc.Refusal.SOURCE_UNUSABLE)
    assert not (tmp_path / "d2").exists()

    # DEST_COLLISION: an existing file survives byte-for-byte.
    victim_file = tmp_path / "victim.bin"
    victim_file.write_bytes(b"precious bytes the helper never made")
    _refuses(wt, victim_file, sc.Refusal.DEST_COLLISION)
    assert victim_file.read_bytes() == (
        b"precious bytes the helper never made")

    # DEST_COLLISION: an existing directory keeps its children.
    victim_dir = tmp_path / "victim-dir"
    victim_dir.mkdir()
    (victim_dir / "keep.txt").write_text("keep\n")
    _refuses(wt, victim_dir, sc.Refusal.DEST_COLLISION)
    assert (victim_dir / "keep.txt").read_text() == "keep\n"

    # NESTED_PATHS: a clone into its own source.
    _refuses(wt, wt / "scratch", sc.Refusal.NESTED_PATHS)
    assert not (wt / "scratch").exists()

    # Source inside destination (see docstring for why two members).
    _refuses(wt, wt.parent, sc.Refusal.NESTED_PATHS,
             sc.Refusal.DEST_COLLISION)

    # After ALL refusals: the source worktree is exactly as built.
    assert _dirty(wt) == []
    assert (wt / "f.txt").read_text() == "two\n"


# --------------------------------------------------------------------------
# Row 6 — the swap seams defeat CPython's (mtime-second, size) bytecode key.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_SWAP_IN or _STUB_SWAP_BACK,
                   raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_swap_roundtrip_defeats_the_bytecode_key(tmp_path):
    """swap_in/swap_back stride the mtime past every state they replace.

    CONTROL (live, this interpreter): a same-size rewrite handed the
    original's exact ``st_mtime_ns`` imports as the ORIGINAL — the mutant
    never runs; +2 s and the mutant runs. Re-derived in-call because the
    entire value of the stride rests on this interpreter still keying
    bytecode that way.

    The stride floor is hard-coded 2 s — the measured clearing value — not
    read from :data:`sc.MTIME_ADVANCE_SECONDS`, so a body that lowers the
    constant and strides by it cannot make this row agree with itself; the
    constant is additionally sealed to >= 2.

    FALSIFY: write the bytes without touching mtime (the naive
    implementation) and both stride assertions fail; restore by checkout
    from a repository and there is no repository to restore from — the
    quarantine is empty.
    """
    # -- CONTROL: the trap, re-derived on this interpreter ---------------
    lab = tmp_path / "pyc-lab"
    lab.mkdir()
    original_src = 'def val():\n    return "ORIGINAL"\n'
    mutated_src = 'def val():\n    return "MUTATED_"\n'
    assert len(original_src) == len(mutated_src)  # same size, by design

    def _imported(cwd: Path) -> str:
        out = subprocess.run(
            [sys.executable, "-c", "import mod; print(mod.val())"],
            cwd=cwd, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()

    (lab / "mod.py").write_text(original_src)
    assert _imported(lab) == "ORIGINAL"
    key_ns = (lab / "mod.py").stat().st_mtime_ns
    (lab / "mod.py").write_text(mutated_src)
    os.utime(lab / "mod.py", ns=(key_ns, key_ns))
    assert _imported(lab) == "ORIGINAL", (
        "control broke: a same-(mtime,size) rewrite no longer serves stale "
        "bytecode on this interpreter — re-measure before trusting strides"
    )
    os.utime(lab / "mod.py", ns=(key_ns + 2 * _NS, key_ns + 2 * _NS))
    assert _imported(lab) == "MUTATED_"

    # -- SEAM: roundtrip with the stride, inside a compliant clone -------
    assert sc.MTIME_ADVANCE_SECONDS >= 2
    _, wt = _mk_source(tmp_path, "s")
    (wt / "mod.py").write_text(original_src)
    clone_path = _hand_quarantine(wt, tmp_path / "clone")
    receipt = sc.ScratchClone(
        path=clone_path, source=wt, git_dir=clone_path / ".git")

    target = clone_path / "mod.py"
    before_ns = target.stat().st_mtime_ns
    token = sc.swap_in(receipt, "mod.py", mutated_src.encode())

    assert target.read_bytes() == mutated_src.encode()
    after_ns = target.stat().st_mtime_ns
    assert after_ns >= before_ns + 2 * _NS
    assert token.relpath == "mod.py"
    assert token.original == original_src.encode()
    assert token.mutated_mtime_ns == after_ns

    sc.swap_back(receipt, token)
    assert target.read_bytes() == original_src.encode()
    assert target.stat().st_mtime_ns >= token.mutated_mtime_ns + 2 * _NS
    # The restore came from the token's bytes: the quarantine repo has no
    # objects to check anything out of, and no backup file lingers.
    assert not list(clone_path.rglob("*.orig"))
    assert not list(clone_path.rglob("*.bak"))


# --------------------------------------------------------------------------
# Row 7 — the swap seams refuse escapes and absent targets, touching nothing
# outside the clone.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_SWAP_IN or _STUB_SWAP_BACK,
                   raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_swap_seams_refuse_escapes_and_missing_targets(tmp_path):
    """A seam write that would land outside the quarantined tree is Hazard A
    with this module's name on it (contract), so every escape spelling is
    refused and the would-be victim is untouched — asserted on bytes, not
    on the refusal alone.
    """
    _, wt = _mk_source(tmp_path, "s")
    clone_path = _hand_quarantine(wt, tmp_path / "clone")
    receipt = sc.ScratchClone(
        path=clone_path, source=wt, git_dir=clone_path / ".git")

    victim = tmp_path / "victim.py"
    victim.write_bytes(b"outside the clone; must never change")

    def _swap_refused(relpath: str, member: sc.Refusal) -> None:
        with pytest.raises(sc.ScratchCloneError) as excinfo:
            sc.swap_in(receipt, relpath, b"payload")
        assert excinfo.value.refusal is member

    # .. traversal, absolute path, symlink whose target is outside.
    _swap_refused("../victim.py", sc.Refusal.SWAP_ESCAPES_CLONE)
    _swap_refused(str(victim), sc.Refusal.SWAP_ESCAPES_CLONE)
    (clone_path / "link.py").symlink_to(victim)
    _swap_refused("link.py", sc.Refusal.SWAP_ESCAPES_CLONE)
    (clone_path / "link.py").unlink()

    # A mutation probe mutates; it does not create.
    _swap_refused("absent.py", sc.Refusal.SWAP_TARGET_MISSING)
    assert not (clone_path / "absent.py").exists()

    # swap_back is bound by the same refusals: a forged token cannot write
    # outside the clone either.
    forged = sc.SwapToken(relpath="../victim.py",
                          original=b"payload", mutated_mtime_ns=0)
    with pytest.raises(sc.ScratchCloneError) as excinfo:
        sc.swap_back(receipt, forged)
    assert excinfo.value.refusal is sc.Refusal.SWAP_ESCAPES_CLONE

    assert victim.read_bytes() == b"outside the clone; must never change"


# --------------------------------------------------------------------------
# Row 8 — GREEN today: scrubbed_git_env, sealed against the contract and
# against the measured GIT_DIR reroute, live.
# --------------------------------------------------------------------------

def test_scrubbed_git_env_drops_routing_pins_config_and_defeats_git_dir(
        tmp_path):
    """The scrub drops every GIT_*, applies exactly the pins, mutates
    nothing, and — behaviorally — makes ``git init`` land where it was
    pointed even under an inherited ``GIT_DIR``.

    CONTROL (live): under the polluted environment, ``git init`` at a fresh
    directory creates NO ``.git`` there and reinitializes the sentinel —
    the measured escape channel 1. Under the scrub of that SAME
    environment, the quarantine lands at the cwd.
    """
    base = {
        "PATH": os.environ.get("PATH", ""),
        "KEEPME": "yes",
        "GIT_DIR": "/somewhere/.git",
        "GIT_WORK_TREE": "/elsewhere",
        "GIT_INDEX_FILE": "/an/index",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.hooksPath",
        "GIT_CONFIG_VALUE_0": "/hooks",
    }
    snapshot = dict(base)
    env = sc.scrubbed_git_env(base)
    assert {k for k in env if k.startswith("GIT_")} == set(sc.GIT_ENV_PINS)
    for key, value in sc.GIT_ENV_PINS.items():
        assert env[key] == value
    assert env["KEEPME"] == "yes"
    assert env["PATH"] == base["PATH"]
    assert base == snapshot and env is not base  # pure, fresh dict
    # Default-base form: reads os.environ, same postcondition.
    ambient = sc.scrubbed_git_env()
    assert {k for k in ambient if k.startswith("GIT_")} == set(
        sc.GIT_ENV_PINS)

    # -- BEHAVIORAL: the measured channel-1 pair, live -------------------
    sentinel = _mk_repo(tmp_path, "sentinel")
    polluted = _env({"GIT_DIR": str(sentinel / ".git")})

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    _git("init", "-q", cwd=fresh, env=polluted)
    assert not (fresh / ".git").exists(), (
        "control broke: an inherited GIT_DIR no longer reroutes git init"
    )

    fresh2 = tmp_path / "fresh2"
    fresh2.mkdir()
    _git("init", "-q", cwd=fresh2, env=sc.scrubbed_git_env(polluted))
    assert (fresh2 / ".git").is_dir()
    assert _abs_git_dir(
        fresh2, env=sc.scrubbed_git_env(polluted)
    ) == (fresh2 / ".git").resolve()


# --------------------------------------------------------------------------
# Row 9 — GREEN today: the refusal table is total and guarded, the error and
# the records carry what the contract says they carry.
# --------------------------------------------------------------------------

def test_refusal_messages_are_total_and_the_guard_names_the_asked_refusal(
        monkeypatch):
    """Totality over the enum, the guard's fidelity to the ASKED member, the
    detail suffix, the error record's fields, and the frozen receipts.

    The guard row reaches into ``_REFUSAL_MESSAGES`` (private) because the
    guard IS contract — "a fold with a default is where a twelfth member
    would silently read as the eleventh" — and there is no public seam that
    can make a member message-less.
    """
    for member in sc.Refusal:
        line = sc.refusal_message(member)
        assert isinstance(line, str) and line.startswith("scratch-clone")
        assert "REFUSED" in line  # no member reads as success by omission
    assert sc.refusal_message(
        sc.Refusal.COPY_FAILED, "ENOSPC").endswith("[ENOSPC]")

    monkeypatch.delitem(sc._REFUSAL_MESSAGES, sc.Refusal.COPY_FAILED)
    with pytest.raises(sc.ScratchCloneError) as excinfo:
        sc.refusal_message(sc.Refusal.COPY_FAILED)
    assert excinfo.value.refusal is sc.Refusal.COPY_FAILED, (
        "the totality guard must carry the refusal it was ASKED about, "
        "never misreport the caller's state"
    )
    monkeypatch.undo()

    err = sc.ScratchCloneError(
        sc.Refusal.DEST_COLLISION, detail="/tmp/x", cleanup_failed=True)
    assert err.refusal is sc.Refusal.DEST_COLLISION
    assert err.detail == "/tmp/x"
    assert err.cleanup_failed is True
    assert "never overwrites" in str(err) and "[/tmp/x]" in str(err)
    default_err = sc.ScratchCloneError(sc.Refusal.COPY_FAILED)
    assert default_err.cleanup_failed is False

    receipt = sc.ScratchClone(
        path=Path("/c"), source=Path("/s"), git_dir=Path("/c/.git"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        receipt.path = Path("/elsewhere")  # type: ignore[misc]
    token = sc.SwapToken(relpath="a", original=b"b", mutated_mtime_ns=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.relpath = "z"  # type: ignore[misc]


# --------------------------------------------------------------------------
# Row 10 — the CLI face: exit codes 0/2/3, the path alone on stdout, the
# refusal line on stderr, and the printed clone is a real quarantine.
# --------------------------------------------------------------------------

@pytest.mark.xfail(_STUB_MAIN or _STUB_MAKE,
                   raises=NotImplementedError, strict=True,
                   reason=_RED_TODAY)
def test_cli_face_exit_codes_and_stdout_contract(tmp_path, capsys):
    """One line to invoke, ``$(...)``-capturable on success, loud on refusal.

    ``main`` is sealed as the FUNCTION the contract declares (returns int);
    a body that ``sys.exit``s instead of returning reds this row, and that
    is the contract's text ("prints ... and exits 0" via the ``__main__``
    shim, which is the only caller of SystemExit).
    """
    _, wt = _mk_source(tmp_path, "s")

    assert sc.main([]) == 3
    assert sc.main([str(wt)]) == 3
    assert sc.main([str(wt), str(tmp_path / "d"), "extra"]) == 3

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    capsys.readouterr()  # drain anything usage printed
    assert sc.main([str(wt), str(occupied)]) == 2
    captured = capsys.readouterr()
    assert "REFUSED" in captured.err
    assert captured.out == ""  # stdout stays $(...)-clean on refusal

    dest = tmp_path / "cli-clone"
    assert sc.main([str(wt), str(dest)]) == 0
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 1
    assert Path(lines[0]).resolve() == dest.resolve()
    # The printed path is a real quarantine, not a receipt for hope.
    assert _abs_git_dir(dest) == (dest / ".git").resolve()
