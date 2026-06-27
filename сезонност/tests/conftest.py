"""Shared pytest fixtures for the phase-1 test suite.

All data-file paths are built relative to this file's location
(project root = parent of the tests/ directory) so the cyrillic
absolute path is never hard-coded inside test logic.
"""
from pathlib import Path

import pytest

# Project root = parent of tests/ (this file lives in <root>/tests/conftest.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def prikhod_dir() -> Path:
    """Directory of приходы with the exchange rate encoded in the filename."""
    return PROJECT_ROOT / "поступления товаров"


@pytest.fixture
def prikhod_rub_dir() -> Path:
    """Directory of приходы in rubles (no rate in filename — rate from CBR API)."""
    return PROJECT_ROOT / "поступления товаров" / "в рублях"


@pytest.fixture
def prodazhi_file() -> Path:
    """Monthly sales workbook (Покупатель -> Номенклатура)."""
    return PROJECT_ROOT / "все продажи с 2023 по 26июня2026.xlsx"


@pytest.fixture
def ostatki_file() -> Path:
    """Stock-on-hand workbook (Номенклатура x склады)."""
    return PROJECT_ROOT / "остатки все 260626.xlsx"


@pytest.fixture
def mock_cbr_xml() -> str:
    """A small windows-1251-encodable CBR XML response containing a USD Valute.

    Nominal=1, Value='96,6338' (comma decimal as CBR returns).
    Used to monkeypatch urllib in test_cbr_cache without hitting the network.
    """
    return (
        '<?xml version="1.0" encoding="windows-1251"?>'
        '<ValCurs Date="18.09.2023" name="Foreign Currency Market">'
        '<Valute ID="R01235">'
        '<NumCode>840</NumCode>'
        '<CharCode>USD</CharCode>'
        '<Nominal>1</Nominal>'
        '<Name>Доллар США</Name>'
        '<Value>96,6338</Value>'
        '<VunitRate>96,6338</VunitRate>'
        '</Valute>'
        '</ValCurs>'
    )


# --- Phase 3 fixtures (interim parquet paths + oracle EANs) -------------------

@pytest.fixture
def master_cost_path() -> Path:
    """Phase 2 artifact: 1300 EAN spine with per-EAN cost + партии (приходы)."""
    return PROJECT_ROOT / "data" / "interim" / "master_cost.parquet"


@pytest.fixture
def prodazhi_path() -> Path:
    """Phase 1 artifact: long-format monthly sales (ean, month, qty, ...)."""
    return PROJECT_ROOT / "data" / "interim" / "prodazhi.parquet"


@pytest.fixture
def report_df(master_cost_path, prodazhi_path):
    """The fully assembled Phase 3 report DataFrame (offline, no network)."""
    from src.build_report import build_report_df

    return build_report_df(master_cost_path, prodazhi_path)


@pytest.fixture
def oracle_eans() -> list[int]:
    """Two real EAN with non-zero sales AND positive stock — verified 2026-06-27.

    Used for manual cumulative / stock-age checks. Both have:
      - has_sales == True, prodazhi qty sum == master qty_sold_total
      - qty_stock > 0 (so DSI is a real number, not "")
      - max(invoice_date по партиям) == 2025-05-28
    """
    return [4525807270297, 4525807270280]


# --- Phase 4 fixtures ---------------------------------------------------------

@pytest.fixture
def weekly_path() -> Path:
    """Weekly stock workbook: «остатки по неделям.xlsx» (1С TDSheet, Кон.остаток by week)."""
    return PROJECT_ROOT / "остатки по неделям.xlsx"


@pytest.fixture
def weekly_months_map(weekly_path):
    """parse_weekly_stock result: dict[int ean, set[(year, month)]] for all EAN rows."""
    from src.parse_ostatki_weekly import parse_weekly_stock

    return parse_weekly_stock(weekly_path)


@pytest.fixture
def model_aliases_path() -> Path:
    """Absolute path to TIMON model_aliases.json (outside the repo)."""
    return Path("C:/Users/abirv/.claude/shared/timon/model_aliases.json")


@pytest.fixture
def season_map():
    """Seasonal index dict: cal_month (1..12) -> float.

    Imports src.seasonality lazily so collection doesn't fail before Plan 02
    creates the module. Falls back to pytest.skip if the module is absent.
    """
    seasonality = pytest.importorskip("src.seasonality")
    prodazhi_path = PROJECT_ROOT / "data" / "interim" / "prodazhi.parquet"
    import pandas as pd

    prodazhi_df = pd.read_parquet(prodazhi_path)
    return seasonality.compute_global_seasonal_index(prodazhi_df)
