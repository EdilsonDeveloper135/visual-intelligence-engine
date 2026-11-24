"""Parse Spanish amounts written in words ("SON: CIENTO VEINTIOCHO CON 62/100 SOLES")."""

from __future__ import annotations

import re
from decimal import Decimal

from .normalize import strip_accents

UNITS = {
    "CERO": 0, "UN": 1, "UNO": 1, "UNA": 1, "DOS": 2, "TRES": 3, "CUATRO": 4, "CINCO": 5, "SEIS": 6, "SIETE": 7,
    "OCHO": 8, "NUEVE": 9, "DIEZ": 10, "ONCE": 11, "DOCE": 12, "TRECE": 13, "CATORCE": 14, "QUINCE": 15,
    "DIECISEIS": 16, "DIECISIETE": 17, "DIECIOCHO": 18, "DIECINUEVE": 19, "VEINTE": 20, "VEINTIUN": 21,
    "VEINTIUNO": 21, "VEINTIDOS": 22, "VEINTITRES": 23, "VEINTICUATRO": 24, "VEINTICINCO": 25,
    "VEINTISEIS": 26, "VEINTISIETE": 27, "VEINTIOCHO": 28, "VEINTINUEVE": 29, "TREINTA": 30, "CUARENTA": 40,
    "CINCUENTA": 50, "SESENTA": 60, "SETENTA": 70, "OCHENTA": 80, "NOVENTA": 90, "CIEN": 100, "CIENTO": 100,
    "DOSCIENTOS": 200, "TRESCIENTOS": 300, "CUATROCIENTOS": 400, "QUINIENTOS": 500, "SEISCIENTOS": 600,
    "SETECIENTOS": 700, "OCHOCIENTOS": 800, "NOVECIENTOS": 900,
    "DOSCIENTAS": 200, "TRESCIENTAS": 300, "CUATROCIENTAS": 400, "QUINIENTAS": 500, "SEISCIENTAS": 600,
    "SETECIENTAS": 700, "OCHOCIENTAS": 800, "NOVECIENTAS": 900,
}


def words_to_int(text: str) -> int | None:
    tokens = [t for t in re.split(r"[\s-]+", strip_accents(text).upper()) if t and t != "Y"]
    if not tokens:
        return None
    total, current = 0, 0
    for tok in tokens:
        if tok in UNITS:
            current += UNITS[tok]
        elif tok == "MIL":
            current = max(current, 1) * 1000
            total += current
            current = 0
        elif tok in ("MILLON", "MILLONES"):
            current = max(current, 1) * 1_000_000
            total += current
            current = 0
        else:
            return None
    return total + current


def parse_amount_in_words(text: str | None) -> Decimal | None:
    """Return the amount expressed in a 'SON: ...' line, or None if it cannot be parsed reliably."""
    if not text:
        return None
    s = strip_accents(text).upper()
    s = re.sub(r"^\s*SON\s*[:.]?\s*", "", s)
    m = re.match(r"(.+?)\s+(?:CON\s+)?(\d{1,2})\s*/\s*100", s)
    if not m:
        return None
    integer = words_to_int(m.group(1).replace(" CON", ""))
    if integer is None:
        return None
    return Decimal(integer) + Decimal(int(m.group(2))) / 100
