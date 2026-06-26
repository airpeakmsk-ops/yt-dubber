"""CBR RF USD/RUB rate lookup with a file-backed cache (DATA-04).

Used for приходы in `поступления товаров/в рублях/` where the exchange rate
is NOT encoded in the filename — we fetch the official CBR rate by invoice date.

CBR notes:
  * URL date format is DD/MM/YYYY.
  * Response XML is encoded windows-1251.
  * <Value> uses a comma decimal ('96,6338'); divide by <Nominal>.
  * For weekends/holidays CBR returns the previous business day's rate
    automatically — no custom retry needed.
"""
import datetime
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CBR_URL = "https://www.cbr.ru/scripts/XML_daily.asp?date_req={}"  # DD/MM/YYYY

# Default on-disk cache location (created on first save).
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "interim" / "cbr_rates_cache.json"

_HTTP_TIMEOUT = 15


def _fetch_usd_rate(date: datetime.date) -> float:
    """Fetch USD/RUB from CBR for a single date (one HTTP request)."""
    url = CBR_URL.format(date.strftime("%d/%m/%Y"))
    with urllib.request.urlopen(url, timeout=_HTTP_TIMEOUT) as resp:
        raw = resp.read()
    xml_text = raw.decode("windows-1251")
    root = ET.fromstring(xml_text)
    for valute in root.findall("Valute"):
        char = valute.findtext("CharCode")
        if char == "USD":
            value = valute.findtext("Value").replace(",", ".")
            nominal = int(valute.findtext("Nominal"))
            return float(value) / nominal
    raise ValueError(f"USD rate not found in CBR response for {date.isoformat()}")


def get_usd_rate(date: datetime.date, cache: dict) -> float:
    """USD/RUB on `date`. Reads/writes `cache` (keyed by date.isoformat()).

    On a cache miss, fetches from CBR and stores the result in `cache`.
    The caller persists `cache` via save_cache() when desired.
    """
    key = date.isoformat()
    if key in cache:
        return cache[key]
    rate = _fetch_usd_rate(date)
    cache[key] = rate
    return rate


def load_cache(path=DEFAULT_CACHE_PATH) -> dict:
    """Load the rate cache from JSON; return {} if the file is absent."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(cache: dict, path=DEFAULT_CACHE_PATH) -> None:
    """Persist the rate cache to JSON, creating parent dirs if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
