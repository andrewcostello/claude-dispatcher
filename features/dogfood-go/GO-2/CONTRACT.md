# GO-2 contract — a tracked build artifact says what it is and when it went stale

Target repository: `claude-workflow`, measured at `docs/explicit-state @ 1db2d41`
(every figure below was re-taken on 2026-08-29 from the blobs at that revision;
where a figure in the task text did not survive re-measurement, this file says so).

The Go skeleton for this contract is staged at
`features/dogfood-go/GO-2/claude-workflow/cmd/artifacts/` in this repository,
mirroring where it lands in `claude-workflow`. See **§7 Placement**.

---

## 1. The ruling on the nine

**Two kinds of deliverable, and everything else is an accident.**

| Path | Disposition | Why |
|---|---|---|
| `cmd/classify/classify` | **DELIVERABLE — pinned** | The differential baseline the B1 seals exec as `pinnedBinary` ("a FIXTURE, not a build artifact: it must not be rebuilt"). Its age is the point. Judged by bytes, never by HEAD. |
| `cmd/gates/gates` | **DELIVERABLE — distributed** | Invoked by path: `roles/coder.md:318`, `roles/tasker.md:193`, `skills/critical-review-dispatch.md:113`, README:39. |
| `cmd/iterate/iterate` | **DELIVERABLE — distributed** | `skills/iteration-protocol.md:130`. |
| `cmd/recheck/recheck` | **DELIVERABLE — distributed** | `skills/iteration-protocol.md:139`; `cmd/iterate/main.go:331` default. |
| `cmd/repro/repro` | **DELIVERABLE — distributed** | `roles/bug-reproducer.md:87`, `skills/bug-fix-protocol.md:29`, evenplay-mono test comments. |
| `cmd/deepseek/deepseek` | **DELIVERABLE — distributed, with a finding** | README:27 declares it ("provider shim used by the `deepseek-scouts` seat"). But NOTHING in the tree execs it at `1db2d41`: the reviewer dropped its colocated-binary resolution at `cb37065` (2026-07-21) and the seat now runs "via claude CLI + DeepSeek models" (`cmd/reviewer/main.go:2509`). A declared tool with zero callers. Kept as distributed because retiring a documented tool is GO-2-4's call, not a scaffold's; README:27 is stale either way. |
| `cmd/reviewer/main` | **DELIVERABLE — distributed. It stays.** | **The task text has this one backwards.** `main` is not "a name that hides it" — it is the name every consumer uses: `cmd/iterate/main.go:330` hardcodes `filepath.Join(root, "cmd/reviewer/main")` as the reviewer default; README:42, `roles/tasker.md:258,272`, `skills/critical-review-dispatch.md:140` all invoke `cmd/reviewer/main`. And on `main` after `1db2d41`, three commits (`b948b1a`, `6c3b1ee`, `bd83282`) rebuild `cmd/reviewer/main` and never touch `reviewer`. It is the invoked program — and at `1db2d41` it is the STALE one: 7 source commits behind (`fd4ce07` → `1db2d41`, 2026-07-19 → 2026-08-08), built dirty. |
| `cmd/reviewer/reviewer` | **ACCIDENT — untrack and delete** | The `go build .` default output name, committed by a wide `git add`. Zero callers anywhere. Its "fresher" stamp (1 commit behind) is the trap: the binary nobody runs is the current one, and the binary everybody runs is the stale one. |
| `cmd/reviewer/deepseek` | **ACCIDENT — untrack and delete** | Byte-identical to `cmd/deepseek/deepseek` (blob `75381e5c3d`, sha256 `6ad7a782…`). It existed because at `14560c5` the reviewer resolved `filepath.Dir(exePath)/deepseek` (main.go:1582,2263 at that revision). That resolution was removed at `cb37065`; since 2026-07-21 nothing reads this file. 8.96 MB of dead weight that will silently go stale again the next time `cmd/deepseek` changes. |

Plainly: **`cmd/reviewer/main` should exist; `cmd/reviewer/deepseek` should not.**
Deleting the two accidents is a different decision from untracking a fixture,
and this contract untracks NO fixture: `cmd/classify/classify` stays tracked and
pinned. Neither ruling requires rebuilding anything.

