"""Classification→gating boundary (design v20; implementation plan v2).

DARK MODE until PR6 (plan §1, grok M1): this package is importable from
tests only.

WHAT ENFORCES THAT, precisely (panel round 4, finding 7): a STATIC gate,
not a runtime one. ``tests/boundary/test_pr0.py`` walks every module under
``src/claude_dispatcher`` and fails on any import of this package, in every
import spelling, while the door-entrypoint allowlist in
``schema/ast_allowlists.yaml`` is empty (asserted empty until PR6).

There is deliberately NO import-time raise here. A module that refuses to
import cannot be imported by the tests that seal it either, and the failure
would surface at run time in the deployment rather than at review time in
CI — the opposite of what dark mode is for. The threat model is honest
misconfiguration (§0.1), which a static gate catches before merge; PR6
retires the question by filling the allowlist.

``boundary.generated`` is written by ``tools/fsmgen.py`` from ``schema/*``
and is the sole source of every FSM/§9/panel/error type (plan §1, grok B2) —
PR2+ may add only the §3.1 ``ClassifyOutcome`` T15 fixture verbatim,
``parse_classification`` + equation checks, and thin adapters.
"""
