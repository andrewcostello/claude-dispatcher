"""Seal: prompt assets are importlib-reachable next to the package.

A pipx/wheel install without verifier_prompts/ makes every LLM verification
fail as verifier_unavailable (live hit: gpa-wave1-20260713). The suite runs
from the source tree, so assert the wheel manifest the way setuptools sees
it: package-data must include the file AND the loader must resolve it
relative to the package, never the CWD.
"""

from pathlib import Path

import claude_dispatcher


def test_verifier_prompt_ships_with_the_package():
    pkg_dir = Path(claude_dispatcher.__file__).parent
    prompt = pkg_dir / "verifier_prompts" / "verifier.md"
    assert prompt.is_file(), (
        "verifier_prompts/verifier.md must live inside the package dir "
        "(and be declared in [tool.setuptools.package-data])"
    )
    assert prompt.stat().st_size > 100


def test_pyproject_declares_prompt_package_data():
    root = Path(claude_dispatcher.__file__).resolve().parents[2].parent
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():  # installed copy — nothing to check here
        return
    text = pyproject.read_text(encoding="utf-8")
    assert "verifier_prompts/*.md" in text
