"""D-61 — a fresh worktree is a new install, and git will not bring the parser.

`ts_parser_vendor`'s docstring says fetching the TypeScript parser is "an
INSTALL-TIME step, and never a judgement-time one. Run it once per install."
That is right for a checkout and false for this dispatcher: every task runs in
a fresh `git worktree`, and `typescript.js` (8.7 MB) is gitignored under the
operator ruling of 2026-08-10, so `git worktree add` never brings it.

Measured on a fresh worktree of this repository before the fix:

    ls src/claude_dispatcher/ts_signature_fingerprint/
      main.cjs                    <- and nothing else
    pytest tests/test_ts_comparator.py
      87 failed, 100 passed, 3 errors

so the mechanical gate went red on the FIRST run of EVERY TASK, the dispatcher
spawned a fix-the-tests agent whose real job was a file copy, that agent
committed NOTHING (the file is ignored), and the second run passed. One wasted
agent spawn plus a ~150 s second suite run per task, on every wave. It was
recorded as a flake in D-57 and it was deterministic.

The fixture is a REAL git worktree of a REAL repository with a REAL gitignore.
A fake filesystem cannot reproduce the defect, because the defect IS what git
chooses to materialise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from claude_dispatcher import worktree as wt_mod

REL = "src/claude_dispatcher/ts_signature_fingerprint/typescript.js"
LICENCE = "src/claude_dispatcher/ts_signature_fingerprint/LICENSE.typescript.txt"


def _git(repo: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=str(repo), capture_output=True, text=True,
        check=True, timeout=30,
    ).stdout.strip()


@pytest.fixture()
def install(tmp_path: Path) -> Path:
    """A repository shaped like this one: the parser present on disk, ignored
    by git, with its tracked sibling committed."""
    repo = tmp_path / "install"
    (repo / "src/claude_dispatcher/ts_signature_fingerprint").mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "s@e.invalid")
    _git(repo, "config", "user.name", "S")
    (repo / ".gitignore").write_text(f"/{REL}\n/{LICENCE}\n")
    (repo / "src/claude_dispatcher/ts_signature_fingerprint/main.cjs").write_text(
        "// tracked sibling\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    # The install-time artifacts: on disk, never in the index.
    (repo / REL).write_text("// 8.7MB of parser, pretend\n")
    (repo / LICENCE).write_text("Apache-2.0\n")
    assert _git(repo, "status", "--porcelain") == "", (
        "the fixture no longer reproduces the input: the parser must be "
        "IGNORED, not merely uncommitted")
    return repo


def test_seal_D61_git_alone_does_not_materialise_the_parser(install, tmp_path):
    """The defect. A fresh worktree gets the tracked sibling and nothing else —
    this is what made the first mechanical verdict of every task meaningless."""
    wt = tmp_path / "bare-wt"
    _git(install, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    assert (wt / "src/claude_dispatcher/ts_signature_fingerprint/main.cjs").is_file()
    assert not (wt / REL).exists(), (
        "if git now brings the ignored parser, this fixture no longer "
        "reproduces D-61")


def test_seal_D61_provisioning_copies_the_install_time_artifacts(install, tmp_path):
    wt = tmp_path / "wt"
    _git(install, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    copied = wt_mod.provision_untracked_deps(wt, source_root=install)
    assert set(copied) == {REL, LICENCE}
    assert (wt / REL).read_text() == (install / REL).read_text()
    assert (wt / LICENCE).is_file()


def test_seal_D61_the_copy_leaves_the_worktree_committed_clean(install, tmp_path):
    """The committed-tree gate treats ANY uncommitted worktree file as a
    verification failure. A provisioning step that dirtied the tree would trade
    one false red for another."""
    wt = tmp_path / "wt"
    _git(install, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    wt_mod.provision_untracked_deps(wt, source_root=install)
    assert _git(wt, "status", "--porcelain") == "", (
        "provisioning dirtied the worktree — the copied files must be covered "
        "by .gitignore, exactly as they are in the install")


def test_seal_D61_an_install_that_never_vendored_is_not_a_creation_failure(tmp_path):
    """Absence is not an error. The TypeScript comparator is one enrolled
    language among several, and the suite's own rows report its absence far
    better than a crash during `git worktree add` would."""
    empty = tmp_path / "no-vendor"
    (empty / "src/claude_dispatcher/ts_signature_fingerprint").mkdir(parents=True)
    wt = tmp_path / "wt"
    wt.mkdir()
    assert wt_mod.provision_untracked_deps(wt, source_root=empty) == []


def test_seal_D61_an_existing_file_is_never_overwritten(install, tmp_path):
    """A worktree that already has a parser — a resumed run, or one an agent
    vendored itself — keeps its own bytes. Overwriting would make this step a
    silent mutation of a tree the digest check has already accepted."""
    wt = tmp_path / "wt"
    _git(install, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    (wt / REL).parent.mkdir(parents=True, exist_ok=True)
    (wt / REL).write_text("// already here\n")
    copied = wt_mod.provision_untracked_deps(wt, source_root=install)
    assert REL not in copied
    assert (wt / REL).read_text() == "// already here\n"


def test_seal_D61_a_REUSED_worktree_is_provisioned_too(install, tmp_path, monkeypatch):
    """The path the first D-61 fix missed, found live.

    `create` is idempotent: an existing worktree returns early. That early
    return sat BEFORE the provisioning call, so a REUSED worktree — the common
    case for a re-dispatched task, after an unblock, a resume, or a run stopped
    mid-flight — never got the parser. Measured on the live run:
    `worktree-DF-5-3` was created at 10:38:43, the run died on a quota 429, and
    the 12:52 re-dispatch reused it carrying `main.cjs` ALONE. It would have
    paid the entire wasted fix-the-tests round D-61 exists to remove.
    """
    wt = tmp_path / "reused"
    _git(install, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    assert not (wt / REL).exists(), "fixture: the reused worktree must start bare"

    monkeypatch.setattr(wt_mod, "worktree_base", lambda *a, **k: tmp_path)
    monkeypatch.setattr(wt_mod, "worktree_path", lambda base, key: wt)
    monkeypatch.setattr(
        wt_mod, "_checked_out_branch", lambda path, branch: branch)
    monkeypatch.setattr(
        Path(__file__).__class__, "cwd", staticmethod(lambda: install),
        raising=False)
    # `create` resolves its source from the RUNNING install, so point it there.
    monkeypatch.setattr(wt_mod, "_UNTRACKED_DEPS", (REL, LICENCE))
    real = wt_mod.provision_untracked_deps
    monkeypatch.setattr(
        wt_mod, "provision_untracked_deps",
        lambda path, source_root=None: real(path, source_root=install))

    got = wt_mod.create(install, "T-1", "feat/t-1", base_branch="main")
    assert got.path == wt
    assert (wt / REL).is_file(), (
        "a reused worktree was returned without the parser — the idempotent "
        "early return skipped provisioning")


def test_seal_D61_create_provisions_without_being_asked(install, tmp_path):
    """The call site, not just the function. Nothing else in the dispatcher
    provisions a worktree, so a `create` that does not call this leaves every
    task back where D-61 started."""
    import inspect

    src = inspect.getsource(wt_mod.create)
    assert src.count("provision_untracked_deps") >= 3, (
        "create must provision on the fresh-add path AND on BOTH idempotent "
        "reuse returns; a reused worktree is the common case for a "
        "re-dispatched task. "
    ) and (
        "worktree.create no longer provisions untracked deps; every task's "
        "first mechanical verdict goes back to being meaningless")


def test_seal_D61_the_dep_list_names_the_parser_and_its_licence():
    """Shipping the parser without its licence is a licensing defect, not a
    tidiness one."""
    assert REL in wt_mod._UNTRACKED_DEPS
    assert LICENCE in wt_mod._UNTRACKED_DEPS
