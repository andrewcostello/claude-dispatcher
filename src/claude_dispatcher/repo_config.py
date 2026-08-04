"""Per-repo dispatcher config: load and validate `.dispatcher.yaml`.

A repo opts into dispatcher verification gates by placing a `.dispatcher.yaml`
at its root. Current schema:

  * `test:` — the shell command run inside a task worktree (exit 0 = green).
  * `panel:` — cross-family panel options. Its only known key today is
    `advisory:`, a list of advisory (probationary, non-blocking) reviewer
    family names — e.g. ``panel: {advisory: [grok]}`` — consumed by the
    orchestrator's cross-family panel.

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

from dataclasses import dataclass, field
from pathlib import Path

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

    # NOTE: `roles:` (the D1 build-protocol immutable-path table) is not in
    # this tuple yet, so a repo that adds one lands it in `unknown_keys` and
    # its additions are IGNORED. That is stated rather than implied because a
    # silently dropped protection is the failure this module's strictness
    # exists to avoid — see role_protocol.role_policy_from_mapping, which P3
    # wires in here.
    known_top_level = ("test", "panel", "integration", "model_routing")
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
    raise NotImplementedError
