"""Phase-1 Test Map (Wave 0).

Foundation tests (plan 01-01):
  - normalize_ean (DATA / MATCH-01, MATCH-01b)  -> green
  - cbr_rates.get_usd_rate (DATA-04)            -> green (cache mocked, api live)

Pending stubs (implemented red until later plans build against them):
  - parsers   (DATA-01..03)  -> plans 01-02 / 01-03
  - matcher   (MATCH-01/02)  -> plan 01-04
"""
import datetime
import pathlib

import pytest

from src.normalize import normalize_ean


# --------------------------------------------------------------------------
# normalize_ean — the single EAN-key contract (MATCH-01, MATCH-01b)
# --------------------------------------------------------------------------
def test_normalize_ean():
    # float from calamine -> int via int(float(v)), never str(v)
    assert normalize_ean(4525807270297.0) == 4525807270297
    # clean numeric string also accepted
    assert normalize_ean("4525807270297") == 4525807270297
    # footer / header / non-EAN values <= 1e12 are rejected
    assert normalize_ean(45.0) is None
    assert normalize_ean(0) is None
    # garbage / empty
    assert normalize_ean(None) is None
    assert normalize_ean("Итого:") is None


def test_exclude_samples():
    # 9999999999999 = free samples, excluded (MATCH-01b)
    assert normalize_ean(9999999999999.0) is None
    assert normalize_ean("9999999999999") is None


def test_exclude_test_skus():
    # str matching ^\d{13}-\d+$ are test SKUs, excluded
    assert normalize_ean("4525807283518-1") is None
    assert normalize_ean("4525807283518-12") is None


# --------------------------------------------------------------------------
# Pending parser stubs — DATA-01..03 (plans 01-02 / 01-03)
# --------------------------------------------------------------------------
def test_parse_prikhod_basic(prikhod_dir):
    """Parse one real файл with курс in name -> non-empty list[dict] in schema."""
    from src.parse_prikhody import parse_prikhod_file

    path = prikhod_dir / "7 приход курс 94.xlsx"
    records = parse_prikhod_file(path, {})

    assert isinstance(records, list)
    assert len(records) > 0

    keys = {"ean", "name", "qty", "price_rub", "invoice_date", "rate_usd", "rate_source"}
    first = records[0]
    assert keys <= set(first.keys())

    # rate came from the filename ("94") for this file
    assert first["rate_source"] == "filename"
    assert first["rate_usd"] == 94.0

    # ean is an int, not a float-with-.0
    assert all(isinstance(r["ean"], int) for r in records)

    # invoice date parsed from row 2 ('Накладная № 4 от 11 апреля 2024 г.')
    assert first["invoice_date"] == datetime.date(2024, 4, 11)

    # a known EAN from this file is present
    eans = {r["ean"] for r in records}
    assert 4525807255034 in eans


def test_all_prikhod_files_parse(prikhod_dir, prikhod_rub_dir):
    """All 21 source files parse, are represented, and yield a sane EAN count."""
    from src.parse_prikhody import parse_all_prikhody

    df = parse_all_prikhody()

    assert len(df) > 0
    # 16 (с курсом) + 5 (в рублях) = 21 source files represented
    assert df["source_file"].nunique() == 21
    # ~1300 spine EANs per RESEARCH — assert a floor, not a brittle exact number
    assert df["ean"].nunique() > 1000

    # в рублях/ files must use the CBR API rate source with positive rates
    cbr_rows = df[df["rate_source"] == "cbr_api"]
    assert len(cbr_rows) > 0
    assert (cbr_rows["rate_usd"] > 0).all()


def test_no_footer_rows(prikhod_dir):
    """Footer/header rows never appear; every ean is a valid 13-digit EAN."""
    from src.parse_prikhody import parse_prikhod_file

    records = parse_prikhod_file(prikhod_dir / "7 приход курс 94.xlsx", {})

    for r in records:
        name = str(r["name"])
        assert "Итого" not in name
        assert "Всего наименований" not in name
        assert r["ean"] > 1e12
        assert r["ean"] != 9999999999999


def test_prodazhi_month_count(prodazhi_file):
    """build_month_map returns exactly 33 months, first 'Октябрь 2023', none 'Итог'."""
    import python_calamine as pc

    from src.parse_prodazhi import build_month_map

    ws = pc.CalamineWorkbook.from_path(str(prodazhi_file)).get_sheet_by_name("TDSheet")
    rows = list(ws.iter_rows())
    months = build_month_map(rows)

    assert len(months) == 33
    assert str(months[0]["label"]).startswith("Октябрь 2023")
    assert all(m["label"] != "Итог" for m in months)


def test_prodazhi_no_name_rows(prodazhi_file):
    """EAN-rows only; no name-row duplication; samples/test-SKU/footer dropped."""
    from src.parse_prodazhi import parse_prodazhi

    df = parse_prodazhi(prodazhi_file)

    # a known EAN that sells across months
    known = 4525807270297
    sub = df[df["ean"] == known]
    assert len(sub) > 0, "known EAN must have records"
    # each month appears at most once for this EAN (no name-row duplication)
    assert sub["month"].is_unique

    # free-sample EAN never present
    assert 9999999999999 not in df["ean"].values

    # every emitted ean is a clean 13-digit int (proves '-1' test SKUs and
    # name/footer rows were dropped, not just sample EANs)
    assert df["ean"].map(lambda e: isinstance(e, (int,)) and not isinstance(e, bool)).all()
    assert df["ean"].map(lambda e: 1_000_000_000_000 <= e < 10_000_000_000_000).all()


