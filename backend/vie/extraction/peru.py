"""Peruvian identifiers and SUNAT electronic-invoice conventions."""

from __future__ import annotations

import re
from datetime import date

from .normalize import parse_date, parse_decimal

RUC_WEIGHTS = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
RUC_PREFIXES = {"10", "15", "16", "17", "20"}

# SUNAT catalogue 01 (tipo de comprobante) -> internal document type
SUNAT_DOC_TYPES = {
    "01": "factura",
    "03": "boleta",
    "07": "nota_credito",
    "08": "nota_debito",
    "09": "guia_remision",
    "31": "guia_remision",
    "12": "ticket",
    "14": "recibo_servicios_publicos",
}

# SUNAT catalogue 06 (tipo de documento de identidad)
SUNAT_ID_TYPES = {"0": "sin_documento", "1": "DNI", "4": "carnet_extranjeria", "6": "RUC", "7": "pasaporte",
                  "A": "cedula_diplomatica", "-": "sin_documento"}


def ruc_check_digit(first10: str) -> int:
    total = sum(int(d) * w for d, w in zip(first10, RUC_WEIGHTS))
    r = 11 - (total % 11)
    return 0 if r == 10 else 1 if r == 11 else r


def ruc_is_valid(ruc: str | None) -> bool:
    if not ruc or not re.fullmatch(r"\d{11}", ruc):
        return False
    if ruc[:2] not in RUC_PREFIXES:
        return False
    return ruc_check_digit(ruc[:10]) == int(ruc[10])


def ruc_problem(ruc: str | None) -> str | None:
    """Human-readable reason why a RUC is invalid, or None if valid."""
    if not ruc:
        return "vacío"
    if not re.fullmatch(r"\d{11}", ruc):
        return "debe tener exactamente 11 dígitos"
    if ruc[:2] not in RUC_PREFIXES:
        return f"prefijo {ruc[:2]} no válido (10, 15, 16, 17 o 20)"
    if ruc_check_digit(ruc[:10]) != int(ruc[10]):
        return "dígito verificador incorrecto (módulo 11)"
    return None


def dni_is_valid(dni: str | None) -> bool:
    return bool(dni) and re.fullmatch(r"\d{8}", dni) is not None


SERIE_NUMERO_RE = re.compile(r"(?<![0-9/-])([FBETV][A-Z0-9]{3})\s*[-–—]\s*(\d{1,8})(?!\d)")


def parse_serie_numero(text: str | None) -> tuple[str, str] | None:
    if not text:
        return None
    m = SERIE_NUMERO_RE.search(text.upper())
    if not m:
        return None
    return m.group(1), m.group(2)


def serie_doc_type(serie: str | None) -> str | None:
    """Document type implied by the series prefix of an electronic voucher."""
    if not serie:
        return None
    s = serie.upper()
    if s.startswith(("FC", "BC")):
        return "nota_credito"
    if s.startswith(("FD", "BD")):
        return "nota_debito"
    if s.startswith("F"):
        return "factura"
    if s.startswith("B"):
        return "boleta"
    if s.startswith(("T", "V")):
        return "guia_remision"
    if s.startswith("E"):
        return None  # issued through SUNAT's SEE-SOL portal: type cannot be inferred from the prefix
    return None


def parse_sunat_qr(text: str | None) -> dict | None:
    """Parse the QR of a SUNAT electronic voucher.

    Format: RUC|TIPO|SERIE|NUMERO|IGV|TOTAL|FECHA|TIPO DOC ADQ|NRO DOC ADQ|[HASH|]
    Returns None if the text does not follow the format.
    """
    if not text or "|" not in text:
        return None
    parts = [p.strip() for p in text.strip().strip("|").split("|")]
    if len(parts) < 7 or not re.fullmatch(r"\d{11}", parts[0]) or not re.fullmatch(r"\d{2}", parts[1]):
        return None
    issue: date | None = parse_date(parts[6])
    igv, total = parse_decimal(parts[4]), parse_decimal(parts[5])
    out = {
        "issuer_ruc": parts[0],
        "doc_type_code": parts[1],
        "document_type": SUNAT_DOC_TYPES.get(parts[1]),
        "serie": parts[2].upper(),
        "numero": parts[3],
        "serie_numero": f"{parts[2].upper()}-{parts[3]}",
        "igv": str(igv) if igv is not None else None,
        "total": str(total) if total is not None else None,
        "issue_date": issue.isoformat() if issue else None,
        "customer_doc_type_code": parts[7] if len(parts) > 7 else None,
        "customer_doc_type": SUNAT_ID_TYPES.get(parts[7]) if len(parts) > 7 else None,
        "customer_doc": parts[8] if len(parts) > 8 and parts[8] not in ("", "-", "0") else None,
        "hash": parts[9] if len(parts) > 9 and parts[9] else None,
    }
    return out