**Why the name `main` survives rather than being normalised to `reviewer`.**
Renaming the deliverable costs one source edit in a frozen tool
(`cmd/iterate/main.go:330` → then `iterate` is itself STALE and must be rebuilt)
plus five role/skill/README sites, for no behavioural gain. Keeping `main` costs
nothing once the stamp (§2) says `"module": ".../reviewer"` out loud — the name
no longer hides anything. The residual trap — anyone running `go build .` in
`cmd/reviewer` produces a `reviewer` file — is closed by §3: an untracked ELF is
nothing, and a tracked one without a stamp is UNDECLARED and red.

## 2. What a tracked binary must carry

Every tracked binary has a tracked sidecar **`<binary>.stamp`** (JSON, stdlib-
parsable, human-readable) next to it. `ls cmd/gates` shows `gates` and
`gates.stamp`; an ELF without a sibling stamp is visibly an accident.

```json
{
  "kind": "distributed",
  "module": "github.com/yourorg/claude-workflow/gates",
  "revision": "bdecc7fa364afc241fc67ac1f5412c9df9422f57",
  "time": "2026-08-01T01:56:45Z",
  "modified": true,
  "go": "go1.24.4",
  "sha256": "9ae1fc5706815e7f6479c4c0cd56aa3135a45464fe6af85b3fda43caf6d56bc6",
  "pin": null
}
```

Rules:

* `kind` ∈ {`distributed`, `pinned`}. No third value; no default.
* `pin` is non-null **iff** `kind == "pinned"`: `{"by": "<commit or decision id>", "reason": "<what execs it as a reference>"}`. A pin on a distributed stamp, or a pinned stamp without one, is MALFORMED.
* `module`, `revision`, `time`, `modified`, `go` are copied from the binary's own buildinfo by `artifacts stamp` (`debug/buildinfo`, no `go` tool needed). A stamp is **never hand-written**; `WriteStamp` is the only producer.
* `sha256` binds the stamp to the exact bytes it describes. A rebuilt binary with an old stamp is STAMP_DRIFT (or PIN_BROKEN), not a quiet update.
* A reader answers "is this stale?" from the stamp alone: `revision` + `time` say what it was built from; `git log <revision>..HEAD -- cmd/<module>/*.go` says what it lacks. `go version -m` is no longer required to read; the checker uses `debug/buildinfo` to *verify* the stamp has not been edited.

The `.stamp` files for the seven deliverables are written by GO-2-3 from the
values in §5. The pin for `cmd/classify/classify` is
`{"by": "GO-2-1", "reason": "differential baseline exec'd as pinnedBinary by cmd/classify seals (B1 lineage); rebuild is an operator decision"}`.

## 3. The state machine — never a silent stale artifact

One verdict per artifact, from a closed set. Precedence is declaration order:
the first that holds wins. `Finding.StaleSince` is filled whenever it is
computable, whatever the state, so "when did it go stale" is always answered.

| State | Holds when | Red? |
|---|---|---|
| `UNDECLARED` | tracked ELF with no `.stamp` | red — an accident until someone declares it |
| `ORPHANED` | a `.stamp` whose binary is missing or is not an ELF | red |
| `UNSTAMPED` | no readable Go buildinfo, or no `vcs.*` keys (built with `-buildvcs=false` or outside a checkout) | red — **cannot be judged is never green** |
| `MALFORMED` | stamp does not parse, or violates the kind/pin rule | red |
| `STAMP_DRIFT` | distributed; `sha256(file) != stamp.sha256` | red — rebuilt without restamping |
| `PIN_BROKEN` | pinned; `sha256(file) != stamp.sha256` | red — someone rebuilt the fixture |
| `DUPLICATE` | same sha256, or same `module`, as another tracked binary (Detail names the sibling) | red — one of them is an accident |
| `FOREIGN` | `revision` is not an ancestor of HEAD (built on an unmerged branch, a squashed PR, or another checkout) | red — staleness is not computable, so it is not asserted |
| `STALE` | distributed; ≥1 commit in `revision..HEAD` touches the module's source (`*.go`, `go.mod` — tracked binaries and stamps excluded, so a rebuild commit is not a source change) | red — StaleSince lists the commits, oldest first |
| `DIRTY` | distributed; `modified == true` | red — unreproducible whatever its age |
| `PINNED` | pinned; bytes equal the pin | **green** — age is not a defect; `modified` is recorded, not judged |
| `CURRENT` | distributed; clean, and no source commit after `revision` | **green** |

