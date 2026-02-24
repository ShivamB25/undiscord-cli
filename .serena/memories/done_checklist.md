When task is completed in this project:
1) Run diagnostics/type checks for touched files if available.
2) Run CLI smoke checks (at least `uv run undiscord --help`).
3) Prefer dry-run checks for behavior changes (`uv run undiscord --dry-run --yes`).
4) For search-path changes, verify both flows:
   - explicit guild flow (`--guild-id <GUILD_ID>`)
   - auto-detect flow (omit `--guild-id`, ensure clean user-facing error on auth failures)
5) Ensure no token leakage in logs/output/docs.
6) Keep entry points aligned: pyproject script, __main__.py, and main.py.
7) If version changed, keep pyproject.toml and undiscord_cli/__init__.py synchronized.