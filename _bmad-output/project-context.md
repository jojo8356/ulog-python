---
project_name: 'ulog-python'
user_name: 'Jojokes'
date: '2026-05-05'
sections_completed: ['technology_stack']
existing_patterns_found: 12
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- **Language:** Python `>=3.10` (CI matrix targets 3.10 / 3.11 / 3.12 / 3.13).
- **Build:** `setuptools>=68.0` (`pyproject.toml` only — no `setup.py` shim). `tool.setuptools.packages.find` is constrained to `include = ["ulog*"]` and excludes `tests*` + `vendor*` so the `vendor/ucolor-python/` submodule is never auto-picked as a sibling top-level package.
- **Runtime deps:** ZERO on PyPI for the core. ucolor lives under `vendor/ucolor-python/` as a **git submodule** — installed locally via `pip install -e ./vendor/ucolor-python`. Without ucolor, ULog falls back to an 8-color ANSI palette gracefully.
- **Optional extras** (`pyproject.toml`):
  - `[dev]` → `pytest>=7.0`, `mypy>=1.0`
  - `[storage]` → `sqlalchemy>=2.0`
  - `[web]` → `django>=5.0`, `sqlalchemy>=2.0`, `django-lucide>=1.3`
- **Console scripts:** `ulog-web = ulog.web.cli:main`.
- **Type checking:** `mypy --strict` (`tool.mypy.strict = true`).
- **Tests:** pytest, `testpaths = ["tests"]`.
- **Frontend (web extra):** Tailwind via CDN in v0.2 prototype (`<script src="https://cdn.tailwindcss.com">`); planned migration to Tailwind standalone CLI shipping `ulog/web/static/ulog/tailwind.css` — see PRD-v0.2 §3.5.
- **Local dev launcher:** `run.sh` (subcommands: `setup`, `prod`, `test`, `dev`, `demo`, `clean`). `Makefile` targets: `install-dev`, `test`, `mypy`, `check`, `build`, `clean`.
- **Profile DBs:** `~/.cache/ulog/<profile>.sqlite` (XDG-aware via `XDG_CACHE_HOME`). Profiles: `prod`, `test`. `auto` resolves to `test` when pytest is running, else `prod`.

## Critical Implementation Rules

_Documented after discovery phase — to be filled with your input in step-02._
