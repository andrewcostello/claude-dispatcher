# Task Batching

> **STATUS: DESIGN DOC — NOT YET IMPLEMENTED.** The `batch_id` field is
> parsed and validated, but the orchestrator currently runs every task as its
> own batch of one (`orchestrator._dispatch_drain`: "Until full batch grouping
> is wired"). Nothing below — shared worktree/session, composite prompt,
> all-or-nothing status — happens yet.

## What is Task Batching?

Task Batching allows the dispatcher to group multiple related tasks from `tasks.yaml` into a single logical execution unit (a "batch"). Instead of spawning an isolated worktree and a fresh LLM session for every individual task, batched tasks are executed together in the same worktree by a single agent session.

## Why is it Important?

1. **Reduced Cost:** Creating an LLM context is expensive. If three tasks modify the same module, batching them eliminates the need to pay for codebase exploration and context caching three separate times.
2. **Drastically Faster Speeds:** Agents spend significant wall-clock time (Time-To-First-Token) analyzing their environment, locating files, and reading instructions. By batching tasks, the agent incurs this "exploration tax" only once per batch.
3. **Cohesive Context:** When related tasks are batched, the agent has native context on its own recent changes. It doesn't have to wait for an upstream PR to merge before it can consume an API or database column it just created in a previous task.

## How to Use Task Batching

To batch tasks, simply assign them the same `batch_id` string in `tasks.yaml`:

```yaml
tasks:
  - key: BSA-FU-100
    summary: Add status_code to Transactions table
    type: feature
    labels: [size:S, epic:refunds]
    batch_id: refund-overhaul
    description: |
      Add a new `status_code` enum column to the Transactions table.
    
  - key: BSA-FU-101
    summary: Update refund API to use status_code
    type: feature
    labels: [size:M, epic:refunds]
    batch_id: refund-overhaul
    description: |
      Update the `POST /api/refund` endpoint to respect the new `status_code` column.
```

### Important Behaviors

- **Status Updates:** If a batch successfully completes, ALL tasks in the batch are marked `Done`. If the batch fails (e.g. LLM Verifier finds gaps or Cross-Family Panel rejects), ALL tasks in the batch are marked `Blocked`.
- **Dependencies:** Ensure that tasks in the same batch do not have strictly ordered cross-dependencies that would prevent them from being in the same runnable "wave", though the orchestrator will safely isolate them if they are.
- **Combined Prompts:** The dispatcher will automatically combine the summaries and descriptions of all batched tasks into a single composite prompt and feed it to the implementer agent.
