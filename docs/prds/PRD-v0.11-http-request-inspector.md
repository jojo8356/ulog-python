---
docType: prd
project_name: ulog-python
version: 0.11.0
date: 2026-05-12
author: jojo8356
status: draft v1
parent_prd: PRD-v0.2-storage-and-ui.md
related_prd:
  - PRD-v0.10-fleet-dashboard.md
---

# ULog v0.11 — HTTP request inspector

> When a record's context carries HTTP-shaped data (`method`, `url`,
> `status_code`, `body`, `headers`), the viewer auto-detects it and
> renders a **dedicated HTTP panel** in the detail view: src URL,
> dest URL, request method, JSON body (pretty-printed, syntax-
> highlighted), response status, response body, latency, error code
> if any. No instrumentation change — if your code already logs HTTP
> calls with the v0.11 convention keys, the viewer just renders them
> nicer.

---

## 0. 30-second pitch

Debugging a failed API call today:

1. `grep` for the request in the logs.
2. Find a record like `log.error("HTTP 500", extra={"method": "POST", "url": "...", "body": {...}})`.
3. The context column shows a 200-char one-line JSON dump.
4. Copy it out, paste into a JSON formatter, **then** read it.

v0.11 collapses this to: **click the record → HTTP panel renders**
with method+url at the top, pretty-printed JSON body + headers (with
sensitive ones masked), status code with semantic color (2xx green,
4xx amber, 5xx red), latency, and a "curl this request" copy button.

Auto-detection is structural — any record whose context contains
`method` + `url` is treated as HTTP. No new logger import, no
configuration, no schema change.

---

## 1. Vision

### 1.1 Why this exists

Three observations from logs-with-HTTP scrutiny:

1. **API calls are the most common debugging axis after stack traces.** When something goes wrong in a microservice mesh, the question is "what did service A send to service B, and what came back?". Currently this lives in `context` JSON, rendered as a single line.
2. **The decoupling pattern is already standard.** Engineers log `extra={"method": ..., "url": ..., "status_code": ...}` because it's the natural shape. v0.11 just rewards that pattern with a better viewer experience.
3. **`curl` reconstruction is the universal debugging move.** Once you have method + url + headers + body, the next 30 seconds are "reproduce with curl". Putting a "Copy as curl" button on the record skips a manual step that every engineer does.

### 1.2 What v0.11 isn't

- **Not an HTTP instrumentation library.** v0.11 does NOT auto-hook `requests` / `httpx` / `aiohttp`. The user's code logs HTTP calls explicitly via `log.info("...", extra={"method": ..., "url": ...})`. v0.11 detects the shape and renders nicely.
- **Not a request replay tool.** "Copy as curl" puts the curl invocation on your clipboard; running it is your job. No in-viewer "replay this request" button (security + side-effects nightmare).
- **Not a man-in-the-middle proxy.** No `ulog-proxy` HTTP server intercepting traffic. Logs in, render out.
- **Not a tracing library.** Spans / trace IDs / W3C `traceparent` propagation are v0.5 / future work. v0.11 is per-record HTTP rendering.

### 1.3 Target users

- **Sara** (carried, library dev) — her library calls 3 upstream APIs; debugging integration tests means scanning HTTP records. v0.11 turns each into a readable panel.
- **Marco** (carried, solo dev) — his Flask app logs every inbound request. v0.11 makes "show me the failed POSTs" a 1-click filter.
- **Maria** (new from v0.10, SRE) — needs to find "the slow request" or "the 500 that started the cascade". v0.11's status + latency rendering is her primary axis.
- **NEW: Adrien**, security engineer auditing a CVE — needs the **header-masking** feature: sensitive headers (`Authorization`, `Cookie`, `X-Api-Key`) render as `Bearer ***` so log dumps in tickets don't leak secrets.

### 1.4 Success criteria

