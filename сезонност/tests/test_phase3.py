"""Phase 3 unit tests — REPORT-01..05 over the assembled report DataFrame (OFFLINE).

These tests build the report from data/interim/master_cost.parquet + prodazhi.parquet
purely in pandas. NO gspread import, NO network call — Sheets writing is covered in
Plan 02 with a mock. RED at first: build_report / report_metrics do not exist yet.

Verified facts (introspection 2026-06-27):
  - master_cost.parquet: 1300 rows, one per EAN; cols include ean, name, qty_prikhod,
    n_partii, partii(list[dict]), qty_stock(NaN@345/neg@4), qty_sold_total, has_sales,
    cost_usd_wavg.
  - prodazhi.parquet: long format, 33 unique months "Октябрь 2023 г." .. "Июнь 2026 г.".
  - oracle EANs 4525807270297 / 4525807270280 — sales match prodazhi, stock > 0.
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd
import pytest

from src import report_metrics
from src.build_report import build_report_df, df_to_rows

RUN_DATE = date(2026, 6, 27)
N_MONTHS = 33
FIRST_MONTH = "Октябрь 2023 г."
LAST_MONTH = "Июнь 2026 г."
SAMPLE_EAN = 9999999999999  # samples must NOT appear
# Распродан: нет строки остатка -> остаток 0 (fillna), есть продажи -> DSI 0 (горящий).
SOLDOUT_EAN = 4525807273205       # has_sales, нет в остатках -> остаток 0 -> DSI 0
NEG_STOCK_EAN = 4525807289329     # qty_stock < 0 (резерв>остатка), есть продажи -> DSI 0


@pytest.fixture
def master_cost(master_cost_path) -> pd.DataFrame:
    return pd.read_parquet(master_cost_path)


@pytest.fixture
def prodazhi(prodazhi_path) -> pd.DataFrame:
    return pd.read_parquet(prodazhi_path)


def _monthly_cols(df: pd.DataFrame) -> list[str]:
    """The 33 plain monthly columns (those that are valid month labels)."""
    return [c for c in df.columns if c.endswith(" г.") and not c.startswith("Кум. ")]


# --- REPORT-01 ---------------------------------------------------------------
def test_report_covers_all_eans(report_df, master_cost):
    assert len(report_df) == 1300
    assert set(report_df["EAN"]) == set(master_cost["ean"])
    assert SAMPLE_EAN not in set(report_df["EAN"])


# --- REPORT-02 ---------------------------------------------------------------
def test_monthly_columns_chronological(report_df):
    monthly = _monthly_cols(report_df)
    assert len(monthly) == N_MONTHS
    expected = sorted(monthly, key=report_metrics.month_sort_key)
    assert monthly == expected
    assert monthly[0] == FIRST_MONTH
    assert monthly[-1] == LAST_MONTH


# --- REPORT-03 ---------------------------------------------------------------
def test_cumulative_oracle(report_df, master_cost, prodazhi, oracle_eans):
    monthly = _monthly_cols(report_df)
    cum_cols = ["Кум. " + m for m in monthly]
    for ean in oracle_eans:
        row = report_df[report_df["EAN"] == ean].iloc[0]
        manual = prodazhi[prodazhi["ean"] == ean]["qty"].sum()
        assert row["Накопит. продажи"] == pytest.approx(manual)
        # last cumulative monthly cell == total cumulative sales
        assert row[cum_cols[-1]] == pytest.approx(row["Накопит. продажи"])
        mc_row = master_cost[master_cost["ean"] == ean].iloc[0]
        assert row["Накопит. приходы"] == pytest.approx(mc_row["qty_prikhod"])


# --- REPORT-04 ---------------------------------------------------------------
def test_velocity_and_dsi(report_df, master_cost, oracle_eans, weekly_months_map):
    """Velocity and DSI now use months_in_stock from weekly file (Phase 4 contract change).

    Fallback for EAN absent from weekly map = N_MONTHS_DEFAULT (33) — backward compat.
    """
    for ean in oracle_eans:
        row = report_df[report_df["EAN"] == ean].iloc[0]
        mc_row = master_cost[master_cost["ean"] == ean].iloc[0]
        # Phase 4 contract: use actual months_in_stock; fallback 33 if absent from weekly
        months_set = weekly_months_map.get(ean)
        m = len(months_set) if months_set is not None else N_MONTHS
        expected_v = mc_row["qty_sold_total"] / m
        assert row["Скорость, шт/мес"] == pytest.approx(expected_v, abs=1e-6), (
            f"EAN {ean}: velocity mismatch (months_in_stock={m})"
        )
        expected_dsi = round(mc_row["qty_stock"] / (expected_v / 30), 1)
        assert row["DSI, дней"] == pytest.approx(expected_dsi), (
            f"EAN {ean}: DSI mismatch (months_in_stock={m})"
        )
    # Распродан (нет в остатках -> остаток 0), есть продажи -> Остаток 0, DSI 0 (горящий).
    soldout_row = report_df[report_df["EAN"] == SOLDOUT_EAN].iloc[0]
    assert soldout_row["Остаток"] == 0, "распроданный товар -> остаток 0, не пусто"
    assert soldout_row["DSI, дней"] == 0, "распроданный товар с продажами -> DSI 0"
    # Отрицательный остаток (резерв>остатка) + продажи -> DSI 0 (нет доступного запаса).
    neg_row = report_df[report_df["EAN"] == NEG_STOCK_EAN].iloc[0]
    assert neg_row["DSI, дней"] == 0


# --- REPORT-05 ---------------------------------------------------------------
def test_stock_age(report_df, master_cost, oracle_eans):
    for ean in oracle_eans:
        row = report_df[report_df["EAN"] == ean].iloc[0]
        partii = master_cost[master_cost["ean"] == ean].iloc[0]["partii"]
        max_inv = max(p["invoice_date"] for p in partii)
        expected_age = (RUN_DATE - max_inv).days
        assert row["Возраст остатка, дней"] == expected_age
        assert isinstance(row["Возраст остатка, дней"], (int,))
        assert row["Возраст остатка, дней"] >= 0


# --- Plan 02: idempotent Sheets write (gspread fully mocked, NO network) ------
class _FakeWorksheet:
    """Records clear()/update() calls; .data holds the last written rows."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.update_count = 0
        self.data: list[list] | None = None

    def clear(self) -> None:
        self.calls.append("clear")
        self.data = None

    def update(self, values, value_input_option=None):
        self.calls.append("update")
        self.update_count += 1
        self.data = values  # overwrite — never append (idempotent)


