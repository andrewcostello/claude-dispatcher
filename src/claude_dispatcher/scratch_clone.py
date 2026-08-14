"""Unit DF-4 — a scratch clone of a worktree that cannot reach the real repo.

**P1 wrote this contract and the tables; P2 (DF-4-2) sealed it from
outside; P3 (DF-4-3, this revision) filled the four control-flow bodies and
the CLI face against those seals. P4 adjudicates and decides whether the
helper becomes mandatory in role briefs.**

Every citation below is `Measured under:` `6293f424` (`main`, the base of
`feat/DF-4-1-...`), git 2.51.0, CPython 3.13.7, 2026-08-13, unless a line
says otherwise. The measurements were taken in throwaway repositories under
`/tmp` — this unit exists because taking them anywhere near a real repo is
exactly the accident being fixed.

Why this unit exists — measured three times before it was a task
================================================================
Three separate agents in the 2026-08-07..12 effort made a `cp -a` copy of a
linked worktree to probe in, and a git command inside the copy operated on
the real repository — most recently a `git revert --no-commit` probe that
MOVED THE REAL INDEX. Every brief already said "remove the .git FILE first".
The sentence did not hold; a helper is the durable form.

The mechanism, re-measured for this scaffold rather than carried from the
incident reports:

  * A linked worktree's ``.git`` is a FILE, not a directory — 54 bytes of
    ``gitdir: <real>/.git/worktrees/<name>``. ``cp -a`` copies it verbatim,
    so ``git -C <copy> rev-parse --absolute-git-dir`` answers the REAL
    repository's private worktree dir.
  * ``git -C <copy> revert --no-commit HEAD`` then left the ORIGINAL
    worktree — untouched by any command — with ``MM f.txt``, a populated
    index, and a pending ``REVERT_HEAD``.
  * Recovery was not even clean: ``git revert --abort`` run from the real
    worktree afterwards FAILED — ``error: Entry 'f.txt' not uptodate. Cannot
    merge.`` — because the working file there never matched what the copy
    had staged. The incident is not "one dirty file"; it is a worktree whose
    index, working tree and sequencer state disagree three ways.

And the fix the briefs kept prescribing is INSUFFICIENT on its own, which is
the second reason a sentence kept failing:

  * With the ``.git`` file removed, a clone parked under ANY ancestor
    repository resolves to that ancestor: measured
    ``git rev-parse --absolute-git-dir`` → the umbrella repo's ``.git``.
    Discovery walks up. Removal changes WHICH wrong repo gets mutated.
  * ``git init`` run at the clone root stops the walk: rev-parse then
    answers ``<clone>/.git`` and nothing else, from anywhere under the
    clone. That empty repository is the QUARANTINE, and it is the load-
    bearing half of the design, not a nicety.

The two adjacent hazards, and the contract's answer to each
===========================================================
The task requires this contract to say whether it handles two more states
measured in the same session. It handles both; the boundary of the first is
stated exactly.

**Hazard A — ``git checkout <tree-ish> -- .`` with ``--work-tree`` pointed
elsewhere.** Measured: from a clean worktree,
``git --work-tree=<elsewhere> checkout HEAD~1 -- .`` wrote the old content
into ``<elsewhere>`` AND staged it in the REAL index — ``MM f.txt``, a
cached diff of 1 file — because ``--work-tree`` relocates the working tree
while discovery still supplies the real index. Handled two ways:

  * *Inside the clone*: the quarantine has no objects and no refs, so the
    same command class dies loudly — measured
    ``fatal: invalid reference: HEAD``, exit 128 — instead of writing
    anything anywhere.
  * *By replacement*: the reason agents typed that command was to mutate a
    file and put it back. :func:`swap_in` / :func:`swap_back` are that
    operation as a seam, so the command has no reason to exist in a brief.

  Stated non-guarantee: a git command run OUTSIDE the clone with
  ``--work-tree`` pointed INTO it never consults the clone's discovery and
  no property of the clone can intercept it. The helper removes the reason
  to type such a command; it cannot police the keyboard. P4 owns whether
  the briefs ban the flag outright.

Four more escape channels, measured for this revision
=====================================================
The first panel review of this scaffold found that the guarantee as then
written could hold while the property it names was false: the sever step
scanned only ``.git`` FILES and SYMLINKS, the probe read only
``--absolute-git-dir``, and nothing sanitized the environment the helper's
own subprocesses inherit. Each channel was then measured (same environment
as above, sentinel repos under ``/tmp``), and the contract below closes
each by name:

  * **Inherited ``GIT_*`` environment.** ``GIT_DIR`` — and its siblings:
    ``GIT_COMMON_DIR``, ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``,
    ``GIT_OBJECT_DIRECTORY``, ``GIT_ALTERNATE_OBJECT_DIRECTORIES``, the
    ``GIT_CONFIG_*`` family — overrides discovery entirely, so the
    quarantine cannot stop what the environment routes around it. Measured
    with ``GIT_DIR`` pointed at a sentinel repo: ``git init`` at a fresh
    directory created NO ``.git`` there and reinitialized the SENTINEL;
    ``git rev-parse --absolute-git-dir`` run inside a git-init'd clone
    answered the SENTINEL's path; and ``git revert --no-commit HEAD``
    inside that clone left the sentinel with ``MM f.txt`` — the original
    incident, reproduced straight through a quarantine. Closed: every git
    subprocess this module spawns runs under :func:`scrubbed_git_env`,
    which drops every ``GIT_*`` variable and pins config lookup away from
    global/system files (:data:`GIT_ENV_PINS`). This covers creation AND
    the probe AND the failure paths — a refusal decided by a rerouted
    subprocess would itself be the incident.
  * **A nested ``.git`` DIRECTORY carrying internal indirection.** A
    ``.git`` directory copied into the clone (a submodule checkout is the
    expected carrier) can hold a ``commondir`` file. Measured: with
    ``sub/.git/commondir`` naming the sentinel, ``git -C sub rev-parse
    --absolute-git-dir`` answered INSIDE the clone while
    ``--git-common-dir`` answered the SENTINEL, and ``git -C sub
    update-ref refs/heads/x HEAD`` created a branch IN THE SENTINEL. The
    previously specified probe passes while the guarantee is false.
    Closed: sever removes EVERY ``.git`` entry under the clone whatever
    its kind — file, directory, or symlink — and the probe checks BOTH
    rev-parse answers and walks the clone for survivors of any kind.
  * **Object alternates.** ``objects/info/alternates`` inside a
    quarantine's own ``.git`` reads the target's objects while
    ``--absolute-git-dir`` still answers in-clone — measured:
    ``git cat-file -t <sentinel commit>`` → ``commit``. Closed: the probe
    audits the quarantine's internals — the root ``.git`` must be a
    directory holding no ``commondir`` and no ``objects/info/alternates``
    — and ``git init`` runs with ``--template=`` (empty) under the
    scrubbed environment, so neither a template nor an inherited config
    can seed indirection or hooks into it.
  * **A symlink not named ``.git``.** Measured: ``clone/notgit →
    <sentinel>/.git`` accepted a write that landed inside the sentinel's
    git dir. A scan keyed on the name ``.git`` never sees it. Closed: no
    symlink under the clone may resolve outside the clone — the build
    refuses with :data:`Refusal.LINK_ESCAPES_CLONE`, and the probe
    re-checks (``outside the clone`` rather than ``into the source``
    because the probe is standalone and knows only the clone; the superset
    is the checkable property, and it is stated as the conservative choice
    it is).

  Stated non-guarantee, parallel to Hazard A's: an agent shell that itself
  exports ``GIT_DIR=<real>`` reroutes ITS OWN subsequent git commands and
  no property of the clone can intercept that. The scrub covers every
  subprocess this module spawns — including the CLI face, which is the
  recommended entry for exactly this reason — but it cannot police the
  caller's keyboard or environment after it returns.

**Hazard B — CPython keys bytecode on (mtime_seconds, size).** Measured: a
same-size mutation whose mtime lands in the same second as the original —
``return "ORIGINAL"`` → ``return "MUTATED_"``, both 36 bytes on disk —
imported as the ORIGINAL: the stale ``.pyc`` matched on (mtime, size) and
the mutant NEVER RAN, so a probe suite reports the mutation covered when it
was never executed. Advancing mtime by 2 seconds made the same import see
the mutant. Handled: :func:`make_scratch_clone` purges every ``__pycache__``
directory and stray ``.pyc`` from the clone before returning, and both
:func:`swap_in` and :func:`swap_back` advance the target's mtime by at least
:data:`MTIME_ADVANCE_SECONDS` past the state they replace, so neither
direction of a swap can collide into the prior key even when sizes match
and the wall clock has not ticked.

What a scratch clone GUARANTEES
===============================
:func:`make_scratch_clone` returns only when ALL of the following hold, and
the last is proven by probe, not by construction:

  1. the clone's tree content equals the source worktree's tree content,
     minus git metadata, Python bytecode, and non-regular files (fifo,
     socket, device node: a fifo blocks the copy forever with no named
     refusal, and none of them is tree content);
  2. no git metadata exists under the clone except the quarantine's own:
     every ``.git`` entry of every kind — the root gitdir pointer FILE, a
     nested ``.git`` DIRECTORY (whose ``commondir``/alternates would route
     git outside while ``--absolute-git-dir`` answers in-clone; measured),
     a ``.git`` symlink, and every CASE VARIANT (``.GIT``: honoured by git
     on a case-insensitive filesystem) — is removed before the quarantine
     is created;
  3. no symlink under the clone, whatever its name, resolves outside the
     clone;
  4. an empty SELF-CONTAINED quarantine repository sits at the clone root
     — init'd under :func:`scrubbed_git_env` with ``--template=``, holding
     no ``commondir`` and no ``objects/info/alternates`` — so git
     discovery from ANY directory under the clone terminates inside the
     clone, including when the clone itself sits under an ancestor repo,
     and git's effective WORK TREE is the clone root itself (no
     ``core.worktree`` redirection: ``--show-toplevel`` must resolve to
     the clone root from every probe directory);
  5. every git subprocess the helper ran to build and prove the clone was
     executed under :func:`scrubbed_git_env` — the guarantee is not
     conditional on the calling shell's environment being clean;
  6. :func:`assert_isolated` — the same probe any caller can re-run without
     reading this module — passes against the finished clone.

How it FAILS: a named state, never a silent copy
================================================
The helper never returns a half-made clone and never lets one linger. Every
failure raises :class:`ScratchCloneError` carrying exactly one
:class:`Refusal` member, and the partial destination is deleted before the
raise; if that deletion itself fails, the error says so
(``cleanup_failed=True``) and names what was left behind. There is no code
path that answers "here is your clone" with less than the full guarantee —
the terminal step is the probe, and an unprovable guarantee is
:data:`Refusal.ISOLATION_UNVERIFIED`, not a warning.

Contract surface
================
Tables and shapes are DATA and are implemented; the control flow is stubbed.

  * :class:`Refusal` — the named failure states. Eleven, exhaustive, none
    of which reads as success by omission.
  * :data:`_REFUSAL_MESSAGES` / :func:`refusal_message` — refusal → the one
    line an agent transcript shows. Total over the enum, guarded.
  * :class:`ScratchCloneError` — the only exception this module raises on
    its own behalf.
  * :class:`ScratchClone`, :class:`SwapToken` — the two records.
  * :data:`MTIME_ADVANCE_SECONDS` — the bytecode-key stride, with its why.
  * :data:`GIT_ENV_PINS` / :func:`scrubbed_git_env` — the environment every
    git subprocess of this module runs under. CHOICE — implemented in the
    scaffold, not stubbed like the control flow; the rejected alternative
    (stub everything uniformly) would leave the guarantee's standing rule
    undependable until P3: it is a table and a pure fold over one, the
    bodies MUST NOT be writable without it, and a seal cannot be written
    against a stub.
  * :func:`make_scratch_clone`, :func:`assert_isolated`, :func:`swap_in`,
    :func:`swap_back`, :func:`main` — the control flow, implemented at P3
    against the P2 seals.

What this unit does NOT do — each a CHOICE, stated so a later reader does
not infer omission: it does not touch `worktree.py` — that module CREATES
real worktrees and its callers want the real repo reached; this one exists
so probes cannot, and folding the two would put the quarantine one import
away from the machinery it quarantines against. And it adds no orchestrator
call site — the rejected alternative, wiring it into the dispatch loop now,
would decide at P1 what P4 owns (whether the helper becomes mandatory in
role briefs); the callers are the protocol's own agents (briefs and probe
scripts), which is why :func:`main` is part of the contract rather than an
afterthought.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import NoReturn, Sequence

#: Pinned into every scrubbed environment AFTER the ``GIT_*`` drop.
#: Discovery routing is handled by the drop itself; these close the CONFIG
#: channel, which is files rather than variables — a global or system
#: gitconfig can seed ``core.hooksPath``, ``includeIf`` chains, or object
#: settings into a quarantine that was init'd under a clean variable set.
#: ``GIT_CONFIG_NOSYSTEM`` rides along for git builds that honour it ahead
#: of ``GIT_CONFIG_SYSTEM``.
GIT_ENV_PINS: dict[str, str] = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def scrubbed_git_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of `base` (default ``os.environ``) safe to hand a git child.

    Drops EVERY variable whose name starts with ``GIT_``, then applies
    :data:`GIT_ENV_PINS`. CHOICE — a drop-by-prefix rather than an
    allowlist of the known routing variables (``GIT_DIR``, ``GIT_COMMON_DIR``,
    ``GIT_WORK_TREE``, ``GIT_INDEX_FILE``, ``GIT_OBJECT_DIRECTORY``,
    ``GIT_ALTERNATE_OBJECT_DIRECTORIES``, ``GIT_CONFIG_COUNT`` and its
    numbered ``GIT_CONFIG_KEY_n``/``GIT_CONFIG_VALUE_n`` rows,
    ``GIT_CEILING_DIRECTORIES``, ``GIT_TEMPLATE_DIR``, ...) because that
    list is the enumeration that falls out of date, and no subprocess this
    module spawns — ``git init``, the rev-parse probes — has a legitimate
    use for ANY of them. Measured (module docstring, escape channel 1):
    with ``GIT_DIR`` inherited, ``git init`` reinitializes the variable's
    target and the probe attests the wrong repository; under this scrub
    both land in the clone.

    Pure: `base` is read, never mutated, and the result is a fresh dict.
    """
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if not k.startswith("GIT_")}
    env.update(GIT_ENV_PINS)
    return env


