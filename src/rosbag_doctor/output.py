from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .models import Report
from .readers import discover_bag_files


class OutputError(ValueError):
    pass


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
            Text(stat.name),
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
            sync_table.add_row(Text(item.name), Text(item.reference), _fmt(item.p95_offset_ms, 2, " ms"), _fmt(item.max_offset_ms, 2, " ms"))
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
        line = Text(symbol, style=style)
        line.append(f"{location}  {issue.message}")
        console.print(line)


def write_text_safely(
    content: str,
    destination: str | Path,
    *,
    bag_paths: Iterable[str | Path] = (),
    input_paths: Iterable[str | Path] = (),
) -> Path:
    """Replace a report atomically while protecting its recording and policy inputs."""
    path = Path(destination).expanduser()
    protected = [Path(item).expanduser() for item in input_paths]
    for bag_path in bag_paths:
        bag_path = Path(bag_path).expanduser()
        _storage, files, _metadata = discover_bag_files(bag_path)
        protected.extend(files)
        # Protect the sidecars even for a direct SQLite input. They may contain
        # committed data or describe the rest of a split recording.
        protected.append((bag_path if bag_path.is_dir() else bag_path.parent) / "metadata.yaml")
        for bag_file in files:
            if bag_file.suffix.lower() in {".db3", ".sqlite3"}:
                protected.extend(Path(f"{bag_file}{suffix}") for suffix in ("-wal", "-shm", "-journal"))
    try:
        resolved_path = path.resolve()
    except RuntimeError as exc:  # Path.resolve raises this for symlink loops on Python < 3.13.
        raise OutputError(f"Could not resolve output path: {path}") from exc
    for source in protected:
        if resolved_path == source.resolve() or (
            path.exists() and source.exists() and path.samefile(source)
        ):
            raise OutputError(f"Output would overwrite an input file: {source}")

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def write_json(
    data: dict[str, Any], destination: str | Path, *,
    bag_paths: Iterable[str | Path] = (), input_paths: Iterable[str | Path] = (),
) -> Path:
    content = json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return write_text_safely(content, destination, bag_paths=bag_paths, input_paths=input_paths)


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, allow_nan=False))
