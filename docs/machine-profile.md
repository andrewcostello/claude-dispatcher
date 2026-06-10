# The machine profile (`machine.yaml`)

`dispatcher doctor` probes the machine once, up front, and writes a plain,
predictable YAML profile that later phases (run-start preflight, done-metadata
provenance, the future provider registry) read without re-probing. This
document specifies the file format completely — enough to hand-write a profile
or to build an independent reader.

## Location

```
$XDG_CONFIG_HOME/claude-dispatcher/machine.yaml
```

falling back to `~/.config/claude-dispatcher/machine.yaml` when
`$XDG_CONFIG_HOME` is unset. `dispatcher doctor --config-dir PATH` overrides
the directory (the filename is always `machine.yaml`).

## Ownership: probed keys vs `manual:`

The file is **shared between the doctor and the user**:

- The doctor owns and **replaces on every probe** exactly these top-level
  keys: `schema_version`, `probed_at`, `host`, `dispatcher`, `agents`,
  `tools`.
- Everything under the top-level **`manual:`** key is **user-owned and never
  touched** by the doctor. The same goes for any other unrecognized top-level
  key.
- **File comments survive re-probes.** The doctor mutates the loaded ruamel
  document in place rather than rebuilding it — the same comment-preserving
  contract the dispatcher gives the tasks YAML.

If an existing `machine.yaml` cannot be parsed (or is not a YAML mapping), the
doctor **refuses to overwrite it** and exits 2, so a hand-maintained `manual:`
section is never destroyed by a corrupted-file overwrite. Fix or delete the
file and re-run.

There is no fixed schema under `manual:` — it is a scratch area for facts the
probe cannot know (account identities, machine-specific notes, capability
overrides you want future tooling to read).

## Full example

A freshly probed profile looks like this (some entries below are abbreviated
to YAML flow style for brevity — the doctor itself writes plain block style;
both parse identically, so either is fine in a hand-written profile):

```yaml
# Machine profile written by `dispatcher doctor`.
# All keys except `manual:` are regenerated on every probe.
# Comments and anything under `manual:` are preserved across re-probes.
schema_version: 1
probed_at: "2026-06-10T22:41:03Z"          # UTC, second precision
host:
  hostname: build-01
  platform: Linux-6.17.0-35-generic-x86_64-with-glibc2.39
dispatcher:
  version: 0.1.0                            # "unknown" when not pip-installed
  install_mode: pipx                        # pipx | editable | venv | system | unknown
  python_version: 3.12.3
agents:
  claude:
    present: true
    path: /home/you/.local/bin/claude
    version: 2.1.34                         # first semver-ish token
    version_raw: "2.1.34 (Claude Code)"     # first line of --version output
    stats_probe: json-output                # see "stats_probe" below
  agy:
    present: true
    path: /usr/local/bin/agy
    version: 0.121.0
    version_raw: "agy 0.121.0"
    stats_probe: null
  codex:
    present: false
    path: null
    version: null
    version_raw: null
    stats_probe: null
  grok:    { present: false, path: null, version: null, version_raw: null, stats_probe: null }
  opencode: { present: false, path: null, version: null, version_raw: null, stats_probe: null }
  qwen:    { present: false, path: null, version: null, version_raw: null, stats_probe: null }
tools:
  git:
    present: true
    path: /usr/bin/git
    version: 2.43.0
    version_raw: git version 2.43.0
  gh:     { present: true, path: /usr/bin/gh, version: 2.45.0, version_raw: gh version 2.45.0 (2026-01-15) }
  docker: { present: false, path: null, version: null, version_raw: null }
  sqlc:   { present: false, path: null, version: null, version_raw: null }
  buf:    { present: false, path: null, version: null, version_raw: null }
# user-owned; doctor never touches anything under this key
manual:
```

## Field reference

### Top level

