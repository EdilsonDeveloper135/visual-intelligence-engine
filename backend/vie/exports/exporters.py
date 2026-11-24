"""Exports of observations (JSON, CSV, XLSX, HTML report).

Spreadsheet formula injection: any cell that starts with = + - @ (or tab/CR) is
prefixed with an apostrophe, because document text is untrusted.
"""

from __future__ import annotations

import csv
import html
import io
import json
from datetime import UTC, datetime

from openpyxl import Workbook
from openpyxl.styles import Font

from ..db.models import Observation

FIELD_COLUMNS = ["issuer_name", "issuer_ruc", "serie_numero", "issue_date", "due_date", "currency", "customer_name",
                 "customer_doc", "taxable_amount", "exempt_amount", "unaffected_amount", "igv", "isc", "icbper",
                 "other_charges", "discount_amount", "total", "payment_terms", "reference_document"]
BASE_COLUMNS = ["observation_id", "created_at", "source", "status", "document_type", "title", "validation_status",
                "needs_review_count", "model", "processing_ms", "original_filename"]


def safe_cell(value):
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value
    s = str(value)
    if s and (s[0] in "=+-@\t\r" or s.startswith("0x")):
        # keep plain negative numbers readable, neutralise everything else
        try:
            float(s)
            return s
        except ValueError:
            return "'" + s
    return s


def _field(o: Observation, name: str):
    fv = ((o.result or {}).get("fields") or {}).get(name)
    return None if fv is None else fv.get("value")


def observation_row(o: Observation) -> dict:
    row = {"observation_id": str(o.id), "created_at": o.created_at.isoformat(), "source": o.source,
           "status": o.status, "document_type": o.document_type, "title": o.title,
           "validation_status": o.validation_status, "needs_review_count": o.needs_review_count,
           "model": o.model_name, "processing_ms": o.processing_ms,
           "original_filename": (o.source_detail or {}).get("original_filename")}
    for name in FIELD_COLUMNS:
        row[name] = _field(o, name)
    dyn = (o.result or {}).get("dynamic_fields") or []
    for d in dyn[:40]:
        row[f"dyn_{d.get('key')}"] = d.get("value")
    return row


def to_json(observations: list[Observation]) -> bytes:
    payload = {"exported_at": datetime.now(UTC).isoformat(), "count": len(observations),
               "observations": [{**(o.result or {}), "observation_id": str(o.id), "status": o.status,
                                 "created_at": o.created_at.isoformat()} for o in observations]}
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")


def to_csv(observations: list[Observation]) -> bytes:
    rows = [observation_row(o) for o in observations]
    columns = BASE_COLUMNS + FIELD_COLUMNS + sorted({k for r in rows for k in r if k.startswith("dyn_")})
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: safe_cell(r.get(k)) for k in columns})
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM: Excel opens UTF-8 correctly


def item_rows(observations: list[Observation]) -> list[dict]:
    out = []
    for o in observations:
        for i, it in enumerate((o.result or {}).get("items") or [], start=1):
            out.append({"observation_id": str(o.id), "line": i, "description": it.get("description"),
                        "quantity": it.get("quantity"), "unit": it.get("unit"), "unit_price": it.get("unit_price"),
                        "amount": it.get("amount"), "source": it.get("source"),
                        "needs_review": it.get("needs_review")})
    return out


def to_csv_items(observations: list[Observation]) -> bytes:
    rows = item_rows(observations)
    columns = ["observation_id", "line", "description", "quantity", "unit", "unit_price", "amount", "source",
               "needs_review"]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns)
    w.writeheader()
    for r in rows:
        w.writerow({k: safe_cell(r.get(k)) for k in columns})
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(observations: list[Observation]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Observaciones"
    rows = [observation_row(o) for o in observations]
    columns = BASE_COLUMNS + FIELD_COLUMNS
    ws.append(columns)
    for r in rows:
        ws.append([safe_cell(r.get(c)) for c in columns])
    items = wb.create_sheet("Items")
    icol = ["observation_id", "line", "description", "quantity", "unit", "unit_price", "amount", "source"]
    items.append(icol)
    for r in item_rows(observations):
        items.append([safe_cell(r.get(c)) for c in icol])
    val = wb.create_sheet("Validacion")
    val.append(["observation_id", "check", "rule", "status", "severity", "message"])
    for o in observations:
        for c in ((o.result or {}).get("validation") or {}).get("checks") or []:
            val.append([str(o.id), safe_cell(c.get("id")), safe_cell(c.get("rule")), c.get("status"),
                        c.get("severity"), safe_cell(c.get("message"))])
    for sheet in (ws, items, val):
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        sheet.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_html(observations: list[Observation]) -> bytes:
    e = html.escape
    parts = ["<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Informe VIE</title>",
             "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">",
             "<style>body{font:14px system-ui,sans-serif;margin:24px;color:#111}table{border-collapse:collapse;"
             "margin:8px 0 24px}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}th{background:#f3f3f3}"
             ".pass{color:#166534}.fail{color:#b91c1c}.warn{color:#b45309}.skipped{color:#6b7280}</style></head><body>",
             f"<h1>Informe de observaciones</h1><p>Generado: {e(datetime.now(UTC).isoformat())} — "
             f"{len(observations)} registro(s). Valores marcados 'revisión' requieren verificación humana.</p>"]
    for o in observations:
        res = o.result or {}
        parts.append(f"<h2>{e(o.title or o.document_type or 'Observación')} <small>{e(str(o.id))}</small></h2>")
        parts.append(f"<p>{e(res.get('description') or '')}</p><p>Estado: {e(o.status)} · Validación: "
                     f"{e(o.validation_status or '-')}</p><table><tr><th>Campo</th><th>Valor</th><th>Fuente</th>"
                     "<th>Revisión</th></tr>")
        for name, fv in (res.get("fields") or {}).items():
            if fv is None:
                continue
            parts.append(f"<tr><td>{e(name)}</td><td>{e(str(fv.get('value')))}</td><td>{e(str(fv.get('source')))}"
                         f"</td><td>{'sí' if fv.get('needs_review') else ''}</td></tr>")
        parts.append("</table><table><tr><th>Verificación</th><th>Estado</th><th>Detalle</th></tr>")
        for c in (res.get("validation") or {}).get("checks") or []:
            st = c.get("status", "")
            parts.append(f"<tr><td>{e(str(c.get('id')))}</td><td class='{e(st)}'>{e(st)}</td>"
                         f"<td>{e(str(c.get('message')))}</td></tr>")
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts).encode("utf-8")


FORMATS = {
    "json": (to_json, "application/json", "json"),
    "csv": (to_csv, "text/csv; charset=utf-8", "csv"),
    "csv_items": (to_csv_items, "text/csv; charset=utf-8", "csv"),
    "xlsx": (to_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "html": (to_html, "text/html; charset=utf-8", "html"),
}
