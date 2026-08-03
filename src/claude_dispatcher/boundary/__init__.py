"""Classification→gating boundary (design v20; implementation plan v2).

DARK MODE until PR6 (plan §1, grok M1): this package is importable from
tests only. The architecture test in tests/boundary/test_pr0.py fails on any
production import of ``claude_dispatcher.boundary``; the door-entrypoint
allowlist in ``schema/ast_allowlists.yaml`` is empty until the PR6 cut-over
fills it.

``boundary.generated`` is written by ``tools/fsmgen.py`` from ``schema/*``
and is the sole source of every FSM/§9/panel/error type (plan §1, grok B2) —
PR2+ may add only the §3.1 ``ClassifyOutcome`` T15 fixture verbatim,
``parse_classification`` + equation checks, and thin adapters.
"""
