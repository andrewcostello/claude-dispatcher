# Setup — macOS (and Linux)

Step-by-step setup for a fresh machine. Three pieces install separately:

1. **`claude-workflow`** — the agent role + skill definitions the Tasker loads
2. **`claude-dispatcher`** — the Python CLI that orchestrates Claude Code sessions
3. **Per-project `.claude/workflow/` symlink** — so each project can see the workflow

Plus optional Jira integration via the `forecast` Go binary.

Total time: ~15-20 minutes on a fresh Mac.

---

## 0. Prerequisites

```bash
# Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Core tooling
brew install git gh python pipx

# Ensure ~/.local/bin is on PATH (pipx puts scripts there).
# Add this to your ~/.zshrc (zsh is macOS's default shell):
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# pipx self-install
pipx ensurepath
```

**Claude Code CLI** — install via the official channel. The dispatcher invokes `claude --print`, so it must be on `$PATH`.

```bash
# Check if you already have it
which claude && claude --version || \
  echo "Install Claude Code from https://docs.claude.com/en/docs/claude-code/quickstart"

# After install, authenticate so `claude` can run non-interactively
claude /login    # follow the prompts
```

**GitHub auth** — the dispatcher uses `gh pr create` in supervised mode and `git push` for branch operations.

```bash
gh auth login   # choose: GitHub.com, HTTPS, login with browser
```

---

## 1. Clone `claude-workflow`

Picks a "home" for the workflow repo that all projects on this machine will symlink to. Common location: `~/Project/claude-workflow/`.

```bash
mkdir -p ~/Project
cd ~/Project
git clone https://github.com/andrewcostello/claude-workflow.git
```

Verify:

```bash
ls ~/Project/claude-workflow/
# Expect: README.md  config  docs  roles  skills
ls ~/Project/claude-workflow/roles/ | head
# Expect: bug-reproducer.md  coder.md  design-agent.md  ...  tasker.md
ls ~/Project/claude-workflow/skills/
# Expect: bug-fix-protocol.md  critical-review-dispatch.md  forecast-fields.md
#         git-worktree-setup.md  iteration-protocol.md  migration-checklist.md
#         pr-raise.md  plan-based-execution.md
```

---

## 2. Clone `claude-dispatcher` and install via `pipx`

```bash
cd ~/Project
git clone https://github.com/andrewcostello/claude-dispatcher.git

# Editable install — edits to ~/Project/claude-dispatcher/ source take effect
# immediately. Better than non-editable for actively-iterating on the dispatcher.
pipx install --editable ~/Project/claude-dispatcher

# Verify
dispatcher --help
dispatcher --version 2>&1 || dispatcher run --help | head -5
which dispatcher
# Expect: /Users/<you>/.local/bin/dispatcher
```

If `pipx install` fails with "externally-managed-environment", install pipx itself via `brew install pipx` rather than `pip install pipx`.

---

## 3. Per-project setup

Each project that should use the dispatcher needs `.claude/workflow/` pointing at the central clone.

```bash
# Replace <your-project> with your project path
cd ~/Project/<your-project>

# Create .claude/ if it doesn't exist
mkdir -p .claude

# Symlink the workflow repo
ln -s ~/Project/claude-workflow .claude/workflow

# Verify
ls -la .claude/workflow
# Expect: .claude/workflow -> /Users/<you>/Project/claude-workflow
ls .claude/workflow/roles/tasker.md
# Expect: the file resolves through the symlink
```

`.claude/` is typically gitignored by projects (each developer manages their own). If your project tracks `.claude/`, exclude the workflow symlink in `.gitignore`.

The dispatcher's prompt template tells the Tasker to read `.claude/workflow/roles/tasker.md`, so the symlink path matters.

### Project-local skills

You can add project-specific skills alongside the shared ones:

```bash
mkdir -p .claude/skills
# Drop project-specific *.md files here. The Tasker can be instructed to
# load them by relative path.
```

The shared skills (in `claude-workflow/skills/`) cover the dispatcher-friendly workflow primitives; project-local skills cover project-specific knowledge (domain rules, checklists, etc.).

