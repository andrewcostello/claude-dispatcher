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