| ID | Metric | Target |
|---|---|---|
| SC1 | A record with `method`+`url` in context auto-renders as HTTP, with src/dest URL + method badge + status code semantic color | yes |
| SC2 | JSON request body pretty-printed with 2-space indent + syntax highlight (Prism.js from v0.8.1) | yes |
| SC3 | Sensitive headers (`Authorization`, `Cookie`, `X-Api-Key`, `X-Auth-Token`, configurable) masked as `<value-elided>` | yes |
| SC4 | "Copy as curl" button writes a valid curl command to the clipboard | yes (verified in test_qa_http_inspector_e2e.py) |
| SC5 | Records list gains an HTTP filter axis: method (GET/POST/...), status range (2xx/4xx/5xx) | yes |
| SC6 | Records list visually distinguishes HTTP records (small `🌐` icon next to msg + truncated url) | yes |
| SC7 | Zero new PyPI runtime deps | yes (stdlib `json`, `urllib.parse`, `shlex`) |

---

## 2. Scope (v0.11)

### 2.1 In scope (8 features, ~ 500 LOC core)

1. **HTTP-shape detector** (`ulog/web/viewer/_http_detect.py`) — given a record's `context` dict, returns `True` if it has at least `{method, url}` (or aliases: `http_method`, `http_url`). Tunable alias list.
2. **HTTP panel** in `/r/<id>/` — between "Test context" (v0.3) and "Authored by" (v0.4). Renders: badge (method) + dest URL (full, with src URL if `referer`/`origin` header present) + request body (JSON pretty-printed, syntax-highlighted via Prism v0.8.1) + headers list (sensitive ones masked) + response: status_code (color-coded) + response_body + latency_ms + error_msg if 4xx/5xx.
3. **Sensitive header masking** — `_DEFAULT_SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "x-auth-token", "proxy-authorization"}`. Configurable via `setup(http_sensitive_headers=[...])`.
4. **"Copy as curl" button** — generates `curl -X METHOD -H 'K: V' [-H ...] -d '<body>' '<url>'` via stdlib `shlex.quote`. Sensitive headers replaced with placeholders so users can fill in real values manually.
5. **Records-list HTTP filter axis** — `?method=GET&method=POST` + `?status_range=4xx,5xx`. Multi-select OR per axis. URL-persisted.
6. **Visual marker in records list** — small `🌐` icon (lucide `globe-2`) next to msg + truncated url (`POST /api/orders/...`) for HTTP-shaped records. Inline, no extra column.
7. **`/docs/http-inspector/` doc page** — covers: what fields the detector looks for, the alias mappings, sensitive-header config, "Copy as curl" mechanics, FAQ ("do I need a logging middleware?", "what about binary bodies?").
8. **Edge cases as tests**: binary bodies → `<binary, N bytes>` placeholder. URL with secrets in query string → masked. `application/x-www-form-urlencoded` body → key=value lines.

### 2.2 Explicit non-goals (deferred or never)

- **Auto-instrumentation of `requests`/`httpx`/`aiohttp`** — out. User logs explicitly. v0.11.x candidate ONLY if a clean opt-in path exists (a `ulog.contrib.requests_hook` perhaps).
- **WebSocket / SSE frame rendering** — out. v1.x candidate.
- **gRPC** — out, forever (different shape; would need its own PRD).
- **Request replay button** — out, forever (side-effects + security).
- **Body-diff between request and response** — out. v0.11.x candidate.
- **HAR file export** — out. v0.11.x candidate (would dovetail with the v0.6.1 snapshot exports).

### 2.3 Edge cases & failure modes

| Case | Behaviour |
|---|---|
| Record has `method` but no `url` | Not detected as HTTP — falls through to generic context render. |
| `url` is malformed (`"not a url"`) | Detected as HTTP, rendered with the broken URL verbatim + a small `⚠ malformed` icon. No crash. |
| Body is `bytes` (binary) | Rendered as `<binary, N bytes>`. No base64 dump in the UI. |
| Body is `str` but not valid JSON | Rendered as a `<pre>` text block (no JSON syntax highlight). |
| Sensitive header value is short (< 4 chars) | Masked as `***` (avoid leaking via length). |
| URL contains a query-string secret (`?token=abc123`) | Visible by default; documented; a `setup(http_mask_query_params=['token', 'api_key'])` opt-in masks them. |
| `status_code` is 304 / 204 (no body) | Body section hidden; status displayed normally. |
| `method` is non-standard (`PROPFIND`, `LOCK`, ...) | Rendered verbatim (badge color: slate). No filter chips for non-standard methods (would clutter). |
| Record carries BOTH HTTP shape AND `test_id` (v0.3) | Both panels render — HTTP panel after Test context. |

