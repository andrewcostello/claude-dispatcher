"""Raise a GitHub PR from prepared metadata via the `gh` CLI.

The dispatcher invokes this when the human approves a Tasker-prepared PR in
supervised mode. The Tasker writes the title, branch, and body into the
summary file; the dispatcher reads them and runs `gh pr create` from the
task's worktree directory.

The Tasker never invokes gh directly in the gated path — it stops short and
hands the metadata to the dispatcher. This centralizes the actual external
side effect (the PR creation) in the dispatcher, which is the place that
owns the audit log and the YAML write-back.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class PRResult:
    url: str | None
    error: str | None


def raise_pr(
    *,
    cwd: Path,
    title: str,
    body: str,
    branch: str,
    base: str = "main",
    gh_bin: str = "gh",
) -> PRResult:
    """Run `gh pr create` from the worktree. Returns the URL on success.

    `gh` reads the body from stdin when --body-file - is used. We never
    write the body to disk — keeps the side effect contained.
    """
    cmd = [
        gh_bin, "pr", "create",
        "--title", title,
        "--body-file", "-",
        "--base", base,
        "--head", branch,
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=body,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            check=False,
            timeout=120,
        )
    except FileNotFoundError:
        return PRResult(url=None, error=f"gh binary not found: {gh_bin}")
    except subprocess.TimeoutExpired:
        return PRResult(url=None, error="gh pr create timed out after 120s")

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "unknown gh error"
        return PRResult(url=None, error=err)

    # gh prints the URL as the last non-empty line of stdout
    url = ""
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("http"):
            url = line
            break
    if not url:
        return PRResult(url=None, error="gh returned no URL on stdout")
    return PRResult(url=url, error=None)
