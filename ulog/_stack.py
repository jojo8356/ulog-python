"""Per-record call-stack capture (PRD-v0.12).

`ulog.setup(capture_stack=True)` flips a process-global flag. The
SQLHandler reads it at emit time and appends the captured frames to
`record.context.stack` (so the schema stays unchanged — Decision
D2 of PRD-v0.12).

`with_locals=True` adds `repr(local)` for each frame, capped at
10 KB per frame to bound the per-record cost.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

CAPTURE_STACK: bool = False
CAPTURE_LOCALS: bool = False
LOCALS_CAP_BYTES: int = 10_000

# Internal logging frames we never want to surface — same approach as
# logging.Logger.findCaller(). Anything under these prefixes is skipped.
_SKIP_PREFIXES: tuple[str, ...] = ("logging/", "/logging/", "ulog/handlers/", "ulog/_stack")


def configure(capture_stack: bool, with_locals: bool = False) -> None:
    global CAPTURE_STACK, CAPTURE_LOCALS
    CAPTURE_STACK = bool(capture_stack)
    CAPTURE_LOCALS = bool(with_locals)


def capture_frames(skip_frames: int = 2) -> list[dict[str, Any]]:
    """Return a list of frame dicts: {function, file, line, locals?}.

    `skip_frames` defaults to 2 so the caller's caller's caller is the
    top-of-stack — strip off the SQLHandler.emit + capture_frames +
    extract_stack frames. Adjust at call site if you wrap further.
    """
    raw = traceback.extract_stack()
    frames: list[dict[str, Any]] = []
    # Walk frames + their FrameSummary in parallel so we can grab locals.
    py_frames = list(_iter_frames())
    for fs, frame in zip(raw[:-skip_frames], py_frames[: len(raw) - skip_frames], strict=False):
        if _is_internal(fs.filename):
            continue
        entry: dict[str, Any] = {
            "function": fs.name,
            "file": fs.filename,
            "line": fs.lineno,
        }
        if CAPTURE_LOCALS and frame is not None:
            entry["locals"] = _capture_locals(frame.f_locals)
        frames.append(entry)
    return frames


def _iter_frames() -> list[Any]:
    """Walk back through `sys._getframe` to get real frame objects for
    each level. Bottom of the list = outermost caller."""
    out = []
    f: Any = sys._getframe(1)
    while f is not None:
        out.append(f)
        f = f.f_back
    out.reverse()
    return out


def _is_internal(file_path: str) -> bool:
    return any(p in file_path for p in _SKIP_PREFIXES)


def _capture_locals(locals_dict: dict[str, Any]) -> dict[str, str]:
    """`repr()` every local, capped at LOCALS_CAP_BYTES total per frame."""
    out: dict[str, str] = {}
    spent = 0
    for k, v in locals_dict.items():
        if k.startswith("_") or k in ("self",):
            continue
        try:
            r = repr(v)
        except Exception as e:
            r = f"<repr failed: {type(e).__name__}>"
        if len(r) > 1000:
            r = r[:1000] + "…"
        if spent + len(r) > LOCALS_CAP_BYTES:
            out["…"] = f"(truncated at {spent}/{LOCALS_CAP_BYTES} bytes)"
            break
        out[k] = r
        spent += len(r)
    return out
