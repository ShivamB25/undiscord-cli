from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from undiscord_cli.config import Settings

console = Console()


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        transient=False,
    )


def print_config(settings: Settings) -> None:
    token_suffix = (
        settings.auth_token[-6:]
        if len(settings.auth_token) >= 6
        else settings.auth_token
    )
    masked_token = (
        f"{'*' * max(len(settings.auth_token) - len(token_suffix), 4)}{token_suffix}"
    )

    table = Table(title="Undiscord Settings", show_header=True)
    table.add_column("Option", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("auth_token", masked_token)
    table.add_row("channel_id", settings.channel_id)
    table.add_row("guild_id", str(settings.guild_id))
    table.add_row("author_id", str(settings.author_id))
    table.add_row("content", str(settings.content))
    table.add_row("has_link", str(settings.has_link))
    table.add_row("has_file", str(settings.has_file))
    table.add_row("min_id", str(settings.min_id))
    table.add_row("max_id", str(settings.max_id))
    table.add_row("include_nsfw", str(settings.include_nsfw))
    table.add_row("include_pinned", str(settings.include_pinned))
    table.add_row("pattern", str(settings.pattern))
    table.add_row("search_delay", f"{settings.search_delay} ms")
    table.add_row("delete_delay", f"{settings.delete_delay} ms")
    table.add_row("dry_run", str(settings.dry_run))

    console.print(table)


def print_summary(deleted: int, failed: int, skipped: int) -> None:
    content = (
        f"[green]Deleted:[/green] {deleted}\n"
        f"[red]Failed:[/red] {failed}\n"
        f"[yellow]Skipped:[/yellow] {skipped}"
    )
    console.print(Panel.fit(content, title="Run Summary"))