def test_ostatki_ean_count(ostatki_file):
    """parse_ostatki -> DataFrame(ean,name,qty_stock); >800 EANs, samples excluded."""
    import pandas as pd

    from src.parse_ostatki import parse_ostatki

    df = parse_ostatki(ostatki_file)

    assert list(df.columns) == ["ean", "name", "qty_stock"]
    # ~959 expected — assert a floor, not a brittle exact
    assert df["ean"].nunique() > 800
    # free-sample EAN excluded
    assert 9999999999999 not in df["ean"].values
    # every ean is a clean 13-digit int
    assert df["ean"].map(lambda e: 1_000_000_000_000 <= e < 10_000_000_000_000).all()
    # qty_stock is numeric. NOTE: it can be negative — 1С free stock goes
    # negative when reserved exceeds physical on-hand (a real urgent-reorder
    # signal), so we assert numeric dtype, not non-negativity.
    assert pd.api.types.is_numeric_dtype(df["qty_stock"])
    # each EAN-row carries a name label
    assert df["name"].notna().all()


def test_rate_extraction():
    """extract_rate_from_filename: float for all 16 курс files, None for the 5 в рублях."""
    from src.parse_prikhody import extract_rate_from_filename

    # 16 files with курс in the name -> exact float
    expected = {
        "11 приход 103,79": 103.79,
        "12.1 приход курс 97,28 (2)": 97.28,
        "12.2 приход курс 97,28": 97.28,
        "13 приход курс 89,57": 89.57,
        "14 приход курс 79,71": 79.71,
        "15 приход курс 79,79": 79.79,
        "16 приход курс 86,67": 86.67,
        "17 приход курс 83,69": 83.69,
        "18 приход  курс 87,59": 87.59,
        "19 приход курс 85,05": 85.05,
        "20 приход курс 82,72": 82.72,
        "3 приход курс 89,67": 89.67,
        "6 приход курс 95,8": 95.8,
        "7 приход курс 94": 94.0,
        "8 приход курс 96": 96.0,
        "9 приход курс 89,54": 89.54,
    }
    for stem, rate in expected.items():
        assert extract_rate_from_filename(stem) == rate, stem

    # 5 в рублях/ files have no rate in the name -> None
    for stem in ["1 приход", "10 приход ", "14 приход", "2 приход", "4 приход "]:
        assert extract_rate_from_filename(stem) is None, stem


# --------------------------------------------------------------------------
# cbr_rates tests — DATA-04
# --------------------------------------------------------------------------
@pytest.mark.live
def test_cbr_api():
    """Live CBR lookup for a known invoice date (~96.63, tolerance +/- 1.0)."""
    from src import cbr_rates

    rate = cbr_rates.get_usd_rate(datetime.date(2023, 9, 18), {})
    assert isinstance(rate, float)
    assert abs(rate - 96.63) < 1.0


def test_cbr_cache(monkeypatch, mock_cbr_xml):
    """Second lookup for the same date hits the cache — exactly ONE HTTP call."""
    from src import cbr_rates

    calls = {"n": 0}

    class _FakeResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _fake_urlopen(url, timeout=None):
        calls["n"] += 1
        return _FakeResponse(mock_cbr_xml.encode("windows-1251"))

    monkeypatch.setattr(cbr_rates.urllib.request, "urlopen", _fake_urlopen)

    cache: dict = {}
    d = datetime.date(2023, 9, 18)

    r1 = cbr_rates.get_usd_rate(d, cache)
    r2 = cbr_rates.get_usd_rate(d, cache)

    assert abs(r1 - 96.6338) < 1e-6
    assert r1 == r2
    assert calls["n"] == 1  # second call served from cache, no extra HTTP


# --------------------------------------------------------------------------
# Pending matcher stubs — MATCH-01 / MATCH-02 (plan 01-04)
# --------------------------------------------------------------------------
_INTERIM = pathlib.Path(__file__).resolve().parent.parent / "data" / "interim"
_PARQUETS_READY = all(
    (_INTERIM / f"{n}.parquet").exists()
    for n in ("prikhody", "prodazhi", "ostatki")
)
_skip_no_parquet = pytest.mark.skipif(
    not _PARQUETS_READY,
    reason="interim parquets not built — run plans 01-02/01-03 first",
)


@_skip_no_parquet
def test_join_coverage_sales():
    """Sale EANs present in the приход spine >= 1282 and coverage > 90%."""
    from src.build_master import build_master

    _master, report = build_master()

    assert report["n_sales_in_spine"] >= 1282
    assert report["coverage_pct_sales"] > 90


@_skip_no_parquet
def test_join_coverage_stock():
    """Stock EANs present in the приход spine >= 955 and coverage > 90%."""
    from src.build_master import build_master

    _master, report = build_master()

    assert report["n_stock_in_spine"] >= 955
    assert report["coverage_pct_stock"] > 90


def test_unmatched_report():
    pytest.fail("pending plan 01-04")