### 2.4 Protected invariants

- **I5 (carried):** Logging API unchanged. v0.11 is viewer-only.
- **I12 (new):** Default sensitive headers are MASKED unconditionally. Users can ADD to the masked list; they CANNOT remove the defaults.

---

## 3. Functional Requirements

### 3.1 Detection

- **FR166**: `is_http_record(context: dict) -> bool` returns True iff `{"method", "url"}` ⊆ context.keys() (or their aliases).
- **FR167**: Alias map: `{"http_method"→"method", "http_url"→"url", "request_method"→"method", "request_url"→"url"}`. Configurable via `setup(http_aliases={...})`.

### 3.2 Detail-view HTTP panel

- **FR168**: Panel renders ONLY when `is_http_record(record.context)` is True.
- **FR169**: Method displayed as a colored badge: GET=blue, POST=emerald, PUT=amber, DELETE=red, PATCH=violet, HEAD/OPTIONS/TRACE=slate, other=slate.
- **FR170**: URL rendered as a clickable `<a href="..." target="_blank">` (only when the URL parses cleanly).
- **FR171**: Status code rendered with color: 2xx green, 3xx blue, 4xx amber, 5xx red, no-code slate.
- **FR172**: Request body: if JSON (parsing succeeds), pretty-print with 2-space indent + Prism (v0.8.1). Else `<pre>` text block. Binary: placeholder.
- **FR173**: Response body: same rules.
- **FR174**: Headers list: 2 columns (key, value). Sensitive keys (case-insensitive) → value `<value-elided>`. Long values (>200 chars) truncated with "expand" toggle.
- **FR175**: Latency: rendered in ms (or s if > 1000ms), color-coded against a 200ms / 1000ms threshold.
- **FR176**: "Copy as curl" button at the bottom — writes to clipboard via the Clipboard API; falls back to a textarea select on insecure contexts.

### 3.3 Records list

- **FR177**: HTTP-shaped records get a `🌐` icon (lucide `globe-2`) inline next to the msg, plus a truncated `METHOD url-path` postfix.
- **FR178**: Sidebar gains "HTTP" section: Method multi-select (GET/POST/PUT/DELETE/PATCH/...), Status-range multi-select (2xx/3xx/4xx/5xx). URL-persisted.

### 3.4 Documentation

- **FR179**: `/docs/http-inspector/` covers: detection contract, alias map, sensitive-header masking, "Copy as curl" mechanics, edge cases (binary body, malformed url), FAQ.
- **FR180**: Listed in `/docs/` index.

---

## 4. Non-Functional Requirements

- **NFR-PERF-120**: HTTP panel render adds ≤ 20 ms to a record detail view (Prism load excluded — already amortised in v0.8.1).
- **NFR-DEP-110**: Zero new PyPI deps. Uses stdlib `json`, `urllib.parse`, `shlex`, plus Prism.js (already vendored in v0.8.1).
- **NFR-SEC-110**: Sensitive headers (defaults + user-extended) MUST be masked. Test gate: `test_qa_http_inspector_e2e.py::test_authorization_header_never_visible_in_dom` greps the rendered HTML for any literal `Bearer ` / `Basic ` token.
- **NFR-SEC-111**: URL query-string masking is opt-in via `setup(http_mask_query_params=[...])`. Default leaves them visible (matches `requests` library default behaviour; opt-in is a deliberate "trust the user" choice).
- **NFR-DOC-110**: Doc page with one full example per shape (GET-no-body, POST-JSON, PUT-form-urlencoded, GET-binary-response).

---

## 5. API surface (sketch)

### 5.1 User code (no API change — uses extra)

```python
import logging
import ulog

log = ulog.get_logger("svc.checkout")

# Outbound HTTP — already a common idiom.
log.info(
    "payment authorized",
    extra={
        "method": "POST",
        "url": "https://payments.internal/charge",
        "status_code": 200,
        "body": {"amount": 1200, "currency": "EUR"},
        "response_body": {"id": "ch_abc123", "captured": True},
        "headers": {"Authorization": "Bearer sk_live_..."},  # ← will be masked
        "latency_ms": 142,
    },
)
```

### 5.2 Setup (new optional kwargs)