#: Both swap directions advance the target's mtime by at least this many
#: seconds past the file state they replace. CPython's source-based pyc
#: validation compares a 32-bit WHOLE-SECOND mtime plus size (PEP 552's
#: timestamp mode, the default); 1 second is therefore the exact boundary,
#: and 2 clears it with a margin for filesystems that round rather than
#: truncate. Measured: a same-second same-size rewrite imported as the OLD
#: content; +2s imported as the new (module docstring, Hazard B).
#: CHOICE — advance mtimes rather than flip the clone to hash-based pyc
#: validation (PEP 552's checked-hash mode): that mode governs only pycs
#: compiled with the flag set, and this helper does not control how a probe
#: invokes the clone's interpreter. The stride is enforceable from this
#: side of the seam; the compile flag is not.
MTIME_ADVANCE_SECONDS = 2


class Refusal(Enum):
    """Why the helper refused. One member per way the guarantee can fail.

    Every member is terminal: the partial destination is removed before the
    carrying :class:`ScratchCloneError` is raised (see ``cleanup_failed``
    for the one thing that can still be left behind). No member means
    "proceeded with a caveat" — a caveat is a silent copy with extra steps,
    and a silent copy is the incident.
    """

    #: The source is not an existing directory. CHOICE — also the answer
    #: for a source that is not a git worktree AT ALL; the rejected
    #: alternative, accepting any directory, is `cp -a` wearing this
    #: helper's name, and lending the name would let "I used the helper"
    #: mean less than the guarantee.
    SOURCE_UNUSABLE = "source_unusable"

    #: The destination already exists — file, dir, symlink, anything.
    #: CHOICE — the helper never deletes what it did not create, so it
    #: never overwrites; the rejected alternative, clobbering (or a --force
    #: to opt into clobbering), turns a typo'd destination into deleting a
    #: tree this module never made. Choosing a fresh path is the caller's
    #: one obligation.
    DEST_COLLISION = "dest_collision"

    #: One of the two paths contains the other. A clone into its own source
    #: recurses; a source inside the destination gets deleted by refusal
    #: cleanup. Both are detectable before any byte is copied, so both are
    #: refused before any byte is copied.
    NESTED_PATHS = "nested_paths"

    #: The copy itself failed partway (ENOSPC, EPERM, a file vanishing
    #: mid-walk). The partial tree is removed; the underlying OS error
    #: rides in ``detail``.
    COPY_FAILED = "copy_failed"

    #: Severing did not leave the clone free of git metadata: a ``.git``
    #: entry — file, DIRECTORY, or symlink — still exists under the clone
    #: after the removal walk, or could not be removed. Sever means remove
    #: EVERY ``.git`` entry whatever its kind, not scan the suspicious
    #: ones: a copied ``.git`` directory carries ``commondir`` and
    #: alternates that route ref writes to the real repository while
    #: ``--absolute-git-dir`` still answers in-clone (measured, escape
    #: channel 2). Nothing named ``.git`` survives, so no internal
    #: indirection survives either.
    SEVER_INCOMPLETE = "sever_incomplete"

    #: A symlink under the clone — under ANY name — resolves outside the
    #: clone. Measured (escape channel 4): ``clone/notgit →
    #: <source>/.git`` accepted a write that landed in the source git dir,
    #: and a scan keyed on the name ``.git`` never sees it. CHOICE —
    #: conservative by construction: a benign out-of-tree symlink is
    #: refused too,
    #: because a standalone check cannot tell a benign target from the
    #: source repository spelled differently, and unprovable gets the same
    #: answer as unsafe.
    LINK_ESCAPES_CLONE = "link_escapes_clone"

    #: ``git init`` of the quarantine repository failed. Without the
    #: quarantine the clone is one ancestor repo away from mutating a
    #: DIFFERENT wrong repository (module docstring: removal changes which
    #: wrong repo gets mutated), so no quarantine, no clone.
    QUARANTINE_FAILED = "quarantine_failed"

    #: Purging ``__pycache__`` / stray ``.pyc`` from the clone failed. A
    #: clone that keeps the source's bytecode inherits Hazard B at full
    #: strength on day one, so the purge is part of the guarantee, not
    #: hygiene.
    PURGE_FAILED = "purge_failed"

    #: The terminal probe — :func:`assert_isolated` over the finished clone
    #: — did not prove the guarantee: either rev-parse answer
    #: (``--absolute-git-dir`` or ``--git-common-dir``) resolved somewhere
    #: other than the quarantine, the quarantine's internals carry
    #: indirection (a ``commondir`` file, ``objects/info/alternates``, a
    #: gitfile root), the repository at the root is not EMPTY (a ref, an
    #: object, a remote, a registered worktree, a HEAD that resolves — the
    #: REAL repository passes every self-containment check, and only
    #: emptiness tells a quarantine from it), git's effective WORK TREE is
    #: not the clone root (``core.worktree`` set, or ``--show-toplevel``
    #: resolving elsewhere — writes would land in the configured tree
    #: while every git-dir answer stays in-clone), a ``.git`` entry (any
    #: case)
    #: or escaping symlink survives under the clone, or a git invocation
    #: needed by the probe itself failed. The clone may even be fine;
    #: UNPROVABLE and UNSAFE get the same answer here by design.
    ISOLATION_UNVERIFIED = "isolation_unverified"

    #: A swap seam was handed a relpath that escapes the clone —
    #: ``..`` traversal, an absolute path, or a symlink inside the clone
    #: whose target is outside it. The whole point of the seams is that
    #: their writes land inside the quarantined tree; a write that escapes
    #: is Hazard A with this module's name on it.
    SWAP_ESCAPES_CLONE = "swap_escapes_clone"

    #: :func:`swap_in` was pointed at a path that does not exist in the
    #: clone (or :func:`swap_back` at one whose file vanished). Creating a
    #: file is not a mutation probe, and a vanished file means the probe
    #: did something this contract does not cover.
    SWAP_TARGET_MISSING = "swap_target_missing"


