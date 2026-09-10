# undiscord-cli

Modern Python CLI for bulk deleting Discord messages in a channel or DM, with filtering, retries, rate-limit handling, and dry-run support.

## Important Notice

Automating user-token actions can violate Discord Terms of Service. Use this tool at your own risk and only where you are authorized to perform these actions.

## Highlights

- Typer-based CLI with rich help and shell completion
- Layered configuration: CLI options > environment (.env) > defaults
- `httpx` client with retries, backoff, and rate-limit parsing
- Supports dry-run mode to preview actions without deleting anything
- Safety stop on repeated `403` responses
- Handles Discord search offset cap (`9975`) with snowflake windowing

## Requirements

- Python `>=3.14`
- `uv` (recommended)

## Install

```bash
uv sync
```

Run help:

```bash
uv run undiscord --help
```

## Configuration

Copy the example file:

```bash
cp .env.example .env
```

Set required values:

```env
UNDISCORD_AUTH_TOKEN=
UNDISCORD_CHANNEL_ID=
```

Optional fields include:

- `UNDISCORD_AUTHOR_ID`
- `UNDISCORD_DRY_RUN`

## Usage

Basic:

```bash
uv run undiscord --yes
```

With explicit flags:

```bash
uv run undiscord \
  --token "YOUR_TOKEN" \
  --channel "CHANNEL_ID" \
  --guild-id "GUILD_ID" \
  --author-id "YOUR_USER_ID" \
  --search-delay 30000 \
  --delete-delay 1000 \
  --yes
```

Dry-run:

```bash
uv run undiscord --dry-run --yes
```

Dry-run still authenticates and searches Discord; it sends no DELETE requests.

Configuration precedence is CLI flags > environment variables > `.env` > JSON
(`--config path/to/settings.json`) > defaults. JSON keys use setting names such
as `auth_token` and `channel_id`, without the `UNDISCORD_` prefix. Explicit
negative flags such as `--no-dry-run` override enabled values in configuration.

Negative delays and invalid regular expressions are rejected before any network
requests. Search pages use a decreasing message-ID boundary so deleting matches
does not skip later pages or hit the 10,000-result offset limit. The client owns
rate-limit and indexing retries; `--delete-delay` also applies after successful
deletions. Failed runs and safety stops return a nonzero exit code.

Filter examples:

```bash
# Only messages with links
uv run undiscord --has-link --yes

# Only messages matching regex
uv run undiscord --pattern "error|failed" --yes

# Date/range window (snowflake IDs)
uv run undiscord --min-id 123 --max-id 456 --yes
```

## CLI Options

Main options:

- `--token`, `-t`
- `--channel`, `-c`
- `--guild-id`, `-g` (optional; auto-detected if omitted, use `@me` for DMs)
- `--author-id`
- `--content`
- `--has-link / --no-has-link`
- `--has-file / --no-has-file`
- `--min-id`
- `--max-id`
- `--include-nsfw / --no-include-nsfw`
- `--include-pinned / --no-include-pinned`
- `--pattern`
- `--search-delay` (ms)
- `--delete-delay` (ms)
- `--config` (JSON file)
- `--dry-run / --no-dry-run`
- `--yes`, `-y`
- `--verbose`, `-v`

## Entry Points

All of these are supported:

```bash
uv run undiscord --help
uv run python -m undiscord_cli --help
uv run python main.py --help
```

## Project Layout

```text
undiscord_cli/
  cli.py       # Typer command + delete flow
  client.py    # Discord HTTP client
  config.py    # pydantic-settings config
  console.py   # Rich output helpers
```

## Troubleshooting

- `401 Unauthorized`: token is invalid/expired
- `403 Forbidden`: message permissions not allowed in that context
- `429 Too Many Requests`: tool waits and retries automatically
- No results found: verify channel ID and filters

## Development

```bash
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked ruff check undiscord_cli tests main.py
uv run --locked ruff format --check undiscord_cli tests main.py
uv build
```

The regression suite uses local HTTP simulations, not live Discord credentials.

### 0.2.0 maintenance update

- Updated compatible runtime dependencies and declared Pydantic directly.
- Consolidated configuration sources and HTTP retries; fixed deletion pacing,
  shrinking-result pagination, and token-safe output.
- Added regression coverage and reproducible Ruff tooling.

## License

MIT. See `LICENSE.md`.
