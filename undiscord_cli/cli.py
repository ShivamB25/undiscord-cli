from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import typer
from pydantic import ValidationError
from typing_extensions import Annotated

from undiscord_cli.client import DiscordClient, MAX_CONSECUTIVE_403, MAX_SEARCH_OFFSET
from undiscord_cli.config import Settings
from undiscord_cli.console import console, create_progress, print_config, print_summary

app = typer.Typer(
    name="undiscord",
    help="Bulk delete Discord messages from channels and DMs.",
    rich_markup_mode="rich",
)

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def _build_settings(cli_values: dict[str, Any], config_path: Optional[str]) -> Settings:
    cli_overrides = {
        key: value for key, value in cli_values.items() if value is not None
    }

    if not config_path:
        return Settings(**cli_overrides)

    with Path(config_path).open("r", encoding="utf-8") as file:
        raw_config = json.load(file)

    if not isinstance(raw_config, dict):
        raise ValueError("Config file must contain a JSON object.")

    config_values: dict[str, Any] = {
        key: value for key, value in raw_config.items() if key in Settings.model_fields
    }

    dotenv_values = Settings._read_dotenv_file()
    for field_name in Settings.model_fields:
        env_key = f"UNDISCORD_{field_name.upper()}"
        if env_key in os.environ or env_key in dotenv_values:
            config_values.pop(field_name, None)

    return Settings(**config_values, **cli_overrides)


def _process_message(
    client: DiscordClient,
    settings: Settings,
    message: dict[str, Any],
    consecutive_403_errors: int,
) -> tuple[str, int]:
    if not settings.include_pinned and message.get("pinned"):
        return "skipped", consecutive_403_errors

    content = message.get("content", "")
    if settings.pattern and not re.search(settings.pattern, content, re.IGNORECASE):
        return "skipped", consecutive_403_errors

    message_id = message.get("id")
    if message_id is None:
        return "failed", consecutive_403_errors

    try:
        status_code = client.delete_message(settings.channel_id, message_id)
        if status_code == 429:
            retry_after = client.last_retry_after_seconds
            logger.warning(
                "Rate limited while deleting %s. Retrying after %.2f seconds.",
                message_id,
                retry_after,
            )
            time.sleep(retry_after)
            status_code = client.delete_message(settings.channel_id, message_id)

        if status_code == 204:
            logger.info("Deleted message %s", message_id)
            return "deleted", 0

        if status_code == 403:
            logger.warning(
                "Failed to delete message %s with status code 403 (Forbidden). You might not have permission.",
                message_id,
            )
            time.sleep(settings.delete_delay / 1000.0)
            return "failed", consecutive_403_errors + 1

        logger.error(
            "Failed to delete message %s with status code %s", message_id, status_code
        )
        time.sleep(settings.delete_delay / 1000.0)
        return "failed", consecutive_403_errors
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        logger.error("Error deleting message %s: %s", message_id, exc)
        time.sleep(settings.delete_delay / 1000.0)
        return "failed", consecutive_403_errors


def _delete_messages(client: DiscordClient, settings: Settings) -> tuple[int, int, int]:
    offset = 0
    total_deleted = 0
    total_failed = 0
    total_skipped = 0
    consecutive_403_errors = 0
    messages_remaining = True

    # Snowflake windowing: when offset hits Discord's hard cap (9975),
    # we reset offset to 0 and set max_id to the oldest message ID from
    # the last batch.  This lets us page through >10k messages.
    current_max_id = settings.max_id

    with create_progress() as progress:
        task_id = progress.add_task("Deleting messages...", total=None)

        while messages_remaining:
            messages_remaining = False

            while True:
                try:
                    response = client.search_messages(
                        settings.channel_id,
                        author_id=settings.author_id,
                        content=settings.content,
                        has_link=settings.has_link,
                        has_file=settings.has_file,
                        min_id=settings.min_id,
                        max_id=current_max_id,
                        include_nsfw=settings.include_nsfw,
                        offset=offset,
                    )
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    logger.error("Error searching messages: %s", exc)
                    break

                message_groups = response.get("messages")
                if not message_groups:
                    logger.info("No more messages found.")
                    break

                messages_remaining = True

                # Track the oldest message ID in this batch for
                # snowflake windowing when we hit the offset cap.
                batch_oldest_id: str | None = None

                for message_group in message_groups:
                    for message in message_group:
                        msg_id = message.get("id")
                        if msg_id is not None:
                            if batch_oldest_id is None or int(msg_id) < int(batch_oldest_id):
                                batch_oldest_id = msg_id

                        result, consecutive_403_errors = _process_message(
                            client=client,
                            settings=settings,
                            message=message,
                            consecutive_403_errors=consecutive_403_errors,
                        )

                        if result == "deleted":
                            total_deleted += 1
                        elif result == "skipped":
                            total_skipped += 1
                        else:
                            total_failed += 1

                        if consecutive_403_errors >= MAX_CONSECUTIVE_403:
                            logger.error(
                                "Encountered %s consecutive 403 errors. Stopping for safety.",
                                MAX_CONSECUTIVE_403,
                            )
                            progress.stop_task(task_id)
                            return total_deleted, total_failed, total_skipped

                        progress.update(
                            task_id,
                            description=(
                                "Deleting messages... "
                                f"deleted={total_deleted}, failed={total_failed}, skipped={total_skipped}"
                            ),
                        )

                offset += len(message_groups)

                # Snowflake windowing: if offset is about to exceed
                # Discord's hard cap, reset to 0 and use the oldest
                # message ID as max_id to continue from that point.
                if offset >= MAX_SEARCH_OFFSET and batch_oldest_id is not None:
                    logger.info(
                        "Offset reached %s (Discord cap). Switching to "
                        "snowflake windowing with max_id=%s.",
                        MAX_SEARCH_OFFSET,
                        batch_oldest_id,
                    )
                    current_max_id = batch_oldest_id
                    offset = 0

                logger.info(
                    "Progress: %s deleted, %s failed, %s skipped",
                    total_deleted,
                    total_failed,
                    total_skipped,
                )
                time.sleep(settings.search_delay / 1000.0)

            if messages_remaining:
                logger.info("Rechecking for remaining messages to delete...")

    return total_deleted, total_failed, total_skipped


