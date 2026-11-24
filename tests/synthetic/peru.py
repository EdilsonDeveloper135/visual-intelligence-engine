"""Peruvian document helpers used only to build *synthetic* test data.

Nothing here is real data: company names are fictitious and RUC numbers are
generated with a valid check digit from a deterministic seed.
"""

from __future__ import annotations

import random
from decimal import ROUND_HALF_UP, Decimal

RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def ruc_check_digit(first10: str) -> int:
    total = sum(int(d) * w for d, w in zip(first10, RUC_WEIGHTS))
    r = 11 - (total % 11)
    if r == 10:
        return 0
    if r == 11:
        return 1
    return r


def make_ruc(rng: random.Random, prefix: str = "20") -> str:
    body = prefix + "".join(str(rng.randint(0, 9)) for _ in range(8))
    return body + str(ruc_check_digit(body))


def make_dni(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(8))


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value: Decimal, symbol: str = "S/") -> str:
    return f"{symbol} {value:,.2f}"


_UNITS = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
_TEENS = {
    10: "DIEZ", 11: "ONCE", 12: "DOCE", 13: "TRECE", 14: "CATORCE", 15: "QUINCE",
    16: "DIECISEIS", 17: "DIECISIETE", 18: "DIECIOCHO", 19: "DIECINUEVE",
    20: "VEINTE", 21: "VEINTIUNO", 22: "VEINTIDOS", 23: "VEINTITRES", 24: "VEINTICUATRO",
    25: "VEINTICINCO", 26: "VEINTISEIS", 27: "VEINTISIETE", 28: "VEINTIOCHO", 29: "VEINTINUEVE",
}
_TENS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_HUNDREDS = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
             "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]


def _below_thousand(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "CIEN"
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if rest:
        if rest < 10:
            parts.append(_UNITS[rest])
        elif rest < 30:
            parts.append(_TEENS[rest])
        else:
            t, u = divmod(rest, 10)
            parts.append(_TENS[t] + (f" Y {_UNITS[u]}" if u else ""))
    return " ".join(parts)


def number_to_words_es(n: int) -> str:
    if n == 0:
        return "CERO"
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    parts = []
    if millions:
        parts.append("UN MILLON" if millions == 1 else f"{_below_thousand(millions)} MILLONES")
    if thousands:
        parts.append("MIL" if thousands == 1 else f"{_below_thousand(thousands)} MIL")
    if units:
        parts.append(_below_thousand(units))
    return " ".join(parts)


def amount_in_words(value: Decimal, currency_word: str = "SOLES") -> str:
    integer = int(value)
    cents = int(q2(value - integer) * 100)
    return f"SON: {number_to_words_es(integer)} CON {cents:02d}/100 {currency_word}"
