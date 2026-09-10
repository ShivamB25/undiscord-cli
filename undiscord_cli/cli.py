from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
from pydantic import ValidationError
from rich.logging import RichHandler

from undiscord_cli.client import MAX_CONSECUTIVE_403, DiscordClient
from undiscord_cli.config import Settings
from undiscord_cli.console import console, create_progress, print_config, print_summary

app = typer.Typer(
    name="undiscord",
    help="Bulk delete Discord messages from channels and DMs.",
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )
        ],
        force=True,
    )
    logging.getLogger("httpx").setLevel(
        logging.WARNING if not verbose else logging.INFO
    )
    logging.getLogger("httpcore").setLevel(
        logging.WARNING if not verbose else logging.INFO
    )


def _process_message(
    client: DiscordClient,
    settings: Settings,
    message: dict[str, Any],
    consecutive_403_errors: int,
    pattern: re.Pattern[str] | None = None,
) -> tuple[str, int]:
    if not settings.include_pinned and message.get("pinned"):
        return "skipped", consecutive_403_errors

    content = message.get("content", "")
    if pattern is not None and not pattern.search(content):
        return "skipped", consecutive_403_errors

    message_id = message.get("id")
    if message_id is None:
        return "failed", consecutive_403_errors

    try:
        status_code = client.delete_message(settings.channel_id, message_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("Error deleting message %s: %s", message_id, type(exc).__name__)
        return "failed", consecutive_403_errors
    finally:
        if not settings.dry_run:
            time.sleep(settings.delete_delay / 1000.0)

    if status_code == 204:
        logger.debug("Deleted message %s", message_id)
        return "deleted", 0

    if status_code == 403:
        logger.warning(
            "Failed to delete message %s with status code 403 (Forbidden). You might not have permission.",
            message_id,
        )
        return "failed", consecutive_403_errors + 1

    if status_code == 401:
        logger.error(
            "Failed to delete message %s with status code 401 (Unauthorized).",
            message_id,
        )
        return "unauthorized", consecutive_403_errors

    logger.error(
        "Failed to delete message %s with status code %s", message_id, status_code
    )
    return "failed", consecutive_403_errors


def _delete_messages(client: DiscordClient, settings: Settings) -> tuple[int, int, int]:
    total_deleted = 0
    total_failed = 0
    total_skipped = 0
    consecutive_403_errors = 0
    current_max_id = settings.max_id
    pattern = (
        re.compile(settings.pattern, re.IGNORECASE)
        if settings.pattern is not None
        else None
    )

    with create_progress() as progress:
        mode_prefix = "[yellow]DRY RUN[/yellow] " if settings.dry_run else ""
        task_id = progress.add_task(
            f"{mode_prefix}Deleting messages...",
            total=None,
            deleted=0,
            failed=0,
            skipped=0,
        )

        while True:
            try:
                response = client.search_messages(
                    settings.channel_id,
                    guild_id=settings.guild_id,
                    author_id=settings.author_id,
                    content=settings.content,
                    has_link=settings.has_link,
                    has_file=settings.has_file,
                    min_id=settings.min_id,
                    max_id=current_max_id,
                    include_nsfw=settings.include_nsfw,
                    offset=0,
                )
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.error("Error searching messages: %s", type(exc).__name__)
                progress.stop_task(task_id)
                raise

            message_groups = response.get("messages")
            if not message_groups:
                logger.debug("No more messages found.")
                break

            page_ids: set[str] = set()
            cursor_ids: list[int] = []
            upper_bound = int(current_max_id) if current_max_id is not None else None

            for message_group in message_groups:
                messages = (
                    (message_group,)
                    if isinstance(message_group, dict)
                    else message_group
                )
                for message in messages:
                    if message.get("hit") is False:
                        continue

                    message_channel_id = message.get("channel_id")
                    if message_channel_id is not None and str(
                        message_channel_id
                    ) != str(settings.channel_id):
                        continue

                    raw_message_id = message.get("id")
                    message_key = (
                        str(raw_message_id) if raw_message_id is not None else None
                    )
                    if message_key is not None:
                        if message_key in page_ids:
                            continue
                        page_ids.add(message_key)

                        try:
                            snowflake = int(message_key)
                        except ValueError:
                            raise RuntimeError(
                                "Search returned an invalid message ID."
                            ) from None
                        if upper_bound is not None and snowflake >= upper_bound:
                            continue
                        cursor_ids.append(snowflake)

                    result, consecutive_403_errors = _process_message(
                        client=client,
                        settings=settings,
                        message=message,
                        consecutive_403_errors=consecutive_403_errors,
                        pattern=pattern,
                    )

                    if result == "deleted":
                        total_deleted += 1
                    elif result == "skipped":
                        total_skipped += 1
                    else:
                        total_failed += 1

                    progress.update(
                        task_id,
                        description=f"{mode_prefix}Deleting messages...",
                        deleted=total_deleted,
                        failed=total_failed,
                        skipped=total_skipped,
                    )

                    if result == "unauthorized":
                        logger.error(
                            "Discord authorization failed. Stopping for safety."
                        )
                        progress.stop_task(task_id)
                        return total_deleted, total_failed, total_skipped

                    if consecutive_403_errors >= MAX_CONSECUTIVE_403:
                        logger.error(
                            "Encountered %s consecutive 403 errors. Stopping for safety.",
                            MAX_CONSECUTIVE_403,
                        )
                        progress.stop_task(task_id)
                        return total_deleted, total_failed, total_skipped

            if not cursor_ids:
                if page_ids:
                    raise RuntimeError(
                        "Search cursor did not decrease; stopping safely."
                    )
                logger.debug("No actual search hits with usable IDs found.")
                break

            next_max_id = str(min(cursor_ids))

            current_max_id = next_max_id
            if settings.search_delay > 0:
                time.sleep(settings.search_delay / 1000.0)

    return total_deleted, total_failed, total_skipped


@app.command()
def delete(
    auth_token: Annotated[
        str | None,
        typer.Option("--token", "-t", help="Discord authorization token."),
    ] = None,
    channel_id: Annotated[
        str | None,
        typer.Option("--channel", "-c", help="Channel ID where messages are located."),
    ] = None,
    guild_id: Annotated[
        str | None,
        typer.Option(
            "--guild-id",
            "-g",
            help="Server (guild) ID for server channels. Use @me for DMs.",
        ),
    ] = None,
    author_id: Annotated[
        str | None, typer.Option("--author-id", help="Filter by author ID.")
    ] = None,
    content: Annotated[
        str | None, typer.Option("--content", help="Filter by text content.")
    ] = None,
    has_link: Annotated[
        bool | None,
        typer.Option(
            "--has-link/--no-has-link", help="Filter messages containing links."
        ),
    ] = None,
    has_file: Annotated[
        bool | None,
        typer.Option(
            "--has-file/--no-has-file", help="Filter messages containing files."
        ),
    ] = None,
    min_id: Annotated[
        str | None, typer.Option("--min-id", help="Only delete after this ID.")
    ] = None,
    max_id: Annotated[
        str | None, typer.Option("--max-id", help="Only delete before this ID.")
    ] = None,
    include_nsfw: Annotated[
        bool | None,
        typer.Option(
            "--include-nsfw/--no-include-nsfw", help="Include NSFW channels in search."
        ),
    ] = None,
    include_pinned: Annotated[
        bool | None,
        typer.Option(
            "--include-pinned/--no-include-pinned", help="Include pinned messages."
        ),
    ] = None,
    pattern: Annotated[
        str | None, typer.Option("--pattern", help="Regex pattern filter.")
    ] = None,
    search_delay: Annotated[
        int | None,
        typer.Option(
            "--search-delay", help="Delay between search calls in milliseconds."
        ),
    ] = None,
    delete_delay: Annotated[
        int | None,
        typer.Option(
            "--delete-delay", help="Delay between delete calls in milliseconds."
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", help="Path to JSON config file."),
    ] = None,
    dry_run: Annotated[
        bool | None,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Search and report matches without deleting messages.",
        ),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.")
    ] = False,
) -> None:
    _configure_logging(verbose)

    try:
        cli_values: dict[str, Any] = {
            "auth_token": auth_token,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "author_id": author_id,
            "content": content,
            "has_link": has_link,
            "has_file": has_file,
            "min_id": min_id,
            "max_id": max_id,
            "include_nsfw": include_nsfw,
            "include_pinned": include_pinned,
            "pattern": pattern,
            "search_delay": search_delay,
            "delete_delay": delete_delay,
            "dry_run": dry_run,
        }
        settings = Settings(
            config_file=config,
            **{key: value for key, value in cli_values.items() if value is not None},
        )
    except FileNotFoundError:
        console.print("[red]Config file not found.[/red]")
        raise typer.Exit(code=1)
    except OSError:
        console.print("[red]Unable to read config file.[/red]")
        raise typer.Exit(code=1)
    except ValidationError, ValueError:
        console.print("[red]Configuration error.[/red]")
        raise typer.Exit(code=1)

    print_config(settings)

    if not yes:
        confirmed = typer.confirm("Proceed with message deletion?", default=False)
        if not confirmed:
            console.print("[yellow]Aborted by user before starting.[/yellow]")
            raise typer.Exit(code=0)

    try:
        started_at = time.monotonic()
        with DiscordClient(settings.auth_token, dry_run=settings.dry_run) as client:
            if settings.guild_id is None:
                try:
                    channel_info = client.get_channel(settings.channel_id)
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if status_code == 401:
                        console.print(
                            "[red]Discord authorization failed (401 Unauthorized).[/red]"
                        )
                    else:
                        console.print(
                            "[red]Failed to auto-detect guild context from channel.[/red]"
                        )
                    logger.error(
                        "Error detecting channel context: %s", type(exc).__name__
                    )
                    raise typer.Exit(code=1)
                except httpx.RequestError:
                    console.print(
                        "[red]Failed to auto-detect guild context from channel.[/red]"
                    )
                    logger.error("Error detecting channel context: network error")
                    raise typer.Exit(code=1)

                settings.guild_id = channel_info.get("guild_id") or "@me"
                logger.info(
                    "Resolved channel %s context as guild_id=%s",
                    settings.channel_id,
                    settings.guild_id,
                )
            deleted, failed, skipped = _delete_messages(client, settings)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted by user.[/yellow]")
        raise typer.Exit(code=130)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code == 401:
            console.print("[red]Discord authorization failed (401 Unauthorized).[/red]")
        else:
            console.print(f"[red]Discord request failed (HTTP {status_code}).[/red]")
        raise typer.Exit(code=1)
    except httpx.RequestError:
        console.print("[red]Discord request failed due to a network error.[/red]")
        raise typer.Exit(code=1)
    except RuntimeError, ValueError:
        console.print(
            "[red]Search returned invalid data or could not advance safely.[/red]"
        )
        raise typer.Exit(code=1)

    print_summary(deleted, failed, skipped, time.monotonic() - started_at)
    if failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
