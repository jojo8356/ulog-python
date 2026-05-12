"""Tests for locale-aware glyph fallback (Story 6.9 / NFR-PORT-50)."""

from __future__ import annotations

import importlib

import pytest


def test_utf8_locale_returns_unicode(monkeypatch):
    """When locale.getpreferredencoding() returns 'utf-8', glyphs are
    Unicode."""
    import ulog._glyphs as gly

    monkeypatch.setattr(gly, "_UNICODE_OK", True)
    monkeypatch.setattr(gly, "_TABLE", gly._GLYPHS_UTF8)
    assert gly.g("inf") == "∞"
    assert gly.g("warn") == "⚠"
    assert gly.g("check") == "✓"
    assert gly.g("cross") == "✗"
    assert gly.g("bullet") == "•"


def test_non_utf8_locale_returns_ascii(monkeypatch):
    """When locale isn't UTF-8, fall back to ASCII."""
    import ulog._glyphs as gly

    monkeypatch.setattr(gly, "_UNICODE_OK", False)
    monkeypatch.setattr(gly, "_TABLE", gly._GLYPHS_ASCII)
    assert gly.g("inf") == "inf"
    assert gly.g("warn") == "WARN"
    assert gly.g("check") == "OK"
    assert gly.g("cross") == "X"
    assert gly.g("bullet") == "*"


def test_unknown_glyph_name_raises_keyerror():
    import ulog._glyphs as gly

    with pytest.raises(KeyError):
        gly.g("nonexistent")


def test_resolve_unicode_ok_recognises_utf8_variants(monkeypatch):
    import locale

    import ulog._glyphs as gly

    # `utf-8` and `UTF8` both should be detected.
    for enc in ["utf-8", "UTF-8", "utf8", "UTF8"]:
        monkeypatch.setattr(locale, "getpreferredencoding", lambda _=False, e=enc: e)
        # Re-import to trigger module-level call.
        importlib.reload(gly)
        assert gly._UNICODE_OK is True, f"failed for {enc!r}"


def test_resolve_unicode_ok_rejects_ascii_and_unknown(monkeypatch):
    import locale

    import ulog._glyphs as gly

    for enc in ["ascii", "ANSI_X3.4-1968", "iso-8859-1", ""]:
        monkeypatch.setattr(locale, "getpreferredencoding", lambda _=False, e=enc: e)
        importlib.reload(gly)
        assert gly._UNICODE_OK is False, f"unexpectedly accepted {enc!r}"


def test_correlate_cli_uses_glyphs(tmp_path, capsys, monkeypatch):
    """End-to-end: correlate output uses g('inf') / g('warn') which
    respect the locale."""
    from sqlalchemy import create_engine, text

    from ulog._cli import main
    from ulog.handlers.sql import SQLHandler

    # Seed a DB with a tenant unique to ERROR → infinite lift.
    db = tmp_path / "g.sqlite"
    h = SQLHandler(url=f"sqlite:///{db}", batch_size=1)
    h._ensure_schema()
    h.close()
    engine = create_engine(f"sqlite:///{db}", future=True)
    with engine.begin() as conn:
        for _i in range(10):
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, context) "
                    "VALUES ('2026-05-12', 'ERROR', 'svc', 'm', 'f', 1, "
                    "json_object('tenant', 'A'))"
                )
            )
        for _i in range(10):
            conn.execute(
                text(
                    "INSERT INTO logs (ts, level, logger, msg, file, line, context) "
                    "VALUES ('2026-05-12', 'INFO', 'svc', 'm', 'f', 1, "
                    "json_object('tenant', 'B'))"
                )
            )
    engine.dispose()

    main(["correlate", "level=ERROR", "--db", str(db)])
    out = capsys.readouterr().out
    # Either `∞` (UTF-8) OR `inf` (ASCII fallback) should be present.
    import ulog._glyphs as gly

    expected = "∞" if gly._UNICODE_OK else "inf"
    assert expected in out, f"expected lift glyph {expected!r} in output: {out!r}"