#: Refusal → the single line an agent transcript shows. Total over
#: :class:`Refusal`; CHOICE — :func:`refusal_message` guards totality
#: rather than defaulting, for the same reason `loop_gate` guards its
#: tables: a fold with a default (the rejected alternative) is where a
#: twelfth member would silently read as the eleventh.
_REFUSAL_MESSAGES: dict[Refusal, str] = {
    Refusal.SOURCE_UNUSABLE: (
        "scratch-clone REFUSED: source is not an existing git worktree"
    ),
    Refusal.DEST_COLLISION: (
        "scratch-clone REFUSED: destination already exists; the helper never "
        "overwrites — pick a fresh path"
    ),
    Refusal.NESTED_PATHS: (
        "scratch-clone REFUSED: source and destination nest; a clone may not "
        "contain or be contained by its source"
    ),
    Refusal.COPY_FAILED: (
        "scratch-clone REFUSED: copy failed partway; partial destination "
        "removed"
    ),
    Refusal.SEVER_INCOMPLETE: (
        "scratch-clone REFUSED: git metadata survived the sever — a .git "
        "entry (file, directory, or symlink) still exists under the clone; "
        "clone removed"
    ),
    Refusal.LINK_ESCAPES_CLONE: (
        "scratch-clone REFUSED: a symlink inside the clone resolves outside "
        "it; a write through it lands outside the quarantine; clone removed"
    ),
    Refusal.QUARANTINE_FAILED: (
        "scratch-clone REFUSED: could not init the quarantine repo at the "
        "clone root; without it git discovery walks to an ancestor repo"
    ),
    Refusal.PURGE_FAILED: (
        "scratch-clone REFUSED: could not purge inherited bytecode; a stale "
        ".pyc reports a mutant as run when it never ran"
    ),
    Refusal.ISOLATION_UNVERIFIED: (
        "scratch-clone REFUSED: could not PROVE the clone cannot reach the "
        "source repo; unprovable and unsafe get the same answer"
    ),
    Refusal.SWAP_ESCAPES_CLONE: (
        "scratch-clone swap REFUSED: path escapes the clone; seam writes "
        "land inside the quarantined tree only"
    ),
    Refusal.SWAP_TARGET_MISSING: (
        "scratch-clone swap REFUSED: target does not exist in the clone; "
        "a mutation probe mutates, it does not create"
    ),
}


