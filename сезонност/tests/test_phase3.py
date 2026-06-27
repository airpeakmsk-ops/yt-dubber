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
NAN_STOCK_EAN = 4525807273205     # has_sales, qty_stock is NaN -> DSI ""
NEG_STOCK_EAN = 4525807289329     # qty_stock < 0 -> DSI ""


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
def test_velocity_and_dsi(report_df, master_cost, oracle_eans):
    for ean in oracle_eans:
        row = report_df[report_df["EAN"] == ean].iloc[0]
        mc_row = master_cost[master_cost["ean"] == ean].iloc[0]
        expected_v = mc_row["qty_sold_total"] / N_MONTHS
        assert row["Скорость, шт/мес"] == pytest.approx(expected_v, abs=1e-6)
        expected_dsi = round(mc_row["qty_stock"] / (expected_v / 30), 1)
        assert row["DSI, дней"] == pytest.approx(expected_dsi)
    # NaN stock -> DSI ""
    nan_row = report_df[report_df["EAN"] == NAN_STOCK_EAN].iloc[0]
    assert nan_row["DSI, дней"] == ""
    # negative stock -> DSI ""
    neg_row = report_df[report_df["EAN"] == NEG_STOCK_EAN].iloc[0]
    assert neg_row["DSI, дней"] == ""


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


# --- serializability ---------------------------------------------------------
def test_df_to_rows_serializable(report_df):
    rows = df_to_rows(report_df)
    assert isinstance(rows, list)
    assert all(isinstance(r, list) for r in rows)
    assert len(rows) == 1301  # header + 1300 data rows
    assert rows[0] == list(report_df.columns)
    for r in rows:
        for cell in r:
            assert not isinstance(cell, date), f"date leaked: {cell!r}"
            if isinstance(cell, float):
                assert not math.isnan(cell), "NaN leaked"
            assert cell.__class__.__module__ != "numpy", f"numpy leaked: {cell!r}"
