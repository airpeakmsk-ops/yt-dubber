"""Phase-1 Test Map (Wave 0).

Foundation tests (plan 01-01):
  - normalize_ean (DATA / MATCH-01, MATCH-01b)  -> green
  - cbr_rates.get_usd_rate (DATA-04)            -> green (cache mocked, api live)

Pending stubs (implemented red until later plans build against them):
  - parsers   (DATA-01..03)  -> plans 01-02 / 01-03
  - matcher   (MATCH-01/02)  -> plan 01-04
"""
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
def test_parse_prikhod_basic():
    pytest.fail("pending plan 01-02")


def test_all_prikhod_files_parse():
    pytest.fail("pending plan 01-02")


def test_no_footer_rows():
    pytest.fail("pending plan 01-02")


def test_prodazhi_month_count():
    pytest.fail("pending plan 01-03")


def test_prodazhi_no_name_rows():
    pytest.fail("pending plan 01-03")


def test_ostatki_ean_count():
    pytest.fail("pending plan 01-03")


def test_rate_extraction():
    pytest.fail("pending plan 01-02")


# --------------------------------------------------------------------------
# cbr_rates tests — DATA-04 (implemented green in task 3 of this plan)
# --------------------------------------------------------------------------
def test_cbr_api():
    pytest.fail("pending plan 01-01 task 3")


def test_cbr_cache():
    pytest.fail("pending plan 01-01 task 3")


# --------------------------------------------------------------------------
# Pending matcher stubs — MATCH-01 / MATCH-02 (plan 01-04)
# --------------------------------------------------------------------------
def test_join_coverage_sales():
    pytest.fail("pending plan 01-04")


def test_join_coverage_stock():
    pytest.fail("pending plan 01-04")


def test_unmatched_report():
    pytest.fail("pending plan 01-04")