def refusal_message(refusal: Refusal, detail: str = "") -> str:
    """The transcript line for `refusal`, with `detail` appended if given.

    Raises :class:`ScratchCloneError` — with the refusal it was ASKED about,
    so the caller's state is not misreported — if the table has no row for
    it. That raise is the totality guard; it fires only when someone adds a
    :class:`Refusal` member without a message, which is a defect in this
    module, not in the caller.
    """
    message = _REFUSAL_MESSAGES.get(refusal)
    if message is None:
        raise ScratchCloneError(
            refusal,
            detail=f"no transcript message defined for {refusal!r} — "
            "_REFUSAL_MESSAGES is meant to be total over Refusal",
        )
    return f"{message} [{detail}]" if detail else message


class ScratchCloneError(RuntimeError):
    """The only exception this module raises on its own behalf.

    Carries exactly one :class:`Refusal`, the free-text ``detail`` (an OS
    error, a surviving path, a probe's stderr), and ``cleanup_failed`` —
    True when the refusal's own cleanup could not remove the partial
    destination, in which case ``detail`` names what was left behind. A
    caller that catches this and proceeds to use the destination path is
    outside the contract; there is nothing usable there.
    """

    def __init__(
        self,
        refusal: Refusal,
        *,
        detail: str = "",
        cleanup_failed: bool = False,
    ) -> None:
        super().__init__(refusal_message(refusal, detail)
                         if refusal in _REFUSAL_MESSAGES
                         else f"{refusal!r}: {detail}")
        self.refusal = refusal
        self.detail = detail
        self.cleanup_failed = cleanup_failed


@dataclass(frozen=True)
class ScratchClone:
    """A clone :func:`make_scratch_clone` finished and PROVED.

    Existence of this record is the success signal: no instance is
    constructed for a tree the probe did not pass. Frozen because the
    record is a receipt, not a handle to mutate.
    """

    #: Root of the quarantined copy. Every probe write belongs under here.
    path: Path
    #: The worktree that was copied — kept for transcripts and for
    #: :func:`swap_in` callers that want to name their provenance. The
    #: clone holds NO other reference to it, live or latent.
    source: Path
    #: The quarantine's git dir, always ``path / ".git"``. Recorded so a
    #: seal can assert the probe's answer against the receipt without
    #: recomputing either.
    git_dir: Path


@dataclass(frozen=True)
class SwapToken:
    """What :func:`swap_in` hands back; what :func:`swap_back` requires.

    CHOICE — restoration carries the original BYTES in the token: the
    rejected alternative, restoring by checkout from a repository, IS the
    incident's restore path (Hazard A), and a backup file parked on disk is
    state a crashed probe leaves behind. The token also carries the mutated
    file's post-swap mtime in
    nanoseconds, so :func:`swap_back` can advance PAST it rather than past
    a wall clock that may not have ticked (Hazard B).
    """

    #: Path relative to the clone root, as given to :func:`swap_in`.
    relpath: str
    #: The file's full content before the mutation was written.
    original: bytes
    #: st_mtime_ns of the MUTATED file as :func:`swap_in` left it;
    #: :func:`swap_back` sets the restored file's mtime to at least this
    #: plus :data:`MTIME_ADVANCE_SECONDS`.
    mutated_mtime_ns: int


_NS_PER_SECOND = 1_000_000_000

#: Ceiling on any git child this module spawns. Every one — the init, the
#: rev-parse probes — is a sub-second operation against a local empty
#: repository; a git that has not answered in this long is stuck (or is not
#: git at all), and a helper that hangs on it is a failure mode neither
#: loud nor named.
_GIT_TIMEOUT_SECONDS = 60


def _git_run(args: Sequence[str],
             cwd: Path) -> subprocess.CompletedProcess[str]:
    """A git child under the standing rule: every one runs scrubbed.

    Fails CLOSED as a RESULT, never as an escape or a hang: a git that
    cannot be started (``OSError`` — missing binary, exec failure) or does
    not answer within :data:`_GIT_TIMEOUT_SECONDS` comes back as a nonzero
    returncode with the cause in stderr, so every caller's returncode check
    turns it into that caller's NAMED refusal — with destination cleanup —
    instead of a raw exception that skips both. Output that is not valid
    UTF-8 (a localized git, garbage from a killed child) is decoded with
    replacement characters rather than letting ``UnicodeDecodeError`` — a
    ``ValueError``, which no refusal path catches — escape the same way.
    """
    cmd = ["git", *args]
    try:
        return subprocess.run(
            cmd, cwd=cwd, env=scrubbed_git_env(),
            capture_output=True, text=True, errors="replace",
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(
            args=cmd, returncode=-1, stdout="",
            stderr=f"git did not run: {exc}")


def _raise_scan_error(exc: OSError) -> NoReturn:
    """``onerror`` for every walk in this module. ``os.walk`` (and
    ``Path.rglob``) SKIP a subtree they cannot read by default, so a scan
    error reads as "nothing found there" — a sever or a probe that misses
    an inherited nested ``.git`` that way has failed OPEN. Raising turns
    every unreadable subtree into the walking step's named refusal."""
    raise exc


def _entries_under(root: Path) -> Iterator[Path]:
    """Every filesystem entry under `root`, symlinks NOT followed — the
    question here is what exists on disk, and following a link would walk
    a tree outside the clone. Raises ``OSError`` on any subtree it cannot
    read (see :func:`_raise_scan_error`): an incomplete answer to "what
    exists on disk" must not read as a complete one."""
    for dirpath, dirnames, filenames in os.walk(
            root, followlinks=False, onerror=_raise_scan_error):
        base = Path(dirpath)
        for name in dirnames + filenames:
            yield base / name


def _copy_ignore(dirpath: str | os.PathLike[str],
                 names: Sequence[str]) -> set[str]:
    """``ignore`` callback for the clone copy: what must not be copied.

    Two classes. Every ``.git`` name (any case — same rule as the sever
    pass): copying a main worktree's object store only for the sever pass
    to delete it is the dominant time and disk cost of a clone and can
    fill the destination volume before the sever runs — the contract is
    that no ``.git`` remains before ``git init``, not that one be copied
    first (the sever and survivor walks stay, as proof that nothing
    slipped through anyway). And every non-regular file — fifo, socket,
    device — because ``copytree`` opening a fifo blocks forever with no
    timeout and no named refusal, and a device node's bytes are not tree
    content. Symlinks pass through (copied AS links; the escape scan
    judges them). ``lstat`` failure propagates: an entry this filter could
    not classify makes the copy fail loudly (COPY_FAILED), not silently
    thin.
    """
    skip: set[str] = set()
    for name in names:
        if name.lower() == ".git":
            skip.add(name)
            continue
        mode = os.lstat(os.path.join(dirpath, name)).st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)
                or stat.S_ISLNK(mode)):
            skip.add(name)
    return skip