```python
ulog.setup(
    # ... existing kwargs ...
    http_aliases={"req_method": "method", "req_url": "url"},  # extend
    http_sensitive_headers=["X-Tenant-Secret"],  # ADD to defaults; cannot remove
    http_mask_query_params=["token", "api_key"],  # opt-in URL query masking
)
```

### 5.3 Viewer URL filters

```
GET /?method=POST&method=PUT          → records with method ∈ {POST,PUT}
GET /?status_range=4xx,5xx             → records with status_code 400-599
GET /?method=GET&logger=svc.checkout   → combined filters
```

---

## 6. Implementation sketch

| Story | Scope | Est. LOC |
|---|---|---|
| 11.1 | `is_http_record` + alias map + setup() kwargs | 50 |
| 11.2 | HTTP panel template (`_http_panel.html` partial) | 90 |
| 11.3 | Sensitive header masking + URL query-param masking | 60 |
| 11.4 | "Copy as curl" JS + textarea fallback | 50 |
| 11.5 | Method badge + status badge + latency render helpers (template tags) | 50 |
| 11.6 | Records-list inline marker + URL truncation | 40 |
| 11.7 | Sidebar HTTP section (method + status-range) + filter wiring | 80 |
| 11.8 | Doc page `/docs/http-inspector/` | n/a |
| 11.9 | Edge case tests (binary, malformed, sensitive headers) | ~ tests |

Total ~ 420 LOC core.

---

## 7. Decisions log

| ID | Decision | Trade-off |
|---|---|---|
| D1 | NO auto-instrumentation of `requests`/`httpx` | Stays viewer-side; no global monkey-patch surprise; respects I5. |
| D2 | Detection is structural (shape-based), NOT a new logger type | Existing user code "just works" if it already logs HTTP with `extra={...}`. |
| D3 | Sensitive header defaults are HARDCODED + ADDITIVE | Users can't accidentally unmask Authorization. Locked baseline; extend allowed. |
| D4 | URL query masking is OPT-IN | Default behaviour matches `requests` (no masking). Opt-in for security-sensitive use cases. |
| D5 | "Copy as curl" via Clipboard API + textarea fallback | Modern + degrades. No backend POST involved. |
| D6 | Binary bodies → placeholder, NOT base64 | Loading multi-MB base64 into the DOM kills perf. Documented. |
| D7 | Prism syntax highlighting reuses v0.8.1 setup | Zero new dep. JSON + form-urlencoded grammars; Prism Python build already bundles JSON. |
| D8 | No tracing (W3C traceparent propagation) | Out of scope. Tracing = its own future PRD (probably v1.x). |
| D9 | Filter axes: method + status_range only | "Smaller is better" — adding host / path filters is hard to do well; defer. |

---

## 8. Open questions

| ID | Question | Tentative |
|---|---|---|
| Q1 | Should we add a per-record "request → response" timeline if `request_started_at` + `response_received_at` are both present in context? | Yes — small 1-line inline marker (`POST → 200 in 142 ms`). |
| Q2 | "Copy as curl" with sensitive headers: include the placeholder (e.g. `-H 'Authorization: Bearer <fill-me-in>'`) or omit the header entirely? | Include with placeholder — keeps the curl invocation complete-shaped. |
| Q3 | Multipart/form-data bodies: pretty-print (parsing the boundary)? | No — too much code. `<pre>` text block. Document the limitation. |
| Q4 | Should v0.11 cooperate with v0.10's fleet probe records (which ALSO have method+url)? | Yes — the HTTP panel renders for probe records too. They get a "🛰 probe" marker in addition to "🌐 http". |
| Q5 | Allow `http_aliases` to map ARBITRARY field names? Or constrain to a whitelist? | Whitelist — only known intent fields (method, url, status_code, body, response_body, headers, latency_ms, error_msg). |

---

## 9. References

- [Source: docs/prds/PRD-v0.2-storage-and-ui.md] — records detail view + sidebar pattern reused
- [Source: docs/prds/PRD-v0.8.1-docs-syntax-highlight.md] — Prism.js highlight reused for JSON bodies
- [Source: docs/prds/PRD-v0.10-fleet-dashboard.md] — probe records reuse the HTTP panel
- [Source: stdlib `shlex.quote`, `urllib.parse`] — chosen tools for curl generation + URL handling
- [OWASP "Logging cheat sheet"] — sensitive header list baseline