---

## 4. (Optional) Jira integration via `forecast`

If your project uses Jira, install the `forecast` Go binary so `dispatcher forecast-create` / `dispatcher forecast-sync` work. Otherwise skip this section — the dispatcher gracefully no-ops when forecast isn't present.

```bash
# Go (if not already installed)
brew install go

# Clone + build forecast
cd ~/Project
git clone https://github.com/andrewcostello/forecast.git
cd forecast
go build -o forecast ./cmd/forecast

# Symlink to ~/.local/bin so it's on PATH
ln -s ~/Project/forecast/forecast ~/.local/bin/forecast

# Verify
which forecast && forecast --help | head -3
```

Each project that uses forecast needs `.forecast/config.yaml` in its repo root:

```bash
cd ~/Project/<your-project>
mkdir -p .forecast
forecast init   # writes a default config; edit to fill in Jira URL, email, etc.
```

API token (recommended approach — read from environment):

```bash
# Add to your ~/.zshrc
export JIRA_EMAIL="you@company.com"
export JIRA_API_TOKEN="atatt..."  # from id.atlassian.com → account settings → security
```

Then `.forecast/config.yaml`:

```yaml
jira:
  url: https://yourcompany.atlassian.net
  email: ${JIRA_EMAIL}
  api_token: ${JIRA_API_TOKEN}
  project_key: SMG
  done_statuses: [Done, "Awaiting Dev Deployment"]
```

Verify auth works:

```bash
cd ~/Project/<your-project>
forecast jira projects 2>&1 | head
# Expect: a list of projects you can access
```

---

## 5. Verify the setup with a dry-run

This part requires a tasks YAML in your project. The bay-session-tasks.yaml format from this repo's README is the canonical schema. Minimal example:

```yaml
project: SMG
epic: SMG-1234              # real Jira epic key if using forecast; else any string
base_branch: main           # or epic/your-branch — what worktrees fork from
forecast_config: .forecast/config.yaml

tasks:
  - key: TBD-1
    summary: "Smoke task: print hello"
    description: |
      Trivial task — print "hello" to stdout in a new file at /tmp/hello.txt.

      Acceptance:
        - File /tmp/hello.txt exists with content "hello"
    type: Task
    labels: [size:XS, type:component]
```

Save as `~/Project/<your-project>/test-tasks.yaml`, then:

```bash
cd ~/Project/<your-project>
dispatcher run test-tasks.yaml --mode dry-run
```

Expected output: a multi-line plan ending with `Dry-run only: no worktrees created, no subprocesses spawned, no YAML writes.`

If it fails: the most common causes are missing `size:` label in `labels`, an invalid `blockedBy` reference, or no `.claude/workflow/roles/tasker.md` at the symlinked path.

---

## 6. Smoke test (real run)

When dry-run passes, do a one-task supervised run as the live smoke. You'll see the Tasker session execute end-to-end:

```bash
cd ~/Project/<your-project>
dispatcher run test-tasks.yaml \
  --mode supervised --max-parallel 1 --only TBD-1 \
  --claude-extra-args "--permission-mode bypassPermissions --allow-dangerously-skip-permissions" \
  2>&1 | tee /tmp/smoke.log
```