def _refuse(dest: Path, refusal: Refusal, detail: str = "") -> NoReturn:
    """Remove the partial destination, then raise the named refusal.

    Only for a destination THIS call CLAIMED — won the atomic ``os.mkdir``
    in :func:`make_scratch_clone` — because the helper never deletes what
    it did not make. Preflight refusals and a lost mkdir race raise
    directly: two concurrent calls to the same destination must not end
    with the loser recursively deleting the winner's clone-in-progress.
    """
    try:
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
    except OSError as exc:
        raise ScratchCloneError(
            refusal,
            detail=(f"{detail}; " if detail else "")
            + f"cleanup failed, left behind {dest}: {exc}",
            cleanup_failed=True,
        )
    raise ScratchCloneError(refusal, detail=detail)


def make_scratch_clone(source: Path, dest: Path) -> ScratchClone:
    """Copy the worktree at `source` to `dest` and QUARANTINE the copy.

    Standing rule over every step: each git subprocess runs under
    :func:`scrubbed_git_env` — measured (escape channel 1), an inherited
    ``GIT_DIR`` reroutes ``git init`` ITSELF to the variable's target, so
    an unscrubbed step violates the guarantee before the probe can refuse.
    This binds the failure paths too: a refusal decided by a rerouted
    subprocess is the incident wearing an error message.

    The five steps the body must implement, in order, each refusing with
    the named state on failure (module docstring for the full contract):

      1. preflight — `source` an existing worktree directory
         (:data:`Refusal.SOURCE_UNUSABLE`), `dest` absent
         (:data:`Refusal.DEST_COLLISION`), no nesting either way
         (:data:`Refusal.NESTED_PATHS`);
      2. copy the tree (:data:`Refusal.COPY_FAILED`);
      3. sever — remove EVERY ``.git`` entry under the clone, root and
         nested, whatever its kind: file, DIRECTORY, or symlink
         (:data:`Refusal.SEVER_INCOMPLETE` when one survives the walk or
         cannot be removed — a nested ``.git`` directory is removed, not
         scanned around: its ``commondir``/alternates route git to the
         real repo while ``--absolute-git-dir`` answers in-clone,
         measured); then scan every symlink under the clone and refuse
         one resolving outside it (:data:`Refusal.LINK_ESCAPES_CLONE`);
         then purge ``__pycache__`` dirs and stray ``.pyc``
         (:data:`Refusal.PURGE_FAILED`);
      4. quarantine — ``git init --template=`` at the clone root, the
         empty template value so no hook, config, or indirection rides
         into the quarantine from a template dir
         (:data:`Refusal.QUARANTINE_FAILED`);
      5. prove — :func:`assert_isolated` over the finished clone; its
         failure IS this function's failure
         (:data:`Refusal.ISOLATION_UNVERIFIED`).

    Any refusal removes the partial destination first; if THAT fails, the
    raised error has ``cleanup_failed=True`` and ``detail`` names the
    leftovers. Returns the :class:`ScratchClone` receipt only after step 5.

    The seals (P2, DF-4-2, a DIFFERENT author: a scaffold that writes the
    seals it will be judged by re-creates the circular oracle) drove this
    signature; this body (P3, DF-4-3) exists to satisfy them — the row that
    matters fails against a naive ``cp -a``.
    """
    # 1. preflight — refuse before any byte is copied. No cleanup on these
    # paths: nothing here was created by this call, and DEST_COLLISION's
    # whole point is that the existing destination survives untouched.
    # "Is a worktree" is judged by the entry on disk (a linked worktree's
    # gitdir FILE, a main worktree's directory) rather than by asking git:
    # discovery walks up, so a plain directory under an umbrella repo would
    # answer yes to git while being exactly the cp -a caller this refusal
    # exists to turn away.
    if not source.is_dir() or not os.path.lexists(source / ".git"):
        raise ScratchCloneError(Refusal.SOURCE_UNUSABLE, detail=str(source))
    if os.path.lexists(dest):
        raise ScratchCloneError(Refusal.DEST_COLLISION, detail=str(dest))
    source_res = source.resolve()
    dest_res = dest.resolve()
    if source_res.is_relative_to(dest_res) or dest_res.is_relative_to(
            source_res):
        raise ScratchCloneError(
            Refusal.NESTED_PATHS, detail=f"{source} <-> {dest}")

    # 2. claim, then copy. The destination is claimed with an ATOMIC
    # os.mkdir before any byte lands: two concurrent calls to the same
    # dest both pass the lexists preflight, and without a single winner
    # the second's refusal cleanup would recursively delete the first's
    # clone-in-progress. The mkdir loser refuses as a collision and
    # deletes NOTHING; every _refuse below acts only on a tree whose
    # mkdir this call won. Copy is cp -a semantics (symlinks preserved
    # as symlinks, so the escape scan below judges them; metadata
    # preserved, including the root dir's via copystat) MINUS what
    # _copy_ignore drops: .git entries (severed at copy time rather than
    # copied-then-deleted) and non-regular files (a fifo blocks copytree
    # forever — the hang the git timeout does not cover).
    try:
        os.mkdir(dest)
    except FileExistsError:
        raise ScratchCloneError(Refusal.DEST_COLLISION, detail=str(dest))
    except OSError as exc:
        raise ScratchCloneError(
            Refusal.COPY_FAILED,
            detail=f"could not create destination: {exc}")
    try:
        shutil.copytree(source, dest, symlinks=True, dirs_exist_ok=True,
                        ignore=_copy_ignore)
    except Exception as exc:
        _refuse(dest, Refusal.COPY_FAILED, detail=str(exc))

    # 3a. sever — every .git entry of every kind, deepest first so a nested
    # one is gone before its parent's turn. _copy_ignore already dropped
    # them at copy time, so this pass normally removes nothing — it stays
    # as the PROOF that nothing slipped through, independent of the copy's
    # filter. Matched CASE-INSENSITIVELY:
    # git honours `.GIT` (any case variant) on a case-insensitive
    # filesystem, so a name-exact scan severs `.git` and walks past the
    # same hazard spelled differently; on a case-sensitive filesystem the
    # variant is inert and removing it is the conservative uniform answer.
    # The walk is _entries_under, not rglob: rglob SKIPS a subtree it
    # cannot read, and a sever that missed an unreadable subtree's .git
    # has failed open (the walk raising folds that subtree into this
    # step's refusal instead).
    try:
        for entry in sorted(
                (e for e in _entries_under(dest)
                 if e.name.lower() == ".git"),
                reverse=True):
            if entry.is_symlink() or entry.is_file():
                entry.unlink()
            else:
                shutil.rmtree(entry)
        survivors = [str(e) for e in _entries_under(dest)
                     if e.name.lower() == ".git"]
    except OSError as exc:
        _refuse(dest, Refusal.SEVER_INCOMPLETE, detail=str(exc))
    if survivors:
        _refuse(dest, Refusal.SEVER_INCOMPLETE, detail=", ".join(survivors))

    # 3b. symlink scan — no link under ANY name may resolve outside the
    # clone; an unresolvable link (dangling target, a loop) gets the same
    # answer (unprovable == unsafe), so resolution is STRICT: the default
    # lexical fallback would ACCEPT a dangling link whose unresolved text
    # merely reads in-clone. A subtree the scan cannot read gets the same
    # answer for the same reason — links there were never judged.
    try:
        for entry in _entries_under(dest):
            if not entry.is_symlink():
                continue
            try:
                # RuntimeError: pre-3.13 CPython reports a symlink loop as
                # RuntimeError rather than OSError(ELOOP).
                target = entry.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                _refuse(dest, Refusal.LINK_ESCAPES_CLONE,
                        detail=f"{entry}: unresolvable: {exc}")
            if not target.is_relative_to(dest_res):
                _refuse(dest, Refusal.LINK_ESCAPES_CLONE,
                        detail=f"{entry} -> {target}")
    except OSError as exc:
        _refuse(dest, Refusal.LINK_ESCAPES_CLONE,
                detail=f"symlink scan could not complete: {exc}")

    # 3c. purge inherited bytecode (Hazard B at full strength on day one).
    # Same strict walk as the sever, same reason: a .pyc in an unreadable
    # subtree survives an rglob purge silently.
    try:
        for cache_dir in sorted(
                (e for e in _entries_under(dest)
                 if e.name == "__pycache__"),
                reverse=True):
            if cache_dir.is_symlink() or cache_dir.is_file():
                cache_dir.unlink()
            else:
                shutil.rmtree(cache_dir)
        for pyc in [e for e in _entries_under(dest)
                    if e.name.endswith(".pyc")]:
            pyc.unlink()
    except OSError as exc:
        _refuse(dest, Refusal.PURGE_FAILED, detail=str(exc))

    # 4. quarantine — empty template so nothing rides in from a template
    # dir; scrubbed env so nothing rides in from the caller's shell.
    init = _git_run(["init", "-q", "--template="], cwd=dest)
    if init.returncode != 0 or not (dest / ".git").is_dir():
        _refuse(dest, Refusal.QUARANTINE_FAILED,
                detail=init.stderr.strip() or f"rc={init.returncode}")

    # 5. prove — the probe's failure IS this function's failure. The
    # second handler is deliberate breadth: a probe that CRASHED (an
    # OSError out of resolve(), anything not already converted to a
    # ScratchCloneError) proved nothing, and a claimed destination must
    # not survive an unproven clone — every post-claim exit runs _refuse.
    try:
        assert_isolated(dest)
    except ScratchCloneError as err:
        _refuse(dest, Refusal.ISOLATION_UNVERIFIED, detail=err.detail)
    except Exception as exc:
        _refuse(dest, Refusal.ISOLATION_UNVERIFIED,
                detail=f"probe crashed: {exc!r}")

    return ScratchClone(path=dest, source=source, git_dir=dest / ".git")


