"""Deterministic validation engine (layer F), independent of the multimodal model.

Each rule declares the fields it needs. Without enough data a rule returns
`skipped` — never `pass`. The model's own opinion about correctness is never an
input to any rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml

from ..core.config import get_settings
from ..doc_schemas.registry import DocSchema
from ..extraction.normalize import parse_decimal
from ..extraction.peru import dni_is_valid, ruc_problem, serie_doc_type
from ..extraction.words import parse_amount_in_words
from ..models.result import CheckResult, FieldValue, Item, ValidationReport
from . import injection

D = Decimal
MONEY_PARTS_PLUS = ("taxable_amount", "exempt_amount", "unaffected_amount", "igv", "isc", "icbper", "other_charges")


@lru_cache
def tax_config() -> dict:
    path = Path(get_settings().configs_dir) / "tax_rates.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return {"igv": {"tolerance_abs": "0.05", "tolerance_rate": "0.002", "rates": [{"rate": "0.18", "label": "general"}]},
            "arithmetic": {"line_tolerance_abs": "0.02", "sum_tolerance_abs": "0.05"},
            "dates": {"future_tolerance_days": 1, "max_age_years": 15}}


@dataclass
class Context:
    schema: DocSchema
    document_type: str | None
    fields: dict[str, FieldValue | None]
    items: list[Item]
    qr: dict | None = None
    rules_document_type: str | None = None
    vlm_document_type: str | None = None
    text_lines: list[tuple[str, str]] = field(default_factory=list)  # (evidence_id, text)
    duplicates: list[dict] = field(default_factory=list)  # other observations with same RUC + serie
    today: date = field(default_factory=date.today)

    def val(self, name: str):
        fv = self.fields.get(name)
        return None if fv is None else fv.value

    def money(self, name: str) -> Decimal | None:
        v = self.val(name)
        return parse_decimal(str(v)) if v is not None else None


Rule = Callable[[Context], list[CheckResult]]
RULES: dict[str, Rule] = {}


def rule(rule_id: str):
    def deco(fn: Rule) -> Rule:
        RULES[rule_id] = fn
        return fn
    return deco


def _skip(rule_id: str, msg: str, fields: list[str]) -> CheckResult:
    return CheckResult(id=f"{rule_id}", rule=rule_id, status="skipped", message=msg, fields=fields)


def _tol() -> tuple[Decimal, Decimal, Decimal]:
    cfg = tax_config()
    return (D(str(cfg["arithmetic"]["line_tolerance_abs"])), D(str(cfg["arithmetic"]["sum_tolerance_abs"])),
            D(str(cfg["igv"]["tolerance_abs"])))


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------
@rule("ruc_issuer")
def check_ruc_issuer(ctx: Context) -> list[CheckResult]:
    ruc = ctx.val("issuer_ruc")
    if not ruc:
        return [_skip("ruc_issuer", "No se encontró RUC del emisor.", ["issuer_ruc"])]
    problem = ruc_problem(str(ruc))
    if problem:
        return [CheckResult(id="ruc_issuer", rule="ruc_issuer", status="fail", severity="error",
                            message=f"RUC del emisor inválido: {problem}.", fields=["issuer_ruc"], observed=ruc)]
    return [CheckResult(id="ruc_issuer", rule="ruc_issuer", status="pass", message="RUC del emisor válido (módulo 11).",
                        fields=["issuer_ruc"], observed=ruc)]


@rule("ruc_any")
def check_ruc_any(ctx: Context) -> list[CheckResult]:
    return check_ruc_issuer(ctx) if ctx.val("issuer_ruc") else []


@rule("ruc_customer")
def check_customer_doc(ctx: Context) -> list[CheckResult]:
    doc = ctx.val("customer_doc")
    if not doc:
        return [_skip("customer_doc", "Sin documento del cliente.", ["customer_doc"])]
    doc = str(doc)
    if len(doc) == 11:
        problem = ruc_problem(doc)
        status, msg = ("fail", f"RUC del cliente inválido: {problem}.") if problem else \
            ("pass", "RUC del cliente válido (módulo 11).")
    elif len(doc) == 8:
        status, msg = ("pass", "DNI del cliente con formato válido (8 dígitos).") if dni_is_valid(doc) else \
            ("fail", "DNI del cliente con formato inválido.")
    else:
        status, msg = "warn", f"Documento del cliente con longitud inusual ({len(doc)} dígitos)."
    return [CheckResult(id="customer_doc", rule="ruc_customer", status=status,
                        severity="error" if status == "fail" else "warning" if status == "warn" else "info",
                        message=msg, fields=["customer_doc"], observed=doc)]


@rule("serie_vs_type")
def check_serie_vs_type(ctx: Context) -> list[CheckResult]:
    sn = ctx.val("serie_numero")
    if not sn or not ctx.document_type:
        return [_skip("serie_vs_type", "Falta serie o tipo de documento.", ["serie_numero"])]
    implied = serie_doc_type(str(sn).split("-")[0])
    if implied is None:
        return [_skip("serie_vs_type", "La serie no permite deducir el tipo (p. ej. serie E o física).",
                      ["serie_numero"])]
    ok = implied == ctx.document_type
    return [CheckResult(id="serie_vs_type", rule="serie_vs_type", status="pass" if ok else "warn",
                        severity="info" if ok else "warning",
                        message=("La serie es coherente con el tipo de documento." if ok else
                                 f"La serie {sn} corresponde a '{implied}' pero el documento se clasificó como "
                                 f"'{ctx.document_type}'."),
                        fields=["serie_numero"], expected=implied, observed=ctx.document_type)]


@rule("customer_doc_vs_type")
def check_customer_doc_vs_type(ctx: Context) -> list[CheckResult]:
    doc, dt = ctx.val("customer_doc"), ctx.document_type
    if not doc or dt not in ("factura", "boleta"):
        return [_skip("customer_doc_vs_type", "No aplica o faltan datos.", ["customer_doc"])]
    doc = str(doc)
    if dt == "factura" and len(doc) != 11:
        return [CheckResult(id="customer_doc_vs_type", rule="customer_doc_vs_type", status="warn", severity="warning",
                            message="Una factura normalmente se emite a un cliente con RUC.",
                            fields=["customer_doc"], observed=doc)]
    return [CheckResult(id="customer_doc_vs_type", rule="customer_doc_vs_type", status="pass",
                        message="Documento del cliente coherente con el tipo de comprobante.",
                        fields=["customer_doc"], observed=doc)]


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------
@rule("item_lines")
def check_item_lines(ctx: Context) -> list[CheckResult]:
    line_tol, _, _ = _tol()
    out = []
    for i, it in enumerate(ctx.items):
        q, p, a = parse_decimal(it.quantity), parse_decimal(it.unit_price), parse_decimal(it.amount)
        if q is None or p is None or a is None:
            out.append(_skip(f"item_line_{i + 1}", f"Ítem {i + 1}: faltan cantidad, precio o importe.",
                             [f"items[{i}]"]))
            continue
        expected = (q * p).quantize(D("0.01"))
        ok = abs(expected - a) <= line_tol
        # line-level mismatches are far more often reading errors than document errors -> review
        out.append(CheckResult(id=f"item_line_{i + 1}", rule="item_lines", status="pass" if ok else "warn",
                               severity="info" if ok else "warning",
                               message=(f"Ítem {i + 1}: {q} × {p} = {expected}" + ("" if ok else
                                        f" ≠ {a}; revise la lectura de esta línea")),
                               fields=[f"items[{i}]"], expected=str(expected), observed=str(a),
                               tolerance=str(line_tol)))
    return out


@rule("items_sum")
def check_items_sum(ctx: Context) -> list[CheckResult]:
    amounts = [parse_decimal(it.amount) for it in ctx.items]
    if not amounts or any(a is None for a in amounts):
        return [_skip("items_sum", "No hay importes de ítems completos.", ["items"])]
    _, sum_tol, _ = _tol()
    tol = sum_tol + D("0.01") * len(amounts)
    s = sum(amounts, D("0"))
    taxable, total = ctx.money("taxable_amount"), ctx.money("total")
    discount = ctx.money("discount_amount") or D("0")
    if taxable is not None and abs(s - discount - taxable) <= tol:
        return [CheckResult(id="items_sum", rule="items_sum", status="pass",
                            message=f"La suma de ítems ({s}) coincide con la base imponible (precios sin IGV).",
                            fields=["items", "taxable_amount"], expected=str(s), observed=str(taxable),
                            tolerance=str(tol))]
    if total is not None and abs(s - discount - total) <= tol:
        return [CheckResult(id="items_sum", rule="items_sum", status="pass",
                            message=f"La suma de ítems ({s}) coincide con el total (precios con IGV incluido).",
                            fields=["items", "total"], expected=str(s), observed=str(total), tolerance=str(tol))]
    if taxable is None and total is None:
        return [_skip("items_sum", "Sin base imponible ni total para comparar.", ["items"])]
    # A mismatch may come from the document OR from an incomplete reading of the table (a missed line),
    # so it is a warning that sends the items to human review; totals_sum is the hard arithmetic check.
    return [CheckResult(id="items_sum", rule="items_sum", status="warn", severity="warning",
                        message=f"La suma de ítems ({s}) no coincide ni con la base ({taxable}) ni con el total "
                                f"({total}): revise los ítems (puede faltar una línea o haber un error).",
                        fields=["items", "taxable_amount", "total"], expected=str(s),
                        observed={"taxable_amount": str(taxable) if taxable is not None else None,
                                  "total": str(total) if total is not None else None}, tolerance=str(tol))]


@rule("totals_sum")
def check_totals_sum(ctx: Context) -> list[CheckResult]:
    total = ctx.money("total")
    parts = {n: ctx.money(n) for n in MONEY_PARTS_PLUS}
    present = {n: v for n, v in parts.items() if v is not None}
    if total is None or "taxable_amount" not in present and "exempt_amount" not in present \
            and "unaffected_amount" not in present:
        return [_skip("totals_sum", "Faltan el total o las bases para verificar la suma.", ["total"])]
    if "igv" not in present and present.get("taxable_amount") not in (None, D("0")):
        return [_skip("totals_sum", "Falta el IGV para verificar la suma del total.", ["igv", "total"])]
    _, sum_tol, _ = _tol()
    discount = ctx.money("discount_amount") or D("0")
    expected = sum(present.values(), D("0")) - discount
    ok = abs(expected - total) <= sum_tol
    detail = " + ".join(f"{n}={v}" for n, v in present.items())
    return [CheckResult(id="totals_sum", rule="totals_sum", status="pass" if ok else "fail",
                        severity="info" if ok else "error",
                        message=(f"Total verificado: {detail}" + (f" − descuento {discount}" if discount else "")
                                 + f" = {expected}" + ("" if ok else f" ≠ total impreso {total}")),
                        fields=list(present) + ["total"], expected=str(expected), observed=str(total),
                        tolerance=str(sum_tol))]


@rule("tax_rate")
def check_tax_rate(ctx: Context) -> list[CheckResult]:
    igv, base = ctx.money("igv"), ctx.money("taxable_amount")
    if igv is None or base is None or base == 0:
        return [_skip("tax_rate", "Faltan IGV o base imponible para calcular la tasa.", ["igv", "taxable_amount"])]
    cfg = tax_config()["igv"]
    tol_rate, tol_abs = D(str(cfg["tolerance_rate"])), D(str(cfg["tolerance_abs"]))
    implied = (igv / base).quantize(D("0.0001"))
    matches = [r for r in cfg["rates"] if abs(D(str(r["rate"])) * base - igv) <= tol_abs
               or abs(D(str(r["rate"])) - implied) <= tol_rate]
    out = []
    if matches:
        r = matches[0]
        out.append(CheckResult(id="tax_rate", rule="tax_rate", status="pass",
                               message=f"Tasa observada {implied * 100:.2f}% coincide con «{r['label']}» "
                                       f"({D(str(r['rate'])) * 100:.0f}%).",
                               fields=["igv", "taxable_amount"], expected=str(r["rate"]), observed=str(implied)))
    else:
        out.append(CheckResult(id="tax_rate", rule="tax_rate", status="warn", severity="warning",
                               message=f"Tasa observada {implied * 100:.2f}% no coincide con ninguna tasa "
                                       "configurada; requiere revisión.",
                               fields=["igv", "taxable_amount"], observed=str(implied)))
    printed = ctx.money("igv_rate")
    if printed is not None:
        ok = abs(printed / 100 - implied) <= tol_rate * 5
        out.append(CheckResult(id="tax_rate_printed", rule="tax_rate", status="pass" if ok else "warn",
                               severity="info" if ok else "warning",
                               message=(f"La tasa impresa ({printed}%) es coherente con los importes." if ok else
                                        f"La tasa impresa ({printed}%) no coincide con la tasa implícita "
                                        f"({implied * 100:.2f}%)."),
                               fields=["igv_rate", "igv"], expected=str(printed), observed=str(implied * 100)))
    return out


@rule("amount_in_words")
def check_amount_in_words(ctx: Context) -> list[CheckResult]:
    words, total = ctx.val("amount_in_words"), ctx.money("total")
    if not words or total is None:
        return [_skip("amount_in_words", "Sin importe en letras o sin total.", ["amount_in_words"])]
    parsed = parse_amount_in_words(str(words))
    if parsed is None:
        return [_skip("amount_in_words", "No se pudo interpretar el importe en letras.", ["amount_in_words"])]
    ok = abs(parsed - total) <= D("0.01")
    return [CheckResult(id="amount_in_words", rule="amount_in_words", status="pass" if ok else "fail",
                        severity="info" if ok else "error",
                        message=(f"El importe en letras ({parsed}) coincide con el total." if ok else
                                 f"El importe en letras ({parsed}) no coincide con el total ({total})."),
                        fields=["amount_in_words", "total"], expected=str(parsed), observed=str(total))]


# ---------------------------------------------------------------------------
# Dates, currency
# ---------------------------------------------------------------------------
@rule("dates")
def check_dates(ctx: Context) -> list[CheckResult]:
    cfg = tax_config()["dates"]
    issue = ctx.val("issue_date")
    if not issue:
        return [_skip("dates", "Sin fecha de emisión.", ["issue_date"])]
    try:
        d = date.fromisoformat(str(issue))
    except ValueError:
        return [CheckResult(id="issue_date_valid", rule="dates", status="fail", severity="error",
                            message="La fecha de emisión no es una fecha válida.", fields=["issue_date"],
                            observed=issue)]
    out = []
    if d > ctx.today + timedelta(days=int(cfg["future_tolerance_days"])):
        out.append(CheckResult(id="issue_date_future", rule="dates", status="fail", severity="error",
                               message=f"La fecha de emisión {d.isoformat()} está en el futuro.",
                               fields=["issue_date"], observed=d.isoformat()))
    elif d < ctx.today.replace(year=ctx.today.year - int(cfg["max_age_years"])):
        out.append(CheckResult(id="issue_date_old", rule="dates", status="warn", severity="warning",
                               message=f"Fecha de emisión inusualmente antigua ({d.isoformat()}).",
                               fields=["issue_date"], observed=d.isoformat()))
    else:
        out.append(CheckResult(id="issue_date_valid", rule="dates", status="pass",
                               message=f"Fecha de emisión válida ({d.isoformat()}).", fields=["issue_date"],
                               observed=d.isoformat()))
    due = ctx.val("due_date")
    if due:
        try:
            dd = date.fromisoformat(str(due))
            ok = dd >= d
            out.append(CheckResult(id="due_after_issue", rule="dates", status="pass" if ok else "fail",
                                   severity="info" if ok else "error",
                                   message="Vencimiento posterior o igual a la emisión." if ok else
                                   "La fecha de vencimiento es anterior a la de emisión.",
                                   fields=["issue_date", "due_date"]))
        except ValueError:
            pass
    return out


@rule("currency")
def check_currency(ctx: Context) -> list[CheckResult]:
    cur = ctx.val("currency")
    symbols = {fv.currency for n, fv in ctx.fields.items() if fv is not None and getattr(fv, "currency", None)}
    if not cur and not symbols:
        return [_skip("currency", "Moneda no identificada.", ["currency"])]
    if cur and symbols and any(s != cur for s in symbols):
        return [CheckResult(id="currency", rule="currency", status="warn", severity="warning",
                            message=f"Moneda declarada {cur} pero los importes muestran {', '.join(sorted(symbols))}.",
                            fields=["currency"], observed=sorted(symbols), expected=cur)]
    return [CheckResult(id="currency", rule="currency", status="pass",
                        message=f"Moneda coherente: {cur or next(iter(symbols))}.", fields=["currency"])]


# ---------------------------------------------------------------------------
# Coherence between sources
# ---------------------------------------------------------------------------
@rule("qr_consistency")
def check_qr(ctx: Context) -> list[CheckResult]:
    if not ctx.qr:
        return [_skip("qr_consistency", "No se encontró QR SUNAT legible.", [])]
    out = []
    pairs = [("issuer_ruc", "issuer_ruc"), ("serie_numero", "serie_numero"), ("total", "total"), ("igv", "igv"),
             ("issue_date", "issue_date"), ("customer_doc", "customer_doc")]
    for field_name, qr_key in pairs:
        fv = ctx.fields.get(field_name)
        qv = ctx.qr.get(qr_key)
        if fv is None or qv is None:
            continue
        others = [s for s in fv.sources if s.source != "qr" and s.value is not None]
        for s in others:
            same = (parse_decimal(str(s.value)) == parse_decimal(str(qv))) if field_name in ("total", "igv") \
                else str(s.value).upper() == str(qv).upper()
            if same:
                status, severity = "pass", "info"
                msg = f"{field_name}: QR y {s.source} coinciden ({qv})."
            elif s.source == "vlm":
                # the printed document agrees with its QR; the model misread it -> review, not an invalid document
                status, severity = "warn", "warning"
                msg = (f"{field_name}: el modelo leyó {s.value} pero el QR indica {qv} "
                       "(probable error de lectura del modelo; se conserva el valor del QR).")
            else:
                status, severity = "fail", "error"
                msg = f"{field_name}: el QR indica {qv} pero el texto impreso ({s.source}) dice {s.value}."
            out.append(CheckResult(id=f"qr_vs_{s.source}_{field_name}", rule="qr_consistency", status=status,
                                   severity=severity, message=msg, fields=[field_name], expected=qv,
                                   observed=s.value))
    return out or [_skip("qr_consistency", "El QR no tiene campos comparables con lo extraído.", [])]


@rule("source_agreement")
def check_sources(ctx: Context) -> list[CheckResult]:
    out = []
    for name, fv in ctx.fields.items():
        if fv is None:
            continue
        disagreements = [r for r in fv.review_reasons if r.startswith("Las fuentes discrepan")]
        if disagreements:
            out.append(CheckResult(id=f"sources_{name}", rule="source_agreement", status="warn", severity="warning",
                                   message=f"{name}: {disagreements[0]}", fields=[name]))
    if not out:
        multi = sum(1 for fv in ctx.fields.values() if fv is not None and len(fv.sources) > 1)
        if multi:
            out.append(CheckResult(id="sources", rule="source_agreement", status="pass",
                                   message=f"{multi} campo(s) confirmados por más de una fuente sin contradicciones."))
        else:
            out.append(_skip("sources", "Ningún campo tiene más de una fuente para comparar.", []))
    return out


@rule("document_type_agreement")
def check_doc_type(ctx: Context) -> list[CheckResult]:
    r, v = ctx.rules_document_type, ctx.vlm_document_type
    if not r or not v:
        return [_skip("document_type_agreement", "Solo una fuente clasificó el documento.", [])]
    ok = r == v
    return [CheckResult(id="document_type_agreement", rule="document_type_agreement", status="pass" if ok else "warn",
                        severity="info" if ok else "warning",
                        message=(f"Reglas y modelo coinciden en el tipo: {r}." if ok else
                                 f"Las reglas clasifican '{r}' y el modelo '{v}'."),
                        expected=r, observed=v)]


@rule("duplicate")
def check_duplicate(ctx: Context) -> list[CheckResult]:
    if not ctx.val("issuer_ruc") or not ctx.val("serie_numero"):
        return [_skip("duplicate", "Sin RUC y serie-número para buscar duplicados.", [])]
    if ctx.duplicates:
        refs = ", ".join(d["id"][:8] for d in ctx.duplicates[:5])
        return [CheckResult(id="duplicate", rule="duplicate", status="warn", severity="warning",
                            message=f"Ya existe(n) {len(ctx.duplicates)} registro(s) con el mismo RUC y "
                                    f"serie-número ({refs}).",
                            fields=["issuer_ruc", "serie_numero"], observed=ctx.duplicates[:5])]
    return [CheckResult(id="duplicate", rule="duplicate", status="pass",
                        message="No hay otro registro con el mismo RUC y serie-número.",
                        fields=["issuer_ruc", "serie_numero"])]


@rule("prompt_injection")
def check_injection(ctx: Context) -> list[CheckResult]:
    findings = injection.scan(ctx.text_lines)
    if not ctx.text_lines:
        return [_skip("prompt_injection", "Sin texto para analizar.", [])]
    if findings:
        return [CheckResult(id="prompt_injection", rule="prompt_injection", status="warn", severity="warning",
                            message=f"El documento contiene {len(findings)} texto(s) con forma de instrucción. "
                                    "Se trataron como datos; revise el documento.",
                            observed=findings[:5])]
    return [CheckResult(id="prompt_injection", rule="prompt_injection", status="pass",
                        message="No se detectaron textos con forma de instrucción.")]


# ---------------------------------------------------------------------------
def validate(ctx: Context) -> ValidationReport:
    checks: list[CheckResult] = []
    for rule_id in ctx.schema.rules:
        fn = RULES.get(rule_id)
        if fn is not None:
            checks.extend(fn(ctx))
    needs_review = []
    for name, fv in ctx.fields.items():
        spec = ctx.schema.field(name)
        if fv is None:
            if spec is not None and spec.required:
                needs_review.append(name)
        elif fv.needs_review:
            needs_review.append(name)
    for i, it in enumerate(ctx.items):
        if it.needs_review:
            needs_review.append(f"items[{i}]")
    for c in checks:
        if c.status == "fail" or (c.status == "warn" and c.rule in ("items_sum", "item_lines")):
            for f in c.fields:
                if f not in needs_review:
                    needs_review.append(f)
    statuses = [c.status for c in checks]
    if "fail" in statuses:
        status = "invalid"
    elif "warn" in statuses:
        status = "valid_with_warnings"
    elif "pass" in statuses:
        status = "valid"
    else:
        status = "insufficient_data"
    warnings = [c.message for c in checks if c.status in ("warn", "fail")]
    missing = [n for n, fv in ctx.fields.items() if fv is None and ctx.schema.field(n) and ctx.schema.field(n).required]
    if missing:
        warnings.append("Campos requeridos no encontrados: " + ", ".join(missing))
    return ValidationReport(status=status, checks=checks, warnings=warnings, needs_review=needs_review)