class _FakeSpreadsheet:
    """worksheet(title) always returns the SAME worksheet (existing sheet, not recreated)."""

    def __init__(self, ws: _FakeWorksheet) -> None:
        self._ws = ws
        self.added: list[str] = []

    def worksheet(self, title):
        return self._ws

    def add_worksheet(self, title, rows, cols):  # pragma: no cover - not hit when ws exists
        self.added.append(title)
        return self._ws


def test_write_is_idempotent_mocked():
    """write_report must clear→update once per run and never duplicate (no network)."""
    from src.sheets_client import write_report

    sample_rows = [["EAN", "name"], [123, "a"], [456, "b"]]
    ws = _FakeWorksheet()
    ss = _FakeSpreadsheet(ws)

    # Run twice — simulate a re-run.
    n1 = write_report(ss, "Отчёт", sample_rows)
    n2 = write_report(ss, "Отчёт", sample_rows)

    # Returns data-row count (rows minus header) each time.
    assert n1 == 2 and n2 == 2
    # Exactly one update per run — batch write, not row-by-row.
    assert ws.update_count == 2
    # clear() always precedes update() within each run.
    assert ws.calls == ["clear", "update", "clear", "update"]
    # Sheet was NOT recreated (sheetId persists for Phase 4).
    assert ss.added == []
    # No duplication: final state == the rows themselves, not rows x 2.
    assert ws.data == sample_rows
    assert len(ws.data) == len(sample_rows)


# --- serializability ---------------------------------------------------------
def test_df_to_rows_serializable(report_df):
    """Column count = 85 (Phase 4 layout: 10 base + 2 cum_summary + 7 analytic + 33 monthly + 33 cum).

    7th analytic col «Распродажа посл. партии, %» added 2026-06-29 (priority gate).
    """
    rows = df_to_rows(report_df)
    assert isinstance(rows, list)
    assert all(isinstance(r, list) for r in rows)
    assert len(rows) == 1301  # header + 1300 data rows
    assert rows[0] == list(report_df.columns)
    # Phase 4 column count: 85 (BASE 10 + CUM_SUMMARY 2 + ANALYTIC 7 + monthly 33 + cum 33)
    assert len(rows[0]) == 85, (
        f"Expected 85 columns after Phase 4 ANALYTIC block, got {len(rows[0])}"
    )
    for r in rows:
        for cell in r:
            assert not isinstance(cell, date), f"date leaked: {cell!r}"
            if isinstance(cell, float):
                assert not math.isnan(cell), "NaN leaked"
            assert cell.__class__.__module__ != "numpy", f"numpy leaked: {cell!r}"