def assert_isolated(clone_path: Path) -> None:
    """Prove git discovery from inside `clone_path` terminates inside it.

    The postcondition as a standalone probe, so "the helper succeeded" is
    checkable without reading the helper — DF-4-3's stated bar — and so a
    brief can demand the probe be re-run after ANY tool touched the clone.

    Every probe subprocess runs under :func:`scrubbed_git_env`: an
    inherited ``GIT_DIR`` makes rev-parse attest the WRONG repository
    (measured, escape channel 1), so an unscrubbed probe is not a probe.
    Must hold — git subprocesses where the question is git's walk, a
    filesystem walk where the question is what exists on disk:

      * ``git rev-parse --absolute-git-dir`` AND ``--git-common-dir``,
        run at the clone root and again at the deepest directory under
        the clone, ALL answer ``<clone>/.git`` — resolved against the
        real filesystem, symlinks and all, and noting that
        ``--git-common-dir`` answers RELATIVE to the invocation directory
        (measured: ``.git`` at the root) where ``--absolute-git-dir``
        answers absolute, so the body resolves before comparing. Both
        answers because a ``commondir`` file splits them: measured
        (escape channel 2),
        ``--absolute-git-dir`` stayed in-clone while ``--git-common-dir``
        named the real repository ref writes were landing in;
      * the root ``.git`` is a DIRECTORY — not a gitfile — whose
        internals carry no indirection: no ``commondir`` file and no
        ``objects/info/alternates`` (measured, escape channel 3: an
        alternates line reads the source's objects while
        ``--absolute-git-dir`` still answers in-clone);
      * the repository at the root is EMPTY the way only a quarantine is:
        no ref anywhere (no file under ``refs/``, no ``packed-refs``), no
        object (no file under ``objects/``), no ``worktrees/`` dir, no
        configured remote, and a HEAD that resolves to no commit. Every
        earlier bullet is satisfied BY THE REAL REPOSITORY ITSELF —
        handed the real main worktree (or a symlink to it), a probe of
        self-containment alone answers "isolated" while writes land in
        the real repo, which is the precise hazard this unit exists to
        refuse. A repository with any history, content, remote,
        registered worktree, or redirected work tree can never pass.
        LIMIT, stated so the claim stays true: what remains
        indistinguishable — and is accepted — is a repository
        byte-identical to a fresh quarantine, because a ``git init`` the
        probe did not watch happen differs in NOTHING an in-tree probe
        can read. Emptiness, not provenance, is what this function
        establishes: "an empty quarantine-shaped repository whose git
        walk and effective work tree both terminate here" — in which no
        ref, object, or foreign tree exists for a write to reach — and
        never "this module made it" (provenance would need a receipt
        carried outside the tree; :class:`ScratchClone` is that receipt
        for clones the helper made);
      * git's EFFECTIVE WORK TREE is the clone root itself:
        ``rev-parse --show-toplevel`` from the root and the deepest
        directory resolves to the clone root, and ``core.worktree`` is
        unset in the local config — the config door that redirects
        ``checkout``/``clean``/``reset`` to a foreign tree while every
        git-dir answer above stays in-clone (the --show-toplevel probe
        closes the redirection class; the config probe names the known
        door);
      * `clone_path` itself is not a symlink — what the caller writes
        through and what was probed must be the same tree, and a probe
        cannot prove that through a link (unprovable == unsafe);
      * no other ``.git`` entry of ANY kind — file, directory, symlink,
        or CASE VARIANT (git honours ``.GIT`` on a case-insensitive
        filesystem) — exists anywhere under the clone;
      * no symlink under the clone, whatever its name, resolves outside
        the clone (measured, escape channel 4; "outside the clone" is the
        checkable superset of "into the source repo" for a standalone
        probe that knows only the clone).

    Raises :class:`ScratchCloneError` with
    :data:`Refusal.ISOLATION_UNVERIFIED` on any other answer, including a
    failed probe invocation: unprovable and unsafe are the same state here.
    Returns None on proof — CHOICE: no boolean form; the rejected
    alternative, ``is_isolated() -> bool``, is one `if` a brief writes and
    forgets, and a forgotten False is a silent copy.
    """
    def _unverified(detail: str) -> NoReturn:
        raise ScratchCloneError(Refusal.ISOLATION_UNVERIFIED, detail=detail)

    root = clone_path
    if root.is_symlink():
        _unverified(
            f"{root} is a symlink — the tree probed and the tree written "
            "through the link cannot be proven the same")
    if not root.is_dir():
        _unverified(f"{root} is not a directory — nothing to probe")
    root_res = root.resolve()

    # Quarantine internals: a DIRECTORY (not a gitfile, not a link), no
    # commondir, no alternates — the channels that split the two rev-parse
    # answers or read foreign objects while both answer in-clone.
    git_root = root / ".git"
    if git_root.is_symlink() or not git_root.is_dir():
        _unverified(f"root .git at {git_root} is not a plain directory")
    quarantine = git_root.resolve()
    if (git_root / "commondir").exists():
        _unverified(f"quarantine carries a commondir file: {git_root}")
    if (git_root / "objects" / "info" / "alternates").exists():
        _unverified(
            f"quarantine carries objects/info/alternates: {git_root}")

    # Quarantine EMPTINESS: every check above is satisfied by the real
    # repository itself — the real main worktree, handed to this probe
    # directly or through a symlink, is self-contained too. What only a
    # quarantine has is NOTHING: no ref, no object, no registered
    # worktree, no remote. A refs file or an object file here means a
    # repository somebody's history lives in, and a write there is the
    # incident regardless of where discovery terminates.
    if os.path.lexists(git_root / "packed-refs"):
        _unverified(f"quarantine carries packed-refs: {git_root}")
    if os.path.lexists(git_root / "worktrees"):
        _unverified(
            f"quarantine carries a worktrees dir — linked worktrees are "
            f"registered against it: {git_root}")
    for subdir, what in ((git_root / "refs", "a ref"),
                         (git_root / "objects", "an object")):
        try:
            content = [e for e in _entries_under(subdir)
                       if e.is_symlink() or not e.is_dir()]
        except OSError as exc:
            _unverified(f"quarantine scan could not complete: {exc}")
        if content:
            _unverified(
                f"quarantine carries {what} — a repository with content "
                f"is not a quarantine: {content[0]}")

    # Filesystem walk: no other .git entry of ANY kind, no symlink under
    # ANY name resolving outside the clone; an unresolvable link (dangling
    # target, a loop) is unprovable and gets the unsafe answer — resolution
    # is STRICT, because the default lexical fallback accepts a dangling
    # link whose unresolved text merely reads in-clone. The walk raises on
    # a subtree it cannot read (default os.walk SKIPS it — a probe that
    # never looked inside a subtree has not proven anything about it). The
    # same pass finds the deepest probe-able directory (never inside a
    # .git).
    deepest = root
    deepest_depth = 0
    try:
        for dirpath, dirnames, filenames in os.walk(
                root, followlinks=False, onerror=_raise_scan_error):
            base = Path(dirpath)
            for name in dirnames + filenames:
                entry = base / name
                # Case-insensitive: git honours `.GIT` (any case variant)
                # on a case-insensitive filesystem, and a probe that only
                # matches the exact spelling walks past it there.
                if (name.lower() == ".git"
                        and entry.relative_to(root) != Path(".git")):
                    _unverified(
                        f"a .git entry exists under the clone: {entry}")
                if entry.is_symlink():
                    try:
                        # RuntimeError: pre-3.13 CPython reports a symlink
                        # loop as RuntimeError rather than OSError(ELOOP).
                        target = entry.resolve(strict=True)
                    except (OSError, RuntimeError) as exc:
                        _unverified(f"unresolvable symlink {entry}: {exc}")
                    if not target.is_relative_to(root_res):
                        _unverified(
                            f"symlink {entry} resolves outside the clone "
                            f"to {target}")
            if any(part.lower() == ".git"
                   for part in base.relative_to(root).parts):
                continue
            for name in dirnames:
                if name.lower() == ".git":
                    continue
                depth = len((base / name).relative_to(root).parts)
                if depth > deepest_depth:
                    deepest_depth = depth
                    deepest = base / name
    except OSError as exc:
        _unverified(f"filesystem scan could not complete: {exc}")

    # Git's own answers to emptiness and routing. Every probe here accepts
    # exactly ONE answer — the one a fresh quarantine gives — and folds
    # every other returncode, including _git_run's synthetic -1 (git did
    # not run) and 128 (corrupt repository), into the unsafe answer: a
    # probe that itself failed has proven nothing, and "proven nothing"
    # must never read as "found nothing".
    #
    # HEAD: `rev-parse --verify --quiet HEAD` answers rc 1 and prints
    # nothing for an unborn HEAD — the only passing shape. rc 0 means a
    # repository with history.
    head = _git_run(["rev-parse", "--verify", "--quiet", "HEAD"], cwd=root)
    if head.returncode == 0:
        _unverified(
            f"HEAD resolves to {head.stdout.strip()} — a repository with "
            "history is not a quarantine")
    if head.returncode != 1 or head.stdout.strip():
        _unverified(
            "HEAD probe did not answer 'unborn': "
            f"rc={head.returncode} {(head.stdout or head.stderr).strip()}")
    # Remotes: a local-path remote.url is a door to the real repo that no
    # filesystem walk of THIS tree can see. `git config --get-regexp`
    # exits 1 for "no match" — the only passing answer.
    remotes = _git_run(
        ["config", "--local", "--get-regexp", r"^remote\."], cwd=root)
    if remotes.returncode != 1:
        _unverified(
            "quarantine carries a configured remote (or the remote probe "
            f"failed): rc={remotes.returncode} "
            f"{(remotes.stdout or remotes.stderr).strip()}")
    # core.worktree: the config door that redirects git's WORK TREE while
    # every git-dir answer stays in-clone — `git checkout`/`git clean` run
    # here would write to the configured tree, not this one. `--get` exits
    # 1 for "unset" — the only passing answer. The --show-toplevel probe
    # below closes work-tree redirection generically; this probe exists so
    # the refusal NAMES the door when it is this one.
    worktree_cfg = _git_run(
        ["config", "--local", "--get", "core.worktree"], cwd=root)
    if worktree_cfg.returncode != 1:
        _unverified(
            "quarantine configures core.worktree (or the probe failed): "
            f"rc={worktree_cfg.returncode} "
            f"{(worktree_cfg.stdout or worktree_cfg.stderr).strip()}")

    # Git's walk: all three rev-parse answers, from the root AND the
    # deepest directory, resolved against the real filesystem before
    # comparing — --git-common-dir answers relative to the invocation dir
    # (measured). --show-toplevel is the WORK-TREE half of the question:
    # both git-dir answers stay in-clone while core.worktree (or any
    # future work-tree redirection) points git's checkout/clean/reset at a
    # foreign tree, so the effective toplevel must resolve to the clone
    # root itself — from every probe cwd, closing the class, not the one
    # config key. In a bare or otherwise toplevel-less repository the flag
    # exits nonzero, which the rc check turns into the same refusal.
    probe_dirs = (root,) if deepest == root else (root, deepest)
    expected = (("--absolute-git-dir", quarantine),
                ("--git-common-dir", quarantine),
                ("--show-toplevel", root_res))
    for probe_cwd in probe_dirs:
        for flag, want in expected:
            proc = _git_run(["rev-parse", flag], cwd=probe_cwd)
            if proc.returncode != 0:
                _unverified(
                    f"probe git rev-parse {flag} failed at {probe_cwd}: "
                    f"{proc.stderr.strip()}")
            raw = Path(proc.stdout.strip())
            answered = (raw if raw.is_absolute() else probe_cwd / raw
                        ).resolve()
            if answered != want:
                _unverified(
                    f"rev-parse {flag} at {probe_cwd} answered {answered}, "
                    f"not {want}")


