# PRD — Grok-first dogfood + single orchestrator

## Intent

Prove that `claude-dispatcher` can improve itself when:

1. The dispatcher is the only orchestrator (no Tasker under dispatch).
2. Grok is the default implementer for dogfood tasks.
3. Claude remains available as an implementer when explicitly chosen.

## Acceptance

- Implementer prompts never require `tasker.md` under `dispatcher run`.
- Dogfood tasks in `tasks.yaml` can complete with `agent: grok`.
- Operator can status/report a run without Claude.

## Non-goals

- Replacing interactive Claude Tasker outside the dispatcher.
- Full multi-agent design stage (later plan phase).
