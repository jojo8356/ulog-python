"""Tests for v0.4.2 markdown renderer extensions."""

from __future__ import annotations

from ulog.web.viewer.views import _markdown_to_html


def test_ordered_list():
    html = _markdown_to_html("1. one\n2. two\n3. three\n")
    assert "<ol" in html
    assert "<li>one</li>" in html
    assert "<li>three</li>" in html


def test_blockquote():
    html = _markdown_to_html("> quoted line\n> another\n")
    assert "<blockquote" in html
    assert "quoted line" in html
    assert "another" in html


def test_horizontal_rule():
    html = _markdown_to_html("para\n\n---\n\nafter\n")
    assert "<hr" in html


def test_italic_em():
    html = _markdown_to_html("this is *italic* text\n")
    assert "<em>italic</em>" in html


def test_bold_still_works():
    html = _markdown_to_html("**bold** word\n")
    assert "<strong>bold</strong>" in html


def test_table_rendering():
    md = (
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 |\n"
        "| 3 | 4 |\n"
    )
    html = _markdown_to_html(md)
    assert "<table" in html
    assert "<th" in html
    assert "<td" in html
    assert ">A<" in html and ">B<" in html
    assert ">1<" in html and ">4<" in html


def test_existing_features_still_work():
    """The pre-v0.4.2 grammar still parses."""
    md = (
        "# title\n\n"
        "## sub\n\n"
        "- one\n- two\n\n"
        "```python\nx = 1\n```\n\n"
        "para with `code` and **bold**.\n"
    )
    html = _markdown_to_html(md)
    assert "<h1" in html
    assert "<h2" in html
    assert "<ul" in html
    assert "<pre" in html
    assert "<strong>bold</strong>" in html
