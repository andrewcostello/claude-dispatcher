# Using the dispatcher on a new project

Start here. `README.md` is the CLI reference and `how-to-author-tasks.md` is the
planner's guide; this page is the shortest path from an empty repo to a run you
can trust, and it covers the build protocol those two predate.

Everything below is measured against the code at `feat/D1-role-protocol`, not
remembered. Where a number appears (20 floor globs, 13 deny globs) it is printed
by the commands shown, so check rather than trust this page.

---

## 1. Install

    pipx install /path/to/claude-dispatcher     # or: pip install -e .

The dispatcher shells out to agent CLIs (`claude`, and optionally `codex`,
`grok`, `gemini`). Probe the machine before the first run:

    dispatcher doctor

Two install-time facts that have each cost a run:

* **A pipx install is a snapshot.** Reinstall after changing dispatcher code, or
  you are running the old dispatcher against the new tree.
* **A worktree is effectively a new install.** Gitignored dependencies do not
  exist in a fresh `git worktree`, and the dispatcher creates one per task.
  Anything vendored-but-gitignored must be provisioned at worktree creation —
  see `worktree.provision_untracked_deps`. Getting this wrong cost one agent
  spawn *per task* until it was fixed.

---

## 2. `.dispatcher.yaml` — the per-repo config

Every key is optional; an absent file means "no test gate, no panel". Print what
the loader actually understood with `dispatcher doctor`.

```yaml
# file: .dispatcher.yaml
# The verification gate. Arbitrary shell, run in each task worktree; exit 0 is
# green. This is the single highest-value key — without it a task's only judge
# is an LLM.
test: |
  set -e
  PY=python3
  [ -x .venv/bin/python ] && PY=.venv/bin/python
  # Known-red register (see §6). POSIX: this runs under /bin/sh, so no arrays.
  set --
  if [ -n "${DISPATCHER_KNOWN_RED_FILE:-}" ] && [ -f "${DISPATCHER_KNOWN_RED_FILE}" ]; then
    while IFS= read -r row; do
      [ -n "$row" ] && set -- "$@" --deselect "$row"
    done < "${DISPATCHER_KNOWN_RED_FILE}"
  fi
  PYTHONPATH=src "$PY" -m pytest tests/ -q "$@"

# Declares that this repo knows HOW to exclude a row. Without it, active
# known-red entries BLOCK with a named fault instead of being ignored.
test_exclusion: pytest-deselect

# Where run artifacts go. Relative paths resolve against the REPO ROOT, so every
# worktree agrees. Point it OUTSIDE the repo: `docs/runs/` is gitignored AND
# lives in a disposable worktree, so the audit trail dies with the worktree.
runs_dir: ../dispatcher-runs

panel:
  advisory: [grok]        # advisory seats: they report, they cannot block
  # Trim the panel to the seat count `cmd/classify` recommends (2 for a small
  # low-risk change, 5 for a risky one). OFF by default — it REDUCES how many
  # families see a change. The dispatcher floors it at 2 whatever the
  # classifier says, because a non-CRITICAL block needs two families to
  # corroborate and a one-seat panel can never produce one.
  #
  # What this saves is subscription quota, not dollars or wall-clock: the
  # seats are fixed-cost CLIs and they run in parallel, so dropping one only
  # shortens the panel when it was the slowest seat.
  honour_classification_seats: false

integration: branch       # or `pr`
model_routing:
  critical: claude-opus-5
  default: claude-sonnet-5
```

### A TypeScript / vitest repo

Two things differ and both have bitten a real run:

