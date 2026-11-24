"""Extraction schemas (known document types) + universal mode.

A schema defines the fields to extract, their types and the label aliases seen on
real documents. From a schema we derive:
  * a flat JSON Schema used as Ollama `format` (constrained decoding),
  * the short field list included in the prompt,
  * the validation rules that apply.
Custom schemas (stored in the DB) use the same definition format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FIELD_TYPES = {"string", "money", "decimal", "integer", "date", "ruc", "dni", "doc_id", "serie_numero",
               "currency", "percent", "enum", "text"}

DOCUMENT_TYPES = [
    "factura", "boleta", "nota_credito", "nota_debito", "guia_remision", "recibo", "recibo_honorarios",
    "comprobante_pago", "orden_compra", "cotizacion", "ticket", "otro_documento", "no_documento",
]

DOCUMENT_TYPE_LABELS = {
    "factura": "Factura electrónica", "boleta": "Boleta de venta", "nota_credito": "Nota de crédito",
    "nota_debito": "Nota de débito", "guia_remision": "Guía de remisión", "recibo": "Recibo",
    "recibo_honorarios": "Recibo por honorarios", "comprobante_pago": "Comprobante de pago",
    "orden_compra": "Orden de compra", "cotizacion": "Cotización", "ticket": "Ticket",
    "otro_documento": "Otro documento", "no_documento": "No es un documento",
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type: str = "string"
    required: bool = False
    description: str = ""
    aliases: tuple[str, ...] = ()
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocSchema:
    id: str
    title: str
    version: str
    document_types: tuple[str, ...]
    fields: tuple[FieldSpec, ...]
    has_items: bool = True
    rules: tuple[str, ...] = ()
    description: str = ""
    builtin: bool = True
    dynamic: bool = False  # universal mode: free key/value fields

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id, "title": self.title, "version": self.version, "description": self.description,
            "document_types": list(self.document_types), "has_items": self.has_items, "rules": list(self.rules),
            "builtin": self.builtin, "dynamic": self.dynamic,
            "fields": [{"name": f.name, "label": f.label, "type": f.type, "required": f.required,
                        "description": f.description, "aliases": list(f.aliases), "enum": list(f.enum)}
                       for f in self.fields],
        }


_PE_COMMON = (
    FieldSpec("issuer_name", "Razón social del emisor", "string", True, "Nombre de la empresa que emite"),
    FieldSpec("issuer_ruc", "RUC del emisor", "ruc", True, "11 dígitos, en el recuadro superior",
              ("R.U.C.", "RUC", "R.U.C. N°")),
    FieldSpec("issuer_address", "Dirección del emisor", "string"),
    FieldSpec("serie_numero", "Serie y número", "serie_numero", True, "Ej. F001-00000123"),
    FieldSpec("issue_date", "Fecha de emisión", "date", True, "", ("Fecha de Emisión", "Fecha")),
    FieldSpec("due_date", "Fecha de vencimiento", "date", False, "", ("Fecha de Vencimiento",)),
    FieldSpec("currency", "Moneda", "currency", True, "PEN o USD", ("Moneda", "Tipo de moneda")),
    FieldSpec("customer_name", "Cliente", "string", False, "", ("Señor(es)", "Cliente", "Razón Social", "Nombre")),
    FieldSpec("customer_doc", "Documento del cliente (RUC/DNI)", "doc_id", False, "",
              ("RUC", "DNI", "Doc. Identidad")),
    FieldSpec("taxable_amount", "Op. gravada", "money", False, "Base imponible",
              ("Op. Gravada", "Operación Gravada", "Valor de venta", "Sub Total", "Subtotal")),
    FieldSpec("exempt_amount", "Op. exonerada", "money", False, "", ("Op. Exonerada",)),
    FieldSpec("unaffected_amount", "Op. inafecta", "money", False, "", ("Op. Inafecta",)),
    FieldSpec("free_amount", "Op. gratuita", "money", False, "", ("Op. Gratuita",)),
    FieldSpec("discount_amount", "Descuentos", "money", False, "", ("Descuento", "Descuentos")),
    FieldSpec("igv", "IGV", "money", False, "Impuesto General a las Ventas", ("IGV", "I.G.V.")),
    FieldSpec("igv_rate", "Tasa IGV indicada", "percent", False, "Porcentaje impreso, p. ej. 18%"),
    FieldSpec("isc", "ISC", "money"),
    FieldSpec("icbper", "ICBPER", "money", False, "Impuesto a las bolsas plásticas"),
    FieldSpec("other_charges", "Otros cargos", "money"),
    FieldSpec("total", "Importe total", "money", True, "", ("Importe Total", "Total a pagar", "TOTAL")),
    FieldSpec("amount_in_words", "Importe en letras", "text", False, "Línea 'SON: ...'"),
    FieldSpec("payment_terms", "Forma de pago", "string", False, "Contado / Crédito"),
)

PE_FACTURA = DocSchema(
    id="pe_factura_electronica", title="Factura electrónica (Perú)", version="1.0",
    document_types=("factura", "nota_credito", "nota_debito"),
    fields=_PE_COMMON + (FieldSpec("reference_document", "Documento que modifica", "serie_numero"),),
    rules=("ruc_issuer", "ruc_customer", "serie_vs_type", "customer_doc_vs_type", "item_lines", "items_sum",
           "totals_sum", "tax_rate", "dates", "currency", "qr_consistency", "source_agreement", "duplicate",
           "document_type_agreement", "prompt_injection", "amount_in_words"),
    description="Factura, nota de crédito y nota de débito electrónicas SUNAT.",
)

PE_BOLETA = DocSchema(
    id="pe_boleta_venta", title="Boleta de venta electrónica (Perú)", version="1.0",
    document_types=("boleta",),
    fields=_PE_COMMON,
    rules=PE_FACTURA.rules,
    description="Boleta de venta electrónica SUNAT (precios normalmente con IGV incluido).",
)

GENERIC_RECEIPT = DocSchema(
    id="receipt_generic", title="Recibo / comprobante genérico", version="1.0",
    document_types=("recibo", "comprobante_pago", "ticket", "cotizacion", "orden_compra", "guia_remision",
                    "recibo_honorarios"),
    fields=(
        FieldSpec("issuer_name", "Emisor", "string"),
        FieldSpec("issuer_ruc", "RUC del emisor", "ruc"),
        FieldSpec("document_number", "Número de documento", "string"),
        FieldSpec("issue_date", "Fecha", "date"),
        FieldSpec("currency", "Moneda", "currency"),
        FieldSpec("customer_name", "Cliente / destinatario", "string"),
        FieldSpec("customer_doc", "Documento del cliente", "doc_id"),
        FieldSpec("subtotal", "Subtotal", "money"),
        FieldSpec("igv", "Impuesto", "money"),
        FieldSpec("total", "Total", "money"),
        FieldSpec("reference", "Referencia / concepto", "text"),
    ),
    rules=("ruc_issuer", "item_lines", "items_sum", "totals_sum", "tax_rate", "dates", "currency",
           "source_agreement", "prompt_injection"),
    description="Recibos, comprobantes de pago, órdenes de compra, cotizaciones y guías (genérico).",
)

UNIVERSAL = DocSchema(
    id="universal", title="Universal (estructura desconocida)", version="1.0",
    document_types=tuple(DOCUMENT_TYPES), fields=(), has_items=True, dynamic=True,
    rules=("ruc_any", "item_lines", "dates", "prompt_injection"),
    description="Modo universal: el modelo propone campos clave/valor dinámicos; todos requieren evidencia.",
)

BUILTIN: dict[str, DocSchema] = {s.id: s for s in (PE_FACTURA, PE_BOLETA, GENERIC_RECEIPT, UNIVERSAL)}

DOC_TYPE_TO_SCHEMA = {
    "factura": "pe_factura_electronica", "nota_credito": "pe_factura_electronica",
    "nota_debito": "pe_factura_electronica", "boleta": "pe_boleta_venta",
    "recibo": "receipt_generic", "comprobante_pago": "receipt_generic", "ticket": "receipt_generic",
    "orden_compra": "receipt_generic", "cotizacion": "receipt_generic", "guia_remision": "receipt_generic",
    "recibo_honorarios": "receipt_generic",
}

_custom: dict[str, DocSchema] = {}


def register_custom(definition: dict[str, Any]) -> DocSchema:
    """Build a DocSchema from a validated custom definition (see api/routers/schemas.py)."""
    schema = DocSchema(
        id=definition["id"], title=definition["title"], version=str(definition.get("version", "1.0")),
        document_types=tuple(definition.get("document_types") or ("otro_documento",)),
        fields=tuple(FieldSpec(f["name"], f.get("label", f["name"]), f.get("type", "string"),
                               bool(f.get("required", False)), f.get("description", ""),
                               tuple(f.get("aliases", ())), tuple(f.get("enum", ())))
                     for f in definition["fields"]),
        has_items=bool(definition.get("has_items", False)),
        rules=tuple(definition.get("rules") or ("dates", "prompt_injection")),
        description=definition.get("description", ""), builtin=False,
    )
    _custom[schema.id] = schema
    return schema


def unregister_custom(schema_id: str) -> None:
    _custom.pop(schema_id, None)


def get_schema(schema_id: str | None) -> DocSchema | None:
    if not schema_id:
        return None
    return BUILTIN.get(schema_id) or _custom.get(schema_id)


def all_schemas() -> list[DocSchema]:
    return list(BUILTIN.values()) + list(_custom.values())


def schema_for_document_type(doc_type: str | None) -> DocSchema:
    return BUILTIN[DOC_TYPE_TO_SCHEMA.get(doc_type or "", "universal")]


# ---------------------------------------------------------------------------
# JSON Schema for constrained decoding (flat: no $defs/$ref, simple nullables)
# ---------------------------------------------------------------------------
_NULLABLE_STR = {"type": ["string", "null"]}


def vlm_json_schema(schema: DocSchema, max_items: int = 25) -> dict[str, Any]:
    props: dict[str, Any] = {
        "is_document": {"type": "boolean"},
        "document_type": {"type": "string", "enum": DOCUMENT_TYPES},
        "description": {"type": "string"},
        "language": {"type": ["string", "null"]},
    }
    required = ["is_document", "document_type", "description", "language"]
    if schema.dynamic:
        props["fields"] = {"type": "array", "maxItems": max_items, "items": {
            "type": "object",
            "properties": {"key": {"type": "string"}, "label": {"type": "string"}, "value": {"type": "string"},
                           "type": {"type": "string", "enum": sorted(FIELD_TYPES)}},
            "required": ["key", "label", "value", "type"]}}
    else:
        props["fields"] = {"type": "object", "properties": {f.name: _NULLABLE_STR for f in schema.fields},
                           "required": [f.name for f in schema.fields]}
    required.append("fields")
    if schema.has_items:
        props["items"] = {"type": "array", "maxItems": max_items, "items": {
            "type": "object",
            "properties": {"description": {"type": "string"}, "quantity": _NULLABLE_STR, "unit": _NULLABLE_STR,
                           "unit_price": _NULLABLE_STR, "amount": _NULLABLE_STR},
            "required": ["description", "quantity", "unit", "unit_price", "amount"]}}
        required.append("items")
    props["objects"] = {"type": "array", "maxItems": 10, "items": {"type": "string"}}
    props["unreadable"] = {"type": "array", "maxItems": 10, "items": {"type": "string"}}
    props["inferences"] = {"type": "array", "maxItems": 5, "items": {
        "type": "object", "properties": {"statement": {"type": "string"}, "basis": {"type": "string"}},
        "required": ["statement", "basis"]}}
    required += ["objects", "unreadable", "inferences"]
    return {"type": "object", "properties": props, "required": required}


def prompt_field_list(schema: DocSchema) -> str:
    if schema.dynamic:
        return ("fields: lista de pares clave/valor visibles en la imagen (key en snake_case, label tal como "
                "aparece, value copiado literalmente, type).")
    lines = []
    for f in schema.fields:
        hint = f" — {f.description}" if f.description else ""
        lines.append(f"- {f.name}: {f.label} ({f.type}){hint}")
    return "\n".join(lines)
