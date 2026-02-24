When task is completed in this project:
1) Run diagnostics/type checks for touched files if available.
2) Run CLI smoke checks (at least `uv run undiscord --help`).
3) Prefer dry-run checks for behavior changes (`uv run undiscord --dry-run --yes`).
4) Ensure no token leakage in logs/output/docs.
5) Keep entry points aligned: pyproject script, __main__.py, and main.py.
6) If version changed, keep pyproject.toml and undiscord_cli/__init__.py synchronized.