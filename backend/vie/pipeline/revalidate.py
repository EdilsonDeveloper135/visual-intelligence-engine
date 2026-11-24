"""Re-run validation on a stored result (after human edits) and carry edits over re-interpretations."""

from __future__ import annotations

from datetime import date

from ..doc_schemas.registry import get_schema, schema_for_document_type
from ..models.result import FieldValue, Item, ObservationResult
from ..validation.engine import Context, validate


def revalidate(result: ObservationResult, duplicates: list[dict] | None = None,
               today: date | None = None) -> ObservationResult:
    schema = get_schema(result.metadata.schema_id) or schema_for_document_type(result.document_type)
    qr = next((c.parsed for c in result.codes if c.parsed), None)
    ctx = Context(schema=schema, document_type=result.document_type, fields=result.fields, items=result.items,
                  qr=qr, rules_document_type=result.document_type_info.rules or result.document_type_info.qr,
                  vlm_document_type=result.document_type_info.vlm,
                  text_lines=[(ln["id"], ln["text"]) for ln in result.text.get("lines", [])],
                  duplicates=duplicates or [], **({"today": today} if today else {}))
    result.validation = validate(ctx)
    return result


def apply_human_edits(new: ObservationResult, old: dict | None) -> ObservationResult:
    """Human corrections always win over automatic re-processing."""
    if not old:
        return new
    for name, fv in (old.get("fields") or {}).items():
        if fv and fv.get("edited_by_human"):
            new.fields[name] = FieldValue.model_validate(fv)
    if any(it.get("source") == "human" for it in old.get("items") or []):
        new.items = [Item.model_validate(it) for it in old["items"]]
    if old.get("document_type_info", {}).get("human"):
        new.document_type = old["document_type"]
        new.document_type_info.final = old["document_type"]
    return new
