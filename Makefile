.PHONY: test mypy check build clean install-dev \
        help tailwind-doctor tailwind-build tailwind-watch tailwind-check tailwind-clean \
        bench-fixture bench-export

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

# ---- Release engineering ------------------------------------------------
# PRD-v0.6.2 (Tailwind standalone CLI build pipeline).
# PRD-v0.6.4 (export-html perf gate).

TAILWIND_VERSION := v4.3.0
TAILWIND_BIN_DIR := .tailwind
TAILWIND_BIN     := $(TAILWIND_BIN_DIR)/tailwindcss

UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_S),Linux)
  ifeq ($(UNAME_M),x86_64)
    TAILWIND_ASSET := tailwindcss-linux-x64
  else ifeq ($(UNAME_M),aarch64)
    TAILWIND_ASSET := tailwindcss-linux-arm64
  else
    $(error Unsupported Linux arch $(UNAME_M))
  endif
else ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),arm64)
    TAILWIND_ASSET := tailwindcss-macos-arm64
  else
    TAILWIND_ASSET := tailwindcss-macos-x64
  endif
else
  $(error Unsupported OS $(UNAME_S))
endif

TAILWIND_URL := https://github.com/tailwindlabs/tailwindcss/releases/download/$(TAILWIND_VERSION)/$(TAILWIND_ASSET)

INPUT_CSS  := ulog/web/static/ulog/_tailwind-input.css
OUTPUT_CSS := ulog/web/static/ulog/tailwind.css
LIGHT_CSS  := ulog/web/static/ulog/ulog-light.css
DARK_CSS   := ulog/web/static/ulog/ulog-dark.css

BENCH_FIXTURE := tests/fixtures/bench_100k.sqlite

help:
	@echo "ulog Makefile targets:"
	@echo "  install-dev / test / mypy / check / build / clean   (existing)"
	@echo ""
	@echo "  tailwind-doctor   — probe host platform + binary URL"
	@echo "  tailwind-build    — build tailwind.css + theme bundles (PRD-v0.6.2)"
	@echo "  tailwind-watch    — rebuild on template save (dev)"
	@echo "  tailwind-check    — CI gate: fail if committed CSS drifts"
	@echo "  tailwind-clean    — drop the binary cache (.tailwind/)"
	@echo ""
	@echo "  bench-fixture     — seed tests/fixtures/bench_100k.sqlite (PRD-v0.6.4)"
	@echo "  bench-export      — run export-html benchmarks (median-of-5)"

tailwind-doctor:
	@echo "host: $(UNAME_S)/$(UNAME_M)"
	@echo "asset: $(TAILWIND_ASSET)"
	@echo "url: $(TAILWIND_URL)"
	@test -x $(TAILWIND_BIN) && echo "binary: cached" || echo "binary: not cached (run make tailwind-build)"

$(TAILWIND_BIN):
	@mkdir -p $(TAILWIND_BIN_DIR)
	@echo "→ downloading $(TAILWIND_ASSET) ($(TAILWIND_VERSION)) …"
	@curl -sSL -o $@ "$(TAILWIND_URL)"
	@chmod +x $@
	@echo "→ cached at $@"

tailwind-build: $(TAILWIND_BIN)
	@echo "→ building $(OUTPUT_CSS) (minified)"
	@$(TAILWIND_BIN) -i $(INPUT_CSS) -o $(OUTPUT_CSS) --minify
	@cp $(OUTPUT_CSS) $(LIGHT_CSS)
	@cp $(OUTPUT_CSS) $(DARK_CSS)
	@echo "→ $$(wc -c < $(OUTPUT_CSS) | awk '{printf "%.1f KB", $$1/1024}')"

tailwind-watch: $(TAILWIND_BIN)
	@$(TAILWIND_BIN) -i $(INPUT_CSS) -o $(OUTPUT_CSS) --watch

tailwind-check: $(TAILWIND_BIN)
	@$(TAILWIND_BIN) -i $(INPUT_CSS) -o /tmp/ulog-tailwind-fresh.css --minify 2>/dev/null
	@if ! diff -q /tmp/ulog-tailwind-fresh.css $(OUTPUT_CSS) >/dev/null 2>&1; then \
	  echo "::error::Tailwind bundle is stale. Run \`make tailwind-build\` and commit." ; \
	  diff /tmp/ulog-tailwind-fresh.css $(OUTPUT_CSS) | head -20 ; \
	  exit 1 ; \
	fi
	@echo "OK: $(OUTPUT_CSS) is in sync with templates."

tailwind-clean:
	rm -rf $(TAILWIND_BIN_DIR) $(OUTPUT_CSS) $(LIGHT_CSS) $(DARK_CSS)

bench-fixture: $(BENCH_FIXTURE)

$(BENCH_FIXTURE):
	@mkdir -p $$(dirname $(BENCH_FIXTURE))
	@.venv/bin/python scripts/seed_bench_fixture.py $(BENCH_FIXTURE)

bench-export: bench-fixture
	@.venv/bin/python -m pytest tests/bench_export_html.py -m slow \
	    --benchmark-only --benchmark-min-rounds=5 \
	    --benchmark-json=benchmark.json
