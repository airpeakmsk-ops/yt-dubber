"""apply_formatting — batch cell colour formatting for the Phase 4 report sheet.

Builds a list of gspread format-request dicts and sends them to Google Sheets
in a SINGLE ws.batch_format() call (Pitfall 4: never loop ws.format() per row).

Colour rules (LOCKED, per 04-CONTEXT.md / 04-RESEARCH.md Паттерн 5):

  DSI (col J) — 4 buckets (VISUAL-01):
    <  30 days  -> red    #F4CCCC  {r:0.957, g:0.800, b:0.800}
    30–59 days  -> yellow #FCE5CD  {r:0.988, g:0.898, b:0.804}
    60–89 days  -> green  #D9EAD3  {r:0.851, g:0.918, b:0.827}
    >= 90 days  -> blue   #CFE2F3  {r:0.812, g:0.886, b:0.953}
    "" / NaN    -> no fill (dsi_bucket == 4)

  % продаж к приходам (col M) — 5 buckets (VISUAL-04):
    < 20%    -> red    #F4CCCC
    20–39%   -> orange #F9CB9C  {r:0.976, g:0.796, b:0.612}
    40–59%   -> yellow #FFE599  {r:1.000, g:0.898, b:0.600}
    60–79%   -> blue   #6FA8DC  {r:0.435, g:0.659, b:0.863}  (контраст, user 2026-06-29)
    80–100%  -> green  #93C47D  {r:0.576, g:0.769, b:0.490}  (контраст, user 2026-06-29)
    "" / NaN -> no fill (pct_bucket == None)

  Скорость, шт/мес (col I) — green if green_item (velocity > 20) (VISUAL-02):
    > 20 шт/мес -> #B6D7A8  {r:0.714, g:0.843, b:0.659}
    else        -> no fill

Column indices are computed from df.columns dynamically (not hardcoded letter)
to survive any column order changes. At 84-col layout the letters are:
  I = index 8 (Скорость, шт/мес), J = index 9 (DSI, дней), M = index 12 (% продаж).

gspread 6.1.4: ws.batch_format(list[{range: str, format: {backgroundColor: {r,g,b}}}])
  ONE API call for ~1300 rows × 3 columns ≈ 3900 format operations.
  RGB values are floats 0.0..1.0 (not 0..255).
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# sys.path bootstrap — allow `python src/apply_formatting.py` without ModuleNotFoundError.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.report_metrics import dsi_bucket, pct_bucket, green_item  # noqa: E402

# ---------------------------------------------------------------------------
# Colour palette (float RGB 0..1, Google Sheets Light colours)
# ---------------------------------------------------------------------------

_RED    = {"red": 0.957, "green": 0.800, "blue": 0.800}   # #F4CCCC
_YELLOW = {"red": 0.988, "green": 0.898, "blue": 0.804}   # #FCE5CD
_GREEN  = {"red": 0.851, "green": 0.918, "blue": 0.827}   # #D9EAD3
_BLUE   = {"red": 0.812, "green": 0.886, "blue": 0.953}   # #CFE2F3
_ORANGE = {"red": 0.976, "green": 0.796, "blue": 0.612}   # #F9CB9C
_LTYELW = {"red": 1.000, "green": 0.898, "blue": 0.600}   # #FFE599
_GRNITM = {"red": 0.714, "green": 0.843, "blue": 0.659}   # #B6D7A8 (green-item)

# Более контрастные зелёный/синий для колонки «% продаж» (M) — запрос пользователя
# 2026-06-29. DSI (J) оставляем на бледных _GREEN/_BLUE (пользователь: J ок).
_PCT_GREEN = {"red": 0.576, "green": 0.769, "blue": 0.490}  # #93C47D (насыщ. зелёный)
_PCT_BLUE  = {"red": 0.435, "green": 0.659, "blue": 0.863}  # #6FA8DC (насыщ. синий)

# DSI bucket index -> colour (bucket 4 = no fill -> None)
_DSI_BUCKET_COLOUR = {
    0: _RED,
    1: _YELLOW,
    2: _GREEN,
    3: _BLUE,
    4: None,
}

# pct_bucket index -> colour (None = no fill). Зелёный/синий — контрастные (_PCT_*).
_PCT_BUCKET_COLOUR = {
    0: _RED,
    1: _ORANGE,
    2: _LTYELW,
    3: _PCT_BLUE,
    4: _PCT_GREEN,
    None: None,
}

# ---------------------------------------------------------------------------
# Column-letter helpers
# ---------------------------------------------------------------------------

def _col_letter(col_index: int) -> str:
    """Convert 0-based column index to Sheets letter (A=0, Z=25, AA=26, ...).

    Uses the same algorithm as gspread.utils.rowcol_to_a1 but only for the
    column part, so we avoid importing gspread in the offline test path.
    """
    letter = ""
    idx = col_index + 1  # 1-based
    while idx > 0:
        idx, remainder = divmod(idx - 1, 26)
        letter = chr(ord("A") + remainder) + letter
    return letter


def _find_col_letter(df: pd.DataFrame, col_name: str) -> str | None:
    """Return the Sheets column letter for col_name in df, or None if absent."""
    try:
        idx = df.columns.get_loc(col_name)
        return _col_letter(idx)
    except KeyError:
        return None


# ---------------------------------------------------------------------------
# Core: build list of format-request dicts
# ---------------------------------------------------------------------------

_DSI_COL  = "DSI, дней"
_PCT_COL  = "% продаж к приходам"
_VEL_COL  = "Скорость, шт/мес"


def build_format_requests(df: pd.DataFrame) -> list[dict]:
    """Build the list of gspread batch_format request dicts for df.

    Iterates df rows (data rows start at Sheets row 2) and produces:
      - One entry per DSI cell with a non-empty bucket (bucket 0–3).
      - One entry per % продаж cell with a non-None bucket (0–4).
      - One entry per Скорость cell where green_item(velocity) is True.

    Column letters are derived from df.columns dynamically (survive column
    reorder). Missing columns are silently skipped.

    Args:
        df: The report DataFrame (84 cols or any subset for testing).

    Returns:
        list[dict] — each dict has {"range": "X<row>", "format": {"backgroundColor": {...}}}
        where colours are float RGB dicts 0..1.
    """
    dsi_letter = _find_col_letter(df, _DSI_COL)
    pct_letter = _find_col_letter(df, _PCT_COL)
    vel_letter = _find_col_letter(df, _VEL_COL)

    requests: list[dict] = []

    for i, row in enumerate(df.itertuples(index=False, name=None), start=2):
        row_dict = dict(zip(df.columns, row))

        # --- DSI (col J in full layout) ---
        if dsi_letter:
            dsi_val = row_dict.get(_DSI_COL, "")
            bucket = dsi_bucket(dsi_val)
            colour = _DSI_BUCKET_COLOUR.get(bucket)
            if colour is not None:
                requests.append({
                    "range": f"{dsi_letter}{i}",
                    "format": {"backgroundColor": colour},
                })

        # --- % продаж к приходам (col M in full layout) ---
        if pct_letter:
            pct_val = row_dict.get(_PCT_COL, "")
            bucket = pct_bucket(pct_val)
            colour = _PCT_BUCKET_COLOUR.get(bucket)
            if colour is not None:
                requests.append({
                    "range": f"{pct_letter}{i}",
                    "format": {"backgroundColor": colour},
                })

        # --- Скорость, шт/мес (col I in full layout) ---
        if vel_letter:
            vel_val = row_dict.get(_VEL_COL, "")
            if green_item(vel_val):
                requests.append({
                    "range": f"{vel_letter}{i}",
                    "format": {"backgroundColor": _GRNITM},
                })

    return requests


# ---------------------------------------------------------------------------
# Public entry point: apply formatting to a live gspread worksheet
# ---------------------------------------------------------------------------

def format_sheet(ws, df: pd.DataFrame) -> None:
    """Apply cell colour formatting to the worksheet in ONE API call (Pitfall 4).

    Builds all format requests from df, then sends them as a SINGLE
    ws.batch_format() call — never loops ws.format() per row.

    Args:
        ws:  gspread Worksheet object (must support .batch_format(list)).
        df:  The report DataFrame (same that was written to the sheet).
    """
    requests = build_format_requests(df)
    ws.batch_format(requests)
