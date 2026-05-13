"""Tailwind drift detector (PRD-v0.6.2 / Story 8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

BUNDLE = Path(__file__).resolve().parent.parent / "ulog/web/static/ulog/tailwind.css"

EXPECTED_CLASSES: tuple[str, ...] = (
    "flex", "grid", "block", "hidden",
    "p-4", "px-2", "py-1",
    "text-sm", "text-xs", "font-mono", "font-semibold",
    "bg-slate-50",
    "text-slate-500",
    "border-slate-200",
    "dark\\:bg-slate-950",
    "dark\\:text-slate-100",
    "bg-red-100", "bg-amber-100", "bg-blue-100",
    "bg-emerald-100",
    "bg-red-600",
)


@pytest.fixture(scope="module")
def bundle_text() -> str:
    if not BUNDLE.exists():
        pytest.skip(f"Tailwind bundle not present at {BUNDLE}; run `make tailwind-build`.")
    return BUNDLE.read_text(encoding="utf-8")


@pytest.mark.parametrize("cls", EXPECTED_CLASSES)
def test_class_present_in_bundle(bundle_text: str, cls: str) -> None:
    needle = f".{cls}"
    assert needle in bundle_text, (
        f"Tailwind class `.{cls}` missing from the bundle. "
        f"Templates likely added a new class — run `make tailwind-build` and commit."
    )


def test_bundle_is_minified(bundle_text: str) -> None:
    lines = bundle_text.count("\n")
    bytes_ = len(bundle_text)
    assert lines <= bytes_ / 100, (
        f"Bundle has {lines} newlines for {bytes_} bytes — looks unminified."
    )


def test_bundle_size_under_100kb(bundle_text: str) -> None:
    size_kb = len(bundle_text) / 1024
    assert size_kb < 100, f"Bundle is {size_kb:.1f} KB — exceeds 100 KB hard cap."
