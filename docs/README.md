# Docs map

Start at **[onboarding/](./onboarding/README.md)** unless you already know
the dispatcher and need a flag or a schema.

## Onboarding

| Doc | What it is |
|---|---|
| [onboarding/README.md](./onboarding/README.md) | Mental model + reading order |
| [onboarding/how-it-works.md](./onboarding/how-it-works.md) | Graph, loop, gates, integration |
| [onboarding/why-it-works.md](./onboarding/why-it-works.md) | Design bets and scars |
| [onboarding/how-to-use.md](./onboarding/how-to-use.md) | First run, observe, unblock |
| [onboarding/design-loop.md](./onboarding/design-loop.md) | Data model + load against raw stores, *before* `tasks.yaml` |

## Setup and authoring

| Doc | What it is |
|---|---|
| [../SETUP.md](../SETUP.md) | Fresh-machine install (dispatcher + workflow + optional forecast) |
| [new-project-setup.md](./new-project-setup.md) | `.dispatcher.yaml`, roles, holes, floor, known-red |
| [how-to-author-tasks.md](./how-to-author-tasks.md) | Planner playbook for `tasks.yaml` |
| [templates/planner-prompt.md](./templates/planner-prompt.md) | Paste-this planner prompt |
| [templates/PRD-template.md](./templates/PRD-template.md) | Feature intent oracle |
| [task-batching.md](./task-batching.md) | `batch_id` mechanics |
| [machine-profile.md](./machine-profile.md) | `dispatcher doctor` profile format |

## Architecture and design

| Doc | What it is |
|---|---|
| [architecture/single-orchestrator.md](./architecture/single-orchestrator.md) | Dispatcher orchestrates; agents implement |
| [contract-first-deviation-model.md](./contract-first-deviation-model.md) | Skeleton first; audited deviations |
| [agent-routing-policy.md](./agent-routing-policy.md) | Cheap-first cascade (policy essay; code is narrower — see onboarding) |
| [feature-review-loop.md](./feature-review-loop.md) | PRD review + disposition + FIX-* loop |
| [presentation-outline.md](./presentation-outline.md) | Talk: working styles, then this dispatcher |

## Run-time reference

| Doc | What it is |
|---|---|
| [../README.md](../README.md) | CLI surface, YAML stamps, PR-flow, failure modes |
| [journal-format.md](./journal-format.md) | Hash-chained event journal (independent-reader spec) |
| [report-json.md](./report-json.md) | `dispatcher report --json` schema |
| [slack-app-setup.md](./slack-app-setup.md) | Slack notifications |

## Dogfood (this repo, on itself)

| Doc | What it is |
|---|---|
| [dogfood/README.md](./dogfood/README.md) | Index |
| [dogfood/GROK_OPERATOR.md](./dogfood/GROK_OPERATOR.md) | Grok-first operator runbook |

## Generated / historical (not onboarding)

`generated/` is produced from `schema/` — do not hand-edit.
`plans/`, `rulings/`, `runs/`, `reviewer-bakeoff/`, `retroactive_panel_results/`
are evidence and design history. Read them when a ruling or a scar is
named; do not start there.
