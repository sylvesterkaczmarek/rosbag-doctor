from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import yaml

from .models import BagData


class BagReadError(RuntimeError):
    pass


def _natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def _metadata_files(directory: Path) -> tuple[str | None, list[Path]]:
    metadata_path = directory / "metadata.yaml"
    if not metadata_path.exists():
        return None, []
    try:
        metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise BagReadError(f"Could not read metadata.yaml: {exc}") from exc

    info = metadata.get("rosbag2_bagfile_information", metadata)
    storage = info.get("storage_identifier")
    relative = info.get("relative_file_paths") or []
    files = [(directory / item).resolve() for item in relative if isinstance(item, str)]
    return storage, files


def discover_bag_files(path: Path) -> tuple[str, list[Path]]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise BagReadError(f"Bag path does not exist: {path}")

    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in {".db3", ".sqlite3"}:
            return "sqlite3", [path]
        if suffix == ".mcap":
            return "mcap", [path]
        raise BagReadError(f"Unsupported bag file: {path.name}. Expected .db3, .sqlite3, or .mcap")

    metadata_storage, metadata_files = _metadata_files(path)
    existing_metadata_files = [item for item in metadata_files if item.exists()]
    if existing_metadata_files:
        storage = (metadata_storage or "").lower()
        if storage in {"sqlite3", "mcap"}:
            return storage, existing_metadata_files
        suffixes = {item.suffix.lower() for item in existing_metadata_files}
        if suffixes <= {".db3", ".sqlite3"}:
            return "sqlite3", existing_metadata_files
        if suffixes == {".mcap"}:
            return "mcap", existing_metadata_files

    db_files = sorted([*path.glob("*.db3"), *path.glob("*.sqlite3")], key=_natural_key)
    mcap_files = sorted(path.glob("*.mcap"), key=_natural_key)
    if db_files and mcap_files:
        raise BagReadError(
            "Directory contains both SQLite2 and MCAP files but metadata.yaml does not identify one storage format"
        )
    if db_files:
        return "sqlite3", db_files
    if mcap_files:
        return "mcap", mcap_files
    raise BagReadError(f"No supported rosbag2 files found in {path}")


def _read_sqlite_file(bag: BagData, path: Path, batch_size: int = 100_000) -> None:
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BagReadError(f"Could not open SQLite bag {path.name}: {exc}") from exc

    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"messages", "topics"}.issubset(tables):
            raise BagReadError(f"{path.name} does not contain rosbag2 'messages' and 'topics' tables")
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
        from mcap.reader import make_reader
    except ImportError as exc:
        raise BagReadError("MCAP support requires the 'mcap' Python package") from exc

    try:
        with path.open("rb") as stream:
            reader = make_reader(stream)
            for schema, channel, message in reader.iter_messages(log_time_order=False):
                message_type = schema.name if schema is not None and schema.name else channel.message_encoding or "unknown"
                bag.get_or_create_topic(channel.topic, message_type).add(
                    int(message.log_time), path.name, message_type
                )
    except Exception as exc:  # mcap exposes several format-specific exception types
        raise BagReadError(f"Could not read MCAP bag {path.name}: {exc}") from exc


def read_bag(path: str | Path) -> BagData:
    bag_path = Path(path)
    storage, files = discover_bag_files(bag_path)
    bag = BagData(path=bag_path.expanduser().resolve(), storage=storage, files=files)
    for file_path in files:
        if storage == "sqlite3":
            _read_sqlite_file(bag, file_path)
        elif storage == "mcap":
            _read_mcap_file(bag, file_path)
        else:
            raise BagReadError(f"Unsupported storage identifier: {storage}")
    if not bag.topics:
        bag.reader_warnings.append("Bag contains no messages")
    return bag
