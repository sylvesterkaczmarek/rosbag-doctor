from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml
from conftest import make_sqlite_bag
from mcap.data_stream import RecordBuilder
from mcap.records import Channel, DataEnd, Footer, Header, Message, Schema
from mcap.writer import CompressionType, Writer

from rosbag_doctor.readers import BagReadError, read_bag


def _database(tmp_path: Path, timestamps=(100, 200)) -> Path:
    return make_sqlite_bag(tmp_path / "bag", {"/imu": ("pkg/msg/Imu", list(timestamps))}) / "bag_0.db3"


def _execute(path: Path, sql: str, parameters=()) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(sql, parameters)


def test_sqlite_orphaned_messages_cannot_disappear_from_report(tmp_path: Path):
    path = _database(tmp_path)
    _execute(path, "INSERT INTO messages(topic_id, timestamp, data) VALUES(99, 300, X'01')")
    with pytest.raises(BagReadError, match="message 3 references unknown topic ID 99"):
        read_bag(path)


@pytest.mark.parametrize("timestamp", [1.75, "bad timestamp", b"123", float("inf")])
def test_sqlite_timestamps_are_not_coerced(tmp_path: Path, timestamp):
    path = _database(tmp_path)
    _execute(path, "UPDATE messages SET timestamp = ? WHERE id = 1", (timestamp,))
    with pytest.raises(BagReadError, match="non-integer timestamp"):
        read_bag(path)


def test_sqlite_keeps_signed_timestamp_limits_and_recording_order(tmp_path: Path):
    path = _database(tmp_path)
    _execute(path, "UPDATE messages SET timestamp = ? WHERE id = 1", (2**63 - 1,))
    _execute(path, "UPDATE messages SET timestamp = ? WHERE id = 2", (-(2**63),))
    assert list(read_bag(path).topics["/imu"].timestamps_ns) == [2**63 - 1, -(2**63)]


@pytest.mark.parametrize("name", ["", b"/imu"])
def test_sqlite_invalid_topic_names_are_not_stringified(tmp_path: Path, name):
    path = _database(tmp_path)
    _execute(path, "UPDATE topics SET name = ?", (name,))
    with pytest.raises(BagReadError, match="no valid name"):
        read_bag(path)


@pytest.mark.parametrize("table", ["topics", "messages"])
def test_sqlite_duplicate_ids_are_rejected(tmp_path: Path, table):
    path = _database(tmp_path)
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE copy AS SELECT * FROM {table}")
        connection.execute(f"INSERT INTO copy SELECT * FROM {table}")
        connection.execute(f"DROP TABLE {table}")
        connection.execute(f"ALTER TABLE copy RENAME TO {table}")
    with pytest.raises(BagReadError, match="invalid or duplicate"):
        read_bag(path)


@pytest.mark.parametrize("field", ["relative_file_paths", "files", "topics_with_message_count"])
@pytest.mark.parametrize("value", [False, 0, ""])
def test_metadata_wrong_empty_types_are_rejected(tmp_path: Path, field: str, value):
    path = _database(tmp_path)
    info = {"storage_identifier": "sqlite3", field: value}
    (path.parent / "metadata.yaml").write_text(yaml.safe_dump(info), encoding="utf-8")
    with pytest.raises(BagReadError, match=field):
        read_bag(path.parent)


def test_invalid_metadata_encoding_has_read_error(tmp_path: Path):
    path = _database(tmp_path)
    (path.parent / "metadata.yaml").write_bytes(b"\xff\xfe\xff")
    with pytest.raises(BagReadError, match="Could not read metadata.yaml"):
        read_bag(path.parent)


def _raw_mcap(path: Path, records, *, end=True) -> Path:
    builder = RecordBuilder()
    Header(profile="", library="test").write(builder)
    for record in records:
        record.write(builder)
    if end:
        DataEnd(data_section_crc=0).write(builder)
    Footer(summary_start=0, summary_offset_start=0, summary_crc=0).write(builder)
    magic = b"\x89MCAP0\r\n"
    path.write_bytes(magic + builder.end() + magic)
    return path


def _schema(name="pkg/msg/Imu", *, schema_id=1) -> Schema:
    return Schema(id=schema_id, name=name, encoding="ros2msg", data=b"")


def _channel(topic="/imu", *, schema_id=1) -> Channel:
    return Channel(id=1, schema_id=schema_id, topic=topic, message_encoding="cdr", metadata={})


def _message(timestamp=100) -> Message:
    return Message(channel_id=1, sequence=0, log_time=timestamp, publish_time=timestamp, data=b"x")