```yaml
# file: .dispatcher.yaml
test: |
  set -e
  # node_modules is gitignored, so a FRESH WORKTREE has none and `npm test`
  # alone exits 2 before running a single test. Installing is the repo's job —
  # the dispatcher does not know what a package manager is.
  npm ci --silent --no-audit --no-fund
  npx tsc --noEmit
  # Vitest cannot deselect a node id; it filters by regex over the test's FULL
  # name. The file holds ONE ready-built pattern because escaping arbitrary
  # test names is not safe in shell — interpolate it, never rebuild it.
  if [ -n "${DISPATCHER_KNOWN_RED_FILE:-}" ] && [ -f "${DISPATCHER_KNOWN_RED_FILE}" ]; then
    npx vitest run --reporter=dot --testNamePattern "$(cat "${DISPATCHER_KNOWN_RED_FILE}")"
  else
    npx vitest run --reporter=dot
  fi

test_exclusion: vitest-name-pattern
runs_dir: ../dispatcher-runs
```

A vitest row is the test's full name — its `describe` names and its own, joined
by single spaces (`split loses nothing`), NOT a file path. The dispatcher
anchors each one, so a registered `loads a user` does not also suppress
`loads a user with no email`.

Strict on purpose: an unrecognised value raises rather than falling back, because
a silently dropped protection is one you believe you have.

---

## 3. `tasks.yaml` — with roles, which is the part the old docs omit

A role-less row is `legacy`: **unrestricted**, and it behaves exactly as the
pre-protocol dispatcher did. That is a valid choice for small work. For anything
where a wrong test would be expensive, use the four-role chain.

```yaml
# file: tasks.yaml
tasks:
  - key: U-1
    role: scaffold          # contract + STUBS. May not write tests.
    summary: scaffold — what a widening is, and where it is decided
    description: |
      The contract this unit must satisfy, the measurement behind it, and the
      question the seals will pin. Do NOT implement the decision logic.
    type: Task
    labels: [size:M]
    agent: claude
    declares:               # see §4 — the PLAN says what to leave undone
      holes:
        - src/pkg/surface.py::compare_whole_diff
        - src/pkg/surface.py::SymbolSet.widened_by
    status: To Do

  - key: U-2
    role: seals             # TESTS ONLY, committed deliberately RED
    summary: seals — a widening is caught wherever in the diff it arrives
    description: |
      Seal U-1's contract. Rows must FAIL against U-1's stubs. Carry an in-test
      control judged in the same call.
    type: Task
    labels: [size:M]
    agent: claude
    blockedBy: [U-1]
    status: To Do

  - key: U-3
    role: bodies            # fills the stubs; may not write tests
    summary: bodies — turn U-2's rows green
    description: |
      Fill every hole U-1 declared. Report, never edit, any seal you disagree
      with — U-4 owns that file.
    type: Task
    labels: [size:M]
    agent: claude
    blockedBy: [U-2]        # REQUIRED — a bodies row naming no seals task is refused
    status: To Do

  - key: U-4
    role: adjudicate        # rules ONE disputed artifact
    summary: adjudicate — rule the seals U-3 disputed
    description: |
      Rule each disputed row: ratified, amended, or struck. Name the before/after
      of every row you amend.
    type: Task
    labels: [size:S]
    agent: claude
    blockedBy: [U-3]
    disputed_paths:         # REQUIRED, and it IS this row's writable set
      - tests/test_surface.py
    status: To Do
```

### Why the roles exist

A scaffold that writes its own seals, or a body that edits the seals judging it,
is the **circular oracle**. This project measured 24 vacuous seals from exactly
that, and it is the shape that let a Critical money bug through in SMG-3966. The
split is enforced, not advised.

    dispatcher run tasks.yaml --mode dry-run --enable-role-loop-gate

Print the real tables rather than trusting this page:

```python
from claude_dispatcher import role_protocol as rp
for r in rp.DEFAULT_ROLE_RULES:
    print(r.role.value, r.kind.value, len(r.globs))
```

| role | rule | means |
|---|---|---|
| `scaffold` | `deny_globs` (13) | everything except tests, testdata, conftest, the config, role/prompt files |
| `seals` | `allow_only_globs` | **only** this repo's test files and `docs/**` |
| `bodies` | `deny_globs` (14) | as scaffold, plus `schema/**` |
| `adjudicate` | `allow_only_globs` | **only** the row's own `disputed_paths` |
| `legacy` | `unrestricted` | a row with no `role:` |