def _swap_target(clone: ScratchClone, relpath: str) -> Path:
    """The one file a swap seam may touch, or the seam's named refusal.

    Escape is judged on the RESOLVED path — ``..``, an absolute path, and
    a symlink anywhere along the way all collapse to "where would the
    write land", and that answer must be inside the clone. Resolution is
    STRICT, same rule as the clone scans: a dangling link or a link loop
    has no provable landing place, and unprovable gets the escape answer
    — the default lexical fallback would accept a dangling link whose
    unresolved text merely reads in-clone. ``SWAP_TARGET_MISSING`` is
    reserved for a target that is genuinely ABSENT along a resolvable
    in-clone path. Escape is checked before existence: a path that
    escapes is refused as an escape even when its target exists.
    """
    if Path(relpath).is_absolute():
        raise ScratchCloneError(Refusal.SWAP_ESCAPES_CLONE, detail=relpath)
    root_res = clone.path.resolve()
    candidate = clone.path / relpath
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        # Absent vs unresolvable: only "nothing at the leaf, no symlink
        # there, parent chain resolves inside the clone" is MISSING;
        # any link involvement (dangling leaf, dangling parent) is an
        # unprovable landing place and refuses as an escape.
        try:
            parent_res = candidate.parent.resolve(strict=True)
        except (OSError, RuntimeError):
            raise ScratchCloneError(
                Refusal.SWAP_ESCAPES_CLONE, detail=f"{relpath}: {exc}")
        if (not os.path.lexists(candidate)
                and parent_res.is_relative_to(root_res)):
            raise ScratchCloneError(
                Refusal.SWAP_TARGET_MISSING, detail=relpath)
        raise ScratchCloneError(
            Refusal.SWAP_ESCAPES_CLONE, detail=f"{relpath}: {exc}")
    except (OSError, RuntimeError) as exc:
        # RuntimeError: pre-3.13 CPython reports a symlink loop as
        # RuntimeError rather than OSError(ELOOP).
        raise ScratchCloneError(
            Refusal.SWAP_ESCAPES_CLONE, detail=f"{relpath}: {exc}")
    if not resolved.is_relative_to(root_res):
        raise ScratchCloneError(Refusal.SWAP_ESCAPES_CLONE, detail=relpath)
    if not resolved.is_file():
        raise ScratchCloneError(Refusal.SWAP_TARGET_MISSING, detail=relpath)
    return resolved


