"""Phase 4 — Batch formatting tests (RED placeholder until Plan 04 creates src/apply_formatting.py).

Collection does NOT fail before Plan 04 — pytest.importorskip handles the missing module.
All tests here are marked xfail/skip until Plan 04 delivers the implementation.

Covers VISUAL-01 (DSI color fill), VISUAL-02 (green item fill), VISUAL-04 (% sales fill).
Uses a mocked gspread worksheet — no network calls in pytest.
"""
from __future__ import annotations

import pytest

# Skip this entire module gracefully until Plan 04 creates src.apply_formatting.
apply_formatting = pytest.importorskip(
    "src.apply_formatting",
    reason="src.apply_formatting not yet implemented (TODO: Plan 04)",
)


@pytest.mark.xfail(reason="TODO: Plan 04 — batch_format_requests not yet implemented", strict=False)
def test_batch_format_requests_dsi():
    """DSI column format requests: red row for DSI<30, correct range notation, correct RGB."""
    import pandas as pd

    # Minimal DataFrame with DSI column
    df = pd.DataFrame({
        "DSI, дней": [15.0, 45.0, 75.0, 120.0, ""],
    })

    formats = apply_formatting.build_dsi_formats(df, dsi_col="DSI, дней", start_row=2)

    assert isinstance(formats, list), "build_dsi_formats must return a list"
    # First row (DSI=15) must be red
    red = formats[0]
    assert "range" in red and "format" in red
    bg = red["format"]["backgroundColor"]
    assert bg["red"] > bg["green"], "Red bucket: red channel should dominate"
    # Empty DSI row (last) should have NO format entry (bucket 4 = no fill)
    ranges_in_formats = [f["range"] for f in formats]
    # Row index 6 (start_row=2 + offset 4) must not appear in format list
    assert not any("6" in r for r in ranges_in_formats), (
        "Empty-DSI row must not receive a color fill"
    )


@pytest.mark.xfail(reason="TODO: Plan 04 — pct_formats not yet implemented", strict=False)
def test_batch_format_requests_pct():
    """Pct-sales column format requests: 5-level palette, None skipped."""
    import pandas as pd

    df = pd.DataFrame({
        "% продаж к приходам": [0.10, 0.30, 0.50, 0.70, 0.90, ""],
    })

    formats = apply_formatting.build_pct_formats(df, pct_col="% продаж к приходам", start_row=2)

    assert isinstance(formats, list)
    # 5 numeric rows -> 5 format entries; empty string -> 0 entries
    assert len(formats) == 5, f"Expected 5 format entries, got {len(formats)}"
