"""report_metrics — pure metric functions for the Phase 3 report (no network, no file IO).

All functions are deterministic and operate on in-memory values, so the whole report
is unit-testable offline. Locked decisions (see 03-01-PLAN.md):

  RUN_DATE        = date(2026, 6, 27)  — project run date ("today").
  N_MONTHS_DEFAULT = 33                — full period окт.2023–июнь.2026 (velocity / DSI base).
  DSI = qty_stock / (velocity_per_month / 30); guard: qty_stock NaN/≤0 OR velocity ≤0 -> "".
  Возраст остатка = (RUN_DATE − max(invoice_date по партиям)).days.
  Месяцы сортируются ВСЕГДА через month_sort_key (RU словарь) — порядок parquet не доверять.
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
