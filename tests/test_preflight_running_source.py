"""Seals for the running-source preflight check.

`_check_dispatcher_staleness` compares version strings and its logic is correct
and sealed — but this project's version has been "0.1.0" in every commit of its
history, so the two strings it compares are always equal and it cannot fire.
Content can differ when a version cannot.

Measured 2026-08-18 against the real pipx snapshot on this machine: 44 modules
differ from the repo, `role_protocol.py` among them — the snapshot predates the
role protocol entirely, and the version check reported nothing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from claude_dispatcher import preflight

PYPROJECT = textwrap.dedent('''
    [project]
    name = "claude-dispatcher"
    version = "0.1.0"
''')


def _repo(tmp_path: Path, *, modules: dict[str, str], name: str = "repo") -> Path:
    root = tmp_path / name
    pkg = root / "src" / "claude_dispatcher"
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(PYPROJECT)
    for rel, body in modules.items():
        f = pkg / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    return root


def _check(repo: Path, running: Path | None = None, monkeypatch=None):
    warnings: list[str] = []
    checks: dict = {}
    if running is not None:
        monkeypatch.setattr(preflight, "__file__", str(running / "preflight.py"))
    preflight._check_running_source(repo, warnings, checks)
    return warnings, checks["running_source"]


def test_a_stale_installed_copy_warns_and_names_what_differs(
    tmp_path: Path, monkeypatch
) -> None:
    """The trap. Measured under: compare versions instead of content and this
    reddens — both copies below carry the same version, as every real pair does.
    """
    repo = _repo(tmp_path, modules={
        "role_protocol.py": "FLOOR_GLOBS = ('a', 'b', 'c')\n",
        "orchestrator.py": "def run(): return 2\n",
    })
    installed = _repo(tmp_path, name="installed", modules={
        "role_protocol.py": "# this snapshot predates the floor\n",
        "orchestrator.py": "def run(): return 2\n",
    }) / "src" / "claude_dispatcher"

    warnings, entry = _check(repo, installed, monkeypatch)
    assert entry["state"] == "differs"
    assert entry["differing_count"] == 1
    assert entry["differing_sample"] == ["role_protocol.py"]
    assert len(warnings) == 1
    assert "role_protocol.py" in warnings[0]
    assert "pipx install --force" in warnings[0]


def test_a_module_present_in_only_one_copy_counts_as_differing(
    tmp_path: Path, monkeypatch
) -> None:
    """The real shape of the measured case: the snapshot does not HAVE
    `role_protocol.py` at all. A content-only comparison that skipped missing
    files would report the two copies identical.

    Measured under: intersect the two indexes instead of unioning them and this
    reddens.
    """
    repo = _repo(tmp_path, modules={
        "orchestrator.py": "x = 1\n", "role_protocol.py": "FLOOR_GLOBS = ()\n",
    })
    installed = _repo(tmp_path, name="installed", modules={
        "orchestrator.py": "x = 1\n",
    }) / "src" / "claude_dispatcher"

    warnings, entry = _check(repo, installed, monkeypatch)
    assert entry["state"] == "differs"
    assert entry["differing_sample"] == ["role_protocol.py"]


def test_identical_source_in_a_different_directory_is_silent(
    tmp_path: Path, monkeypatch
) -> None:
    """A `pip install -e` or a freshly reinstalled snapshot lives elsewhere and
    is not stale. Warning here would fire on every correct install.
    """
    mods = {"orchestrator.py": "def run(): return 1\n"}
    repo = _repo(tmp_path, modules=mods)
    installed = _repo(tmp_path, name="installed", modules=mods) / "src" / "claude_dispatcher"
    warnings, entry = _check(repo, installed, monkeypatch)
    assert warnings == [] and entry["state"] == "identical"


def test_running_from_the_repo_itself_is_silent(tmp_path: Path, monkeypatch) -> None:
    """`python -m claude_dispatcher` from the repo — the normal case here."""
    repo = _repo(tmp_path, modules={"orchestrator.py": "x = 1\n"})
    warnings, entry = _check(repo, repo / "src" / "claude_dispatcher", monkeypatch)
    assert warnings == [] and entry["state"] == "running_from_repo"


def test_another_project_is_not_applicable(tmp_path: Path, monkeypatch) -> None:
    """Only claude-dispatcher dispatching ITSELF can be compared this way — any
    other repo's `src/claude_dispatcher` is a coincidence of naming.

    The copies here DIFFER on purpose. With identical copies the name guard is
    unobservable (`running_from_repo` keeps it silent either way), and this row
    passed under a mutation that deleted the guard — the vacuity was found by
    that mutation firing someone else's row instead of this one.
    """
    repo = _repo(tmp_path, modules={"orchestrator.py": "x = 1\n"})
    (repo / "pyproject.toml").write_text(
        PYPROJECT.replace("claude-dispatcher", "some-other-project"))
    installed = _repo(tmp_path, name="installed", modules={
        "orchestrator.py": "x = 999  # a different build entirely\n",
    }) / "src" / "claude_dispatcher"
    warnings, entry = _check(repo, installed, monkeypatch)
    assert warnings == [], "another project must not be judged by this check"
    assert entry["applicable"] is False


def test_a_pure_RENAME_is_not_reported_as_identical(tmp_path: Path, monkeypatch) -> None:
    """Two trees holding the same bytes under different names are not the same
    build: a module that moved is a module the running copy will not import.

    Measured under: drop the path from `_package_digest` and this reddens — the
    contents hash equal and the copies are reported identical.
    """
    repo = _repo(tmp_path, modules={"role_protocol.py": "FLOOR_GLOBS = ()\n"})
    installed = _repo(tmp_path, name="installed", modules={
        "role_policy.py": "FLOOR_GLOBS = ()\n",
    }) / "src" / "claude_dispatcher"
    warnings, entry = _check(repo, installed, monkeypatch)
    assert entry["state"] == "differs"
    assert entry["differing_count"] == 2
    assert len(warnings) == 1


def test_a_repo_without_the_package_is_a_named_skip(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "bare"
    root.mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    warnings, entry = _check(root, tmp_path / "elsewhere", monkeypatch)
    assert warnings == [] and entry["applicable"] is False
    assert "no src/claude_dispatcher" in entry["detail"]


def test_the_check_is_wired_into_run_preflight() -> None:
    """AST, not a substring: a comment satisfies a text search."""
    import ast

    tree = ast.parse(Path(preflight.__file__).read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "run_preflight")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_check_running_source" in called
