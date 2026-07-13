# Single orchestrator

Under `dispatcher run`, the **dispatcher is the only orchestrator**. Agents
are **workers**.

## Rule

| Job | Owner |
|-----|--------|
| Worktree, branch, dependency merge | Dispatcher |
| What runs next / cascade / resume | Dispatcher |
| Mechanical test gate | Dispatcher |
| LLM verify / cross-family panel | Dispatcher (spawns workers) |
| PR, merge, journal, status | Dispatcher |
| **Write the code** | Implementer agent (claude / grok / codex / gemini) |
| Optional design options | Future dispatcher *stage* → design worker |
| Interactive multi-step coaching | `tasker.md` **outside** the dispatcher |

## Prompt contract

Every implementer spawn gets the same job shape (`IMPLEMENTER_PROMPT_TEMPLATE`
in `spawn.py`):

- implement the task in CWD  
- do not adopt Tasker  
- do not open PRs  
- write a short summary to `$SUMMARY_PATH`

## Interactive vs dispatched

| Mode | Orchestrator | Role file |
|------|--------------|-----------|
| `dispatcher run` | Dispatcher | implementer brief (no Tasker) |
| Claude Code `/work-ticket` (no dispatcher) | Tasker | `.claude/workflow/roles/tasker.md` |
| Grok TUI interactive | Human + agent | optional Tasker later |

## Why

Stacking Tasker under the dispatcher creates two orchestrators, double review
risk, and unfair comparisons (Claude “thick” path vs Grok thin path). Quality
for batch work belongs in mechanical gates, verifier, and panel — not in
re-implementing Tasker inside the model.
