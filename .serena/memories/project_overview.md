Purpose: CLI tool to bulk-delete Discord messages in channels/DMs using user auth token workflows.
Tech stack: Python 3.14+, Typer CLI, httpx HTTP client, pydantic-settings config loading, Rich terminal UI, uv package manager, hatchling build backend.
Repository type: single-package Python CLI project (not monorepo).
Primary package: undiscord_cli/ with modules for cli, client, config, console.
Key behavior: search routing is context-aware — guild channels use `/guilds/{guild_id}/messages/search` with `channel_id`; DMs use `/channels/{channel_id}/messages/search`. `guild_id` can be explicit or auto-detected from `GET /channels/{channel_id}`.