def test_mcap_missing_schema_cannot_masquerade_as_schemaless(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_channel(), _message()])
    with pytest.raises(BagReadError, match="unknown schema 1"):
        read_bag(path)


@pytest.mark.parametrize("records,match", [
    ([_schema(), _schema("other/msg/Type"), _channel(), _message()], "schema 1"),
    ([_schema(), _channel(), _message(), _channel("/other"), _message()], "channel 1"),
])
def test_mcap_conflicting_repeated_definitions_are_rejected(tmp_path: Path, records, match):
    path = _raw_mcap(tmp_path / "bag.mcap", records)
    with pytest.raises(BagReadError, match=f"conflicting definitions of {match}"):
        read_bag(path)


def test_mcap_identical_repeated_definitions_remain_valid(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel(), _message(), _schema(), _channel()])
    bag = read_bag(path)
    assert bag.total_messages == 1
    assert bag.topics["/imu"].message_type == "pkg/msg/Imu"


def test_mcap_zero_schema_record_is_ignored_for_schemaless_channel(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(schema_id=0), _channel(schema_id=0), _message()])
    assert read_bag(path).topics["/imu"].message_type == "unknown"


def test_mcap_timestamps_above_supported_range_have_clear_error(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel(), _message(2**63)])
    with pytest.raises(BagReadError, match="signed 64-bit nanosecond range"):
        read_bag(path)


def test_mcap_trailing_content_is_not_ignored(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel(), _message()])
    with path.open("ab") as stream:
        stream.write(b"unexpected trailing data")
    with pytest.raises(BagReadError, match="trailing bytes"):
        read_bag(path)


def test_mcap_missing_data_end_is_rejected(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel(), _message()], end=False)
    with pytest.raises(BagReadError, match="no DataEnd"):
        read_bag(path)


def test_mcap_messages_after_data_end_are_rejected(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel(), DataEnd(0), _message()], end=False)
    with pytest.raises(BagReadError, match="message after the data section"):
        read_bag(path)


def test_mcap_summary_crc_is_checked(tmp_path: Path):
    path = tmp_path / "bag.mcap"
    with path.open("wb") as stream:
        writer = Writer(stream, compression=CompressionType.NONE, enable_crcs=True)
        writer.start()
        channel = writer.register_channel(schema_id=0, topic="/imu", message_encoding="cdr")
        writer.add_message(channel, log_time=100, publish_time=100, data=b"x")
        writer.finish()
    assert read_bag(path).total_messages == 1
    data = bytearray(path.read_bytes())
    data[-12] ^= 1  # Footer summary CRC, immediately before trailing magic.
    path.write_bytes(data)
    with pytest.raises(BagReadError, match="summary CRC"):
        read_bag(path)


@pytest.mark.parametrize("compression", list(CompressionType))
def test_mcap_compressed_chunks_keep_physical_message_order(tmp_path: Path, compression):
    path = tmp_path / "bag.mcap"
    with path.open("wb") as stream:
        writer = Writer(stream, compression=compression, chunk_size=1, enable_data_crcs=True)
        writer.start()
        channel = writer.register_channel(schema_id=0, topic="/imu", message_encoding="cdr")
        for timestamp in (300, 100, 200):
            writer.add_message(channel, log_time=timestamp, publish_time=timestamp, data=b"x")
        writer.finish()
    assert list(read_bag(path).topics["/imu"].timestamps_ns) == [300, 100, 200]


def test_mcap_empty_channel_remains_visible(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_schema(), _channel()])
    bag = read_bag(path)
    assert bag.total_messages == 0
    assert bag.topics["/imu"].message_type == "pkg/msg/Imu"


@pytest.mark.parametrize("value", [False, 0, [], ""])
def test_metadata_non_mapping_roots_are_rejected(tmp_path: Path, value):
    path = _database(tmp_path)
    (path.parent / "metadata.yaml").write_text(yaml.safe_dump(value), encoding="utf-8")
    with pytest.raises(BagReadError, match="root must be a mapping"):
        read_bag(path.parent)


@pytest.mark.parametrize("value", [False, 0, []])
def test_metadata_non_string_storage_identifiers_are_rejected(tmp_path: Path, value):
    path = _database(tmp_path)
    (path.parent / "metadata.yaml").write_text(yaml.safe_dump({"storage_identifier": value}), encoding="utf-8")
    with pytest.raises(BagReadError, match="storage_identifier must be a string"):
        read_bag(path.parent)