@app.command()
def delete(
    auth_token: Annotated[
        Optional[str],
        typer.Option("--token", "-t", help="Discord authorization token."),
    ] = None,
    channel_id: Annotated[
        Optional[str],
        typer.Option("--channel", "-c", help="Channel ID where messages are located."),
    ] = None,
    author_id: Annotated[
        Optional[str], typer.Option("--author-id", help="Filter by author ID.")
    ] = None,
    content: Annotated[
        Optional[str], typer.Option("--content", help="Filter by text content.")
    ] = None,
    has_link: Annotated[
        Optional[bool],
        typer.Option(
            "--has-link/--no-has-link", help="Filter messages containing links."
        ),
    ] = None,
    has_file: Annotated[
        Optional[bool],
        typer.Option(
            "--has-file/--no-has-file", help="Filter messages containing files."
        ),
    ] = None,
    min_id: Annotated[
        Optional[str], typer.Option("--min-id", help="Only delete after this ID.")
    ] = None,
    max_id: Annotated[
        Optional[str], typer.Option("--max-id", help="Only delete before this ID.")
    ] = None,
    include_nsfw: Annotated[
        Optional[bool],
        typer.Option(
            "--include-nsfw/--no-include-nsfw", help="Include NSFW channels in search."
        ),
    ] = None,
    include_pinned: Annotated[
        Optional[bool],
        typer.Option(
            "--include-pinned/--no-include-pinned", help="Include pinned messages."
        ),
    ] = None,
    pattern: Annotated[
        Optional[str], typer.Option("--pattern", help="Regex pattern filter.")
    ] = None,
    search_delay: Annotated[
        Optional[int],
        typer.Option(
            "--search-delay", help="Delay between search calls in milliseconds."
        ),
    ] = None,
    delete_delay: Annotated[
        Optional[int],
        typer.Option(
            "--delete-delay", help="Delay between delete calls in milliseconds."
        ),
    ] = None,
    config: Annotated[
        Optional[Path],
        typer.Option("--config", help="Path to JSON config file."),
    ] = None,
    dry_run: Annotated[
        Optional[bool],
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Simulate deletions without making API calls.",
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

        settings = _build_settings(cli_values, str(config) if config else None)
    except FileNotFoundError:
        console.print(f"[red]Config file not found:[/red] {config}")
        raise typer.Exit(code=1)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid JSON in config file:[/red] {exc}")
        raise typer.Exit(code=1)
    except ValidationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1)
    except ValueError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1)

    print_config(settings)

    if not yes:
        confirmed = typer.confirm("Proceed with message deletion?", default=False)
        if not confirmed:
            console.print("[yellow]Aborted by user before starting.[/yellow]")
            raise typer.Exit(code=0)

    try:
        with DiscordClient(settings.auth_token, dry_run=settings.dry_run) as client:
            deleted, failed, skipped = _delete_messages(client, settings)
    except KeyboardInterrupt:
        console.print("[yellow]Interrupted by user.[/yellow]")
        raise typer.Exit(code=130)

    print_summary(deleted, failed, skipped)


if __name__ == "__main__":
    app()
