"""The scope gate as wired: real git diff, and a block that does not cascade."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from claude_dispatcher import orchestrator as orch
from claude_dispatcher import scope_excursion as scope_mod

HOLD = ["apps/finance-domain/wallet/v2/hold/**"]


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                           text=True, check=True).stdout.strip()


def _repo_reproducing_hold3(tmp_path: Path):
    """The WAL-HOLD-3 shape: own unit modified, another unit's body DELETED."""
    repo = tmp_path / "r"
    (repo / "apps/finance-domain/wallet/v2/hold").mkdir(parents=True)
    (repo / "apps/finance-domain/wallet/v2/ledger").mkdir(parents=True)
    _git(repo.parent, "init", "-q", str(repo))
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "apps/finance-domain/wallet/v2/hold/hold.go").write_text("package hold\n")
    (repo / "apps/finance-domain/wallet/v2/ledger/body.go").write_text("package ledger\n")
    (repo / "apps/finance-domain/wallet/v2/ledger/ledger.go").write_text("package ledger\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "feat/hold-3")
    (repo / "apps/finance-domain/wallet/v2/hold/hold.go").write_text("package hold\n// body\n")
    (repo / "apps/finance-domain/wallet/v2/ledger/ledger.go").write_text("package ledger\n// rewritten\n")
    (repo / "apps/finance-domain/wallet/v2/ledger/body.go").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "[WAL-HOLD-3] codex implementation")
    return repo, base


def test_the_real_diff_reproduces_the_block(tmp_path) -> None:
    repo, base = _repo_reproducing_hold3(tmp_path)
    r = orch._scope_excursion_report(
        repo, "feat/hold-3", base, HOLD, tmp_path / "log", "WAL-HOLD-3")
    assert r is not None
    assert r.severity is scope_mod.Severity.BLOCK
    assert [e.path for e in r.blocking] == [
        "apps/finance-domain/wallet/v2/ledger/body.go"]


def test_the_task_s_own_changes_are_not_excursions(tmp_path) -> None:
    repo, base = _repo_reproducing_hold3(tmp_path)
    r = orch._scope_excursion_report(
        repo, "feat/hold-3", base, HOLD, tmp_path / "log", "K")
    assert all("/hold/" not in e.path for e in r.excursions), r.excursions


def test_no_declared_ownership_asks_nothing(tmp_path) -> None:
    """None means UNJUDGED, not clean -- and the caller must not block on it,
    or every worklist predating `owns:` blocks on its first task."""
    repo, base = _repo_reproducing_hold3(tmp_path)
    assert orch._scope_excursion_report(
        repo, "feat/hold-3", base, [], tmp_path / "log", "K") is None


def test_a_git_failure_is_unjudged_not_blocking(tmp_path) -> None:
    repo, _base = _repo_reproducing_hold3(tmp_path)
    assert orch._scope_excursion_report(
        repo, "feat/hold-3", "not-a-sha", HOLD, tmp_path / "log", "K") is None
    assert orch._scope_excursion_report(
        repo, "feat/hold-3", None, HOLD, tmp_path / "log", "K") is None


def test_a_moved_foreign_file_is_seen_as_a_delete(tmp_path) -> None:
    """`--no-renames` is load-bearing: as R a rename is ONE path and its
    reported name is the DESTINATION, which is inside the owned unit -- so a
    task that moves another unit's file into its own reads as clean. As A+D the
    D half is visible, which is the whole point.

    The moved file is large and byte-identical after the move, on purpose. An
    earlier version of this test also EDITED the file, which dropped git's
    similarity index below the rename threshold so A+D was reported either
    way -- the fixture could not tell the two flags apart, and a mutation
    swapping --no-renames for --find-renames survived it.
    """
    repo, base = _repo_reproducing_hold3(tmp_path)
    src = repo / "apps/finance-domain/wallet/v2/ledger/big.go"
    src.write_text("package ledger\n" + "\n".join(
        f"func F{i}() int {{ return {i} }}" for i in range(200)) + "\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "ledger owns a big file")
    base2 = _git(repo, "rev-parse", "HEAD")
    _git(repo, "mv", str(src.relative_to(repo)),
         "apps/finance-domain/wallet/v2/hold/stolen.go")
    _git(repo, "commit", "-qm", "move it into my unit")

    # Rename detection really would collapse it: prove the fixture discriminates.
    collapsed = _git(repo, "diff", "--name-status", "--find-renames",
                     f"{base2}...feat/hold-3")
    assert collapsed.startswith("R"), collapsed

    r = orch._scope_excursion_report(
        repo, "feat/hold-3", base2, HOLD, tmp_path / "log", "K")
    assert r.severity is scope_mod.Severity.BLOCK
    assert any(e.change == "D" and e.path.endswith("ledger/big.go")
               for e in r.excursions), r.excursions


def test_a_git_exception_is_unjudged_too(tmp_path, monkeypatch) -> None:
    """The other failure path. The bad-SHA test above exercises a non-zero
    RETURN CODE; a raise (timeout, missing binary) is a different branch, and a
    mutation making it fail closed survived until this existed."""
    repo, base = _repo_reproducing_hold3(tmp_path)
    import subprocess as sp

    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd="git", timeout=1)

    # The helper does a function-local `import subprocess`, so the module
    # attribute is the only seam. monkeypatch reverts it.
    monkeypatch.setattr(sp, "run", boom)
    assert orch._scope_excursion_report(
        repo, "feat/hold-3", base, HOLD, tmp_path / "log", "K") is None


def test_the_block_is_terminal_and_does_not_advance_a_rung() -> None:
    """CONTROL FLOW, sealed on source because reaching it behaviourally means
    standing up a full cascade dispatch.

    Asserts there is exactly ONE scope-block site before matching it -- a
    regex that silently found a second is how #99's first seal passed while
    the cascade stayed broken. The property: the site ends the attempt
    (`break`) rather than advancing to the next rung (`continue`), because a
    retry cannot answer "was this appropriate".
    """
    import inspect
    src = inspect.getsource(orch)
    sites = re.findall(
        r"if excursion is not None and excursion\.severity is "
        r"scope_mod\.Severity\.BLOCK:\n(.*?)\n\n", src, re.DOTALL)
    assert len(sites) == 1, f"expected one scope-block site, found {len(sites)}"
    body = sites[0]
    assert "final_status = plan_mod.BLOCKED" in body, body
    assert "break" in body, body
    assert "continue" not in body, "a scope block must not advance a rung"


def test_the_gate_uses_the_same_base_as_the_role_loop_gate() -> None:
    """A different base judges a different diff. `gate_base_sha` already
    accounts for D-54's adjudicated-retry anchor; recomputing one here would
    silently diverge from the gate beside it."""
    import inspect
    src = inspect.getsource(orch)
    call = re.findall(r"excursion = _scope_excursion_report\(\n(.*?)\n        \)",
                      src, re.DOTALL)
    assert len(call) == 1, f"expected one call, found {len(call)}"
    assert "gate_base_sha" in call[0], call[0]
