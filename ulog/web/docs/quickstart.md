# Quickstart

Five steps from "I'd like persistent logs" to "I'm debugging a user report in
the browser."

## 1. Install

```bash
pip install ulog[storage,web]
```

## 2. Configure your application

```python
import ulog
ulog.setup(
    handlers=['stream', 'sql'],
    sql_url='sqlite:///./logs.sqlite',
)
log = ulog.get_logger(__name__)
log.info("hello")
```

## 3. Run your code

Logs accumulate in `./logs.sqlite` (and on stderr, since we kept `stream`
in the handler list).

## 4. Open the inspection UI

```bash
ulog-web ./logs.sqlite
```

A browser tab opens on `http://127.0.0.1:<random-port>` with the filter
sidebar already populated.

## 5. Filter

- Tick **ERROR** in the **Level** sidebar to focus on what failed.
- Click a **Sector** to drill into one part of the codebase
  (e.g. `qlnes.audio.renderer`).
- Click a row to open the full detail view (JSON pretty-print + traceback).

That's it. No daemon to keep running, no auth wall to set up, no infra cost.
