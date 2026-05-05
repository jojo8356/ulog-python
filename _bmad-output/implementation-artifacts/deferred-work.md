# Deferred Work

This file tracks findings from BMAD code reviews that are real but not actionable in their originating story. Each entry should be re-evaluated when its scope context arrives (the next story touching the file/area, or a dedicated tech-debt cleanup story).

---

## Deferred from: code review of story 1-1-pytest-plugin-entry-point-registration (2026-05-05)

- **`_isolate_logging` fixture hardcoded logger names brittle for Story 1.2+** — `tests/test_pytest_plugin.py:36` (and the mirrored `tests/test_setup.py:17`) iterate over a hardcoded list `(None, "test", "test.sub", "myapp", "qlnes")`. Any test in Stories 1.2-1.5 that calls `ulog.setup(name='<other-name>')` will leak `_ulog_managed` handlers across tests, silently corrupting later test state. Robust alternative: walk `logging.root.manager.loggerDict` to find all loggers carrying `_ulog_managed=True` handlers and clean them generically. Either absorb into Story 1.2 when it adds new logger names, or carve a dedicated tech-debt story.
