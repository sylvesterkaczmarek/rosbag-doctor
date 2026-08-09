from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from .models import BagData


class BagReadError(RuntimeError):
    pass


def _natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def _load_metadata(directory: Path) -> dict[str, Any] | None:
    metadata_path = directory / "metadata.yaml"
    if not metadata_path.exists():
        return None
    try:
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise BagReadError(f"Could not read metadata.yaml: {exc}") from exc
    if not isinstance(metadata, dict):
        raise BagReadError("metadata.yaml root must be a mapping")
    info = metadata.get("rosbag2_bagfile_information", metadata)
    if not isinstance(info, dict):
        raise BagReadError("metadata.yaml rosbag2_bagfile_information must be a mapping")
    return info


def _safe_metadata_files(directory: Path, info: dict[str, Any]) -> list[Path]:
    relative = info.get("relative_file_paths") or []
    if not isinstance(relative, list) or not all(isinstance(item, str) for item in relative):
        raise BagReadError("metadata.yaml relative_file_paths must be a list of strings")

    if not relative:
        file_info = info.get("files") or []
        if not isinstance(file_info, list):
            raise BagReadError("metadata.yaml files must be a list")
        extracted: list[str] = []
        for index, item in enumerate(file_info):
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise BagReadError(f"metadata.yaml files[{index}].path must be a string")
            extracted.append(item["path"])
        relative = extracted

    root = directory.resolve()
    files: list[Path] = []
    for entry in relative:
        if not entry:
            raise BagReadError("metadata.yaml contains an empty relative_file_paths entry")
        raw = Path(entry)
        if raw.is_absolute():
            raise BagReadError(f"metadata.yaml file path must be relative: {entry}")
        resolved = (root / raw).resolve()
        if not resolved.is_relative_to(root):
            raise BagReadError(f"metadata.yaml file path escapes the bag directory: {entry}")
        if not resolved.exists():
            raise BagReadError(f"metadata.yaml references a missing bag file: {entry}")
        if not resolved.is_file():
            raise BagReadError(f"metadata.yaml bag path is not a file: {entry}")
        if resolved in files:
            raise BagReadError(f"metadata.yaml lists the same bag file more than once: {entry}")
        files.append(resolved)
    return files


def _metadata_topic_entries(info: dict[str, Any]) -> list[tuple[str, str, int | None]]:
    raw_entries = info.get("topics_with_message_count") or []
    if not isinstance(raw_entries, list):
        raise BagReadError("metadata.yaml topics_with_message_count must be a list")

    entries: list[tuple[str, str, int | None]] = []
    for index, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise BagReadError(f"metadata.yaml topics_with_message_count[{index}] must be a mapping")
        topic_meta = raw.get("topic_metadata") or {}
        if not isinstance(topic_meta, dict):
            raise BagReadError(
                f"metadata.yaml topics_with_message_count[{index}].topic_metadata must be a mapping"
            )
        name = topic_meta.get("name")
        if not isinstance(name, str) or not name:
            raise BagReadError(f"metadata.yaml topic entry {index} has no valid name")
        message_type = topic_meta.get("type") or "unknown"
        if not isinstance(message_type, str):
            message_type = "unknown"
        message_count = raw.get("message_count")
        if message_count is not None:
            if isinstance(message_count, bool) or not isinstance(message_count, int) or message_count < 0:
                raise BagReadError(f"metadata.yaml topic '{name}' has an invalid message_count")
        entries.append((name, message_type, message_count))
    return entries


def discover_bag_files(path: Path) -> tuple[str, list[Path], dict[str, Any] | None]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise BagReadError(f"Bag path does not exist: {path}")

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in {".db3", ".sqlite3"}:
            return "sqlite3", [path], None
        if suffix == ".mcap":
            return "mcap", [path], None
        raise BagReadError(f"Unsupported bag file: {path.name}. Expected .db3, .sqlite3, or .mcap")

    info = _load_metadata(path)
    metadata_storage = ""
    if info is not None:
        storage_raw = info.get("storage_identifier") or ""
        if not isinstance(storage_raw, str):
            raise BagReadError("metadata.yaml storage_identifier must be a string")
        metadata_storage = storage_raw.lower()
        if metadata_storage and metadata_storage not in {"sqlite3", "mcap"}:
            raise BagReadError(f"Unsupported storage_identifier in metadata.yaml: {storage_raw}")

        metadata_files = _safe_metadata_files(path, info)
        if metadata_files:
            storage = metadata_storage
            suffixes = {item.suffix.lower() for item in metadata_files}
            inferred: str | None = None
            if suffixes <= {".db3", ".sqlite3"}:
                inferred = "sqlite3"
            elif suffixes == {".mcap"}:
                inferred = "mcap"
            else:
                compression_mode = str(info.get("compression_mode") or "").lower()
                if compression_mode == "file":
                    raise BagReadError(
                        "File-compressed rosbag2 bags are not supported; decompress the bag files first"
                    )
                raise BagReadError("metadata.yaml references mixed or unsupported bag file formats")
            if storage and storage != inferred:
                raise BagReadError(
                    f"metadata.yaml storage_identifier '{storage}' does not match referenced {inferred} files"
                )
            return storage or inferred, metadata_files, info

    db_files = sorted([*path.glob("*.db3"), *path.glob("*.sqlite3")], key=_natural_key)
    mcap_files = sorted(path.glob("*.mcap"), key=_natural_key)
    if db_files and mcap_files:
        raise BagReadError(
            "Directory contains both SQLite3 and MCAP files but metadata.yaml does not identify one storage format"
        )
    if db_files:
        if metadata_storage and metadata_storage != "sqlite3":
            raise BagReadError(
                f"metadata.yaml storage_identifier '{metadata_storage}' does not match discovered sqlite3 files"
            )
        return "sqlite3", db_files, info
    if mcap_files:
        if metadata_storage and metadata_storage != "mcap":
            raise BagReadError(
                f"metadata.yaml storage_identifier '{metadata_storage}' does not match discovered mcap files"
            )
        return "mcap", mcap_files, info
    raise BagReadError(f"No supported rosbag2 files found in {path}")