Plan-time refusals you will meet (each is an error, not a warning): a `bodies`
row with no `seals` edge (`PO-2`), an `adjudicate` row with no
scaffold/seals/bodies edge (`PO-3`) or no `disputed_paths`, an override that
*narrows* a deny list, and a `disputed_paths` entry naming the floor.

### The suite expectation per role

    scaffold GREEN   seals UNJUDGED   bodies GREEN   adjudicate GREEN

`seals` is `UNJUDGED` because its rows are *supposed* to be red, and the gate
refuses to guess: it abstains, journals the abstention, and never spawns the
fix-the-tests retry for that role — the only route to green there is weakening
the seals.

---

## 4. `declares.holes` — what the scaffold must leave undone

Three scaffolds in one wave implemented **32/32, 18/27 and 8/9** of their own
functions with nothing measuring it. Had those merged, the seals task would have
been written against existing, panel-confirmed defective code.

So the **plan** declares which functions belong to the body:

```yaml
# fragment: the scaffold row's declaration
declares:
  holes:
    - path/to/file.py::qualified.name
```

* Only on the **scaffold** row. The body's expectation is *derived* from it —
  two copies could disagree and the gate would read whichever it loaded first.
* Declared by the **plan author**, never by the scaffold: a role that could
  write its own check could declare zero holes and pass.
* Enforced after the role gate and **before** the suite: `scaffold` must leave
  each hole raising `NotImplementedError`; `bodies` must leave none of them.
* A hole naming a function nobody wrote is its own failure, so a scaffold cannot
  satisfy its declaration by writing nothing.
* Declaring nothing means **no check** — every pre-existing unit still works.

Measure any file's shape directly:

    python -m claude_dispatcher.scaffold_shape measure src/pkg/surface.py
    python -m claude_dispatcher.scaffold_shape holes --scaffold 'src/pkg/surface.py::compare_whole_diff'

---

## 5. The floor — paths **no** role may write

    python -c "from claude_dispatcher import role_protocol as r; print(len(r.FLOOR_GLOBS))"

24 globs today. It holds the gates themselves plus the whole delegation closure
of their decisions, because a branch that edits the *matcher* defeats the gate
while touching nothing the floor names — measured, twice.

Consequences worth knowing before you plan:

* Naming a floored path in `disputed_paths` **raises at plan time**. The most
  privileged role cannot grant itself the policy.
* So a unit whose deliverable is floored **cannot be completed by any role.**
  Plan it as: an unfloored module the body builds and the seals seal, plus an
  explicit **operator transcription** row carrying the floored one-liner. The
  seals target the final wired surface and are registered known-red (§6) until
  the operator applies it. That way the review discipline still covers the
  floored change and the operator's job is transcription, not design.

---

## 6. The known-red register

Between a seals task merging and its body merging, the branch is red **by
design** — and the mechanical gate runs the whole suite. Without a register,
every task dispatched in that window fails a gate it cannot satisfy, pays a
fix-the-tests spawn that cannot help, and cascades to a higher effort tier.

`config/known-red.yaml`:

```yaml
# file: config/known-red.yaml
entries:
  - rows:
      - tests/test_surface.py::test_widening_is_caught
    seals_task: U-2
    body_task: U-3          # retires the entry when Done; NOT exempted itself
    reason: P2 seal; red until U-3 lands.
    registered_at_sha: 0db7fb2
```

* Rows are hidden from every gate **except `body_task`'s** — greening them is
  its deliverable.
* Entries retire automatically when `body_task` is Done.
* Prove a row is red before adding it: `pytest '<nodeid>' -q` — or, for a
  vitest repo, `npx vitest run -t '<full name>'` — must exit non-zero.
* A stale or misspelled entry deselects nothing, so the row still runs. The
  mechanism **fails toward red** and cannot hide a regression.
* No dispatched role may write this file — it is on the floor. An operator can.

---

## 6a. `.agent/risk-paths.json` — what a change is worth reviewing

