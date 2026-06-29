"""order_plan — pure compute module for Phase 4 order planning and stock labels.

Provides the 6 analytical columns (cols M–R) and row presort for the report:
  M  % продаж к приходам      pct_sales()
  N  Зелёный товар             green_item() (re-exported from report_metrics)
  O  Индекс сезона (след. 2 мес)  avg_next2_index() — season_map passed as param
  P  К заказу на 2 мес        compute_order_qty()
  Q  Мёртвый                   is_dead()
  R  Залежалый                 is_stale()

CRITICAL (Pitfall 5): this module MUST NOT import build_report.
Dependency direction: build_report -> order_plan (one-way only).
avg_season_idx is always passed as a parameter — never imported from seasonality here.

Locked formulas (CONTEXT C, 04-CONTEXT.md):
  pct_sales = qty_sold_total / qty_prikhod (штуки, вся история).
  Порог ORDER-01: pct_sales >= 0.60 (60%).
  ORDER-02: К заказу = max(0, round(velocity*2*avg_season_idx - qty_stock, 1));
            '' if pct_sales < 0.60. Negative qty_stock -> treat as 0.
  Мёртвый   = qty_stock > 0 AND recent_12mo_sales == 0.
  Залежалый = recent_12mo_sales > 0 AND (DSI > 90 OR age_days > 180).
              Mutually exclusive with Мёртвый.
  Presort   = sort by (dsi_bucket ASC, DSI numeric ASC); '' -> bucket 4 -> last.

RUN_DATE = 2026-06-27. Last 12 months window: (2025, 7) .. (2026, 6) inclusive.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd

# sys.path bootstrap: allow `python src/order_plan.py` and pytest to find siblings.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.report_metrics import dsi_bucket, green_item, sht_per_month, dsi_days  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ORDER-01 threshold (LOCKED): pct_sales must be >= 60% to be eligible for reorder.
ORDER_THRESHOLD: float = 0.60

# Priority sell-through gate (user 2026-06-29): товары, у которых продано < 70%
# от ПОСЛЕДНЕЙ закупки (после её даты), НЕ должны попадать в приоритет дозаказа
# (верх списка / малый DSI). Они демотируются в presort, цвет DSI сохраняется.
PRIORITY_SELL_THROUGH_THRESHOLD: float = 0.70

# Имя колонки доли распродажи последней партии (используется presort для приоритета).
SELL_THROUGH_COL: str = "Распродажа посл. партии, %"

# SEASON-02: Dead-stock cutoff — last 12 months relative to RUN_DATE 2026-06-27.
# Window: July 2025 (2025, 7) .. June 2026 (2026, 6), inclusive.
DEAD_CUTOFF: tuple[int, int] = (2025, 7)

# Stale thresholds (Claude's Discretion, documented default per 04-CONTEXT.md C).
STALE_DSI_THRESHOLD: float = 90.0   # days — DSI > 90 -> stale
STALE_AGE_THRESHOLD: float = 180.0  # days — stock age > 180 -> stale


# ---------------------------------------------------------------------------
# ORDER-01: % продаж к приходам
# ---------------------------------------------------------------------------

def pct_sales(qty_sold_total, qty_prikhod) -> float | str:
    """Fraction of received units that have been sold (ORDER-01).

    Args:
        qty_sold_total: total units sold over full history.
        qty_prikhod:    total units received over full history.

    Returns:
        float (0.0–1.0+) if qty_prikhod > 0, else "" (sentinel — no fill, no order).
    """
    if qty_prikhod is None:
        return ""
    try:
        p = float(qty_prikhod)
    except (TypeError, ValueError):
        return ""
    if pd.isna(p) or p <= 0:
        return ""
    try:
        s = float(qty_sold_total)
    except (TypeError, ValueError):
        return ""
    return s / p


# ---------------------------------------------------------------------------
# Priority gate: распродажа последней партии
# ---------------------------------------------------------------------------

def sell_through_last_batch(last_qty, qty_stock) -> float | str:
    """Доля распродажи последней партии по истощению остатка (user 2026-06-29).

    = (last_qty − текущий_остаток) / last_qty, клампится в [0, 1].

    Смысл: сколько последней закупки уже ушло со склада. Распроданный товар
    (остаток 0) -> 1.0 (распродан полностью -> в приоритете дозаказа). Большая
    недавняя закупка с высоким остатком -> низкая доля -> демотируется.
    Отрицательный/NaN остаток -> 0 (нет доступного остатка -> распродан -> 1.0).
    Остаток больше партии (накоплен из прежних партий) -> кламп в 0 (не распродан).

    last_qty:   кол-во последней партии (самая свежая по дате накладной).
    qty_stock:  текущий суммарный остаток.

    Returns float in [0,1] if last_qty > 0, else "" (нет данных о последней закупке).
    """
    if last_qty is None:
        return ""
    try:
        lq = float(last_qty)
    except (TypeError, ValueError):
        return ""
    if pd.isna(lq) or lq <= 0:
        return ""
    try:
        stock = float(qty_stock)
    except (TypeError, ValueError):
        stock = 0.0
    if pd.isna(stock) or stock < 0:
        stock = 0.0
    ratio = (lq - stock) / lq
    return max(0.0, min(1.0, ratio))


def is_priority_eligible(sell_through) -> bool:
    """True если товар может попадать в приоритет дозаказа (распродажа посл. партии >= 70%).

    sell_through: доля (float) или "" (нет данных) -> НЕ eligible (демотируется).
    """
    if sell_through == "" or sell_through is None:
        return False
    try:
        v = float(sell_through)
    except (TypeError, ValueError):
        return False
    if pd.isna(v):
        return False
    return v >= PRIORITY_SELL_THROUGH_THRESHOLD


# ---------------------------------------------------------------------------
# ORDER-02: К заказу на 2 мес
# ---------------------------------------------------------------------------

def compute_order_qty(
    velocity: float,
    qty_stock,
    pct,
    avg_season_idx: float,
) -> float | str:
    """Compute 2-month reorder quantity with seasonal adjustment (ORDER-02, LOCKED).

    Formula (order of operations locked):
        raw = velocity * 2 * avg_season_idx - stock
        К заказу = max(0, round(raw, 1))

    Returns "" when pct_sales < ORDER_THRESHOLD (0.60) or pct is sentinel "".
    Negative qty_stock is treated as 0 (CONTEXT C locked detail).

    Args:
        velocity:       availability-based шт/мес (months_in_stock denominator).
        qty_stock:      current stock; NaN or < 0 -> treated as 0.
        pct:            pct_sales fraction (float) or "" sentinel.
        avg_season_idx: average seasonal index for the next 2 months (July + Aug 2026).
                        Passed as parameter — NOT imported from seasonality (Pitfall 5).

    Returns:
        float >= 0.0 (rounded to 1 dp) or "" if ineligible.
    """
    # Eligibility check (ORDER-01 gate)
    if pct == "" or pct is None:
        return ""
    try:
        pct_f = float(pct)
    except (TypeError, ValueError):
        return ""
    if pd.isna(pct_f) or pct_f < ORDER_THRESHOLD:
        return ""

    # Treat negative or NaN stock as 0 (LOCKED detail)
    if qty_stock is None:
        stock = 0.0
    else:
        try:
            stock = float(qty_stock)
        except (TypeError, ValueError):
            stock = 0.0
        if pd.isna(stock) or stock < 0:
            stock = 0.0

    raw = float(velocity) * 2 * float(avg_season_idx) - stock
    return max(0.0, round(raw, 1))


# ---------------------------------------------------------------------------
# SEASON-02: Мёртвый / Залежалый flags
# ---------------------------------------------------------------------------

def is_dead(qty_stock, recent_12mo_sales: float) -> bool:
    """Return True if the item is «Мёртвый» (dead stock).

    Dead = qty_stock > 0 AND 0 sales in the last 12 months (CONTEXT C, LOCKED).
    Negative or NaN stock -> False (no positive physical stock to worry about).

    Args:
        qty_stock:        current stock (may be NaN or negative).
        recent_12mo_sales: sum of qty sold in last 12 months (Jul 2025..Jun 2026).

    Returns:
        bool
    """
    if qty_stock is None:
        return False
    try:
        stock = float(qty_stock)
    except (TypeError, ValueError):
        return False
    if pd.isna(stock) or stock <= 0:
        return False
    return float(recent_12mo_sales) == 0


def is_stale(dsi_val, age_days: float, recent_12mo_sales: float) -> bool:
    """Return True if the item is «Залежалый» (stale/slow-moving).

    Stale = recent_12mo_sales > 0 AND (DSI > 90 OR age_days > 180).
    Mutually exclusive with is_dead: recent == 0 -> False (that's the dead category).

    Args:
        dsi_val:           DSI in days (numeric) or "" sentinel (no stock -> not stale).
        age_days:          age of freshest batch in days (stock_age_days result).
        recent_12mo_sales: sum of qty sold in last 12 months.

    Returns:
        bool
    """
    if recent_12mo_sales == 0:
        return False  # dead category, not stale

    # Parse DSI; sentinel "" -> treat as 0 (no stock means no DSI trigger)
    if dsi_val == "" or dsi_val is None:
        dsi_num = 0.0
    else:
        try:
            dsi_num = float(dsi_val)
        except (TypeError, ValueError):
            dsi_num = 0.0

    return dsi_num > STALE_DSI_THRESHOLD or float(age_days) > STALE_AGE_THRESHOLD


# ---------------------------------------------------------------------------
# VISUAL-03: Presort by DSI bucket
# ---------------------------------------------------------------------------

def presort_by_dsi(df: pd.DataFrame) -> pd.DataFrame:
    """Sort so the TOP is the actionable reorder priority list (user 2026-06-29).

    Primary key:   приоритет-годность — товары, распродавшие < 70% последней партии,
                   демотируются ВНИЗ (не попадают в приоритет). Eligible=0, иначе=1.
                   Если колонки SELL_THROUGH_COL нет (юнит-тесты presort) — все eligible.
    Secondary key: dsi_bucket(DSI, дней) ascending (0=red..4=no_stock).
    Tertiary key:  numeric DSI ascending within bucket (lowest DSI = most urgent first).
    '' / NaN DSI -> bucket 4 (low); numeric key = 9999.

    Цвет DSI (VISUAL-01) НЕ зависит от сортировки — демотированные строки сохраняют заливку.
    Does NOT modify the input DataFrame — returns a sorted copy with reset index.

    Args:
        df: DataFrame with column «DSI, дней» (и опционально SELL_THROUGH_COL).

    Returns:
        Sorted copy of df with index reset to 0..N-1.
    """
    df = df.copy()
    if SELL_THROUGH_COL in df.columns:
        df["_e"] = df[SELL_THROUGH_COL].map(lambda v: 0 if is_priority_eligible(v) else 1)
    else:
        df["_e"] = 0  # presort unit-tests pass a df without the sell-through column
    df["_b"] = df["DSI, дней"].map(dsi_bucket)
    df["_d"] = pd.to_numeric(df["DSI, дней"], errors="coerce").fillna(9999)
    # Доп. ключ: внутри одинакового DSI (в т.ч. DSI=0 распроданных) — скорость по убыванию
    # (самые ходовые выше). Сортируем по −скорость как возрастающий ключ.
    if "Скорость, шт/мес" in df.columns:
        df["_v"] = -pd.to_numeric(df["Скорость, шт/мес"], errors="coerce").fillna(0.0)
    else:
        df["_v"] = 0.0
    df = df.sort_values(["_e", "_b", "_d", "_v"], ascending=[True, True, True, True])
    return df.drop(columns=["_e", "_b", "_d", "_v"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# enrich_df — single assembly point for 6 analytical columns (M..R)
# ---------------------------------------------------------------------------

def enrich_df(
    df: pd.DataFrame,
    master_df: pd.DataFrame,
    prodazhi_df: pd.DataFrame,
    season_map: dict[int, float],
    weekly_months_map: dict[int, set],
    next_months: tuple[int, int] = (7, 8),
) -> pd.DataFrame:
    """Add 6 analytical columns (M..R) to the report DataFrame.

    Column order (LOCKED, per 04-RESEARCH.md layout):
      M  % продаж к приходам
      N  Зелёный товар
      O  Индекс сезона (след. 2 мес)
      P  К заказу на 2 мес
      Q  Мёртвый
      R  Залежалый

    Velocity source: df must already contain «Скорость, шт/мес» (computed by build_report
    using months_in_stock from weekly_months_map — availability-based, not fixed 33).
    DSI is taken from df column «DSI, дней».
    Возраст остатка is taken from df column «Возраст остатка, дней».

    avg_season_idx is computed here from season_map[next_months] so callers don't need
    to pre-compute it. season_map is accepted as a plain dict parameter (no seasonality
    module import — Pitfall 5 guard).

    NOTE: presort_by_dsi is NOT called here. build_report calls it after enrich_df
    so that the sort sees all columns including the new ones.

    Args:
        df:               assembled report DataFrame (must have EAN, Скорость, DSI, Возраст).
        master_df:        master_cost DataFrame with qty_sold_total, qty_prikhod, qty_stock.
        prodazhi_df:      long-format sales (ean, sort_key tuple, qty).
        season_map:       dict[cal_month_num (1..12) -> float seasonal index].
        weekly_months_map: dict[ean -> set[(year, month)]] from parse_ostatki_weekly.
        next_months:      tuple of 2 calendar month numbers for seasonal avg (default Jul+Aug).

    Returns:
        df with 6 new columns appended in order M..R.
    """
    # Compute avg seasonal index for the next 2 months
    avg_idx = sum(season_map[m] for m in next_months) / len(next_months)

    # Build lookup dicts from master_df indexed by EAN
    master_indexed = master_df.set_index("ean") if "ean" in master_df.columns else master_df.set_index(master_df.columns[0])
    qty_prikhod_map = master_indexed["qty_prikhod"].to_dict()
    qty_sold_map = master_indexed["qty_sold_total"].to_dict()
    qty_stock_map = master_indexed["qty_stock"].to_dict()

    # Compute recent 12-month sales per EAN from prodazhi_df
    # recent = sum of qty where sort_key >= DEAD_CUTOFF
    recent_sales_map: dict = {}
    if "sort_key" in prodazhi_df.columns:
        recent_df = prodazhi_df[prodazhi_df["sort_key"] >= DEAD_CUTOFF]
        recent_sales_map = recent_df.groupby("ean")["qty"].sum().to_dict()
    elif "month" in prodazhi_df.columns:
        # fallback: parse sort_key from month label using report_metrics
        from src.report_metrics import month_sort_key as _msk
        prodazhi_df = prodazhi_df.copy()
        prodazhi_df["_sk"] = prodazhi_df["month"].map(_msk)
        recent_df = prodazhi_df[prodazhi_df["_sk"] >= DEAD_CUTOFF]
        recent_sales_map = recent_df.groupby("ean")["qty"].sum().to_dict()

    # --- last-batch qty (priority gate by stock depletion, user 2026-06-29) -------
    # last_qty_map[ean] = qty последней партии (самая свежая по дате накладной).
    last_qty_map: dict = {}
    if "partii" in master_df.columns and "ean" in master_df.columns:
        for ean_v, partii in zip(master_df["ean"], master_df["partii"]):
            try:
                last_dt = max(p["invoice_date"] for p in partii)
            except (ValueError, TypeError, KeyError):
                continue
            lm = (last_dt.year, last_dt.month)
            last_qty_map[ean_v] = sum(
                p["qty"] for p in partii
                if (p["invoice_date"].year, p["invoice_date"].month) == lm
            )

    # EAN column — first column of df
    ean_col = df.columns[0]  # «EAN» or similar

    rows_pct = []
    rows_green = []
    rows_idx = []
    rows_order = []
    rows_dead = []
    rows_stale = []
    rows_sellthru = []

    for _, row in df.iterrows():
        ean = row[ean_col]

        # % продаж к приходам (col M)
        sold = qty_sold_map.get(ean, 0)
        prikhod = qty_prikhod_map.get(ean, 0)
        pct = pct_sales(sold, prikhod)
        rows_pct.append(pct)

        # Зелёный товар (col N) — "Да" / ""
        velocity = row.get("Скорость, шт/мес", 0) if "Скорость, шт/мес" in df.columns else 0
        rows_green.append("Да" if green_item(velocity) else "")

        # Индекс сезона (след. 2 мес) (col O)
        rows_idx.append(round(avg_idx, 4))

        # К заказу на 2 мес (col P)
        order_qty = compute_order_qty(velocity, qty_stock_map.get(ean), pct, avg_idx)
        rows_order.append(order_qty)

        # Мёртвый (col Q)
        recent = recent_sales_map.get(ean, 0)
        stock = qty_stock_map.get(ean, 0)
        dead = is_dead(stock, recent)
        rows_dead.append("Мёртвый" if dead else "")

        # Залежалый (col R) — mutually exclusive with Мёртвый; только при положительном остатке
        # (распроданный товар с остатком 0 — не залежалый, даже если возраст > 180 дней).
        dsi_val = row.get("DSI, дней", "")
        age = row.get("Возраст остатка, дней", 0) or 0
        try:
            stock_pos = float(stock) > 0
        except (TypeError, ValueError):
            stock_pos = False
        stale = (not dead) and stock_pos and is_stale(dsi_val, age, recent)
        rows_stale.append("Залежалый" if stale else "")

        # Распродажа посл. партии, % (col S) — priority gate by stock depletion (user 2026-06-29)
        st = sell_through_last_batch(last_qty_map.get(ean), qty_stock_map.get(ean))
        rows_sellthru.append(round(st, 3) if st != "" else "")

    df = df.copy()
    df["% продаж к приходам"] = rows_pct
    df["Зелёный товар"] = rows_green
    df["Индекс сезона (след. 2 мес)"] = rows_idx
    df["К заказу на 2 мес"] = rows_order
    df["Мёртвый"] = rows_dead
    df["Залежалый"] = rows_stale
    df[SELL_THROUGH_COL] = rows_sellthru

    return df
