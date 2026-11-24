/** User-facing vocabulary (Spanish). Names describe what users see, not how the system works. */

export const DOC_TYPES: Record<string, string> = {
  factura: "Factura electrónica",
  boleta: "Boleta de venta",
  nota_credito: "Nota de crédito",
  nota_debito: "Nota de débito",
  guia_remision: "Guía de remisión",
  recibo: "Recibo",
  recibo_honorarios: "Recibo por honorarios",
  comprobante_pago: "Comprobante de pago",
  orden_compra: "Orden de compra",
  cotizacion: "Cotización",
  ticket: "Ticket",
  otro_documento: "Otro documento",
  no_documento: "No es un documento",
};

export const FIELD_LABELS: Record<string, string> = {
  issuer_name: "Emisor",
  issuer_ruc: "RUC del emisor",
  issuer_address: "Dirección del emisor",
  serie_numero: "Serie y número",
  issue_date: "Fecha de emisión",
  due_date: "Fecha de vencimiento",
  currency: "Moneda",
  customer_name: "Cliente",
  customer_doc: "Documento del cliente",
  taxable_amount: "Op. gravada",
  exempt_amount: "Op. exonerada",
  unaffected_amount: "Op. inafecta",
  free_amount: "Op. gratuita",
  discount_amount: "Descuentos",
  igv: "IGV",
  igv_rate: "Tasa IGV impresa",
  isc: "ISC",
  icbper: "ICBPER",
  other_charges: "Otros cargos",
  total: "Importe total",
  amount_in_words: "Importe en letras",
  payment_terms: "Forma de pago",
  reference_document: "Documento que modifica",
  document_number: "Número de documento",
  subtotal: "Subtotal",
  reference: "Referencia",
};

export const SOURCES: Record<string, string> = {
  qr: "QR",
  ocr_rules: "OCR",
  vlm: "Modelo",
  pdf_text: "PDF",
  human: "Persona",
  validator: "Cálculo",
};

export const STATUS: Record<string, string> = {
  queued: "En cola",
  processing: "Leyendo",
  ocr_ready: "Texto listo",
  interpreting: "Interpretando",
  completed: "Completado",
  partial: "Parcial",
  failed: "Error",
};

export const VALIDATION: Record<string, string> = {
  pending: "Pendiente",
  valid: "Verificado",
  valid_with_warnings: "Con advertencias",
  invalid: "Inconsistente",
  insufficient_data: "Datos insuficientes",
};

export const CHECK_STATUS: Record<string, string> = {
  pass: "Correcto",
  fail: "Falla",
  warn: "Advertencia",
  skipped: "Sin datos",
};

export const QUALITY_FLAGS: Record<string, string> = {
  blurry: "Desenfocada",
  too_dark: "Oscura",
  overexposed: "Sobreexpuesta",
  low_contrast: "Bajo contraste",
  noisy: "Con ruido",
  low_resolution: "Baja resolución",
};

export const STEPS: Record<string, string> = {
  perspective_correction: "Corrección de perspectiva",
  deskew: "Enderezado",
  illumination_and_contrast: "Iluminación y contraste",
  denoise: "Reducción de ruido",
  upscale_small_document: "Ampliación del documento",
  preprocessing: "Preprocesamiento",
};

export const fieldLabel = (k: string) => FIELD_LABELS[k] ?? k.replace(/_/g, " ");
export const docTypeLabel = (k: string | null | undefined) => (k ? (DOC_TYPES[k] ?? k) : "Sin clasificar");
