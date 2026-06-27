"""report_metrics — pure metric functions for the Phase 3/4 report (no network, no file IO).

All functions are deterministic and operate on in-memory values, so the whole report
is unit-testable offline. Locked decisions (see 03-01-PLAN.md / 04-01-PLAN.md):

  RUN_DATE         = date(2026, 6, 27)  — project run date ("today").
  N_MONTHS_DEFAULT = 33                 — fallback when EAN absent from weekly file (Pitfall 6).
                                          PRIMARY base for velocity/DSI is months_in_stock
                                          from parse_ostatki_weekly (Phase 4 contract change).
  DSI = qty_stock / (velocity_per_month / 30); guard: qty_stock NaN/≤0 OR velocity ≤0 -> "".
  Возраст остатка = (RUN_DATE − max(invoice_date по партиям)).days.
  Месяцы сортируются ВСЕГДА через month_sort_key (RU словарь) — порядок parquet не доверять.

Phase 4 additions (single source of truth for all bucket/flag logic):
  GREEN_THRESHOLD = 20                  — «зелёный товар»: velocity > 20 шт/мес (VISUAL-02).
  dsi_bucket(v)   → int 0–4            — VISUAL-01 colour bucket.
  pct_bucket(p)   → int 0–4 | None     — VISUAL-04 5-level % продаж palette.
  green_item(v)   → bool               — VISUAL-02 flag.
"""
from __future__ import annotations

import pathlib
import sys
from datetime import date

import pandas as pd

# Allow `python src/report_metrics.py` and pytest to import siblings without ModuleNotFoundError.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# --- LOCKED constants (single source of truth) -------------------------------
RUN_DATE = date(2026, 6, 27)   # project run date ("today"), LOCKED
N_MONTHS_DEFAULT = 33          # full period окт.2023–июнь.2026 (verified 33 months), LOCKED

# RU month name -> number. Single source of truth for parsing «<Месяц> <год> г.» labels.
RU_MONTHS: dict[str, int] = {
    "Январь": 1, "Февраль": 2, "Март": 3, "Апрель": 4,
    "Май": 5, "Июнь": 6, "Июль": 7, "Август": 8,
    "Сентябрь": 9, "Октябрь": 10, "Ноябрь": 11, "Декабрь": 12,
}


def month_sort_key(label: str) -> tuple[int, int]:
    """Sort key for a RU month label «Октябрь 2023 г.» -> (2023, 10).

    Returns (year, month) so chronological sort = окт.2023 → июнь.2026.
    """
    parts = label.split()  # ["Октябрь", "2023", "г."]
    month_word = parts[0]
    year = int(parts[1])
    return (year, RU_MONTHS[month_word])


def sht_per_month(qty_sold_total: float, n_months: int = N_MONTHS_DEFAULT) -> float:
    """Average units sold per month: qty_sold_total / n_months (REPORT-04 velocity).

    n_months defaults to 33 (whole period, locked). n_months == 0 -> 0.0 (no div-by-zero).
    """
    if n_months == 0:
        return 0.0
    return qty_sold_total / n_months


def dsi_days(qty_stock, velocity_per_month: float):
    """Days Sales of Inventory: qty_stock / (velocity_per_month / 30).

    Guard (locked): if qty_stock is NaN/≤0 OR velocity_per_month ≤0 -> "" (empty string,
    never NaN/inf). Negative qty_stock = «нет покрытия» -> "". Otherwise round to 1 dp.
    """
    if pd.isna(qty_stock) or qty_stock <= 0 or velocity_per_month <= 0:
        return ""
    return round(qty_stock / (velocity_per_month / 30), 1)


def stock_age_days(partii: list[dict]) -> int:
    """Age of the freshest приход: (RUN_DATE − max(invoice_date по партиям)).days (REPORT-05).

    invoice_date is already datetime.date in the parquet. Returns int ≥ 0.
    """
    last = max(p["invoice_date"] for p in partii)
    return (RUN_DATE - last).days


def cumulative(pivot: pd.DataFrame) -> pd.DataFrame:
    """Running cumulative sum across the month columns (left → right): pivot.cumsum(axis=1).

    Caller must pass a pivot whose columns are already month_sort_key-ordered.
    """
    return pivot.cumsum(axis=1)


# ---------------------------------------------------------------------------
# Phase 4 — availability-based bucket / flag functions (VISUAL-01/02/04)
# Single source of truth used by order_plan, apply_formatting, and presort.
# ---------------------------------------------------------------------------

# «Зелёный товар» threshold: velocity strictly > GREEN_THRESHOLD шт/мес (VISUAL-02, LOCKED).
GREEN_THRESHOLD: float = 20.0


def dsi_bucket(v) -> int:
    """Map a DSI value to a colour bucket integer (VISUAL-01, LOCKED thresholds).

    Thresholds (days):
      <  30  -> 0  red    (горит, critical)
      30–59  -> 1  yellow (watch)
      60–89  -> 2  green  (ok)
      >= 90  -> 3  blue   (overstock)
      '' / NaN -> 4 (no stock — sort to bottom, no fill)

    Args:
        v: numeric DSI value (int/float), empty string "", or NaN.

    Returns:
        int 0–4.
    """
    if v == "" or (isinstance(v, float) and pd.isna(v)):
        return 4
    try:
        d = float(v)
    except (TypeError, ValueError):
        return 4
    if pd.isna(d):
        return 4
    if d < 30:
        return 0
    if d < 60:
        return 1
    if d < 90:
        return 2
    return 3


def pct_bucket(p) -> int | None:
    """Map % продаж к приходам to a 5-level colour bucket (VISUAL-04, LOCKED).

    Thresholds (fraction 0.0–1.0):
      < 0.20          -> 0  red
      0.20 – <0.40    -> 1  orange
      0.40 – <0.60    -> 2  yellow
      0.60 – <0.80    -> 3  blue
      0.80 – 1.0      -> 4  green
      '' / NaN        -> None (no fill)

    Args:
        p: fraction value (float 0..1), empty string "", or NaN.

    Returns:
        int 0–4, or None for missing / sentinel values.
    """
    if p == "" or p is None:
        return None
    try:
        frac = float(p)
    except (TypeError, ValueError):
        return None
    if pd.isna(frac):
        return None
    if frac < 0.20:
        return 0
    if frac < 0.40:
        return 1
    if frac < 0.60:
        return 2
    if frac < 0.80:
        return 3
    return 4


def green_item(velocity) -> bool:
    """Return True if velocity strictly exceeds GREEN_THRESHOLD (20 шт/мес) (VISUAL-02).

    Args:
        velocity: numeric (int/float) или "" / None для товаров без продаж.

    Returns:
        bool — True means «Зелёный товар» label and Скорость cell gets green fill.
    """
    if velocity == "" or velocity is None:
        return False
    try:
        v = float(velocity)
    except (TypeError, ValueError):
        return False
    return v > GREEN_THRESHOLD
