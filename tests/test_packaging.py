"""Seal: prompt assets are importlib-reachable next to the package.

A pipx/wheel install without verifier_prompts/ makes every LLM verification
fail as verifier_unavailable (live hit: gpa-wave1-20260713). The suite runs
from the source tree, so assert the wheel manifest the way setuptools sees
it: package-data must include the file AND the loader must resolve it
relative to the package, never the CWD.
"""

from pathlib import Path

import claude_dispatcher


def test_every_source_data_asset_ships_with_the_package():
    """Class seal, not an instance seal: EVERY non-.py asset in the source
    tree must be importlib-reachable next to the installed package. The
    instance version of this test missed reviewer_prompts/ and the panel
    broke on the next run (gpa-wave1b)."""
    pkg_dir = Path(claude_dispatcher.__file__).parent
    src_pkg = Path(__file__).resolve().parents[1] / "src" / "claude_dispatcher"
    if not src_pkg.is_dir():  # running from an installed copy
        src_pkg = pkg_dir
    assets = [
        p.relative_to(src_pkg)
        for p in src_pkg.rglob("*")
        if p.is_file() and p.suffix != ".py" and "__pycache__" not in p.parts
    ]
    assert assets, "expected at least the prompt assets in the source tree"
    missing = [str(rel) for rel in assets if not (pkg_dir / rel).is_file()]
    assert not missing, (
        f"source data assets not reachable next to the installed package "
        f"(declare them in [tool.setuptools.package-data]): {missing}"
    )


def test_pyproject_declares_prompt_package_data():
    root = Path(claude_dispatcher.__file__).resolve().parents[2].parent
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():  # installed copy — nothing to check here
        return
    text = pyproject.read_text(encoding="utf-8")
    assert "verifier_prompts/*.md" in text


def test_every_asset_matches_a_declared_package_data_glob():
    """Compare the source tree against the DECLARED GLOBS, not against an
    installed copy.

    `test_every_source_data_asset_ships_with_the_package` cannot catch a
    missing declaration in the way the suite is actually run: with
    PYTHONPATH=src, `claude_dispatcher.__file__` IS the source tree, so it
    compares src against itself and passes whatever pyproject says. Its own
    docstring records that the previous version missed reviewer_prompts/ and
    the panel broke on the next run -- and the replacement is vacuous in the
    same configuration.

    Measured 2026-09-03: `*_prompts/*.md` is one level deep, so the three
    files in reviewer_prompts/domains/ shipped in no wheel. A pipx-installed
    dispatcher then failed every cross-family panel with "domain context
    missing: .../domains/_default.md. Available:" -- an empty list, because
    the directory was empty.
    """
    import pathlib, tomllib
    root = pathlib.Path(__file__).resolve().parents[1]
    src_pkg = root / "src" / "claude_dispatcher"
    if not src_pkg.is_dir():
        import pytest
        pytest.skip("not running from a source checkout")
    globs = tomllib.loads((root / "pyproject.toml").read_text(
        encoding="utf-8"))["tool"]["setuptools"]["package-data"]["claude_dispatcher"]
    # Only TRACKED files are source assets. A local build output (a compiled
    # helper under .build/) is gitignored and ships from nobody's checkout.
    import subprocess
    tracked = set(subprocess.run(
        ["git", "ls-files", "-z", "src/claude_dispatcher"], cwd=root,
        capture_output=True, text=True, check=True).stdout.split("\0"))
    unmatched = []
    for f in src_pkg.rglob("*"):
        if not f.is_file() or f.suffix == ".py" or "__pycache__" in f.parts:
            continue
        if f.relative_to(root).as_posix() not in tracked:
            continue
        rel = f.relative_to(src_pkg).as_posix()
        if not any(pathlib.PurePosixPath(rel).full_match(g) for g in globs):
            unmatched.append(rel)
    assert not unmatched, (
        "source assets matched by NO [tool.setuptools.package-data] glob, so "
        f"they ship in no wheel: {sorted(unmatched)[:12]}"
    )