def _open_sqlite_read_only(path: Path) -> sqlite3.Connection:
    # Path.as_uri() percent-encodes URI metacharacters such as '?' and '#'.
    uri = f"{path.resolve().as_uri()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BagReadError(f"Could not open SQLite bag {path.name}: {exc}") from exc


def _read_sqlite_file(bag: BagData, path: Path, batch_size: int = 100_000) -> None:
    connection = _open_sqlite_read_only(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"messages", "topics"}.issubset(tables):
            raise BagReadError(f"{path.name} does not contain rosbag2 'messages' and 'topics' tables")

        # Register every topic before reading messages so zero-message topics remain visible.
        for name, message_type in connection.execute("SELECT name, type FROM topics ORDER BY id"):
            bag.get_or_create_topic(str(name), str(message_type or "unknown"))

        cursor = connection.execute(
            """
            SELECT t.name, t.type, m.timestamp
            FROM messages AS m
            JOIN topics AS t ON m.topic_id = t.id
            ORDER BY m.id
            """
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for name, message_type, timestamp in rows:
                bag.get_or_create_topic(str(name), str(message_type or "unknown")).add(
                    int(timestamp), path.name, str(message_type or "unknown")
                )
    except sqlite3.Error as exc:
        raise BagReadError(f"Could not read SQLite bag {path.name}: {exc}") from exc
    finally:
        connection.close()


def _read_mcap_file(bag: BagData, path: Path) -> None:
    try:
        from mcap.records import Channel, Message, Schema
        from mcap.stream_reader import StreamReader
    except ImportError as exc:
        raise BagReadError("MCAP support requires the 'mcap' Python package") from exc

    schemas: dict[int, Any] = {}
    channels: dict[int, Any] = {}
    try:
        with path.open("rb") as stream:
            reader = StreamReader(stream, validate_crcs=True)
            for record in reader.records:
                if isinstance(record, Schema):
                    schemas[record.id] = record
                elif isinstance(record, Channel):
                    channels[record.id] = record
                elif isinstance(record, Message):
                    channel = channels.get(record.channel_id)
                    if channel is None:
                        raise BagReadError(
                            f"MCAP message in {path.name} references unknown channel {record.channel_id}"
                        )
                    schema = schemas.get(channel.schema_id)
                    message_type = (
                        schema.name
                        if schema is not None and getattr(schema, "name", None)
                        else "unknown"
                    )
                    bag.get_or_create_topic(channel.topic, message_type).add(
                        int(record.log_time), path.name, message_type
                    )

        # Channels with no messages should still be represented when the file declares them.
        for channel in channels.values():
            schema = schemas.get(channel.schema_id)
            message_type = (
                schema.name
                if schema is not None and getattr(schema, "name", None)
                else "unknown"
            )
            bag.get_or_create_topic(channel.topic, message_type)
    except BagReadError:
        raise
    except Exception as exc:  # mcap exposes several format-specific exception types
        raise BagReadError(f"Could not read MCAP bag {path.name}: {exc}") from exc


def _apply_metadata(bag: BagData, info: dict[str, Any] | None) -> None:
    if info is None:
        return

    total = info.get("message_count")
    if total is not None:
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise BagReadError("metadata.yaml message_count must be a non-negative integer")
        bag.metadata_total_messages = total

    topic_entries = _metadata_topic_entries(info)
    seen_topics: set[str] = set()
    for name, message_type, count in topic_entries:
        if name in seen_topics:
            raise BagReadError(f"metadata.yaml contains duplicate topic entries for: {name}")
        seen_topics.add(name)
        bag.get_or_create_topic(name, message_type)
        if count is not None:
            bag.metadata_topic_counts[name] = count

    if bag.metadata_total_messages is not None and topic_entries and all(
        count is not None for _name, _message_type, count in topic_entries
    ):
        topic_total = sum(int(count) for _name, _message_type, count in topic_entries if count is not None)
        if topic_total != bag.metadata_total_messages:
            raise BagReadError(
                "metadata.yaml message_count does not equal the sum of topics_with_message_count"
            )


def read_bag(path: str | Path) -> BagData:
    bag_path = Path(path)
    storage, files, metadata = discover_bag_files(bag_path)
    bag = BagData(path=bag_path.expanduser().resolve(), storage=storage, files=files)
    _apply_metadata(bag, metadata)

    for file_path in files:
        if storage == "sqlite3":
            _read_sqlite_file(bag, file_path)
        elif storage == "mcap":
            _read_mcap_file(bag, file_path)
        else:
            raise BagReadError(f"Unsupported storage identifier: {storage}")

    if not bag.topics:
        bag.reader_warnings.append("Bag contains no topics")
    return bag
