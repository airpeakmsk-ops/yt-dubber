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