Expect:
1. The dispatcher creates a worktree at `../worktree-TBD-1` (sibling of your project)
2. A `claude --print` subprocess starts (visible in `ps aux | grep claude`)
3. The Tasker reads `.claude/workflow/roles/tasker.md` and processes the task
4. After ~5-15 min, a summary file appears at `docs/runs/<run-id>/TBD-1/summary.md`
5. The dispatcher updates the YAML's `TBD-1` row to `status: Done`
6. If the task touched the `--financial-paths` list (it didn't in this trivial case), the dispatcher would have prompted "approve/reject/skip" before raising a PR

When done:

```bash
dispatcher report   # quality dashboard for the latest run
```

---

## 7. Updating the workflow

When the upstream `claude-workflow` or `claude-dispatcher` ships new commits:

```bash
# Workflow (roles + skills) — affects all projects via the symlink
git -C ~/Project/claude-workflow pull

# Dispatcher (the CLI) — `pipx --editable` means a pull alone is enough
git -C ~/Project/claude-dispatcher pull
```

No reinstall step needed because of the `--editable` install. To force-rebuild if something seems stale:

```bash
pipx reinstall claude-dispatcher
```

---

## macOS-specific gotchas

| Issue | Fix |
|---|---|
| `pipx: command not found` after install | `brew install pipx` (not `pip install pipx` on system Python — PEP 668 will block it) |
| `which dispatcher` returns nothing after install | Add `~/.local/bin` to PATH in `~/.zshrc` and `source ~/.zshrc` |
| `claude` permission prompts in unattended mode | Pass `--claude-extra-args "--permission-mode bypassPermissions --allow-dangerously-skip-permissions"` |
| Worktrees created at `../worktree-<key>` collide with iCloud-synced parent dirs | Override with `--worktree-base /tmp/dispatcher-worktrees` (or any iCloud-excluded path) |
| `git worktree add` fails with "fatal: invalid reference: epic/..." | The base branch doesn't exist locally. Run `git fetch origin epic/your-branch:epic/your-branch` first, or set `base_branch: main` in the YAML if you don't need an epic branch |
| `forecast jira create` returns "unsupported protocol scheme" | `.forecast/config.yaml` not reachable from the cwd you invoked from. Recent dispatcher (`b242780+`) passes `--config` explicitly to avoid this. If you see it, `git -C ~/Project/claude-dispatcher pull` then retry. |
| `gh pr create` fails with "unauthorized" | `gh auth login` again; SSH key may not be authorized for this org |
| Apple Silicon — `go build` fails for forecast | Use Go 1.21+ from brew (universal binary), or build with `GOARCH=arm64 go build` |

---

## Layout once everything's installed

```
~/Project/
├── claude-workflow/          # the roles + skills, single source of truth
│   ├── roles/                #   tasker.md, coder.md, reviewer.md, ...
│   ├── skills/               #   forecast-fields, pr-raise, ...
│   ├── config/               #   team-config.yaml (per-project overrides)
│   └── docs/
├── claude-dispatcher/        # the CLI (pipx --editable target)
│   └── src/claude_dispatcher/
├── forecast/                 # optional Jira CLI binary
├── <your-project-1>/
│   ├── .claude/
│   │   ├── workflow -> ~/Project/claude-workflow    # symlink
│   │   └── skills/                                   # optional, project-local skills
│   ├── .forecast/config.yaml                         # optional, Jira config
│   ├── <project-name>-tasks.yaml                     # your YAML(s)
│   └── docs/runs/<run-id>/                           # dispatcher-written per-run artifacts
└── <your-project-2>/
    └── .claude/workflow -> ~/Project/claude-workflow
```

And in `~/.local/bin/`:
- `dispatcher` (pipx)
- `forecast` (optional, symlinked from `~/Project/forecast/`)
- `claude` (Claude Code install)

---

## Troubleshooting starter set

```bash
# Is everything where it should be?
which dispatcher claude forecast 2>&1
ls -la ~/Project/claude-workflow/roles/tasker.md
ls -la ~/Project/<your-project>/.claude/workflow

# Can the dispatcher find its dependencies?
dispatcher run --help 2>&1 | head -5

# What's the dispatcher running? (mid-run)
pgrep -af "claude --print"
tail -20 ~/Project/<your-project>/docs/runs/$(ls -t ~/Project/<your-project>/docs/runs/ | head -1)/run.log

# Cancel a recurring cron-style status check started by /loop
# (only relevant if you set one up in Claude Code)
# Look for the job ID in the original /loop response, then run CronDelete in Claude Code
```

If any of these fail in a way the table above doesn't cover, the artifacts to attach when asking for help:
- `which dispatcher claude forecast` output
- `dispatcher report` output for the affected run
- The relevant `docs/runs/<run-id>/<task-key>/summary.md`
- The YAML row state for the affected task
