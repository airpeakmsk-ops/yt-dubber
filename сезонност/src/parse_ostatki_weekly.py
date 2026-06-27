"""parse_ostatki_weekly — weekly stock parser for «остатки по неделям.xlsx».

Produces a dict[int EAN, set[(year, month)]] representing every calendar month
in which the EAN had at least one week with Кон.остаток > 0.

File structure (1С TDSheet, verified 2026-06-27):
  Row 9  : column headers — col 1 = «Номенклатура, Базовая единица измерения»,
            cols 2..N = «Неделя с DD.MM.YYYY»
  Row 10 : «Номенклатура.Артикул» | «Количество»
  Row 11 : (empty) | «Кон. остаток»
  Rows 12+: PAIRS of rows per product — (name_row, ean_row).
            Both rows carry identical Кон.остаток values in weekly columns.
            Use ONLY EAN-rows (where normalize_ean(col1) is not None) to avoid
            double-counting. EAN values are in col index 1 (0-based).

Algorithm:
  1. Parse col-index → week_date from row 9 headers («Неделя с DD.MM.YYYY»).
  2. Iterate rows 12+; skip rows where normalize_ean(col1) is None.
  3. For each EAN row, collect (year, month) tuples for all week columns with val > 0.
  4. Return dict[ean → set[(year, month)]].

Pitfalls handled:
  - Pitfall 1: data duplicated on both rows of pair — only EAN-rows used.
  - Pitfall 2: non-7-day gaps between weeks (6 gaps of 14–28 days) — month
    membership requires only ≥1 week with stock > 0, not continuity.
  - Pitfall 6: EAN absent from weekly file → caller uses fallback (N_MONTHS_DEFAULT=33).

Coverage: 1324 EAN in file; 1300/1300 master EAN covered (100%).
"""
from __future__ import annotations

import logging
import pathlib
import sys
from datetime import datetime

import pandas as pd

# Allow `python src/parse_ostatki_weekly.py` without ModuleNotFoundError.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.normalize import normalize_ean  # EAN contract — DO NOT reimplement

log = logging.getLogger(__name__)

# Fallback months_in_stock for EAN absent from weekly file (Pitfall 6).
_FALLBACK_MONTHS = 33


def parse_weekly_stock(path) -> dict[int, set[tuple[int, int]]]:
    """Parse «остатки по неделям.xlsx» → dict[EAN, set[(year, month)]].

    Returns a mapping from integer EAN to the set of (year, month) tuples in
    which that EAN had Кон.остаток > 0 for at least one week.

    Args:
        path: Path-like or str to the xlsx workbook.

    Returns:
        dict[int, set[tuple[int, int]]] — EAN → set of (year, month) pairs.
    """
    df = pd.read_excel(path, sheet_name=0, header=None, engine="calamine")

    # --- Step 1: build col_index -> week_date from row 9 headers ---------------
    week_col_dates: dict[int, object] = {}  # col_index -> datetime.date
    for c in range(2, len(df.columns)):
        raw = df.iloc[9, c]
        if not isinstance(raw, str):
            # calamine may return the string or a parsed date; normalise to str
            raw = str(raw).strip()
        h = raw.strip()
        if h.startswith("Неделя с "):
            date_str = h.replace("Неделя с ", "").strip()
            try:
                week_date = datetime.strptime(date_str, "%d.%m.%Y").date()
                week_col_dates[c] = week_date
            except ValueError:
                log.warning("Unparseable week header at col %d: %r", c, h)

    if not week_col_dates:
        raise ValueError(
            f"No «Неделя с DD.MM.YYYY» headers found in row 9 of {path}. "
            "Check that engine='calamine' reads the file correctly."
        )

    log.info("Found %d week columns in %s", len(week_col_dates), path)

    # --- Step 2–3: iterate EAN rows (rows 12+), collect (year, month) sets ----
    result: dict[int, set[tuple[int, int]]] = {}
    skipped_name_rows = 0

    for i in range(12, len(df)):
        raw_col1 = df.iloc[i, 1]
        ean = normalize_ean(raw_col1)
        if ean is None:
            skipped_name_rows += 1
            continue  # name-row or footer — skip

        months_with_stock: set[tuple[int, int]] = set()
        for c, week_date in week_col_dates.items():
            val = df.iloc[i, c]
            if pd.notna(val) and val > 0:
                months_with_stock.add((week_date.year, week_date.month))

        result[ean] = months_with_stock

    log.info(
        "parse_weekly_stock: %d EAN rows parsed, %d name/footer rows skipped",
        len(result),
        skipped_name_rows,
    )
    return result


def months_in_stock(weekly_map: dict[int, set], ean: int, default: int = _FALLBACK_MONTHS) -> int:
    """Return number of months with stock > 0 for ean, or default if absent.

    Args:
        weekly_map: result of parse_weekly_stock().
        ean:        integer EAN to look up.
        default:    fallback when EAN is absent from the weekly file (Pitfall 6).
                    Defaults to 33 (full period, backward-compatible with Phase 3).

    Returns:
        int >= 0 — number of (year, month) pairs with stock > 0.
    """
    if ean in weekly_map:
        return len(weekly_map[ean])
    log.debug("EAN %d absent from weekly map; using fallback %d months", ean, default)
    return default


# --- Smoke-test entrypoint ----------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Project root is one level above src/
    project_root = Path(__file__).resolve().parent.parent
    weekly_file = project_root / "остатки по неделям.xlsx"

    if not weekly_file.exists():
        print(f"ERROR: file not found: {weekly_file}", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print(f"Parsing {weekly_file} ...")
    wmap = parse_weekly_stock(weekly_file)
    print(f"Total EAN rows parsed: {len(wmap)}")

    # Oracle check
    oracle_ean = 4525807270297
    if oracle_ean in wmap:
        m = months_in_stock(wmap, oracle_ean)
        print(f"Oracle EAN {oracle_ean}: months_in_stock = {m}  (expected 18)")
    else:
        print(f"WARNING: oracle EAN {oracle_ean} not found in result!")

    # Coverage against master
    master_path = project_root / "data" / "interim" / "master_cost.parquet"
    if master_path.exists():
        import pandas as pd  # noqa: F811

        master = pd.read_parquet(master_path)
        master_eans = set(master["ean"].astype(int))
        intersection = master_eans & set(wmap.keys())
        print(f"Master EAN coverage: {len(intersection)}/{len(master_eans)}")
    else:
        print(f"(master_cost.parquet not found, skipping coverage check)")
