import subprocess
from pathlib import Path

import claude_dispatcher.cross_family_reviewer as cfr


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_collect_diff_excludes_generated(tmp_path: Path):
    """Generated pb.go/lockfile churn must not consume the review diff window
    (2026-07-12: four tasks false-blocked verification_incomplete with real
    code past the truncation cap while generated output filled it)."""
    repo = tmp_path
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "real.go").write_text("package a\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "checkout", "-qb", "feat")
    (repo / "real.go").write_text("package a // changed\n")
    (repo / "big.pb.go").write_text("x\n" * 500)
    (repo / "go.sum").write_text("dep v1\n" * 200)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "work")

    diff = cfr.collect_diff(repo_root=repo, base_branch="main", branch="feat")
    assert "real.go" in diff
    assert "big.pb.go" not in diff
    assert "go.sum" not in diff
