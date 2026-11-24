"""Deterministic extraction from OCR text (no model involved).

Produces candidate values with their visual evidence (line ids + boxes). These
candidates are later merged with the QR and the multimodal model output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from ..models.result import FieldSource, FieldValue, Item, TextLine
from .layout import Row, build_rows, union_bbox
from .normalize import clean_text, detect_currency, money_str, parse_date, parse_decimal, strip_accents
from .peru import SERIE_NUMERO_RE, dni_is_valid, parse_sunat_qr, ruc_is_valid, serie_doc_type

TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("nota_credito", re.compile(r"NOTA\s+DE\s+CREDITO")),
    ("nota_debito", re.compile(r"NOTA\s+DE\s+DEBITO")),
    ("guia_remision", re.compile(r"GUIA\s+DE\s+REMISION")),
    ("recibo_honorarios", re.compile(r"RECIBO\s+POR\s+HONORARIOS")),
    ("boleta", re.compile(r"BOLETA\s+DE\s+VENTA")),
    ("factura", re.compile(r"\bFACTURA\b")),
    ("orden_compra", re.compile(r"ORDEN\s+DE\s+COMPRA")),
    ("cotizacion", re.compile(r"\bCOTIZACION\b|\bPROFORMA\b")),
    ("comprobante_pago", re.compile(r"COMPROBANTE\s+DE\s+PAGO|CONSTANCIA\s+DE\s+(PAGO|TRANSFERENCIA)|\bYAPE\b|\bPLIN\b")),
    ("ticket", re.compile(r"\bTICKET\b")),
    ("recibo", re.compile(r"\bRECIBO\b")),
]

MONEY_LABELS: list[tuple[str, re.Pattern]] = [
    ("taxable_amount", re.compile(r"OP(?:\.|ERACION(?:ES)?)?\s*GRAVAD[AO]S?|VALOR\s+DE\s+VENTA|SUB\s*-?\s*TOTAL|BASE\s+IMPONIBLE")),
    ("exempt_amount", re.compile(r"EXONERAD[AO]S?")),
    ("unaffected_amount", re.compile(r"INAFECT[AO]S?")),
    ("free_amount", re.compile(r"GRATUIT[AO]S?")),
    ("discount_amount", re.compile(r"DESCUENTOS?")),
    ("icbper", re.compile(r"ICBPER")),
    ("isc", re.compile(r"\bI\.?\s?S\.?\s?C\.?\b")),
    ("igv", re.compile(r"\bI\.?\s?G\.?\s?V\.?\b")),
    ("other_charges", re.compile(r"OTROS\s+CARGOS")),
    ("total", re.compile(r"IMPORTE\s+TOTAL|TOTAL\s+A\s+PAGAR|TOTAL\s+VENTA|PRECIO\s+TOTAL|^TOTAL\b|\bTOTAL\s*(S/|US\$|\$|:)")),
]

UNITS = {"NIU", "ZZ", "UND", "UNID", "UNIDAD", "KGM", "KG", "LT", "LTR", "MTR", "M", "CJA", "PAQ", "GLB", "SERV",
         "DOC", "PZA", "BX", "GLL", "TNE"}
COMPANY_SUFFIX = re.compile(r"\b(S\.?A\.?C\.?|E\.?I\.?R\.?L\.?|S\.?R\.?L\.?|S\.?A\.?A\.?|S\.?A\.?)\s*$")
ADDRESS_RE = re.compile(r"^(AV\.?|AVENIDA|JR\.?|JIRON|CALLE|CAL\.|PSJE|PASAJE|MZ\.?|CARRETERA|URB\.?)\b")
NUMBER_TOKEN = re.compile(r"-?\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d{1,2})|-?\d+(?:[.,]\d{1,2})?")


def _u(text: str) -> str:
    return strip_accents(text).upper()


@dataclass
class RulesResult:
    document_type: str | None = None
    document_type_evidence: list[str] = field(default_factory=list)
    fields: dict[str, FieldValue] = field(default_factory=dict)
    items: list[Item] = field(default_factory=list)
    qr: dict | None = None
    qr_evidence: str | None = None
    igv_rate_printed: Decimal | None = None
    rucs: list[dict] = field(default_factory=list)


def _field(value, raw: str | None, typ: str, lines: list[TextLine], **extra) -> FieldValue:
    ids = [ln.id for ln in lines]
    bbox = union_bbox([ln.bbox for ln in lines]) if lines else None
    return FieldValue(value=value, raw=clean_text(raw, 300), type=typ, provenance="observed", source="ocr_rules",
                      sources=[FieldSource(source="ocr_rules", value=value, raw=clean_text(raw, 300),
                                           evidence_ids=ids)],
                      evidence_ids=ids, bounding_box=bbox, page=lines[0].page if lines else None, **extra)


def _lines_with(row: Row, needle: str) -> list[TextLine]:
    n = re.sub(r"\s+", "", _u(needle))
    hit = [ln for ln in row.lines if n and n in re.sub(r"\s+", "", _u(ln.text))]
    return hit or row.lines


def _numbers(text: str) -> list[tuple[str, Decimal]]:
    out = []
    for m in NUMBER_TOKEN.finditer(text):
        val = parse_decimal(m.group(0))
        if val is not None:
            out.append((m.group(0), val))
    return out


def classify(rows: list[Row], page_heights: dict[int, int]) -> tuple[str | None, list[str]]:
    best: tuple[float, str, list[str]] | None = None
    for row in rows:
        utext = _u(row.text)
        if "REPRESENTACION IMPRESA" in utext:
            continue  # legal footer, mentions the type but is weak evidence
        h = page_heights.get(row.page, 1) or 1
        pos_weight = 2.0 if row.bbox[1] < 0.3 * h else 1.0
        size_weight = min(2.0, max(0.5, (row.bbox[3] - row.bbox[1]) / max(1, 0.015 * h)))
        for doc_type, pattern in TYPE_PATTERNS:
            if pattern.search(utext):
                score = pos_weight * size_weight * (1.5 if row.page == 0 else 1.0)
                if best is None or score > best[0]:
                    best = (score, doc_type, row.ids)
                break
    return (best[1], best[2]) if best else (None, [])


def extract(lines: list[TextLine], page_heights: dict[int, int], codes: list[dict] | None = None) -> RulesResult:
    res = RulesResult()
    rows = build_rows(lines)

    # ---- QR (SUNAT) -----------------------------------------------------------
    for i, code in enumerate(codes or []):
        parsed = parse_sunat_qr(code.get("text"))
        if parsed:
            res.qr = parsed
            res.qr_evidence = code.get("id") or f"c_{i + 1:02d}"
            break

    # ---- document type -----------------------------------------------------------
    res.document_type, res.document_type_evidence = classify(rows, page_heights)

    # ---- RUCs, DNIs, series --------------------------------------------------------
    first_page_h = page_heights.get(0, 1) or 1
    for row in rows:
        utext = _u(row.text)
        for m in re.finditer(r"(?<!\d)(\d{11})(?!\d)", re.sub(r"(?<=\d)[ .](?=\d)", "", row.text)):
            ruc = m.group(1)
            if ruc_is_valid(ruc):
                labelled = bool(re.search(r"R\.?\s?U\.?\s?C", utext))
                res.rucs.append({"ruc": ruc, "row": row, "labelled": labelled,
                                 "top": row.page == 0 and row.bbox[1] < 0.25 * first_page_h,
                                 "customer_ctx": bool(re.search(r"SENOR|CLIENTE|ADQUIRIENTE|DESTINATARIO", utext))})
        if "serie_numero" not in res.fields:
            m = SERIE_NUMERO_RE.search(utext)
            if m and not re.search(r"MODIFICA|REFERENCIA|AFECTADO", utext):
                sn = f"{m.group(1)}-{m.group(2)}"
                res.fields["serie_numero"] = _field(sn, m.group(0), "serie_numero", _lines_with(row, m.group(2)))
        if re.search(r"MODIFICA|REFERENCIA|AFECTADO", utext) and "reference_document" not in res.fields:
            m = SERIE_NUMERO_RE.search(utext)
            if m:
                res.fields["reference_document"] = _field(f"{m.group(1)}-{m.group(2)}", m.group(0), "serie_numero",
                                                          _lines_with(row, m.group(2)))
        dm = re.search(r"\b(DNI|D\.N\.I\.?)\b\s*(?:N[°º]?\.?)?\s*:?\s*(\d{8})(?!\d)", utext)
        if dm and dni_is_valid(dm.group(2)) and "customer_doc" not in res.fields:
            res.fields["customer_doc"] = _field(dm.group(2), dm.group(0), "doc_id", _lines_with(row, dm.group(2)),
                                                doc_type="DNI")

    issuer = next((r for r in res.rucs if r["labelled"] and r["top"]), None) or \
        next((r for r in res.rucs if r["top"]), None)
    if issuer:
        res.fields["issuer_ruc"] = _field(issuer["ruc"], issuer["row"].text, "ruc",
                                          _lines_with(issuer["row"], issuer["ruc"]))
    customer = next((r for r in res.rucs if (not issuer or r["ruc"] != issuer["ruc"]) and not r["top"]), None)
    if customer and "customer_doc" not in res.fields:
        res.fields["customer_doc"] = _field(customer["ruc"], customer["row"].text, "doc_id",
                                            _lines_with(customer["row"], customer["ruc"]), doc_type="RUC")

    # ---- labelled values ------------------------------------------------------------
    in_items = False
    for idx, row in enumerate(rows):
        text, utext = row.text, _u(row.text)
        if re.search(r"FECHA\s+DE\s+EMISION|FECHA\s+EMISION|F\.\s*EMISION", utext) and "issue_date" not in res.fields:
            d = parse_date(text)
            if d:
                res.fields["issue_date"] = _field(d.isoformat(), text, "date", _date_lines(row))
        elif re.search(r"VENCIMIENTO", utext) and "due_date" not in res.fields:
            d = parse_date(text)
            if d:
                res.fields["due_date"] = _field(d.isoformat(), text, "date", _date_lines(row))
        if re.search(r"^(SENOR\s*\(?ES\)?|CLIENTE|RAZON\s+SOCIAL|ADQUIRIENTE|NOMBRE)\b", utext) and \
                "customer_name" not in res.fields:
            value = re.sub(r"^[^:]*:\s*", "", text) if ":" in text else " ".join(ln.text for ln in row.lines[1:])
            value = clean_text(value, 200)
            if value and not re.fullmatch(r"[\d\s-]+", value):
                res.fields["customer_name"] = _field(value, text, "string", row.lines[1:] or row.lines)
        if re.search(r"^MONEDA\b|TIPO\s+DE\s+MONEDA", utext) and "currency" not in res.fields:
            cur = detect_currency(text.split(":", 1)[-1])
            if cur:
                res.fields["currency"] = _field(cur, text, "currency", row.lines[1:] or row.lines)
        if re.search(r"FORMA\s+DE\s+PAGO|CONDICION\s+DE\s+PAGO", utext) and "payment_terms" not in res.fields:
            pt = "CONTADO" if "CONTADO" in utext else "CREDITO" if "CREDITO" in utext else None
            if pt:
                res.fields["payment_terms"] = _field(pt, text, "string", row.lines)
        if utext.startswith("SON") and "amount_in_words" not in res.fields:
            res.fields["amount_in_words"] = _field(clean_text(text, 300), text, "text", row.lines)

        # money rows (labels on the right side of the document)
        for name, pattern in MONEY_LABELS:
            if name in res.fields:
                continue
            if name == "total" and re.search(r"SUB\s*-?\s*TOTAL", utext):
                continue
            m = pattern.search(utext)
            if not m:
                continue
            after = text[m.end():] if name != "igv" else text
            nums = [n for n in _numbers(after) if not re.fullmatch(r"\d{1,2}", n[0].strip())] if name == "igv" \
                else _numbers(after)
            if name == "igv":
                rate = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%", text)
                if rate:
                    res.igv_rate_printed = parse_decimal(rate.group(1))
                    res.fields["igv_rate"] = _field(str(res.igv_rate_printed), rate.group(0), "percent",
                                                    _lines_with(row, rate.group(0)))
                    nums = [n for n in nums if n[0] not in rate.group(0)]
            if not nums:
                continue
            raw, value = nums[-1]
            res.fields[name] = _field(money_str(value), raw, "money", _lines_with(row, raw),
                                      currency=detect_currency(text))
            break

        # items table
        if re.search(r"\bCANT", utext) and re.search(r"DESCRIPCION|DETALLE|CONCEPTO", utext):
            in_items = True
            continue
        if in_items:
            if any(p.search(utext) for _, p in MONEY_LABELS) or utext.startswith("SON"):
                in_items = False
                continue
            item = _parse_item(row)
            if item:
                res.items.append(item)

    # Currency fallback from money labels (S/ or US$)
    if "currency" not in res.fields:
        for name in ("total", "taxable_amount", "igv"):
            fv = res.fields.get(name)
            if fv and fv.currency:
                res.fields["currency"] = FieldValue(value=fv.currency, raw=fv.raw, type="currency",
                                                    provenance="observed", source="ocr_rules",
                                                    sources=[FieldSource(source="ocr_rules", value=fv.currency,
                                                                         evidence_ids=fv.evidence_ids)],
                                                    evidence_ids=fv.evidence_ids, bounding_box=fv.bounding_box,
                                                    page=fv.page)
                break

    # Issuer name / address: top rows of the first page
    top_rows = [r for r in rows if r.page == 0 and r.bbox[1] < 0.22 * first_page_h]
    for row in top_rows:
        utext = _u(row.text)
        candidate = row.lines[0].text if row.lines else ""
        if "issuer_name" not in res.fields and COMPANY_SUFFIX.search(_u(candidate)):
            res.fields["issuer_name"] = _field(clean_text(candidate, 200), candidate, "string", row.lines[:1])
        if "issuer_address" not in res.fields and ADDRESS_RE.search(utext):
            res.fields["issuer_address"] = _field(clean_text(row.lines[0].text, 200), row.lines[0].text, "string",
                                                  row.lines[:1])
    return res


def _date_lines(row: Row) -> list[TextLine]:
    hit = [ln for ln in row.lines if parse_date(ln.text)]
    return hit or row.lines


def _parse_item(row: Row) -> Item | None:
    tokens = row.text.split()
    if len(tokens) < 3:
        return None
    nums = _numbers(row.text)
    if len(nums) < 2:
        return None
    quantity = None
    if re.fullmatch(r"\d+(?:[.,]\d+)?", tokens[0]):
        quantity = parse_decimal(tokens[0])
        tokens = tokens[1:]
    unit = None
    if tokens and tokens[0].upper().strip(".") in UNITS:
        unit = tokens[0].upper().strip(".")
        tokens = tokens[1:]
    amount_raw, amount = nums[-1]
    price_raw, price = nums[-2]
    desc_tokens = []
    for tok in tokens:
        if parse_decimal(tok) is not None and re.fullmatch(r"[\d.,]+", tok):
            break
        desc_tokens.append(tok)
    description = clean_text(" ".join(desc_tokens), 300)
    if not description:
        return None
    return Item(description=description, quantity=str(quantity) if quantity is not None else None, unit=unit,
                unit_price=money_str(price), amount=money_str(amount), provenance="observed", source="ocr_rules",
                evidence_ids=row.ids, bounding_box=row.bbox, page=row.page)
