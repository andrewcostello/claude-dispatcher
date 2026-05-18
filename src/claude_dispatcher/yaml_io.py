"""YAML I/O with comment and ordering preservation.

The task YAML files contain authoritative context in their header comments and
section dividers (design pivot history, the "what NOT to do" notes). Losing
those on write would silently destroy load-bearing documentation, so the
dispatcher uses ruamel.yaml in round-trip mode for every read/write.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


def _yaml() -> YAML:
    """Construct a configured round-trip YAML instance.

    Returning a fresh instance per call is intentional — ruamel's YAML object
    holds parser state that is not safe to share across concurrent reads.
    """
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096  # don't auto-wrap long descriptions
    return y


def load(path: str | Path) -> Any:
    """Load a YAML file, preserving comments and ordering."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        return _yaml().load(fh)


def dump(data: Any, path: str | Path) -> None:
    """Atomically write YAML to disk, preserving comments and ordering.

    Writes to a sibling temp file, then renames into place. The rename is
    atomic on POSIX filesystems, so a reader catching the file mid-write
    sees either the old or new contents — never a half-written file.
    """
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        _yaml().dump(data, fh)
    os.replace(tmp, p)


def dumps(data: Any) -> str:
    """Render YAML to a string. For tests and dry-run output."""
    buf = io.StringIO()
    _yaml().dump(data, buf)
    return buf.getvalue()


class LockTimeout(RuntimeError):
    """Raised when the YAML lock file is still held after the timeout."""


class FileLock:
    """A simple advisory lock file used to serialize YAML writes across
    parallel dispatcher subprocesses.

    Implemented as an exclusive O_CREAT|O_EXCL file at <yaml-path>.lock.
    Holders write their PID for diagnostics. The lock is released on
    context-manager exit OR on garbage collection — readers stale-lock-out
    only when something has truly crashed.
    """

    def __init__(self, target: str | Path, timeout_seconds: float = 30.0):
        self.lock_path = Path(str(target) + ".lock")
        self.timeout = timeout_seconds
        self._fd: int | None = None

    def __enter__(self) -> "FileLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
                os.write(self._fd, f"{os.getpid()}\n".encode())
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"YAML lock at {self.lock_path} still held after "
                        f"{self.timeout:.0f}s — another dispatcher may be running"
                    )
                time.sleep(0.1)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass
