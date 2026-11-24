"""Merge candidate values from QR, OCR rules and the multimodal model.

Priority: QR (machine-readable) > OCR rules (validated) > model. Every candidate
is kept in `sources`; disagreements and values without OCR evidence are flagged
for human review. The model never overrides a validated machine-readable value.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

from ..doc_schemas.registry import DOCUMENT_TYPES, DocSchema
from ..models.result import (DocumentTypeInfo, Entity, FieldSource, FieldValue, Inference, Item, Relationship,
                             TextLine, Unreadable)
from .grounding import ground
from .layout import union_bbox
from .normalize import (clean_text, detect_currency, digits, money_str, parse_date, parse_decimal,
                        strip_accents)
from .peru import parse_serie_numero, ruc_is_valid
from .rules import RulesResult

QR_FIELD_MAP = {"issuer_ruc": "issuer_ruc", "serie_numero": "serie_numero", "igv": "igv", "total": "total",
                "issue_date": "issue_date", "customer_doc": "customer_doc"}


def normalize_value(typ: str, raw: Any) -> tuple[Any, dict]:
    """Normalise a raw string according to the field type. Returns (value, extras)."""
    if raw is None:
        return None, {}
    s = clean_text(str(raw), 500)
    if not s or s.lower() in ("null", "none", "n/a", "-", "no visible", "ilegible"):
        return None, {}
    extra: dict = {}
    if typ in ("money", "decimal"):
        v = parse_decimal(s)
        cur = detect_currency(s)
        if cur:
            extra["currency"] = cur
        return (money_str(v) if typ == "money" else (str(v) if v is not None else None)), extra
    if typ == "percent":
        v = parse_decimal(s.replace("%", ""))
        return (str(v) if v is not None else None), extra
    if typ == "integer":
        v = parse_decimal(s)
        return (int(v) if v is not None and v == v.to_integral_value() else None), extra
    if typ == "date":
        d = parse_date(s)
        return (d.isoformat() if d else None), extra
    if typ == "ruc":
        d = digits(s)
        return (d if len(d) == 11 else None), extra
    if typ == "dni":
        d = digits(s)
        return (d if len(d) == 8 else None), extra
    if typ == "doc_id":
        d = digits(s)
        if len(d) == 11:
            extra["doc_type"] = "RUC"
        elif len(d) == 8:
            extra["doc_type"] = "DNI"
        return (d or None), extra
    if typ == "serie_numero":
        sn = parse_serie_numero(s)
        return (f"{sn[0]}-{sn[1]}" if sn else s.upper()), extra
    if typ == "currency":
        cur = detect_currency(s) or (s.upper() if s.upper() in ("PEN", "USD", "EUR") else None)
        return cur, extra
    return s, extra


def same_value(typ: str, a: Any, b: Any) -> bool:
    if a is None or b is None:
        return True
    if typ in ("money", "decimal", "percent"):
        da, db = parse_decimal(str(a)), parse_decimal(str(b))
        return da is not None and db is not None and abs(da - db) <= Decimal("0.01")
    if typ in ("ruc", "dni", "doc_id"):
        return digits(str(a)) == digits(str(b))
    if typ in ("string", "text"):
        na = re.sub(r"\W+", " ", strip_accents(str(a)).upper()).strip()
        nb = re.sub(r"\W+", " ", strip_accents(str(b)).upper()).strip()
        return fuzz.ratio(na, nb) >= 88 or (len(na) > 6 and (na in nb or nb in na))
    return str(a).strip().upper() == str(b).strip().upper()


def _code_bbox(codes: list[dict], code_id: str | None) -> tuple[list[int] | None, int | None]:
    for c in codes:
        if c.get("id") == code_id:
            return c.get("bbox"), c.get("page")
    return None, None


def merge_fields(schema: DocSchema, rules: RulesResult, vlm: dict | None, lines: list[TextLine],
                 codes: list[dict]) -> dict[str, FieldValue | None]:
    vlm_fields = (vlm or {}).get("fields") if isinstance((vlm or {}).get("fields"), dict) else {}
    names = [f.name for f in schema.fields] if not schema.dynamic else []
    # generic fields found by rules are kept even in universal mode
    for name in rules.fields:
        if name not in names:
            names.append(name)
    out: dict[str, FieldValue | None] = {}
    for name in names:
        spec = schema.field(name)
        typ = spec.type if spec else (rules.fields[name].type if name in rules.fields else "string")
        cands: list[tuple[str, Any, FieldValue | None, dict]] = []

        if rules.qr and name in QR_FIELD_MAP and rules.qr.get(QR_FIELD_MAP[name]):
            qv, qextra = normalize_value(typ, rules.qr[QR_FIELD_MAP[name]])
            if qv is not None:
                cands.append(("qr", qv, None, qextra))
        rfv = rules.fields.get(name)
        if rfv is not None and rfv.value is not None:
            if not (typ == "ruc" and not ruc_is_valid(str(rfv.value))):
                cands.append(("ocr_rules", rfv.value, rfv, {}))
        if name in vlm_fields:
            vv, vextra = normalize_value(typ, vlm_fields.get(name))
            if vv is not None:
                cands.append(("vlm", vv, None, vextra))

        if name == "reference_document":
            own_sn = (rules.qr or {}).get("serie_numero") or (rules.fields.get("serie_numero").value
                                                              if rules.fields.get("serie_numero") else None)
            cands = [c for c in cands if not (own_sn and str(c[1]).upper() == str(own_sn).upper())]
        if not cands:
            out[name] = None
            continue
        source, value, base, extra = cands[0]
        sources = [FieldSource(source=s, value=v, raw=(b.raw if b else None),
                               evidence_ids=(b.evidence_ids if b else []))
                   for s, v, b, _ in cands]
        if source == "ocr_rules" and base is not None:
            fv = base.model_copy(deep=True)
            fv.sources = sources
        else:
            fv = FieldValue(value=value, raw=None, type=typ, provenance="observed", source=source, sources=sources,
                            **{k: v for k, v in extra.items() if k in ("currency",)})
            if source == "qr":
                bbox, page = _code_bbox(codes, rules.qr_evidence)
                fv.evidence_ids = [rules.qr_evidence] if rules.qr_evidence else []
                fv.bounding_box, fv.page = bbox, page
                # also anchor to the printed value if the OCR read it
                printed = ground(value, typ, lines, limit=2)
                if printed:
                    # point the user at the printed value; the QR remains as additional evidence
                    fv.evidence_ids += [ln.id for ln in printed]
                    fv.bounding_box, fv.page = printed[0].bbox, printed[0].page
            else:  # vlm
                hits = ground(value, typ, lines)
                if hits:
                    fv.evidence_ids = [ln.id for ln in hits]
                    fv.bounding_box = union_bbox([ln.bbox for ln in hits[:1]])
                    fv.page = hits[0].page
                    fv.sources[0].evidence_ids = fv.evidence_ids
                elif typ != "currency":
                    fv.needs_review = True
                    fv.review_reasons.append("Valor propuesto por el modelo sin evidencia en el texto OCR.")
        if "doc_type" in extra and not getattr(fv, "doc_type", None):
            setattr(fv, "doc_type", extra["doc_type"])
        distinct = [c for c in cands if not same_value(typ, c[1], value)]
        if distinct:
            fv.needs_review = True
            detail = ", ".join(f"{s}={v}" for s, v, _, _ in cands)
            fv.review_reasons.append(f"Las fuentes discrepan ({detail}).")
        out[name] = fv
    return out


def merge_items(rules: RulesResult, vlm: dict | None, lines: list[TextLine]) -> list[Item]:
    if rules.items and all(it.amount for it in rules.items):
        return rules.items
    items: list[Item] = []
    for raw in (vlm or {}).get("items") or []:
        if not isinstance(raw, dict):
            continue
        desc = clean_text(raw.get("description"), 300)
        if not desc:
            continue
        qty, _ = normalize_value("decimal", raw.get("quantity"))
        price, _ = normalize_value("money", raw.get("unit_price"))
        amount, _ = normalize_value("money", raw.get("amount"))
        hits = ground(desc, "string", lines, limit=1)
        it = Item(description=desc, quantity=qty, unit=clean_text(raw.get("unit"), 20), unit_price=price,
                  amount=amount, provenance="observed", source="vlm")
        if hits:
            it.evidence_ids = [h.id for h in hits]
            it.bounding_box, it.page = hits[0].bbox, hits[0].page
        else:
            it.needs_review = True
        items.append(it)
    return items or rules.items


def merge_dynamic(vlm: dict | None, lines: list[TextLine]) -> list[dict]:
    out = []
    raw_fields = (vlm or {}).get("fields")
    if not isinstance(raw_fields, list):
        return out
    seen = set()
    for f in raw_fields:
        if not isinstance(f, dict):
            continue
        key = re.sub(r"[^a-z0-9_]", "_", strip_accents(str(f.get("key") or "")).lower()).strip("_")[:60]
        if not key or key in seen:
            continue
        seen.add(key)
        typ = f.get("type") if f.get("type") in ("money", "decimal", "date", "ruc", "dni", "doc_id", "percent",
                                                  "integer", "currency", "serie_numero") else "string"
        value, extra = normalize_value(typ, f.get("value"))
        hits = ground(value, typ, lines) if value is not None else []
        fv = FieldValue(value=value, raw=clean_text(f.get("value"), 300), type=typ, provenance="observed",
                        source="vlm", sources=[FieldSource(source="vlm", value=value)],
                        evidence_ids=[h.id for h in hits],
                        bounding_box=hits[0].bbox if hits else None, page=hits[0].page if hits else None,
                        needs_review=not hits,
                        review_reasons=[] if hits else ["Campo dinámico sin evidencia en el texto OCR."],
                        **{k: v for k, v in extra.items() if k == "currency"})
        out.append({"key": key, "label": clean_text(f.get("label"), 120) or key, **fv.model_dump()})
    return out


def document_type(rules: RulesResult, vlm: dict | None) -> DocumentTypeInfo:
    info = DocumentTypeInfo(rules=rules.document_type, qr=(rules.qr or {}).get("document_type"))
    vt = (vlm or {}).get("document_type")
    info.vlm = vt if vt in DOCUMENT_TYPES else None
    serie = rules.fields.get("serie_numero")
    from .peru import serie_doc_type

    serie_type = serie_doc_type(str(serie.value).split("-")[0]) if serie and serie.value else None
    info.final = info.qr or info.rules or serie_type or info.vlm
    return info


def vlm_lists(vlm: dict | None) -> tuple[list[Unreadable], list[Inference], list[dict]]:
    unreadable = [Unreadable(element=clean_text(u, 200)) for u in (vlm or {}).get("unreadable") or []
                  if isinstance(u, str) and clean_text(u, 200)]
    inferences = []
    for inf in (vlm or {}).get("inferences") or []:
        if isinstance(inf, dict) and clean_text(inf.get("statement"), 300):
            inferences.append(Inference(statement=clean_text(inf.get("statement"), 300),
                                        basis=clean_text(inf.get("basis"), 300)))
    objects = [{"label": clean_text(o, 80), "source": "vlm", "provenance": "observed", "bounding_box": None,
                "verified": None}
               for o in (vlm or {}).get("objects") or [] if isinstance(o, str) and clean_text(o, 80)]
    return unreadable, inferences, objects


def verify_objects(objects: list[dict], codes: list[dict]) -> list[dict]:
    """Cross-check model-claimed objects that a deterministic detector can confirm (QR / barcodes)."""
    has_qr = any((c.get("format") or "").lower().startswith("qr") for c in codes)
    has_bar = any(c for c in codes if not (c.get("format") or "").lower().startswith("qr"))
    for o in objects:
        label = strip_accents(o["label"]).lower()
        if "qr" in label:
            o["verified"] = has_qr
            o["verified_by"] = "zxing-cpp"
        elif "barra" in label or "barcode" in label:
            o["verified"] = has_bar
            o["verified_by"] = "zxing-cpp"
    # add detector-found codes the model did not mention
    if has_qr and not any("qr" in strip_accents(o["label"]).lower() for o in objects):
        objects.append({"label": "código QR", "source": "qr", "provenance": "observed", "bounding_box":
                        next(c.get("bbox") for c in codes if (c.get("format") or "").lower().startswith("qr")),
                        "verified": True, "verified_by": "zxing-cpp"})
    return objects


def build_entities(fields: dict[str, FieldValue | None]) -> tuple[list[Entity], list[Relationship]]:
    ents: list[Entity] = []
    rels: list[Relationship] = []

    def add(name: str, etype: str, role: str | None = None):
        fv = fields.get(name)
        if fv is None or fv.value in (None, ""):
            return
        ents.append(Entity(type=etype, value=str(fv.raw or fv.value), normalized=str(fv.value), role=role,
                           bounding_box=fv.bounding_box, page=fv.page, evidence_ids=fv.evidence_ids,
                           provenance=fv.provenance, source=fv.source or "ocr_rules"))

    add("issuer_name", "organization", "issuer")
    add("issuer_ruc", "tax_id", "issuer")
    add("issuer_address", "address", "issuer")
    cust_doc = fields.get("customer_doc")
    add("customer_name", "organization" if cust_doc and len(str(cust_doc.value or "")) == 11 else "person",
        "customer")
    add("customer_doc", "tax_id" if cust_doc and len(str(cust_doc.value or "")) == 11 else "national_id",
        "customer")
    add("issue_date", "date", "issue")
    add("due_date", "date", "due")
    add("total", "amount", "total")
    add("serie_numero", "document_id", "document")

    def has(*names):
        return all(fields.get(n) is not None and fields[n].value not in (None, "") for n in names)

    if has("issuer_name", "issuer_ruc"):
        rels.append(Relationship(type="identified_by", source="issuer_name", target="issuer_ruc",
                                 description="El RUC identifica al emisor"))
    if has("customer_name", "customer_doc"):
        rels.append(Relationship(type="identified_by", source="customer_name", target="customer_doc",
                                 description="Documento de identidad del cliente"))
    if has("serie_numero", "customer_name"):
        rels.append(Relationship(type="issued_to", source="serie_numero", target="customer_name",
                                 description="Comprobante emitido al cliente"))
    if has("igv", "taxable_amount"):
        rels.append(Relationship(type="tax_of", source="igv", target="taxable_amount",
                                 description="IGV calculado sobre la base imponible"))
    if has("total", "taxable_amount", "igv"):
        rels.append(Relationship(type="sum_of", source="total", target="taxable_amount + igv (+ otros)",
                                 description="El total es la suma de base, impuestos y cargos"))
    if has("reference_document"):
        rels.append(Relationship(type="modifies", source="serie_numero", target="reference_document",
                                 description="Documento que se modifica (nota de crédito/débito)"))
    return ents, rels
