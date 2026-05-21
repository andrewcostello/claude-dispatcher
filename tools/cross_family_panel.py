#!/usr/bin/env python3
"""Standalone runner for the cross-family reviewer panel.

Invokes the three-family panel against an arbitrary git diff + summary.md
without going through the dispatcher's lifecycle. Lets us validate the
panel mechanics retroactively (against an already-integrated ticket) or
test prompt iteration without running a full dispatcher cycle.

Usage:
    python tools/cross_family_panel.py \
        --repo /path/to/repo \
        --base main \
        --branch feat/my-ticket \
        --ticket TICKET-1 \
        --summary-md /path/to/summary.md

For a retroactive run against an already-merged ticket:
    python tools/cross_family_panel.py \
        --repo /home/andrew/Project/evenplay-mono \
        --base 49efcc8b^2 \
        --branch 49efcc8b \
        --ticket SMG-2947 \
        --summary-md /home/andrew/Project/evenplay-mono/docs/runs/.../summary.md

Output is JSON on stdout (panel.to_dict()), with progress to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _add_src_to_path() -> None:
    """Make `from claude_dispatcher import ...` work when running this
    script directly without `pip install -e`.
    """
    here = Path(__file__).resolve().parent
    src = here.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_add_src_to_path()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", required=True,
                   help="Path to the git repo (worktree-aware).")
    p.add_argument("--base", required=True,
                   help="Base ref (branch name or commit SHA). The diff is "
                        "computed as `git diff <base>...<branch>`.")
    p.add_argument("--branch", required=True,
                   help="Feature ref (branch name or commit SHA).")
    p.add_argument("--ticket", required=True,
                   help="Ticket key (e.g. SMG-2947).")
    p.add_argument("--ticket-summary", default="",
                   help="Optional one-line ticket summary (rendered in the prompt).")
    p.add_argument("--summary-md", required=True, type=Path,
                   help="Path to the Tasker's summary.md.")
    p.add_argument("--family",
                   choices=("all", "claude", "gemini", "codex"),
                   default="all",
                   help="Restrict to one family (for debugging / prompt iteration).")
    p.add_argument("--timeout", type=int, default=600,
                   help="Per-reviewer timeout in seconds (default: 600).")
    p.add_argument("--max-diff-lines", type=int, default=None,
                   help="Cap the diff at this many lines (default: module default).")
    p.add_argument("--output",
                   choices=("json", "markdown", "both"),
                   default="markdown",
                   help="Output format. 'markdown' is human-readable; 'json' is "
                        "PanelVerdict.to_dict(); 'both' prints markdown then JSON.")
    p.add_argument("--dry-run-with-stub-output",
                   help="Path to a file containing a stub reviewer output. If set, "
                        "skips real CLI invocations and feeds this output to all "
                        "three reviewers. Used for testing the parser.")
    args = p.parse_args(argv)

    from claude_dispatcher import cross_family_reviewer as cfr

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists() and not (repo / ".git").is_file():
        print(f"error: {repo} is not a git repo", file=sys.stderr)
        return 2
    if not args.summary_md.exists():
        print(f"error: summary.md not found: {args.summary_md}", file=sys.stderr)
        return 2

    print(f"[panel] ticket={args.ticket} base={args.base} branch={args.branch}",
          file=sys.stderr)
    print(f"[panel] computing diff...", file=sys.stderr)
    diff = cfr.collect_diff(
        repo_root=repo,
        base_branch=args.base,
        branch=args.branch,
        max_lines=args.max_diff_lines or cfr.MAX_DIFF_LINES,
    )
    print(f"[panel] diff: {diff.count(chr(10))} lines, {len(diff)} bytes",
          file=sys.stderr)

    summary_md = args.summary_md.read_text(encoding="utf-8")

    reviewers = _build_reviewers(args.family, args.timeout, args.dry_run_with_stub_output)
    print(f"[panel] reviewers: {[r.family for r in reviewers]}", file=sys.stderr)

    panel = cfr.run_panel(
        ticket_key=args.ticket,
        ticket_summary=args.ticket_summary,
        summary_md=summary_md,
        diff=diff,
        branch=args.branch,
        base_branch=args.base,
        reviewers=reviewers,
        log=lambda m: print(m, file=sys.stderr),
    )

    if args.output in ("markdown", "both"):
        print(cfr.render_findings_markdown(panel))
    if args.output in ("json", "both"):
        print(json.dumps(panel.to_dict(), indent=2))

    # Exit 0 on approve, 1 on block, 2 on incomplete (so CI can gate)
    return {"approve": 0, "block": 1, "incomplete": 2}.get(panel.consensus, 1)


def _build_reviewers(family: str, timeout: int, stub_path: str | None) -> list:
    from claude_dispatcher import cross_family_reviewer as cfr

    if stub_path:
        return [_StubReviewer(fam, stub_path) for fam in ("claude", "gemini", "codex")
                if family in ("all", fam)]

    families = ["claude", "gemini", "codex"] if family == "all" else [family]
    table = {
        "claude": cfr.ClaudeReviewer,
        "gemini": cfr.GeminiReviewer,
        "codex": cfr.CodexReviewer,
    }
    return [table[f](timeout_seconds=timeout) for f in families]


class _StubReviewer:
    """A reviewer that reads its 'output' from a file. Used by
    --dry-run-with-stub-output to exercise the parser end-to-end without
    touching the real CLIs.
    """

    def __init__(self, family: str, stub_path: str) -> None:
        self.family = family
        self.stub_path = stub_path

    def review(self, prompt: str):  # noqa: ARG002
        from claude_dispatcher import cross_family_reviewer as cfr

        text = Path(self.stub_path).read_text(encoding="utf-8")
        return cfr.parse_review_output(self.family, text)


if __name__ == "__main__":
    sys.exit(main())
