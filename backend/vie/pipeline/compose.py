"""Compose an ObservationResult from vision analyses (+ optional model output).

Pure function: no I/O. Used by the worker for both stages (OCR-only preliminary
result and final result after the multimodal model) and by the tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .. import PIPELINE_VERSION
from ..doc_schemas.registry import DocSchema, get_schema, schema_for_document_type
from ..extraction import merge
from ..extraction.rules import RulesResult, extract
from ..models.result import Metadata, ObservationResult, PageInfo, TextLine
from ..validation.engine import Context, validate
from .adapter import code_models, codes_from_analysis, lines_from_analysis


@dataclass
class PageAnalysis:
    index: int
    analysis: dict  # vision /v1/analyze response (without images)
    work_asset_id: str | None = None
    processed_asset_id: str | None = None


@dataclass
class Composed:
    result: ObservationResult
    rules: RulesResult
    lines: list[TextLine]
    codes: list[dict]
    schema: DocSchema
    search_text: str = ""
    extra: dict = field(default_factory=dict)


def collect(pages: list[PageAnalysis]) -> tuple[list[TextLine], list[dict], dict[int, int], list[PageInfo]]:
    lines: list[TextLine] = []
    codes: list[dict] = []
    heights: dict[int, int] = {}
    infos: list[PageInfo] = []
    for p in sorted(pages, key=lambda x: x.index):
        a = p.analysis
        page_lines = lines_from_analysis(p.index, a, start=len(lines) + 1)
        lines.extend(page_lines)
        codes.extend(codes_from_analysis(p.index, a, start=len(codes) + 1))
        w, h = a.get("processed_size") or a.get("work_size") or [0, 0]
        heights[p.index] = h
        changed = (a.get("preprocessing") or {}).get("changed")
        infos.append(PageInfo(
            index=p.index, width=w, height=h, source_size=a.get("source_size"),
            quality=(a.get("quality") or {}).get("work", {}),
            preprocessing=(a.get("preprocessing") or {}).get("steps", []),
            document_quad=(a.get("preprocessing") or {}).get("document_quad"),
            transform=(a.get("preprocessing") or {}).get("transform"),
            work_asset_id=p.work_asset_id, processed_asset_id=p.processed_asset_id,
            display_asset_id=(p.processed_asset_id if changed and p.processed_asset_id else p.work_asset_id),
            text_source=("pdf_text" if page_lines and page_lines[0].source == "pdf_text" else
                         "ocr" if page_lines else "none"),
        ))
    return lines, codes, heights, infos


def compose(observation_id: str, source: str, pages: list[PageAnalysis], *, vlm: dict | None = None,
            vlm_meta: dict | None = None, schema_id: str | None = None, duplicates: list[dict] | None = None,
            profile: str = "lite", ocr_engine: str | None = None, today: date | None = None) -> Composed:
    lines, codes, heights, infos = collect(pages)
    rules = extract(lines, heights, codes)
    dt_info = merge.document_type(rules, vlm)
    schema = get_schema(schema_id) or schema_for_document_type(dt_info.final)
    fields = merge.merge_fields(schema, rules, vlm, lines, codes)
    items = merge.merge_items(rules, vlm, lines) if schema.has_items else []
    dynamic = merge.merge_dynamic(vlm, lines) if schema.dynamic else []
    entities, relationships = merge.build_entities(fields)
    unreadable, inferences, objects = merge.vlm_lists(vlm)
    objects = merge.verify_objects(objects, codes)

    ctx = Context(schema=schema, document_type=dt_info.final, fields=fields, items=items, qr=rules.qr,
                  rules_document_type=dt_info.rules or dt_info.qr, vlm_document_type=dt_info.vlm,
                  text_lines=[(ln.id, ln.text) for ln in lines], duplicates=duplicates or [],
                  **({"today": today} if today else {}))
    report = validate(ctx)

    full_text = "\n".join(ln.text for ln in lines)
    is_document = (vlm or {}).get("is_document") if vlm else (True if rules.document_type or rules.qr else None)
    description = None
    if vlm and isinstance(vlm.get("description"), str):
        from ..extraction.normalize import clean_text

        description = clean_text(vlm["description"], 600)
    meta = Metadata(pipeline_version=PIPELINE_VERSION, schema_id=schema.id, profile=profile, ocr_engine=ocr_engine,
                    **(vlm_meta or {}))
    result = ObservationResult(
        observation_id=observation_id, source=source, document_type=dt_info.final, document_type_info=dt_info,
        is_document=is_document, description=description,
        language=(vlm or {}).get("language") or ("es" if lines else None),
        pages=infos, text={"full_text": full_text, "lines": [ln.model_dump() for ln in lines]},
        entities=entities, objects=objects, codes=code_models(codes), fields=fields, dynamic_fields=dynamic,
        items=items, relationships=relationships, unreadable=unreadable, inferences=inferences,
        validation=report, metadata=meta,
    )
    search_parts = [full_text] + [str(fv.value) for fv in fields.values() if fv is not None and fv.value]
    search_parts += [str(d.get("value")) for d in dynamic if d.get("value")]
    if description:
        search_parts.append(description)
    return Composed(result=result, rules=rules, lines=lines, codes=codes, schema=schema,
                    search_text="\n".join(search_parts)[:200_000])
