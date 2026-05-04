"""ULog v0.2 web inspection UI (Django + Tailwind).

Run via the `ulog-web` console-script:

    ulog-web /path/to/logs.sqlite     # auto-detects sqlite/jsonl/csv
    ulog-web --port 8080 ./logs.jsonl

The Django project root is `ulog.web`; the single app is
`ulog.web.viewer`. Settings + URL routes are minimal — this is a
read-only inspection UI, not a CRUD app.
"""