Green is exactly `{PINNED, CURRENT}`. Everything else is red, and every red
carries a name and the specific reason. There is no "warn" tier.

**The checker's own failure is not an artifact state.** If `git` is missing,
`git ls-files` fails, or `debug/buildinfo` cannot be loaded, `Check` returns an
error and the process exits **3** — never 0, never an empty green report. A
check that reports success because it did not look has certified nothing
(GO-2-2's trap, named in advance).

Exit codes, per the repository's convention: `0` all green · `1` any red ·
`3` could not judge / invalid input.

## 4. The skeleton (staged; see §7)

`cmd/artifacts/` — a new stdlib-only module, the eighth, following the one-
module-per-tool pattern. **It has no tracked binary of its own** and never
will; it runs as `go run . check -repo ../..`. Exported surface:

```go
type Kind string            // KindDistributed | KindPinned
type Pin struct{ By, Reason string }
type Stamp struct{ Kind; Module, Revision, Time string; Modified bool; Go, SHA256 string; Pin *Pin }
type State string           // the twelve states of §3, in precedence order
func Green(State) bool
type Commit struct{ SHA, Date, Subject string }
type Finding struct{ Path string; State; Stamp *Stamp; StaleSince []Commit; Detail string }
type Report struct{ Findings []Finding }; func (Report) Red() []Finding
func StampPath(binary string) string                              // binary + ".stamp"

func TrackedELF(repo string) ([]string, error)                    // HOLE
func ReadBuildInfo(path string) (Stamp, error)                    // HOLE
func ReadStamp(path string) (Stamp, error)                        // HOLE
func WriteStamp(binary string, kind Kind, pin *Pin) error         // HOLE
func SourceCommitsAfter(repo, moduleDir, revision string) ([]Commit, error) // HOLE
func Judge(repo, path string, all []Finding) Finding              // HOLE
func Check(repo string) (Report, error)                           // HOLE
func main()                                                       // HOLE
```

**Declared holes (8):** `TrackedELF`, `ReadBuildInfo`, `ReadStamp`,
`WriteStamp`, `SourceCommitsAfter`, `Judge`, `Check`, `main`. Each body is
`panic("GO-2 hole: …")` today; the module vets and builds. GO-2-3 fills all
eight and nothing else in this file except what a ruling forces.

Seal-relevant constraints the skeleton fixes:

* `TrackedELF` derives the set from `git ls-files -z` + the 4-byte ELF magic.
  Not a path list, not a glob, not a count (the hand-list bug).
* `ReadBuildInfo` uses `debug/buildinfo`, so the check does not depend on a
  `go` binary on PATH — and when buildinfo is absent it errors, which `Judge`
  maps to `UNSTAMPED`.
* `SourceCommitsAfter` returns a distinct error (`ErrForeign`, to be defined by
  the body) when `revision` is not an ancestor of HEAD; `Judge` maps it to
  `FOREIGN`. It must not fall through to "0 commits ⇒ CURRENT".

## 5. The worked oracle at `1db2d41` — what `Check` must say once the seven are stamped

| Path | kind | stamped revision (vcs.time) | modified | source commits after revision | **State** |
|---|---|---|---|---|---|
| `cmd/classify/classify` | pinned | `bdecc7fa` (2026-08-01T01:56:45Z) | true | 1 — `2b18e02` 2026-07-31 | **PINNED** (sha256 `ad289891…`; dirty is recorded, not judged) |
| `cmd/deepseek/deepseek` | distributed | `fd4ce076` (2026-07-19T15:21:54Z) | false | 0 | **CURRENT** (the only clean build of the nine) |
| `cmd/gates/gates` | distributed | `bdecc7fa` (2026-08-01T01:56:45Z) | true | 1 — `2b18e02` 2026-07-31 | **STALE** since `2b18e02`; also dirty |
| `cmd/iterate/iterate` | distributed | `830ff3cc` (2026-08-01T00:45:00Z) | true | n/a — `830ff3cc` is NOT an ancestor of `1db2d41` (squashed into `840928c`, PR #2) | **FOREIGN**; also dirty |
| `cmd/recheck/recheck` | distributed | `0a457fff` (2026-08-01T04:15:35Z) | true | 0 | **DIRTY** |
| `cmd/repro/repro` | distributed | `eb32f172` (2026-07-08T00:27:29Z) | true | 1 — `fd4ce07` 2026-07-19 | **STALE** since `fd4ce07`; also dirty |
| `cmd/reviewer/main` | distributed | `52d46438` (2026-07-19T04:25:12Z) | true | 7 — `fd4ce07`, `cb37065`, `a25c0e0`, `c14da76`, `b2a9ba5`, `7916067`, `1db2d41` | **STALE** since `fd4ce07` 2026-07-19; also dirty |
| `cmd/reviewer/reviewer` | — (untracked by GO-2-3) | `0864e52c` (2026-08-04T05:52:19Z) | true | 1 — `1db2d41` | before GO-2-3: **UNDECLARED** (and DUPLICATE of `reviewer/main` by module). After: absent. |
| `cmd/reviewer/deepseek` | — (untracked by GO-2-3) | `fd4ce076` | false | — | before GO-2-3: **UNDECLARED** (and DUPLICATE of `deepseek/deepseek` by bytes). After: absent. |

So at `1db2d41`, once declared, **one green distributed binary and one green
pin; five red**. That is the honest state of the tree and it is what GO-2-2's
rows must assert — not that the tree is clean. GO-2-3 does not rebuild anything
(its task text forbids it); the five reds remain red and *named* after GO-2-3,
which is the whole point: a stale artifact that says so, instead of a
`-temperature` failure at 2 a.m.

Corrections to the task text, from re-measurement:

1. "`cmd/reviewer/main` … under a name that hides it" — inverted; see §1. The
   hidden one is `reviewer`.
2. **Seven** of nine carry `+dirty`; only `deepseek/deepseek` and its
   byte-copy are clean builds. The task said "BOTH reviewer binaries" —
   true, and an understatement: every deliverable except `deepseek` is
   unreproducible.
3. `cmd/iterate/iterate`'s revision is not on the branch at all — a state the
   task did not name and the checker now does (`FOREIGN`).

## 6. `.gitignore` (GO-2-4's disputed path)

No `.gitignore` change is required, and none is sufficient. `cmd/reviewer/main`
is a deliverable, so build outputs cannot be ignored by name; and an ignore
line for `cmd/reviewer/reviewer` would be the hand-list bug in a new file. The
closed set is enforced by `artifacts check`: an ELF that is untracked is
nothing; an ELF that is tracked without a stamp is UNDECLARED and red. Leave
`.gitignore` as it is (`scratch/`).

## 7. Placement — DEVIATION (new-surface): staged, not landed

This run was pointed at `claude-dispatcher` (journal `run_config.tasks_yaml`
= `features/dogfood-go/tasks.yaml`; worktree = a `claude-dispatcher` branch),
but every path in this unit is in `claude-workflow`, and `tasks.yaml` lines
4–10 say the operator must point the run there. A scaffold cannot commit into a
repository the dispatcher is not integrating into, so the skeleton is staged
here at its target-relative path:

```
features/dogfood-go/GO-2/claude-workflow/cmd/artifacts/go.mod
features/dogfood-go/GO-2/claude-workflow/cmd/artifacts/main.go
features/dogfood-go/GO-2/claude-workflow/cmd/artifacts/main_test.go   (GO-2-2 seals)
```

The seals need the checker's own precondition: **full history**. `git log
rev..HEAD` and `merge-base --is-ancestor` are meaningless in a shallow clone,
and the §5 oracle replays `1db2d41` in a throwaway clone of the enclosing
repository. In `gates.yml` the `artifacts` job must check out with
`fetch-depth: 0`. The real-tree and oracle seals locate the repository via
`git rev-parse --show-toplevel` (override: `ARTIFACTS_REPO`) and **fail, never
skip**, when it is not claude-workflow — a seal over an empty set is the
measurement trap in test form.

To land it: `cp -r features/dogfood-go/GO-2/claude-workflow/. ~/Project/claude-workflow/`
on a `claude-workflow` branch off `docs/explicit-state`, add `artifacts` to
`.github/workflows/gates.yml`'s module matrix, then run GO-2-2 against
`claude-workflow`. Blast radius: GO-2-2, GO-2-3, GO-2-4 cannot run in this
repository at all.
