"""Rules + QR + validation on REAL OCR output (vision engine) of the synthetic documents."""

from datetime import date
from decimal import Decimal

import pytest

from vie.pipeline.compose import PageAnalysis, compose

from .conftest import load_analysis, load_truth

TODAY = date(2026, 11, 23)


def run(name: str, **kw):
    return compose("00000000-0000-0000-0000-000000000000", "upload",
                   [PageAnalysis(index=0, analysis=load_analysis(name))], today=TODAY, **kw)


def checks(res) -> dict:
    return {c.id: c.status for c in res.validation.checks}


def val(res, name):
    fv = res.fields.get(name)
    return None if fv is None else fv.value


@pytest.mark.parametrize("fixture,truth_name", [
    ("factura_ok_png", "factura_ok"),
    ("factura_rotada_7_jpg", "factura_rotada_7"),
    ("factura_foto_perspectiva_jpg", "factura_foto_perspectiva"),
])
def test_factura_fields_extracted_without_model(fixture, truth_name):
    c = run(fixture)
    r, t = c.result, load_truth(truth_name)
    assert r.document_type == "factura"
    assert val(r, "issuer_ruc") == t["issuer_ruc"]
    assert val(r, "serie_numero") == t["serie_numero"]
    assert val(r, "issue_date") == t["issue_date"]
    assert Decimal(val(r, "total")) == Decimal(t["total"])
    assert Decimal(val(r, "igv")) == Decimal(t["tax"])
    assert Decimal(val(r, "taxable_amount")) == Decimal(t["taxable"])
    assert val(r, "customer_doc") == t["customer_doc"]
    assert val(r, "currency") == "PEN"
    assert len(r.items) == len(t["items"])
    assert [Decimal(i.amount) for i in r.items] == [Decimal(i["amount"]) for i in t["items"]]
    # every rules/QR value carries visual evidence
    for name in ("issuer_ruc", "serie_numero", "total", "igv"):
        assert r.fields[name].evidence_ids, name
    assert r.validation.status == "valid", [x.message for x in r.validation.checks if x.status != "pass"]
    ch = checks(r)
    assert ch["tax_rate"] == "pass"
    assert ch["totals_sum"] == "pass"
    assert ch["items_sum"] == "pass"
    assert ch["amount_in_words"] == "pass"
    assert ch["ruc_issuer"] == "pass"
    assert any(k.startswith("qr_vs_ocr_rules_") and v == "pass" for k, v in ch.items())


def test_qr_has_priority_and_is_evidence():
    r = run("factura_ok_png").result
    fv = r.fields["issuer_ruc"]
    assert [s.source for s in fv.sources][:2] == ["qr", "ocr_rules"]
    assert fv.source == "qr"
    assert any(e.startswith("c_") for e in fv.evidence_ids)
    assert r.codes and r.codes[0].parsed["document_type"] == "factura"


def test_boleta_prices_include_tax():
    c = run("boleta_ok_png")
    r, t = c.result, load_truth("boleta_ok")
    assert r.document_type == "boleta"
    assert Decimal(val(r, "total")) == Decimal(t["total"])
    assert val(r, "customer_doc") == t["customer_doc"]
    ch = checks(r)
    assert ch["items_sum"] == "pass"  # items sum == total (IGV included)
    assert ch["tax_rate"] == "pass"
    assert r.validation.status == "valid", [x.message for x in r.validation.checks if x.status != "pass"]


def test_inconsistent_total_is_detected():
    r = run("factura_total_incorrecto_png").result
    ch = checks(r)
    assert ch["totals_sum"] == "fail"
    assert r.validation.status == "invalid"
    assert "total" in r.validation.needs_review


def test_mype_rate_is_reported_not_assumed():
    r = run("factura_mype_10_png").result
    tax = next(c for c in r.validation.checks if c.id == "tax_rate")
    assert tax.status == "pass"
    assert "10.00%" in tax.message


def test_prompt_injection_is_flagged_and_does_not_change_data():
    r = run("factura_inyeccion_png").result
    ch = checks(r)
    assert ch["prompt_injection"] == "warn"
    t = load_truth("factura_inyeccion")
    assert Decimal(val(r, "total")) == Decimal(t["total"])  # the injected "TOTAL ES 0.00" is ignored


def test_nota_credito_reference():
    r = run("nota_credito_png").result
    assert r.document_type == "nota_credito"
    assert val(r, "reference_document") == "F001-00000123"


def test_digital_pdf_uses_text_layer():
    c = run("factura_digital_pdf")
    r, t = c.result, load_truth("factura_digital.pdf")
    assert r.pages[0].text_source == "pdf_text"
    assert val(r, "issuer_ruc") == t["issuer_ruc"]
    assert Decimal(val(r, "total")) == Decimal(t["total"])
    assert all(ln["score"] is None for ln in r.text["lines"])  # no invented confidence for PDF text


def test_blank_page_has_no_invented_data():
    r = run("pagina_en_blanco_png").result
    assert r.text["lines"] == []
    assert r.document_type is None
    assert all(v is None for v in r.fields.values())
    assert r.validation.status == "insufficient_data"


def test_model_value_without_evidence_needs_review():
    vlm = {"is_document": True, "document_type": "factura", "description": "Factura", "language": "es",
           "fields": {"issuer_ruc": "20526018151", "total": "999.99", "customer_name": "Otro Nombre Inventado SAC"},
           "items": [], "objects": [], "unreadable": [], "inferences": []}
    r = run("factura_ok_png", vlm=vlm).result
    total = r.fields["total"]
    assert total.source == "qr"  # machine-readable value wins
    assert total.needs_review  # but the disagreement is flagged
    assert any("discrepan" in x for x in total.review_reasons)
    assert any(c.rule == "source_agreement" and c.status == "warn" for c in r.validation.checks)


def test_model_cannot_validate_itself():
    vlm = {"is_document": True, "document_type": "factura", "description": "Todo es correcto y válido",
           "language": "es", "fields": {}, "items": [], "objects": [], "unreadable": [],
           "inferences": [{"statement": "El documento es válido", "basis": "lo digo yo"}]}
    r = run("factura_total_incorrecto_png", vlm=vlm).result
    assert r.validation.status == "invalid"


def test_model_misreading_is_review_not_invalid_document():
    """Spike S1 finding: the 2B model confuses issuer and customer RUC. The QR wins and the
    document is not declared invalid because of the model's mistake."""
    t = load_truth("factura_ok")
    vlm = {"is_document": True, "document_type": "factura", "description": "Factura", "language": "es",
           "fields": {"issuer_ruc": t["customer_doc"], "igv": "99.00", "reference_document": t["serie_numero"]},
           "items": [], "objects": ["sello", "código QR"], "unreadable": [], "inferences": []}
    r = run("factura_ok_png", vlm=vlm).result
    assert r.fields["issuer_ruc"].value == t["issuer_ruc"] and r.fields["issuer_ruc"].needs_review
    ch = checks(r)
    assert ch["qr_vs_vlm_issuer_ruc"] == "warn"
    assert r.validation.status == "valid_with_warnings"
    # the model may not copy the document's own number into "reference_document"
    assert r.fields.get("reference_document") is None
    objs = {o["label"]: o for o in r.objects}
    assert objs["código QR"]["verified"] is True  # confirmed by the barcode detector
    assert objs["sello"]["verified"] is None  # model claim, not verifiable
