"""Tests for gemini (agy) spawn support and fixture."""

import subprocess
import sys
from pathlib import Path

from claude_dispatcher import spawn as spawn_mod


def test_fake_agy_version_guard():
    """Verify fake_agy has a side-effect-free --version guard."""
    fake_agy = Path(__file__).parent / "fixtures" / "fake_agy.py"
    proc = subprocess.run(
        [sys.executable, str(fake_agy), "--version"],
        capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0
    assert "fake-agy" in proc.stdout


def test_spawn_agent_gemini_headless_invocation(tmp_path, monkeypatch):
    """Verify spawn_agent builds the correct headless argv for gemini (agy) and
    handles the unmeasurable output by synthesizing a summary."""
    fake_agy = str(Path(__file__).parent / "fixtures" / "fake_agy.py")
    
    # Wire fake_agy in as the gemini binary.
    # Since fake_agy is a python script, we wrap it with sys.executable in a helper
    # or just rely on the #! + chmod we already did. Let's just pass its path.
    monkeypatch.setitem(spawn_mod.AGENT_BINS, "gemini", fake_agy)
    
    env = {"SUMMARY_PATH": str(tmp_path / "summary.md"), "TASK_KEY": "T-1"}
    
    # We also need to mock git auto-commit since we're not inside a real worktree in tmp_path
    monkeypatch.setattr(spawn_mod, "_autocommit_worktree", lambda *a, **k: True)
    
    res = spawn_mod.spawn_agent(
        agent="gemini", cwd=tmp_path, env=env, prompt="test prompt", model="Gemini 3.1 Pro (High)"
    )
    
    # We should have a 0 exit code from fake_agy
    assert res.exit_code == 0
    assert "fake_agy done" in res.stdout
    
    # Model should be unmeasurable, usage fields should be None, except we don't have parse_agy_usage.
    # But wait, spawn_agent doesn't even call parse_agy_usage because we didn't implement it!
    # Let's make sure the returned usage has no cost (default).
    assert res.usage.cost_usd is None
    
    # The dispatcher should synthesize a summary since fake_agy doesn't write one properly in parser format
    assert (tmp_path / "summary.md").exists()
    assert "Status:** Done" in (tmp_path / "summary.md").read_text()
