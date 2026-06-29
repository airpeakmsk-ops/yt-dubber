"""Parse all 21 приход (incoming-invoice) files into one DataFrame (DATA-01, DATA-04).

приходы are the master spine — the set of all products that ever entered the
warehouse. Every downstream join (продажи, остатки) is left-joined onto these EANs.

Two source folders (read directly from project root):
  * "поступления товаров/*.xlsx"          — 16 files, курс encoded in the filename
  * "поступления товаров/в рублях/*.xlsx"  — 5 files, no курс -> CBR API by invoice date

Each приход file is a 1C TDSheet export read via python-calamine (openpyxl can't
open them — no sharedStrings.xml). Column layout is uniform across all 21 files.
"""
import datetime
import re
import sys
from pathlib import Path

import pandas as pd
import python_calamine

# Project root = parent of src/ (this file lives in <root>/src/parse_prikhody.py).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Allow `python src/parse_prikhody.py` (script mode) to resolve the `src.` package
# the same way pytest / `python -m` already do.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cbr_rates import get_usd_rate, load_cache, save_cache  # noqa: E402
from src.normalize import normalize_ean  # noqa: E402
PRIKHOD_DIR = PROJECT_ROOT / "поступления товаров"
PRIKHOD_RUB_DIR = PRIKHOD_DIR / "в рублях"

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
PARQUET_PATH = INTERIM_DIR / "prikhody.parquet"
CBR_CACHE_PATH = INTERIM_DIR / "cbr_rates_cache.json"

# Verified column indices (TDSheet, header_row=8, data from row index 10).
COL_EAN = 2
COL_NAME = 5
COL_QTY = 20
COL_PRICE = 25
COL_TOTAL = 28

# Файлы, исключаемые из приходов (решение пользователя 2026-06-29).
# «4 приход .xlsx» = Накладная №2 от 01.02.2024 — НЕ настоящий приход (возврат/переучёт).
# Проверено: все 72 EAN этой накладной есть в других приходах → исключение не теряет товаров.
EXCLUDED_PRIKHOD_FILES = {"4 приход .xlsx"}

# ⛔ Семантика колонки «Цена» зависит от типа файла (CODE_DOMAIN: multi-source one-column trap):
#   - файлы «в рублях/» (rate_source=cbr_api): цена УЖЕ в рублях
#   - файлы «X приход курс YY,YY» (rate_source=filename): цена в ВАЛЮТЕ (USD), курс в имени
#     переводит её в рубли → price_rub = цена * курс. Иначе compute_cost делит на курс повторно.

_RATE_RE = re.compile(r"(?:приход|курс)\s+([\d,\.]+)")

_RU_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


def extract_rate_from_filename(stem: str) -> float | None:
    """USD/RUB rate encoded in the filename, or None for в рублях/ files.

    e.g. "11 приход 103,79" -> 103.79, "7 приход курс 94" -> 94.0.
    Returns None when no numeric rate follows 'приход'/'курс' (the 5 в рублях names).
    """
    m = _RATE_RE.search(stem)
    if not m:
        return None
    raw = m.group(1).strip(".,").replace(",", ".")
    if not raw:
        return None
    return float(raw)


def parse_invoice_date(rows) -> datetime.date:
    """Invoice date from row index 2: 'Накладная № N от DD Month YYYY г.'."""
    m = re.search(r"от (\d+) (\w+) (\d{4})", str(rows[2][0]))
    if not m:
        raise ValueError(f"invoice date not found in: {rows[2][0]!r}")
    day, mon_str, year = int(m[1]), m[2], int(m[3])
    return datetime.date(year, _RU_MONTHS[mon_str], day)


def parse_prikhod_file(path, cbr_cache: dict) -> list[dict]:
    """Parse one приход file into a list of row-dicts in the documented schema.

    Footer/header rows are dropped via the EAN filter (isinstance float and > 1e12),
    then normalize_ean removes samples (9999...) and any residual non-EAN noise.
    Duplicate-EAN rows within one file are real партии (different price) — KEPT.
    """
    path = Path(path)
    wb = python_calamine.CalamineWorkbook.from_path(str(path))
    ws = wb.get_sheet_by_name("TDSheet")
    rows = list(ws.iter_rows())

    invoice_date = parse_invoice_date(rows)
    rate = extract_rate_from_filename(path.stem)
    if rate is not None:
        rate_source = "filename"
    else:
        rate = get_usd_rate(invoice_date, cbr_cache)
        rate_source = "cbr_api"

    records: list[dict] = []
    for row in rows[10:]:
        if len(row) <= COL_EAN:
            continue
        ean_raw = row[COL_EAN]
        # Footer/header rows have non-float or <=1e12 in the EAN column.
        if not isinstance(ean_raw, float) or ean_raw <= 1e12:
            continue
        ean = normalize_ean(ean_raw)
        if ean is None:  # samples (9999...) and residual noise
            continue
        raw_price = row[COL_PRICE]
        # «курс в имени» -> цена в валюте (USD); переводим в рубли (см. примечание у COL_PRICE).
        # «в рублях» -> цена уже в рублях, оставляем как есть.
        price_rub = raw_price * rate if rate_source == "filename" else raw_price
        records.append({
            "ean": ean,
            "name": row[COL_NAME],
            "qty": row[COL_QTY],
            "price_rub": price_rub,
            "invoice_date": invoice_date,
            "rate_usd": rate,
            "rate_source": rate_source,
            "source_file": path.name,
        })
    return records


def parse_all_prikhody(cbr_cache: dict | None = None) -> pd.DataFrame:
    """Parse all 21 приход files (both folders) into one DataFrame.

    Keeps duplicate-EAN rows (партии). The schema is:
    ean, name, qty, price_rub, invoice_date, rate_usd, rate_source, source_file.
    """
    if cbr_cache is None:
        cbr_cache = load_cache(CBR_CACHE_PATH)

    # 16 files with курс in name (top folder only, not the в рублях/ subfolder).
    files = sorted(p for p in PRIKHOD_DIR.glob("*.xlsx"))
    # 5 files без курса (CBR by invoice date).
    files += sorted(PRIKHOD_RUB_DIR.glob("*.xlsx"))
    # Исключённые накладные (не приходы — решение пользователя).
    files = [p for p in files if p.name not in EXCLUDED_PRIKHOD_FILES]

    records: list[dict] = []
    for path in files:
        records.extend(parse_prikhod_file(path, cbr_cache))

    df = pd.DataFrame(records, columns=[
        "ean", "name", "qty", "price_rub",
        "invoice_date", "rate_usd", "rate_source", "source_file",
    ])
    df["ean"] = df["ean"].astype("int64")
    return df


def main() -> None:
    """Parse all приходы, persist parquet + CBR cache, print a one-line summary."""
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    cache = load_cache(CBR_CACHE_PATH)

    df = parse_all_prikhody(cache)

    save_cache(cache, CBR_CACHE_PATH)
    df.to_parquet(PARQUET_PATH, engine="pyarrow", index=False)

    by_source = df["rate_source"].value_counts()
    n_cbr = int(by_source.get("cbr_api", 0))
    n_filename = int(by_source.get("filename", 0))
    print(
        f"prikhody: {df['source_file'].nunique()} files, {len(df)} rows, "
        f"{df['ean'].nunique()} unique EAN, "
        f"rate_source: filename={n_filename} cbr_api={n_cbr} "
        f"-> {PARQUET_PATH}"
    )


if __name__ == "__main__":
    main()
