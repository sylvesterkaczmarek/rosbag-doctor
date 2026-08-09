.PHONY: install test lint demo smoke

install:
	python -m pip install -e '.[dev]'

test:
	pytest

lint:
	ruff check .

demo:
	rm -rf .demo-bag
	python examples/make_demo_bag.py .demo-bag
	rosbag-doctor .demo-bag --config examples/doctor.yaml || test $$? -eq 1

smoke:
	rm -rf .demo-bag .demo-report.json
	python examples/make_demo_bag.py .demo-bag
	rosbag-doctor .demo-bag --json .demo-report.json || test $$? -eq 1
	test -s .demo-report.json
