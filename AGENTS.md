# PROJECT KNOWLEDGE BASE

**Generated:** 2026-02-24 21:24:57 IST  
**Commit:** 9bb643e  
**Branch:** master

## OVERVIEW
Python CLI for bulk Discord message deletion. Stack: Typer + httpx + pydantic-settings + Rich, packaged with `uv` and `hatchling`.

## STRUCTURE
```text
undiscord-cli/
├── undiscord_cli/      # Core package (CLI flow, HTTP client, config, console)
├── main.py             # Thin script entry
├── pyproject.toml      # Metadata, deps, script entrypoint
├── .env.example        # Required env schema
└── uv.lock             # Locked dependency graph
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Add/modify CLI flags | `undiscord_cli/cli.py` | `delete()` command is the only command surface |
| Change Discord HTTP behavior | `undiscord_cli/client.py` | Retry, headers, rate-limit parsing, guild/DM API path selection |
| Adjust config loading rules | `undiscord_cli/config.py` | Precedence + env parsing logic (`guild_id` supported) |
| Adjust output/progress UX | `undiscord_cli/console.py` | Rich table/panel/progress only |
| Update packaging/run behavior | `pyproject.toml`, `main.py`, `undiscord_cli/__main__.py` | Three entry paths must stay aligned |

## CODE MAP
| Symbol | Type | Location | Refs | Role |
|--------|------|----------|------|------|
| `delete` | command fn | `undiscord_cli/cli.py` | entry | CLI orchestration: config, confirm, run |
| `_delete_messages` | helper fn | `undiscord_cli/cli.py` | internal | Main search/delete loop + snowflake windowing |
| `_process_message` | helper fn | `undiscord_cli/cli.py` | internal | Per-message filtering + status handling |
| `DiscordClient` | class | `undiscord_cli/client.py` | used by CLI | API interaction and retry behavior |
| `get_channel` | helper fn | `undiscord_cli/client.py` | used by CLI | Channel metadata fetch for guild/DM auto-detection |
| `Settings` | class | `undiscord_cli/config.py` | used by CLI+console | Typed config model and env loading |

## CONVENTIONS
- Python `>=3.14` is required (`.python-version` + `pyproject.toml`).
- Package manager is `uv`; use `uv sync` and `uv run ...` (not `pip install` + direct execution).
- Config priority is `CLI args > env vars > defaults`; env var prefix is `UNDISCORD_`.
- Single command model: all behavior hangs off the root `undiscord` command in `delete()`.
- Keep token-safe display behavior (masked token only) when changing output.
- Search endpoint must match context: guild channels use `/guilds/{guild_id}/messages/search` (+ `channel_id`); DMs use `/channels/{channel_id}/messages/search`.

## ANTI-PATTERNS (THIS PROJECT)
- Do not reintroduce legacy files (`undiscord.py`, `config.json`, `requirements.txt`).
- Do not print raw auth token anywhere (logs, exceptions, console tables).
- Do not bypass 403 safety-stop logic or rate-limit handling in client/CLI flow.
- Do not add alternate business logic entrypoints that diverge from `undiscord_cli/cli.py`.
- Do not switch API version/header behavior without validating against current Discord behavior.
- Do not force `/channels/{channel_id}/messages/search` for guild channels; this causes `400` on server channels.

## UNIQUE STYLES
- API throttling and retry logic are centralized in `DiscordClient`; keep network policy out of CLI layer.
- CLI layer owns orchestration and progress reporting, not transport details.
- Snowflake windowing logic is intentionally in `_delete_messages` to handle offset cap (`9975`).
- `guild_id` can be passed explicitly (`--guild-id` / `UNDISCORD_GUILD_ID`) or auto-resolved from `GET /channels/{channel_id}`.

## COMMANDS
```bash
uv sync
uv run undiscord --help
uv run undiscord --channel <CHANNEL_ID> --guild-id <GUILD_ID> --author-id <AUTHOR_ID> --yes
uv run undiscord --dry-run --yes
uv run python -m undiscord_cli --help
uv run python main.py --help
uv build
```

## NOTES
- Repository has no test suite/CI workflow yet; verification is currently diagnostics + CLI smoke runs.
- Version appears in `pyproject.toml` and `undiscord_cli/__init__.py`; keep them synchronized.
