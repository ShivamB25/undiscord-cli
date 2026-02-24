# MODULE KNOWLEDGE BASE

## OVERVIEW
Core runtime package for undiscord: CLI orchestration, Discord HTTP client, config loading, and Rich output helpers.

## STRUCTURE
```text
undiscord_cli/
├── cli.py       # Typer command + orchestration + deletion loop
├── client.py    # HTTP layer, retries, headers, rate-limit parsing
├── config.py    # Pydantic settings + .env/config resolution
├── console.py   # Rich UI (config table, progress, summary)
├── __main__.py  # Module entry wrapper
└── __init__.py  # Package version
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Add a new CLI option | `cli.py` | Add to `delete()` signature and `cli_values` map |
| Change delete/search algorithm | `cli.py` | `_delete_messages` + `_process_message` |
| Tune API retries/rate-limit parsing | `client.py` | `_request_with_retry` + `_parse_rate_limit` |
| Change config fields/preference | `config.py` | `Settings` model + `from_config_file` |
| Change terminal output format | `console.py` | Keep auth token masked |

## CONVENTIONS
- `cli.py` is orchestration only; avoid embedding raw HTTP details there.
- `client.py` handles Discord protocol concerns: headers, retry/backoff, and status parsing.
- Use `Settings` as the single typed config object across all modules.
- Treat `MAX_SEARCH_OFFSET` and snowflake windowing as behavior-critical, not cosmetic.

## ANTI-PATTERNS
- Don't move retry logic out of `client.py` into CLI call sites.
- Don't duplicate settings parsing in `cli.py`; extend `Settings` instead.
- Don't log or display full tokens; preserve masking in `console.py`.
- Don't remove 403 consecutive-stop behavior without a replacement safeguard.
- Don't change output-only modules (`console.py`) to perform business logic.