| Key | Type | Meaning |
|-----|------|---------|
| `schema_version` | int | Currently `1`. Bumped on incompatible format changes. |
| `probed_at` | string | UTC timestamp of the probe, `YYYY-MM-DDTHH:MM:SSZ`. |
| `host` | map | `hostname` (from the OS) and `platform` (Python's `platform.platform()` string). |
| `dispatcher` | map | How the dispatcher itself is installed — see below. |
| `agents` | map | One entry per known agent CLI: `claude`, `agy`, `codex`, `grok`, `opencode`, `qwen`. |
| `tools` | map | One entry per known tool: `git`, `gh`, `docker`, `sqlc`, `buf`. |
| `manual` | any | User-owned; `null` in a fresh file. Never written by the doctor. |

### `dispatcher`

| Key | Type | Meaning |
|-----|------|---------|
| `version` | string | Installed `claude-dispatcher` distribution version; `"unknown"` when the package is not installed (e.g. a `PYTHONPATH` run). |
| `install_mode` | string | `pipx` (a `pipx` path component in `sys.prefix`), `editable` (PEP 660 / `pip install -e`, per the distribution's `direct_url.json`), `venv` (any other virtualenv), `system`, or `unknown` (a probe step failed). Checked in that order. |
| `python_version` | string | The interpreter running the doctor. |

### Per-binary entries (`agents.*` and `tools.*`)

Every entry — present or not — carries the same base keys, so readers never
need existence checks beyond the top-level name:

| Key | Type | Meaning |
|-----|------|---------|
| `present` | bool | `shutil.which(name)` found it on `$PATH`. |
| `path` | string \| null | Resolved absolute path; `null` when absent. |
| `version` | string \| null | First semver-ish token (`2.43.0`, `0.1`, `1.2.3-rc1`) extracted from the `--version` output. `null` when absent, unparseable, or the probe failed. |
| `version_raw` | string \| null | First line of `--version` output verbatim (stdout preferred, stderr as fallback — some CLIs print there). |
| `version_error` | string | **Optional** — present only when something went wrong reading the version: `--version timed out after 10s`, `--version exited N`, `--version could not run: …`, or `no version token in --version output`. A misbehaving binary degrades to `version: null` + this note; the probe never crashes. |

`agents.*` entries additionally carry:

| Key | Type | Meaning |
|-----|------|---------|
| `stats_probe` | string \| null | How usage/cost can be read for this CLI, from a static capability table (a stop-gap pending the provider registry): `json-output` (parse the CLI's `--print` JSON output — how Claude usage is read today), `stats-command` (the CLI has a dedicated stats/usage subcommand), or `null` (no probe known, **or the CLI is absent** — absent CLIs always get `null`). Currently: `claude` → `json-output`, `codex` → `stats-command`, all others `null`. |

## Exit codes and `--check`

| Code | Meaning |
|------|---------|
| 0 | Profile written (and, with `--check`, all required entries present). |
| 1 | `--check` only: a **required** entry is missing. Required entries are exactly `agents.claude` and `tools.git`. Every other entry is *soft* — reported in the table, never affecting the exit code. |
| 2 | Environment/file error — most notably an existing `machine.yaml` that cannot be parsed (the doctor refuses to overwrite it). |

Note `--check` still writes the profile first; the check gates only the exit
code, making `dispatcher doctor --check` directly usable as a CI/setup gate.

## The staleness warning

The profile records `dispatcher.install_mode` and `dispatcher.version` because
of a failure mode dogfooding hit: a **pipx-installed dispatcher is a snapshot**
— fixes committed to the repo do not change the installed tool until you
reinstall. Dogfood run #2's fixes silently didn't apply for exactly this
reason.

The run-start preflight (see the README's *Run-start preflight* section) turns
this into a warning: when the repo being dispatched **is claude-dispatcher
itself**, it compares the installed version against the repo HEAD's
`pyproject.toml` version and warns on mismatch:

```
warning: preflight: installed claude-dispatcher is 0.1.0 but this repo's HEAD
pyproject.toml says 0.2.0 — the installed dispatcher may be a stale pipx
snapshot; reinstall, e.g. `pipx install --force .`
```

It is a **warning, never a failure** — a stale tool still runs; refusing would
be overreach. For any other repo (or when either version is unknown) the check
records itself as not-applicable and stays silent.

Re-run `dispatcher doctor` after installing or upgrading anything the profile
covers — the probe is cheap and the file is the durable record of what this
box can do.
