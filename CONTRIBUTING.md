# Contributing

Small, testable changes are preferred.

## Development setup

```bash
git clone https://github.com/sylvesterkaczmarek/rosbag-doctor.git
cd rosbag-doctor
python -m pip install -e '.[dev]'
pytest
```

## Before opening a pull request

Run:

```bash
pytest
ruff check .
make smoke
```

If a check changes, add or update a synthetic bag test that demonstrates the behavior. Do not commit real customer or field recordings unless they are intentionally public and appropriately licensed.

## Adding a check

1. Keep the check independent of ROS message deserialization unless payload access is essential.
2. Give failures a stable issue code.
3. Add a configuration field only when a user can reasonably know the expected value.
4. Test both passing and failing cases.
5. Document the metric in `docs/checks.md`.

## Adding a storage format

Readers should return topic names, message types when available, recorded timestamps, and source filenames through the internal `BagData` model. Keep payload loading out of the common timing path.