Without this file every changed path is **unmatched**, and unmatched fails
closed to **high** risk — so every task runs a full three-seat cross-family
panel. That is safe and expensive, and the run does not say which it is: the
log reads `risk=high unclassified=N` whether the repo declared nothing or
genuinely touched its riskiest code. Preflight warns when the table is absent.

It must be **tracked at the base branch** — the classifier reads it out of the
base ref's tree, so a file present only in your working copy is not there for a
task worktree.

```json
{
  "schema_version": 1,
  "unmatched_risk": "high",
  "server_surface_extensions": [".ts", ".tsx"],
  "rules": [
    {
      "id": "money",
      "risk": "high",
      "note": "Why this is risky, in a sentence a reviewer can act on.",
      "paths": ["src/money.ts"]
    },
    {
      "id": "tests",
      "risk": "medium",
      "note": "Weakening a seal is invisible in a green run.",
      "paths": ["tests/**"]
    }
  ]
}
```

Leave `unmatched_risk` at `high`. It is the fail-closed default: a path nobody
has classified is a path nobody has thought about.

---

## 7. Running

```bash
dispatcher run features/<epic>/tasks.yaml --mode dry-run    # always first

dispatcher run features/<epic>/tasks.yaml \
  --mode unattended --auto-integrate --enable-role-loop-gate \
  --base-branch main \
  --max-parallel 2 \
  --max-cost-usd 200 \
  --task-timeout-seconds 7200 \
  --claude-extra-args '--permission-mode bypassPermissions --allow-dangerously-skip-permissions'
```

* `--enable-role-loop-gate` — **without it the role rules are not enforced at
  diff time.** Roles without this flag are documentation.
* `--task-timeout-seconds` — set it from measurement. Across 97 recorded spawns
  the median was 5.4 min and the longest success 34 min; a 40-minute wall killed
  a task that had already committed 2,233 lines. The built-in default is 4h.
* `--max-parallel` — a suite with an out-of-process dependency does not
  parallelise for free.
* `--max-cost-usd` — a ceiling that stops starting new work and drains what is
  in flight.

Then, while it runs:

```bash
dispatcher status <run-id> --tasks-yaml features/<epic>/tasks.yaml
dispatcher blocked features/<epic>/tasks.yaml       # exit 3 when anything is blocked
dispatcher report --tasks-yaml features/<epic>/tasks.yaml
```

Watch the YAML's `status:` fields rather than tailing the log; the row carries
the gate stamps (`role_diff_loop`, `mechanical_verification`, `blocked_reason`).

---

## 8. When a task blocks

**Measure the cause before clearing it.** In the first dogfood wave most blocks
were dispatcher defects rather than agent errors, and unblocking without
measuring would have discarded correct work.

    dispatcher unblock tasks.yaml U-3 --note "your adjudication"

* `--note` is **appended to the task description permanently** and the
  re-spawned agent reads it. Use it to carry a real adjudication; omit it when
  there is nothing to adjudicate, or you pollute the brief forever.
* Never `--all` when rows are Blocked for different reasons.
* `unblock` grants a retry, never a waiver: every gate re-runs.
* The branch and worktree are **preserved** on Blocked. That is deliberate and
  has recovered real work repeatedly — including a task whose output was
  uncommitted and which `git log` reported as having done nothing.

---

## 9. The gates, and what each one actually answers

| gate | question | notes |
|---|---|---|
| role loop gate | did this branch touch a path its role forbids? | needs `--enable-role-loop-gate` |
| declared holes | did the scaffold leave, or the body fill, the declared holes? | inert until a unit declares |
| mechanical verify | does the repo's own `test:` command exit 0? | exit code only — it never parses test output, by ruling |
| seal redness | for a `seals` task, are its own rows red? | abstains (`UNJUDGED`) pending a style ruling |
| LLM verifier | did the diff do what the task **asked**? | completeness only — **not** a code reviewer |
| cross-family panel | is the code **correct**? | multi-family; corroboration required to block |

The verifier passing while the panel blocks is **not** a contradiction: they
answer orthogonal questions. Expect that combination on hard tasks.
