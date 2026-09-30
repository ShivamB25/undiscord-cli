# undiscord-cli

Delete Discord messages from a channel or DM, with filters and a dry-run mode.

Automating user-token actions can violate Discord's Terms of Service. Use only
where you are authorized. Deletions cannot be undone.

## Run

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14 or later. From this checkout:

```bash
uvx --python 3.14 --from . undiscord --help
```

`uvx` runs the package in an isolated environment; no `uv sync` is needed.
Add `--refresh` before `--python` after changing source. Tool environments do not
use `uv.lock`; use `uv run --locked undiscord ...` for locked dependencies.

## Configure

Copy `.env.example` to `.env` and set:

```env
UNDISCORD_AUTH_TOKEN=your-token
UNDISCORD_CHANNEL_ID=channel-id
UNDISCORD_AUTHOR_ID=your-user-id
```

Token and channel are required. Set the author filter to limit matches to your
messages. Keep the token out of shell history and version control.

Precedence: CLI flags > environment variables > `.env` > JSON > defaults.
Use `--config path/to/settings.json` for JSON configuration; keys are setting
names such as `auth_token` and `channel_id`, without the `UNDISCORD_` prefix.
Negative flags such as `--no-dry-run` override enabled configuration values.

## Delete messages

Preview matches first:

```bash
uvx --python 3.14 --from . undiscord --dry-run
```

Dry-run authenticates and searches Discord but sends no DELETE requests.
To delete, run:

```bash
uvx --python 3.14 --from . undiscord --no-dry-run
```

The command asks for confirmation. Add `--yes` to skip it.
Guild context is auto-detected; use `--guild-id GUILD_ID` to set it explicitly
or `--guild-id @me` for a DM.

Filters can be combined:

```bash
uvx --python 3.14 --from . undiscord --dry-run --has-link --content "example"
uvx --python 3.14 --from . undiscord --dry-run --pattern "error|failed"
uvx --python 3.14 --from . undiscord --dry-run --min-id 123 --max-id 456
```

Pinned messages are skipped unless `--include-pinned` is set. Use `--has-file`
for attachments and `--include-nsfw` to include NSFW search results.
Run `--help` for all options.

## Request handling

- `--search-delay` and `--delete-delay` are in milliseconds; defaults are 30000
  and 1000. Negative delays and invalid regex patterns fail before requests start.
- Search uses decreasing message-ID boundaries to avoid skipping matches as
  messages disappear and to stay below Discord's search offset limit.
- Rate limits, pending search indexes, and transient failures have bounded retries.
- Authorization failures and repeated `403` responses stop deletion. Failed runs
  return a nonzero exit code.

For `401`, check the token. For `403`, check permissions. If search returns no
matches, check the channel, author, and filters.

## Development

```bash
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uvx ruff@0.16.9 check undiscord_cli tests main.py
uvx ruff@0.16.9 format --check undiscord_cli tests main.py
uv build
```

Tests use simulated HTTP responses, not live Discord credentials. Ruff runs as a
standalone tool. Refresh dependencies with `uv lock --upgrade` and commit the
updated lockfile with any metadata changes.

The module and script entry points use the same CLI:

```bash
uv run --locked python -m undiscord_cli --help
uv run --locked python main.py --help
```

## License

[MIT](LICENSE.md).
