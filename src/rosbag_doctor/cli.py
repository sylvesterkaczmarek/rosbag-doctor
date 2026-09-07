from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__
from .baseline import write_baseline
from .compare import compare_bags
from .config import ConfigError
from .doctor import inspect_bag
from .output import OutputError, print_json, print_report, write_json
from .readers import BagReadError

VERSION = __version__


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rosbag-doctor", add_help=True)
    parser.add_argument("bag", help="ROS 2 bag directory, .db3/.sqlite3 file, or .mcap file")
    parser.add_argument("-c", "--config", help="YAML health policy")
    parser.add_argument("--json", dest="json_path", help="Write machine-readable JSON report")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="stdout format")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    return parser


def _baseline_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rosbag-doctor baseline")
    parser.add_argument("bag")
    parser.add_argument("-o", "--output", default="rosbag-doctor.yaml")
    parser.add_argument("--rate-tolerance", type=float, default=0.15)
    parser.add_argument("--gap-multiplier", type=float, default=1.5)
    return parser


def _compare_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rosbag-doctor compare")
    parser.add_argument("base")
    parser.add_argument("candidate")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--json", dest="json_path")
    return parser


def _print_help() -> None:
    parser = _check_parser()
    parser.description = "Check ROS 2 recordings for timing, rate, gap, coverage and sync problems."
    parser.epilog = (
        "Other commands: rosbag-doctor baseline BAG [options]; "
        "rosbag-doctor compare BASE CANDIDATE [options]. "
        "Run each command with --help for details. Use --version to show the version."
    )
    parser.print_help()


def _print_compare(data: dict) -> None:
    console = Console()
    console.print("[bold]ROSBag Doctor compare[/bold]")
    console.print(f"base: {data['base']}", markup=False)
    console.print(f"candidate: {data['candidate']}", markup=False)
    for label in ("base", "candidate"):
        health = data[f"{label}_health"]
        console.print(f"{label} health: {health['status'].upper()}", markup=False)
        for issue in health["issues"]:
            location = f" {issue['topic']}" if issue["topic"] else ""
            console.print(
                f"  {issue['severity']}{location}: {issue['message']}", markup=False,
            )
    console.print()
    table = Table(show_header=True, header_style="bold")
    table.add_column("Topic")
    table.add_column("State")
    table.add_column("Rate before", justify="right")
    table.add_column("Rate after", justify="right")
    table.add_column("Rate Δ", justify="right")
    table.add_column("Gap before", justify="right")
    table.add_column("Gap after", justify="right")

    def fmt(value, suffix=""):
        return "-" if value is None else f"{value:.2f}{suffix}"

    for row in data["topics"]:
        table.add_row(
            Text(row["topic"]),
            "type changed" if row.get("type_changed") else row["state"],
            fmt(row["base_rate_hz"], " Hz"),
            fmt(row["candidate_rate_hz"], " Hz"),
            fmt(row["rate_change_pct"], "%"),
            fmt(row["base_max_gap_ms"], " ms"),
            fmt(row["candidate_max_gap_ms"], " ms"),
        )
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _print_help()
        return 2
    if argv[0] in {"--version", "-V"}:
        print(VERSION)
        return 0
    if argv[0] in {"--help", "-h"}:
        _print_help()
        return 0

    try:
        if argv[0] == "baseline":
            args = _baseline_parser().parse_args(argv[1:])
            output = write_baseline(
                args.bag,
                args.output,
                rate_tolerance=args.rate_tolerance,
                gap_multiplier=args.gap_multiplier,
            )
            print(f"Wrote {output}")
            return 0

        if argv[0] == "compare":
            args = _compare_parser().parse_args(argv[1:])
            data = compare_bags(args.base, args.candidate)
            if args.json_path:
                write_json(data, args.json_path, bag_paths=[args.base, args.candidate])
            if args.format == "json":
                print_json(data)
            else:
                _print_compare(data)
            return 0

        args = _check_parser().parse_args(argv)
        report = inspect_bag(args.bag, args.config, strict=args.strict)
        data = report.to_dict()
        if args.json_path:
            write_json(
                data, args.json_path, bag_paths=[args.bag],
                input_paths=[args.config] if args.config else [],
            )
        if args.format == "json":
            print_json(data)
        else:
            print_report(report)
        return 0 if report.status in {"pass", "warn"} else 1
    except (BagReadError, ConfigError, OutputError, OSError) as exc:
        Console(stderr=True).print(Text(f"error: {exc}", style="red"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
