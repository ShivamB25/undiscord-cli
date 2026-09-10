from __future__ import annotations

from datetime import timedelta

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from undiscord_cli.config import Settings

console = Console()


def _literal(value: object) -> Text:
    return Text(str(value))


class _CountColumn(ProgressColumn):
    def __init__(self, field_name: str, style: str, label: str) -> None:
        super().__init__()
        self._field_name = field_name
        self._style = style
        self._label = label

    def render(self, task: Task) -> Text:
        value = int(task.fields.get(self._field_name, 0))
        return Text(f"{self._label}:{value}", style=self._style)


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        _CountColumn("deleted", "green", "del"),
        _CountColumn("failed", "red", "fail"),
        _CountColumn("skipped", "yellow", "skip"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True,
        transient=False,
    )


def print_config(settings: Settings) -> None:
    masked_token = "********"

    table = Table(title="Undiscord Settings", show_header=True)
    table.add_column("Group", style="cyan", no_wrap=True)
    table.add_column("Option", style="bright_cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Auth", "auth_token", _literal(masked_token))
    table.add_row("Target", "channel_id", _literal(settings.channel_id))
    table.add_row("Target", "guild_id", _literal(settings.guild_id or "auto-detect"))
    table.add_row("Filter", "author_id", _literal(settings.author_id))
    table.add_row("Filter", "content", _literal(settings.content))
    table.add_row("Filter", "has_link", _literal(settings.has_link))
    table.add_row("Filter", "has_file", _literal(settings.has_file))
    table.add_row("Filter", "min_id", _literal(settings.min_id))
    table.add_row("Filter", "max_id", _literal(settings.max_id))
    table.add_row("Filter", "include_nsfw", _literal(settings.include_nsfw))
    table.add_row("Filter", "include_pinned", _literal(settings.include_pinned))
    table.add_row("Filter", "pattern", _literal(settings.pattern))
    table.add_row("Timing", "search_delay", _literal(f"{settings.search_delay} ms"))
    table.add_row("Timing", "delete_delay", _literal(f"{settings.delete_delay} ms"))
    table.add_row("Mode", "dry_run", _literal(settings.dry_run))

    console.print(table)
    if settings.dry_run:
        console.print(
            Panel.fit(
                "[yellow]Dry-run mode enabled:[/yellow] no messages will be deleted.",
                title="Safety",
                border_style="yellow",
            )
        )


def print_summary(
    deleted: int, failed: int, skipped: int, runtime_seconds: float
) -> None:
    total = deleted + failed + skipped
    success_rate = (deleted / total * 100.0) if total else 0.0
    throughput = (total / runtime_seconds) if runtime_seconds > 0 else 0.0
    runtime = str(timedelta(seconds=int(runtime_seconds)))

    content = (
        f"[green]Deleted:[/green] {deleted}\n"
        f"[red]Failed:[/red] {failed}\n"
        f"[yellow]Skipped:[/yellow] {skipped}\n"
        f"[cyan]Processed:[/cyan] {total}\n"
        f"[cyan]Success rate:[/cyan] {success_rate:.1f}%\n"
        f"[cyan]Runtime:[/cyan] {runtime}\n"
        f"[cyan]Throughput:[/cyan] {throughput:.1f} msg/s"
    )
    console.print(Panel.fit(content, title="Run Summary"))
