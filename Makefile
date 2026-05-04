.PHONY: test mypy check build clean install-dev

install-dev:
	python3 -m pip install -e ".[dev]"

test:
	python3 -m pytest tests/ -v

mypy:
	python3 -m mypy ulog/

check: mypy test

build:
	python3 -m build

clean:
	rm -rf build/ dist/ *.egg-info ulog/__pycache__ tests/__pycache__ .mypy_cache .pytest_cache
