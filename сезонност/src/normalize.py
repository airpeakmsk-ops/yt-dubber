"""normalize_ean — the single EAN-key contract for the whole pipeline.

All three parsers and the matcher route EAN values through this one function
so the exclusion rules (free samples, test SKUs, footer/non-EAN noise) are
authoritative in exactly one place.
"""
import re

# 13-digit EAN-13 are >= 1_000_000_000_000; anything at/below is footer/header noise.
_MIN_EAN = 1_000_000_000_000

# Free-sample marker EAN (excluded — MATCH-01b).
_SAMPLE_EAN = 9999999999999

# Test SKUs look like a 13-digit EAN with a -N suffix, e.g. '4525807283518-1'.
_TEST_SKU_RE = re.compile(r"^\d{13}-\d+$")


def normalize_ean(v) -> int | None:
    """Coerce a raw cell value to a clean 13-digit EAN int, or return None.

    Returns None when the value is:
      * the free-sample marker 9999999999999 (MATCH-01b),
      * a test SKU string matching ^\\d{13}-\\d+$,
      * any numeric value <= 1_000_000_000_000 (footer/header/non-EAN),
      * empty / non-numeric / None.

    Floats from calamine are coerced with int(float(v)) — NEVER str(v),
    which would leave a trailing '.0' and corrupt the key.
    """
    if v is None:
        return None

    # Strings: reject test SKUs first, then require a clean numeric body.
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        if _TEST_SKU_RE.match(s):
            return None
        try:
            ean = int(float(s))
        except (ValueError, TypeError):
            return None
    else:
        # Numeric (float/int from calamine).
        try:
            ean = int(float(v))
        except (ValueError, TypeError):
            return None

    if ean == _SAMPLE_EAN:
        return None
    if ean <= _MIN_EAN:
        return None
    return ean
