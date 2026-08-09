from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from .models import Report


def _fmt(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}{suffix}"


def print_report(report: Report, console: Console | None = None) -> None:
    console = console or Console()
    status_style = {"pass": "bold green", "warn": "bold yellow", "fail": "bold red"}[report.status]
    console.print(f"[bold]ROSBag Doctor[/bold]  [{status_style}]{report.status.upper()}[/{status_style}]")
    console.print(
        f"{report.storage} · {len(report.files)} file(s) · {report.total_messages:,} messages · {report.bag_duration_s:.2f} s"
    )
    console.print()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Topic")
    table.add_column("Messages", justify="right")
    table.add_column("Rate", justify="right")
    table.add_column("Max gap", justify="right")
    table.add_column("p95 jitter", justify="right")
    table.add_column("Coverage", justify="right")
    for stat in report.topics:
        table.add_row(
            stat.name,
            f"{stat.count:,}",
            _fmt(stat.effective_rate_hz, 2, " Hz"),
            _fmt(stat.max_gap_ms, 1, " ms"),
            _fmt(stat.p95_jitter_ms, 1, " ms"),
            _fmt(stat.coverage * 100 if stat.coverage is not None else None, 1, "%"),
        )
    console.print(table)

    if report.sync:
        console.print()
        sync_table = Table(title="Sensor sync", show_header=True, header_style="bold")
        sync_table.add_column("Check")
        sync_table.add_column("Reference")
        sync_table.add_column("p95 offset", justify="right")
        sync_table.add_column("Max offset", justify="right")
        for item in report.sync:
            sync_table.add_row(item.name, item.reference, _fmt(item.p95_offset_ms, 2, " ms"), _fmt(item.max_offset_ms, 2, " ms"))
        console.print(sync_table)

    console.print()
    if not report.issues:
        console.print("[green]✓ No problems found[/green]")
        return
    errors = sum(issue.severity == "error" for issue in report.issues)
    warnings = sum(issue.severity == "warning" for issue in report.issues)
    console.print(f"[bold]{errors} error(s), {warnings} warning(s)[/bold]")
    for issue in report.issues:
        symbol = "✗" if issue.severity == "error" else "⚠"
        style = "red" if issue.severity == "error" else "yellow"
        location = f" {issue.topic}" if issue.topic else ""
        console.print(f"[{style}]{symbol}[/{style}]{location}  {issue.message}")


def write_json(data: dict[str, Any], destination: str | Path) -> Path:
    path = Path(destination)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))
