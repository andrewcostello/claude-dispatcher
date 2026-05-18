"""Allow `python -m claude_dispatcher ...` invocation."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
