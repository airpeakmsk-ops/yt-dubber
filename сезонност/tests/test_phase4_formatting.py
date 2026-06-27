"""Phase 4 — Batch formatting unit tests (Task 2, Plan 04-04).

Tests for src/apply_formatting.py:
  - build_format_requests(df) -> list[dict]: DSI (col J in full layout), % продаж (col M),
    Скорость (col I)
  - format_sheet(ws, df): calls ws.batch_format() EXACTLY ONCE (Pitfall 4)

All tests use in-memory DataFrames and a FakeWorksheet — NO network calls.
Column letters are derived dynamically from the test df (not hardcoded) so tests
work for both minimal test dfs and the full 84-col layout.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.apply_formatting import build_format_requests, format_sheet, _col_letter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(dsi_vals, pct_vals, velocity_vals):
    """Build a minimal DataFrame with the three coloured columns in the same
    relative order as the real report (Скорость at col I=8, DSI at J=9, % продаж
    at M=12 in 84-col layout).

    For unit tests we use a 3-column df; letters are derived dynamically.
    """
    return pd.DataFrame({
        "Скорость, шт/мес": velocity_vals,
        "DSI, дней": dsi_vals,
        "% продаж к приходам": pct_vals,
    })


def _letter_for(df: pd.DataFrame, col_name: str) -> str:
    """Return the Sheets column letter for col_name in df."""
    idx = list(df.columns).index(col_name)
    return _col_letter(idx)


class FakeWorksheet:
    """Records batch_format() calls; never touches the network."""

    def __init__(self):
        self.calls: list[list] = []  # list of format-list args
        self.call_count: int = 0

    def batch_format(self, formats: list):
        self.calls.append(formats)
        self.call_count += 1


# ---------------------------------------------------------------------------
# Test 1: DSI colour buckets produce correct ranges + colours
# ---------------------------------------------------------------------------

def test_batch_format_requests_dsi():
    """build_format_requests: DSI column gets correct colour per bucket."""
    df = _make_df(
        dsi_vals=[15.0, 45.0, 75.0, 120.0, ""],
        pct_vals=["", "", "", "", ""],
        velocity_vals=[0, 0, 0, 0, 0],
    )
    dsi_col = _letter_for(df, "DSI, дней")
    reqs = build_format_requests(df)

    # Filter only DSI-column requests
    dsi_reqs = [r for r in reqs if r["range"].startswith(dsi_col) and not r["range"].startswith(dsi_col + dsi_col)]
    # More precise: range == "<letter><row>"
    dsi_reqs = [r for r in reqs if r["range"][:-1] == dsi_col or r["range"][:-2] == dsi_col]
    # Simplest: filter startswith(dsi_col) with correct letter
    dsi_reqs = [r for r in reqs if r["range"].startswith(dsi_col) and r["range"][len(dsi_col):].isdigit()]

    # 4 numeric DSI values -> 4 requests; "" -> no request
    assert len(dsi_reqs) == 4, f"Expected 4 DSI format entries, got {len(dsi_reqs)}: {dsi_reqs}"

    # Row 2 -> DSI=15 -> red; row 3 -> DSI=45 -> yellow; row 4 -> DSI=75 -> green; row 5 -> DSI=120 -> blue
    def get_req(row_num):
        return next(r for r in dsi_reqs if r["range"] == f"{dsi_col}{row_num}")

    red_req    = get_req(2)
    yellow_req = get_req(3)
    green_req  = get_req(4)
    blue_req   = get_req(5)

    # Red: red channel > green channel
    bg = red_req["format"]["backgroundColor"]
    assert bg["red"] > bg["green"], "Red bucket: red channel should dominate"

    # Yellow/orange: red > blue
    bg = yellow_req["format"]["backgroundColor"]
    assert bg["red"] > bg["blue"], "Yellow bucket: red channel should dominate"

    # Green: green > red
    bg = green_req["format"]["backgroundColor"]
    assert bg["green"] > bg["red"], "Green bucket: green channel should dominate"

    # Blue: blue > red
    bg = blue_req["format"]["backgroundColor"]
    assert bg["blue"] > bg["red"], "Blue bucket: blue channel should dominate"

    # Empty DSI row (row 6) must NOT appear
    ranges = [r["range"] for r in dsi_reqs]
    assert f"{dsi_col}6" not in ranges, "Empty-DSI row must not receive a color fill"


# ---------------------------------------------------------------------------
# Test 2: % продаж colour buckets — 5 levels, '' skipped
# ---------------------------------------------------------------------------

def test_batch_format_requests_pct():
    """build_format_requests: % продаж column gets correct 5-level colour."""
    df = _make_df(
        dsi_vals=["", "", "", "", "", ""],
        pct_vals=[0.10, 0.30, 0.50, 0.70, 0.90, ""],
        velocity_vals=[0, 0, 0, 0, 0, 0],
    )
    pct_col = _letter_for(df, "% продаж к приходам")
    reqs = build_format_requests(df)

    pct_reqs = [r for r in reqs if r["range"].startswith(pct_col) and r["range"][len(pct_col):].isdigit()]

    # 5 numeric values -> 5 requests; "" -> no request
    assert len(pct_reqs) == 5, f"Expected 5 pct format entries, got {len(pct_reqs)}"

    def get_req(row_num):
        return next(r for r in pct_reqs if r["range"] == f"{pct_col}{row_num}")

    # Row 2 (0.10) -> red bucket
    bg = get_req(2)["format"]["backgroundColor"]
    assert bg["red"] > bg["green"], "Pct 10% should be red (red > green)"

    # Row 6 (0.90) -> green bucket: green channel > red
    bg = get_req(6)["format"]["backgroundColor"]
    assert bg["green"] > bg["red"], "Pct 90% should be green (green > red)"

    # Empty '' row 7 must NOT appear
    ranges = [r["range"] for r in pct_reqs]
    assert f"{pct_col}7" not in ranges, "Empty-pct row must not receive a color fill"


# ---------------------------------------------------------------------------
# Test 3: Скорость (col I) green fill only for green_item (velocity > 20)
# ---------------------------------------------------------------------------

def test_batch_format_requests_velocity():
    """build_format_requests: Скорость col gets green fill only when velocity > 20."""
    df = _make_df(
        dsi_vals=["", "", ""],
        pct_vals=["", "", ""],
        velocity_vals=[5.0, 25.0, ""],   # row2=not green, row3=green, row4=empty
    )
    vel_col = _letter_for(df, "Скорость, шт/мес")
    reqs = build_format_requests(df)

    vel_reqs = [r for r in reqs if r["range"].startswith(vel_col) and r["range"][len(vel_col):].isdigit()]

    # Only row 3 (velocity=25 > 20) should get a fill
    ranges = [r["range"] for r in vel_reqs]
    assert f"{vel_col}2" not in ranges, "velocity=5 should not get green fill"
    assert f"{vel_col}3" in ranges, "velocity=25 should get green fill"
    assert f"{vel_col}4" not in ranges, "velocity='' should not get green fill"

    # The colour must be the green-item colour (#B6D7A8)
    i3 = next(r for r in vel_reqs if r["range"] == f"{vel_col}3")
    bg = i3["format"]["backgroundColor"]
    assert bg["green"] > bg["red"], "Green-item fill: green channel should dominate"


# ---------------------------------------------------------------------------
# Test 4: format_sheet calls ws.batch_format EXACTLY ONCE (Pitfall 4)
# ---------------------------------------------------------------------------

def test_format_sheet_single_call():
    """format_sheet must make exactly one ws.batch_format() call, regardless of df size."""
    df = _make_df(
        dsi_vals=[10.0, 45.0, 80.0, ""],
        pct_vals=[0.15, 0.55, 0.85, ""],
        velocity_vals=[5.0, 25.0, 3.0, 0],
    )
    ws = FakeWorksheet()
    format_sheet(ws, df)

    assert ws.call_count == 1, (
        f"format_sheet must call ws.batch_format exactly once, called {ws.call_count} times"
    )
    # The one call must contain a non-empty list (we have coloured rows)
    assert len(ws.calls[0]) > 0, "batch_format was called with empty list — no formats built"


# ---------------------------------------------------------------------------
# Test 5: format dict structure is valid (has 'range' and 'format.backgroundColor')
# ---------------------------------------------------------------------------

def test_format_request_structure():
    """Every format request must have 'range' (str) and format.backgroundColor (R/G/B floats)."""
    df = _make_df(
        dsi_vals=[20.0],
        pct_vals=[0.5],
        velocity_vals=[0],
    )
    reqs = build_format_requests(df)
    assert len(reqs) >= 1, "Should produce at least one format request"
    for req in reqs:
        assert "range" in req, f"Missing 'range' key in {req}"
        assert "format" in req, f"Missing 'format' key in {req}"
        bg = req["format"]["backgroundColor"]
        assert "red" in bg and "green" in bg and "blue" in bg, (
            f"backgroundColor must have red/green/blue float keys, got {bg}"
        )
        for k in ("red", "green", "blue"):
            v = bg[k]
            assert isinstance(v, float) and 0.0 <= v <= 1.0, (
                f"backgroundColor.{k} must be float 0..1, got {v!r}"
            )


# ---------------------------------------------------------------------------
# Test 6: Full 84-col layout — verify actual column letters I, J, M
# ---------------------------------------------------------------------------

def test_full_layout_column_letters():
    """In the real 84-col layout, DSI=J(9), %=M(12), Скорость=I(8)."""
    from src.build_report import BASE_COLS, CUM_SUMMARY_COLS, ANALYTIC_COLS

    # Build header list matching the real layout (just the first 18 fixed cols)
    headers = BASE_COLS + CUM_SUMMARY_COLS + ANALYTIC_COLS
    df_stub = pd.DataFrame(columns=headers)

    assert _col_letter(headers.index("Скорость, шт/мес")) == "I", "Скорость must be col I (index 8)"
    assert _col_letter(headers.index("DSI, дней")) == "J", "DSI must be col J (index 9)"
    assert _col_letter(headers.index("% продаж к приходам")) == "M", "% продаж must be col M (index 12)"
