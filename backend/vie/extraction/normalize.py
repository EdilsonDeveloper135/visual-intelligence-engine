"""Normalisation of dates, money, currencies and numbers found in Peruvian documents.

All functions are pure and return None when the input cannot be interpreted —
they never guess.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

MONTHS_ES = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3, "abril": 4, "abr": 4,
    "mayo": 5, "may": 5, "junio": 6, "jun": 6, "julio": 7, "jul": 7, "agosto": 8, "ago": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "set": 9, "sept": 9, "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11, "diciembre": 12, "dic": 12,
}

CURRENCY_PATTERNS = [
    (re.compile(r"US\s*\$|U\.S\.\s*\$|\bUSD\b|D[OÓ]LAR(ES)?(\s+AMERICANOS)?", re.I), "USD"),
    (re.compile(r"S/\.?|\bPEN\b|\bSOLES\b|\bSOL\b|NUEVOS\s+SOLES", re.I), "PEN"),
    (re.compile(r"€|\bEUR\b|\bEUROS?\b", re.I), "EUR"),
]


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def detect_currency(text: str | None) -> str | None:
    if not text:
        return None
    for pattern, code in CURRENCY_PATTERNS:
        if pattern.search(text):
            return code
    if "$" in text:
        return "USD"
    return None


_NUM_RE = re.compile(r"-?\d[\d.,\s]*\d|-?\d")


def parse_decimal(text: str | None) -> Decimal | None:
    """Parse '1,234.56', '1.234,56', '1 234,56', '128.62', '-5' -> Decimal. None if ambiguous/invalid."""
    if text is None:
        return None
    if isinstance(text, (int, float, Decimal)):
        return Decimal(str(text))
    s = str(text).strip()
    m = _NUM_RE.search(s.replace("O", "0") if re.fullmatch(r"[\dO.,\s-]+", s) else s)
    if not m:
        return None
    num = m.group(0).replace(" ", "")
    neg = num.startswith("-")
    num = num.lstrip("-")
    last_dot, last_comma = num.rfind("."), num.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        decimal_sep = "." if last_dot > last_comma else ","
    elif last_comma >= 0:
        # "1,234" (thousands) vs "12,50" (decimal): 2 digits after the comma -> decimal
        tail = num[last_comma + 1:]
        decimal_sep = "," if len(tail) in (1, 2) and num.count(",") == 1 else None
    elif last_dot >= 0:
        tail = num[last_dot + 1:]
        decimal_sep = "." if not (len(tail) == 3 and num.count(".") >= 1 and len(num) > 4) else None
        if num.count(".") > 1:
            decimal_sep = None
    else:
        decimal_sep = None
    if decimal_sep == ".":
        cleaned = num.replace(",", "")
    elif decimal_sep == ",":
        cleaned = num.replace(".", "").replace(",", ".")
    else:
        cleaned = num.replace(",", "").replace(".", "")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if neg else value


def parse_money(text: str | None) -> tuple[Decimal | None, str | None]:
    if text is None:
        return None, None
    return parse_decimal(text), detect_currency(str(text))


def money_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value.quantize(Decimal("0.01")))


_DATE_NUMERIC = re.compile(r"\b(\d{1,4})[/\-.](\d{1,2})[/\-.](\d{1,4})\b")
_DATE_TEXT = re.compile(r"\b(\d{1,2})\s*(?:de\s+)?([A-Za-zÁÉÍÓÚáéíóú]{3,10})\.?\s*(?:de|del)?\s*(\d{2,4})\b", re.I)


def _year(y: int) -> int:
    return y + 2000 if y < 100 else y


def parse_date(text: str | None, dayfirst: bool = True) -> date | None:
    """Parse Peruvian date formats. Returns None if invalid or ambiguous beyond dd/mm convention."""
    if not text:
        return None
    s = str(text).strip()
    m = _DATE_NUMERIC.search(s)
    if m:
        a, b, c = (int(x) for x in m.groups())
        try:
            if len(m.group(1)) == 4:  # ISO yyyy-mm-dd
                return date(a, b, c)
            if dayfirst:
                return date(_year(c), b, a)
            return date(_year(c), a, b)
        except ValueError:
            return None
    m = _DATE_TEXT.search(s)
    if m:
        day, month_name, year = m.groups()
        month = MONTHS_ES.get(strip_accents(month_name).lower())
        if month:
            try:
                return date(_year(int(year)), month, int(day))
            except ValueError:
                return None
    return None


def clean_text(value: str | None, max_len: int = 500) -> str | None:
    """Sanitise free text coming from documents/models: drop control chars, collapse spaces, cap length."""
    if value is None:
        return None
    s = "".join(ch for ch in str(value) if ch == "\n" or (ord(ch) >= 32 and ord(ch) != 127))
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s[:max_len] if s else None


def digits(text: str | None) -> str:
    return re.sub(r"\D", "", text or "")
