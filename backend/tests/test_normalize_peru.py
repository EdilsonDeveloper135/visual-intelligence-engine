from datetime import date
from decimal import Decimal

import pytest

from vie.extraction.normalize import clean_text, detect_currency, parse_date, parse_decimal, parse_money
from vie.extraction.peru import (dni_is_valid, parse_serie_numero, parse_sunat_qr, ruc_check_digit, ruc_is_valid,
                                 ruc_problem, serie_doc_type)
from vie.extraction.words import parse_amount_in_words, words_to_int


@pytest.mark.parametrize("text,expected", [
    ("128.62", "128.62"), ("S/ 1,234.56", "1234.56"), ("1.234,56", "1234.56"), ("12,50", "12.50"),
    ("1,234", "1234"), ("US$ 99", "99"), ("-5.00", "-5.00"), ("1 234,50", "1234.50"), ("abc", None),
])
def test_parse_decimal(text, expected):
    got = parse_decimal(text)
    assert (str(got) if got is not None else None) == expected


@pytest.mark.parametrize("text,cur", [("S/ 10", "PEN"), ("S/. 10", "PEN"), ("SOLES", "PEN"), ("US$ 5", "USD"),
                                      ("DÓLARES AMERICANOS", "USD"), ("$ 5", "USD"), ("10.00", None)])
def test_detect_currency(text, cur):
    assert detect_currency(text) == cur


def test_parse_money():
    assert parse_money("S/ 128.62") == (Decimal("128.62"), "PEN")


@pytest.mark.parametrize("text,expected", [
    ("15/11/2026", date(2026, 11, 15)), ("Fecha de Emisión: 02/11/2026", date(2026, 11, 2)),
    ("2026-11-15", date(2026, 11, 15)), ("15-11-26", date(2026, 11, 15)),
    ("23 de noviembre de 2026", date(2026, 11, 23)), ("5 SET 2026", date(2026, 9, 5)),
    ("31/02/2026", None), ("sin fecha", None),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_clean_text_removes_control_chars_and_caps_length():
    assert clean_text("a\x00b\x1b[31m  c", 50) == "ab[31m c"
    assert len(clean_text("x" * 1000, 10)) == 10


def test_ruc_checksum():
    # check digit computed independently from the weights 5,4,3,2,7,6,5,4,3,2
    assert ruc_check_digit("2052601815") == 1
    assert ruc_is_valid("20526018151")
    assert not ruc_is_valid("20526018152")
    assert not ruc_is_valid("30526018151")  # invalid prefix
    assert ruc_problem("123") == "debe tener exactamente 11 dígitos"
    assert "verificador" in ruc_problem("20526018152")


def test_dni():
    assert dni_is_valid("12345678")
    assert not dni_is_valid("1234567")


def test_serie_numero_and_type():
    assert parse_serie_numero("F001-00000123") == ("F001", "00000123")
    assert parse_serie_numero("Serie: B002 - 4567") == ("B002", "4567")
    assert serie_doc_type("F001") == "factura"
    assert serie_doc_type("B002") == "boleta"
    assert serie_doc_type("FC01") == "nota_credito"
    assert serie_doc_type("T001") == "guia_remision"
    assert serie_doc_type("E001") is None


def test_sunat_qr():
    qr = parse_sunat_qr("20526018151|01|F001|00000123|19.62|128.62|2026-11-15|6|20908301669|aGFzaA==|")
    assert qr["issuer_ruc"] == "20526018151"
    assert qr["document_type"] == "factura"
    assert qr["serie_numero"] == "F001-00000123"
    assert qr["total"] == "128.62" and qr["igv"] == "19.62"
    assert qr["issue_date"] == "2026-11-15"
    assert qr["customer_doc_type"] == "RUC" and qr["customer_doc"] == "20908301669"
    assert parse_sunat_qr("https://example.com") is None
    assert parse_sunat_qr("hola|mundo") is None


def test_amount_in_words():
    assert words_to_int("CIENTO VEINTIOCHO") == 128
    assert words_to_int("DOS MIL QUINIENTOS TREINTA Y UNO") == 2531
    assert words_to_int("UN MILLON DOSCIENTOS MIL") == 1_200_000
    assert parse_amount_in_words("SON: CIENTO VEINTIOCHO CON 62/100 SOLES") == Decimal("128.62")
    assert parse_amount_in_words("SON: CIEN CON 00/100 SOLES") == Decimal("100.00")
    assert parse_amount_in_words("texto cualquiera") is None