@pytest.mark.parametrize("use_summary_offsets", [False, True])
def test_mcap_with_no_summary_remains_readable(tmp_path: Path, use_summary_offsets):
    from mcap.writer import IndexType

    path = tmp_path / "bag.mcap"
    with path.open("wb") as stream:
        writer = Writer(
            stream, repeat_schemas=False, repeat_channels=False, use_statistics=False,
            use_summary_offsets=use_summary_offsets, index_types=IndexType.NONE,
        )
        writer.start()
        channel = writer.register_channel(schema_id=0, topic="/imu", message_encoding="cdr")
        writer.add_message(channel, log_time=100, publish_time=100, data=b"x")
        writer.finish()
    assert read_bag(path).total_messages == 1


def _chunk(records=(), *, data=None, compression="", size=None):
    from mcap.records import Chunk

    if data is None:
        builder = RecordBuilder()
        for record in records:
            record.write(builder)
        data = builder.end()
    return Chunk(
        compression=compression, data=data, message_start_time=100, message_end_time=100,
        uncompressed_crc=0, uncompressed_size=len(data) if size is None else size,
    )


def test_unknown_chunk_compression_cannot_be_read_as_uncompressed(tmp_path: Path):
    chunk = _chunk([_schema(), _channel(), _message()], compression="unsupported")
    path = _raw_mcap(tmp_path / "bag.mcap", [chunk])
    with pytest.raises(BagReadError, match="unsupported chunk compression"):
        read_bag(path)


@pytest.mark.parametrize("compression", list(CompressionType))
def test_wrong_uncompressed_chunk_size_is_rejected(tmp_path: Path, compression):
    import lz4.frame
    import zstandard

    chunk = _chunk([_schema(), _channel(), _message()])
    if compression == CompressionType.LZ4:
        chunk.data = lz4.frame.compress(chunk.data)
        chunk.compression = "lz4"
    elif compression == CompressionType.ZSTD:
        chunk.data = zstandard.compress(chunk.data)
        chunk.compression = "zstd"
    chunk.uncompressed_size += 1
    path = _raw_mcap(tmp_path / "bag.mcap", [chunk])
    with pytest.raises(BagReadError, match="uncompressed_size"):
        read_bag(path)


@pytest.mark.parametrize("record", [Header(profile="", library="test"), DataEnd(0)])
def test_chunk_cannot_hide_container_boundary_records(tmp_path: Path, record):
    path = _raw_mcap(tmp_path / "bag.mcap", [_chunk([record, _schema(), _channel(), _message()])])
    with pytest.raises(BagReadError, match="forbidden chunk record"):
        read_bag(path)


def test_chunk_record_length_cannot_extend_into_next_record(tmp_path: Path):
    import struct

    chunk = _chunk([_schema(), _channel(), _message()])
    chunk.data = bytes([3]) + struct.pack("<Q", len(chunk.data) + 1) + chunk.data[9:]
    path = _raw_mcap(tmp_path / "bag.mcap", [chunk])
    with pytest.raises(BagReadError, match="record extending beyond its chunk"):
        read_bag(path)


def test_chunk_field_length_cannot_read_past_record(tmp_path: Path):
    import struct

    # Schema declares a 99-byte body, but only one byte remains inside the record.
    payload = struct.pack("<HIII", 1, 0, 0, 99) + b"x"
    chunk = _chunk(data=bytes([3]) + struct.pack("<Q", len(payload)) + payload)
    path = _raw_mcap(tmp_path / "bag.mcap", [chunk])
    with pytest.raises(BagReadError, match="field extends beyond its record boundary"):
        read_bag(path)


def test_chunk_truncated_record_header_is_rejected(tmp_path: Path):
    path = _raw_mcap(tmp_path / "bag.mcap", [_chunk(data=b"\x03\x01")])
    with pytest.raises(BagReadError, match="truncated chunk record header"):
        read_bag(path)


@pytest.mark.parametrize("opcode", [0x10, 0x80])
def test_chunk_unknown_future_and_private_records_remain_skippable(tmp_path: Path, opcode):
    import struct

    chunk = _chunk([_schema(), _channel(), _message()])
    chunk.data = bytes([opcode]) + struct.pack("<Q", 3) + b"xyz" + chunk.data
    chunk.uncompressed_size = len(chunk.data)
    path = _raw_mcap(tmp_path / "bag.mcap", [chunk])
    assert read_bag(path).total_messages == 1


def test_chunk_schema_extension_fields_do_not_desynchronise_next_record(tmp_path: Path):
    import struct

    chunk = _chunk([_schema()])
    schema_record = chunk.data
    original_size = struct.unpack_from("<Q", schema_record, 1)[0]
    records = bytes([3]) + struct.pack("<Q", original_size + 3) + schema_record[9:] + b"new"
    records += _chunk([_channel(), _message()]).data
    path = _raw_mcap(tmp_path / "bag.mcap", [_chunk(data=records)])
    assert read_bag(path).total_messages == 1
