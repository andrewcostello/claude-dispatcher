"""Per-repo dispatcher config: load and validate `.dispatcher.yaml`.

A repo opts into dispatcher verification gates by placing a `.dispatcher.yaml`
at its root. Current schema:

  * `test:` — the shell command run inside a task worktree (exit 0 = green).
  * `panel:` — cross-family panel options. Its only known key today is
    `advisory:`, a list of advisory (probationary, non-blocking) reviewer
    family names — e.g. ``panel: {advisory: [grok]}`` — consumed by the
    orchestrator's cross-family panel.
  * `roles:` — the build-protocol immutable-path additions (see
    `role_protocol`). Validated here, but NOT returned: the gating path reads
    this section from the protected base, never from a working tree. Load-time
    validation exists so an invalid or self-weakening policy is a refusal
    rather than a line silently dropped into `unknown_keys`.

Future sections (`e2e:`, `risk:`) will arrive in later phases, so this
loader tolerates unknown top-level keys rather than rejecting them: a repo
configured for a newer dispatcher must still load under an older one.
Unknown keys are reported via `RepoConfig.unknown_keys` so callers can
journal a note; unknown keys nested inside `panel:` are reported there as
``panel.<key>``.

The loader is read-only and goes through yaml_io's round-trip mode, so any
future writer inherits comment/ordering preservation for free. An absent
file is not an error — the caller journals that mechanical tests are
skipped; notes flow through return values, never logging.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ruamel.yaml.error import YAMLError

from claude_dispatcher import yaml_io

CONFIG_FILENAME = ".dispatcher.yaml"


class RepoConfigError(ValueError):
    """Raised when .dispatcher.yaml exists but is malformed or invalid.

    The message always includes the config file path so the failure is
    diagnosable from the journal alone.
    """


@dataclass(frozen=True)
class RepoConfig:
    """Parsed per-repo dispatcher configuration.

    `test` is the verification command verbatim (never stripped), or None
    when the file or key is absent. `panel_advisory` is the tuple of
    advisory reviewer family names from `panel.advisory` (empty when the
    file, the `panel` key, or the `advisory` key is absent). `unknown_keys`
    lists keys this loader doesn't understand — top-level keys verbatim,
    keys nested under `panel` as ``panel.<key>`` — sorted, for the caller
    to journal.
    """

    test: str | None
    unknown_keys: tuple[str, ...] = field(default=())
    panel_advisory: tuple[str, ...] = ()
    # Repo-default integration mode (PRF-1): "branch" (today's behavior) or
    # "pr" (run-level feature branch + auto PRs). None when the key is absent
    # — the orchestrator then falls back to the built-in "branch" default. The
    # `dispatcher run --integration` CLI flag always wins over this.
    integration: str | None = None
    # Tier-based default model routing (2026-07-08): maps a task row's `risk:`
    # value (lowercased; plus the special key "default") to a model id. Used
    # ONLY when the row has no explicit `model:` — per-row model always wins,
    # which is where per-task complexity judgment lives. Empty when the key is
    # absent (the orchestrator then inherits the CLI/session default — the
    # behavior that let an entire epic silently run on the most expensive
    # tier, which this key exists to prevent).
    model_routing: tuple[tuple[str, str], ...] = ()

    def routed_model(self, risk: str | None) -> str | None:
        """The configured model for ``risk`` (case-insensitive), falling back
        to the "default" entry, else None (inherit the CLI/session default)."""
        table = dict(self.model_routing)
        if risk:
            hit = table.get(str(risk).strip().lower())
            if hit:
                return hit
        return table.get("default")


def load(repo_root: str | Path) -> RepoConfig:
    """Load `<repo_root>/.dispatcher.yaml` into a RepoConfig.

    Absent file → RepoConfig(test=None). Empty or comments-only file →
    test=None. Anything structurally wrong — non-mapping root, unparseable
    YAML, a `test:` value that is not a non-blank string, a `panel:` value
    that is not a mapping, a `panel.advisory` that is not a list of
    non-empty strings — raises RepoConfigError.

    A `roles:` section is validated through
    `role_protocol.role_policy_from_mapping` and its failure is re-raised as a
    RepoConfigError; the parsed policy is discarded (see the comment at the
    call). An invalid or narrowing section is therefore a load failure, not a
    dropped line.
    """
    path = Path(repo_root) / CONFIG_FILENAME
    if not path.exists():
        return RepoConfig(test=None)

    try:
        doc = yaml_io.load(path)
    except YAMLError as exc:
        raise RepoConfigError(f"malformed YAML in {path}: {exc}") from exc

    if doc is None:  # empty or comments-only document
        return RepoConfig(test=None)
    if not isinstance(doc, dict):
        raise RepoConfigError(
            f"root of {path} must be a mapping, got {type(doc).__name__}"
        )

    test = doc.get("test")
    if "test" in doc:
        # Strict on purpose: a bool/int/list here means the YAML didn't say
        # what the author thought it said, and silently skipping the gate
        # would defeat its purpose. Note bool is not a str subclass, so bare
        # `true` is rejected by the isinstance check like any other non-str.
        if not isinstance(test, str) or not test.strip():
            raise RepoConfigError(
                f"'test' in {path} must be a non-empty string command, "
                f"got {test!r}"
            )

    panel_advisory: tuple[str, ...] = ()
    panel_unknown: list[str] = []
    if "panel" in doc:
        panel = doc.get("panel")
        if not isinstance(panel, dict):
            raise RepoConfigError(
                f"'panel' in {path} must be a mapping, "
                f"got {type(panel).__name__}"
            )
        if "advisory" in panel:
            advisory = panel.get("advisory")
            if not isinstance(advisory, list):
                raise RepoConfigError(
                    f"'panel.advisory' in {path} must be a list of reviewer "
                    f"names, got {advisory!r}"
                )
            for entry in advisory:
                # Same strictness rationale as `test:` — and bool is not a
                # str subclass, so a bare `true` entry is rejected too.
                if not isinstance(entry, str) or not entry.strip():
                    raise RepoConfigError(
                        f"entries of 'panel.advisory' in {path} must be "
                        f"non-empty strings, got {entry!r}"
                    )
            panel_advisory = tuple(advisory)
        # Unknown keys INSIDE panel are tolerated (same forward-compat
        # stance as the top level) and reported as "panel.<key>".
        panel_unknown = [
            f"panel.{key}" for key in panel if key != "advisory"
        ]

    integration: str | None = None
    if "integration" in doc:
        integration = doc.get("integration")
        # Strict, same rationale as `test:`: an unrecognized value here means
        # the repo asked for a mode the dispatcher doesn't have, and silently
        # falling back to "branch" would hide that. bool is not a str subclass,
        # so bare `true` is rejected by the membership check.
        if integration not in ("branch", "pr"):
            raise RepoConfigError(
                f"'integration' in {path} must be 'branch' or 'pr', "
                f"got {integration!r}"
            )

    model_routing: tuple[tuple[str, str], ...] = ()
    if "model_routing" in doc:
        mr = doc.get("model_routing")
        if not isinstance(mr, dict):
            raise RepoConfigError(
                f"'model_routing' in {path} must be a mapping of "
                f"risk-tier -> model id, got {type(mr).__name__}"
            )
        pairs: list[tuple[str, str]] = []
        for k, v in mr.items():
            if not isinstance(k, str) or not k.strip():
                raise RepoConfigError(
                    f"'model_routing' key in {path} must be a non-empty "
                    f"string risk tier, got {k!r}"
                )
            if not isinstance(v, str) or not v.strip():
                raise RepoConfigError(
                    f"'model_routing.{k}' in {path} must be a non-empty "
                    f"model id string, got {v!r}"
                )
            pairs.append((k.strip().lower(), v.strip()))
        model_routing = tuple(pairs)

    # `roles:` — the D1 build-protocol immutable-path table. This loader
    # VALIDATES the section and deliberately does not keep the parsed policy:
    # `load` reads the working tree, and the gating path must take its policy
    # from the protected base (role_protocol.load_role_policy_from_base,
    # invariant 6), or a branch could supply the policy that judges it.
    #
    # Validating it here anyway is the point. Before this wiring the section
    # landed in `unknown_keys` and its additions were IGNORED — so a repo that
    # asked for extra protection got none, silently, and a repo that wrote a
    # *narrowing* entry (`immutable_paths: ['!**/tests/**']`) got a
    # self-weakening policy that no one refused. A silently dropped protection
    # is the failure this module's strictness exists to avoid, and the only
    # place a human sees this file before it is used is a load.
    #
    # Imported inside the function: role_protocol reads this module for the
    # one base-pinned reader, so a module-level import here would be a cycle.
    # The section NAME comes from role_protocol too — one fact, one place, so
    # a rename cannot leave the loader watching the old key.
    from claude_dispatcher import role_protocol

    roles_key = role_protocol.CONFIG_SECTION
    if roles_key in doc:
        try:
            role_protocol.role_policy_from_mapping(doc.get(roles_key))
        except role_protocol.RoleProtocolError as exc:
            raise RepoConfigError(
                f"'{roles_key}' in {path} is not a usable role policy: {exc}"
            ) from exc

    known_top_level = ("test", "panel", "integration", "model_routing", roles_key)
    unknown = tuple(sorted(
        [str(key) for key in doc if key not in known_top_level]
        + panel_unknown
    ))
    return RepoConfig(
        test=test,
        unknown_keys=unknown,
        panel_advisory=panel_advisory,
        integration=integration,
        model_routing=model_routing,
    )


class BaseConfigError(RepoConfigError):
    """Raised when `.dispatcher.yaml` cannot be read out of a base ref's tree.

    Distinct from a malformed-config error so a caller can tell "the policy is
    invalid" from "the policy could not be fetched" — both fail closed, but
    they have different operator actions.
    """


def load_text_at_base(repo_root: str | Path, base_ref: str) -> str | None:
    """SCAFFOLD (D1/P1) — the ONE base-pinned reader of `.dispatcher.yaml`.

    Returns the file's UTF-8 text as it exists in ``base_ref``'s **object
    store**, or None when ``base_ref`` resolves to a tree that simply does not
    contain the file. Never reads the working copy: on the in-worktree gating
    path the working copy is the checkout of the very branch being judged, so
    a branch could otherwise supply its own gate policy (design §8,
    implementation-plan invariant 6).

    Contract, exhaustively:

      * ``base_ref`` resolves and the tree has no ``.dispatcher.yaml`` → None.
        Absence is one state with one meaning; the caller applies its
        compiled-in defaults, which are its strictest setting.
      * ``base_ref`` resolves and the entry is a regular-file blob (mode
        100644/100755) that decodes as UTF-8 → its text.
      * anything else raises :class:`BaseConfigError`: the ref does not
        resolve, the entry is a symlink (a redirect to somewhere the base does
        not govern) or a submodule, git fails or times out, or the bytes are
        not UTF-8. There is deliberately no fallback to the working copy and
        none to "absent" — "I could not read the policy" must never be
        reported as "there is no policy".

    Implementation note for P3 (invariant 5 — one fact, one place): the
    identical git read exists as steps 1–3 of
    ``risk.load_risk_config_from_base`` on the unmerged
    ``fix/authority-doc-carveout`` branch. Implement this as that read,
    extracted, and make ``risk.py`` delegate to it in the same commit once
    that branch has merged. Do not create a second reader — the two would
    diverge on precisely the interesting cases (symlink, submodule, non-UTF-8),
    and the file whose read they disagree about is the gate's own policy.

    Consumers: :func:`role_protocol.load_role_policy_from_base` today; the
    ``risk:`` loader after the carveout merge.
    """
    try:
        return blob_text_at(repo_root, base_ref, CONFIG_FILENAME)
    except BaseConfigError:
        raise
    except Exception as exc:  # pragma: no cover - defensive; blob_text_at maps
        raise BaseConfigError(
            f"cannot read {CONFIG_FILENAME} at {base_ref}: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# The one git blob reader (invariant 5)
# --------------------------------------------------------------------------- #
#
# `load_text_at_base` above is the one reader of THIS file's policy;
# `blob_text_at` is the one reader of ANY path out of a ref's object store, and
# both go through it so the interesting cases — symlink, submodule, non-UTF-8,
# unresolvable ref — cannot be answered two different ways.
# `role_protocol.file_text_at` (the signature gate's reader) delegates here too.
#
# Two git reads, in this order:
#
#   1. `git ls-tree -z <ref>: -- <path>` — the AUTHORITATIVE answer. rc 0 with
#      no output means the tree genuinely does not contain the path (None); an
#      entry gives the mode, and any mode other than a regular-file blob
#      (symlink 120000, gitlink 160000, tree) is refused rather than read as
#      text. The tree-ish is spelled `<ref>:` rather than `<ref>` so the argv
#      carries the same `<ref>:<path>`-shaped token the blob read does, which
#      keeps injectable `run` seams that model only object-store reads able to
#      answer it.
#   2. `git cat-file blob <ref>:<path>` — the content. Reached when step 1
#      itself could not be answered (an unresolvable ref, or an injected seam
#      that models only blob reads). A failure here is classified by git's own
#      message: "does not exist in" is the absent-from-tree state (None);
#      anything else — invalid object name, bad file (a gitlink), a broken
#      repository — raises. Absence is never inferred from a failure whose
#      cause is unknown.
#
# Bytes are decoded STRICTLY: a non-UTF-8 blob raises rather than returning
# mojibake or None, because both of those read as "the policy says nothing".

_GIT_TIMEOUT_SECONDS = 30

#: git's message when a path is not in the named tree. The one failure that
#: means "absent" rather than "unreadable".
_GIT_ABSENT_MARKERS = ("does not exist in", "does not exist in the")


def _run_git(
    cmd: list[str],
    cwd: str,
    run: Callable[..., object] | None,
) -> tuple[int, bytes | str, str]:
    """`(returncode, stdout, stderr)` for one git command.

    ``run`` is the injectable subprocess seam (``push_verify``'s convention).
    Its result may be a ``CompletedProcess`` or a ``(rc, out, err)`` triple —
    both are accepted, because the seam's shape is the caller's choice and
    neither reading is more correct. Raises whatever the seam raises; callers
    map that to their own error type.
    """
    if run is None:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, timeout=_GIT_TIMEOUT_SECONDS
        )
        stderr = proc.stderr or b""
        return (
            proc.returncode,
            proc.stdout or b"",
            stderr.decode("utf-8", "replace"),
        )
    result = run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SECONDS,
    )
    if hasattr(result, "returncode"):
        rc = int(getattr(result, "returncode"))
        out = getattr(result, "stdout", "") or ""
        err = getattr(result, "stderr", "") or ""
        return rc, out, str(err)
    if isinstance(result, tuple) and len(result) >= 2:
        rc = int(result[0])
        out = result[1] or ""
        err = str(result[2]) if len(result) > 2 and result[2] else ""
        return rc, out, err
    raise BaseConfigError(
        f"injected git seam returned an unusable result: {type(result).__name__}"
    )


def _as_text(stdout: bytes | str, ref: str, path: str) -> str:
    if isinstance(stdout, str):
        return stdout
    try:
        return stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BaseConfigError(
            f"{path} at {ref} is not valid UTF-8: {exc}"
        ) from exc


def blob_text_at(
    repo_root: str | Path,
    ref: str,
    path: str,
    *,
    run: Callable[..., object] | None = None,
) -> str | None:
    """One path's UTF-8 text out of ``ref``'s object store, or None when
    ``ref``'s tree does not contain it.

    Never touches the working copy. Raises :class:`BaseConfigError` when the
    ref does not resolve, the entry is not a regular-file blob (symlink,
    submodule, directory), git fails or times out, or the bytes are not UTF-8 —
    "I could not read it" is never reported as "it is not there".
    """
    root = str(repo_root)
    try:
        rc, out, err = _run_git(
            ["git", "ls-tree", "-z", f"{ref}:", "--", path], root, run
        )
    except BaseConfigError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaseConfigError(f"cannot list {path} at {ref}: {exc}") from exc
    if rc == 0:
        entries = [
            entry
            for entry in _as_text(out, ref, path).split("\0")
            if entry.strip()
        ]
        if not entries:
            return None
        if len(entries) > 1:
            raise BaseConfigError(
                f"{path} at {ref} resolves to {len(entries)} tree entries"
            )
        meta, _tab, _name = entries[0].partition("\t")
        fields = meta.split()
        if len(fields) < 3:
            raise BaseConfigError(
                f"unparseable tree entry for {path} at {ref}: {entries[0]!r}"
            )
        mode, obj_type = fields[0], fields[1]
        if obj_type != "blob" or mode not in ("100644", "100755"):
            raise BaseConfigError(
                f"{path} at {ref} is a {obj_type} with mode {mode}, not a "
                "regular file — a symlink or submodule is a redirect to "
                "somewhere this ref does not govern"
            )

    try:
        rc, out, err = _run_git(
            ["git", "cat-file", "blob", f"{ref}:{path}"], root, run
        )
    except BaseConfigError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaseConfigError(f"cannot read {path} at {ref}: {exc}") from exc
    if rc != 0:
        lowered = err.lower()
        if any(marker in lowered for marker in _GIT_ABSENT_MARKERS):
            return None
        raise BaseConfigError(
            f"cannot read {path} at {ref} (git exit {rc}): {err.strip()}"
        )
    return _as_text(out, ref, path)