def swap_in(clone: ScratchClone, relpath: str, mutated: bytes) -> SwapToken:
    """Write `mutated` over `relpath` in the clone, defeating Hazard B.

    The replacement for every ``git checkout <tree-ish> -- .`` /
    ``--work-tree`` restore dance a probe brief has improvised (Hazard A,
    "by replacement"). Reads the original bytes, writes `mutated`, and sets
    the file's mtime at least :data:`MTIME_ADVANCE_SECONDS` past the
    ORIGINAL's — same-size same-second mutations are the measured trap, so
    the stride is unconditional, not a fallback for equal sizes.

    Refuses with :data:`Refusal.SWAP_ESCAPES_CLONE` when `relpath` resolves
    outside ``clone.path`` (``..``, absolute, or through a symlink), and
    with :data:`Refusal.SWAP_TARGET_MISSING` when there is nothing there to
    mutate. Returns the :class:`SwapToken` that :func:`swap_back` requires.
    """
    target = _swap_target(clone, relpath)
    original = target.read_bytes()
    original_ns = target.stat().st_mtime_ns
    target.write_bytes(mutated)
    new_ns = max(target.stat().st_mtime_ns,
                 original_ns + MTIME_ADVANCE_SECONDS * _NS_PER_SECOND)
    os.utime(target, ns=(new_ns, new_ns))
    return SwapToken(relpath=relpath, original=original,
                     mutated_mtime_ns=target.stat().st_mtime_ns)


def swap_back(clone: ScratchClone, token: SwapToken) -> None:
    """Restore the original bytes from `token`, defeating Hazard B again.

    Writes ``token.original`` over ``token.relpath`` and sets mtime at
    least :data:`MTIME_ADVANCE_SECONDS` past ``token.mutated_mtime_ns`` —
    the restore direction is where the measured incident lived (a same-size
    mutation RESTORED within one second reports as covered when it is not),
    so the restored file may never share a (whole-second mtime, size) key
    with the mutant. Same escape and existence refusals as
    :func:`swap_in`.
    """
    target = _swap_target(clone, token.relpath)
    target.write_bytes(token.original)
    new_ns = max(
        target.stat().st_mtime_ns,
        token.mutated_mtime_ns + MTIME_ADVANCE_SECONDS * _NS_PER_SECOND)
    os.utime(target, ns=(new_ns, new_ns))


def main(argv: Sequence[str]) -> int:
    """CLI face: ``python -m claude_dispatcher.scratch_clone SRC DEST``.

    The callers this unit is for are agents in shell sessions — the
    incident was three agents typing ``cp -a`` — so the helper must cost
    one line to invoke or the briefs will keep losing to muscle memory.
    Exactly two positional arguments; on success prints the clone path
    alone on stdout (so ``$(...)`` captures it) and exits 0. On refusal
    prints :func:`refusal_message` to stderr and exits 2. Anything else
    about the invocation is usage, exit 3. CHOICE — no flags at all: the
    rejected alternative, a --force / --skip-probe escape hatch, is the
    silent copy with a receipt. The face inherits
    the scrub by delegation — it calls :func:`make_scratch_clone` and adds
    no git subprocess of its own — which is why it is the recommended
    entry for an agent shell whose environment may carry ``GIT_*``.
    """
    args = list(argv)
    if len(args) != 2 or any(arg.startswith("-") for arg in args):
        print("usage: python -m claude_dispatcher.scratch_clone SRC DEST",
              file=sys.stderr)
        return 3
    try:
        clone = make_scratch_clone(Path(args[0]), Path(args[1]))
    except ScratchCloneError as err:
        print(err, file=sys.stderr)
        return 2
    print(clone.path)
    return 0


if __name__ == "__main__":  # pragma: no cover - script face
    raise SystemExit(main(sys.argv[1:]))
