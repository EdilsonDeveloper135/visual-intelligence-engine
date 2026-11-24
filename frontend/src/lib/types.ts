export type Provenance = "observed" | "computed" | "inferred";
export type SourceName = "qr" | "ocr_rules" | "vlm" | "pdf_text" | "human" | "validator";

export interface Score {
  value: number;
  source: string;
  note?: string;
}

export interface TextLine {
  id: string;
  page: number;
  text: string;
  bbox: [number, number, number, number];
  polygon?: number[][] | null;
  score: Score | null;
  source: "ocr" | "pdf_text";
}

export interface FieldSource {
  source: SourceName;
  value: unknown;
  raw?: string | null;
  evidence_ids: string[];
}

export interface FieldValue {
  value: string | number | null;
  raw: string | null;
  type: string;
  unit?: string | null;
  currency?: string | null;
  provenance: Provenance;
  source: SourceName | null;
  sources: FieldSource[];
  evidence_ids: string[];
  bounding_box: [number, number, number, number] | null;
  page: number | null;
  score: Score | null;
  needs_review: boolean;
  review_reasons: string[];
  edited_by_human: boolean;
  doc_type?: string;
}

export interface Item {
  description: string | null;
  quantity: string | null;
  unit: string | null;
  unit_price: string | null;
  amount: string | null;
  provenance: Provenance;
  source: SourceName | null;
  evidence_ids: string[];
  bounding_box: [number, number, number, number] | null;
  page: number | null;
  needs_review: boolean;
}

export interface CheckResult {
  id: string;
  rule: string;
  status: "pass" | "fail" | "warn" | "skipped";
  severity: "info" | "warning" | "error";
  message: string;
  fields: string[];
  expected?: unknown;
  observed?: unknown;
  tolerance?: string | null;
}

export type ValidationStatus = "pending" | "valid" | "valid_with_warnings" | "invalid" | "insufficient_data";

export interface PageInfo {
  index: number;
  width: number;
  height: number;
  source_size: number[] | null;
  quality: { metrics?: Record<string, number>; flags?: string[]; level?: string };
  preprocessing: { name: string; applied: boolean; [k: string]: unknown }[];
  document_quad: number[][] | null;
  work_asset_id: string | null;
  processed_asset_id: string | null;
  display_asset_id: string | null;
  text_source: "ocr" | "pdf_text" | "none";
}

export interface Code {
  format: string;
  text: string;
  page: number;
  bbox: [number, number, number, number] | null;
  parsed: Record<string, string | null> | null;
  source: string;
}

export interface ObservationResult {
  observation_id: string;
  source: string;
  document_type: string | null;
  document_type_info: { final: string | null; rules: string | null; vlm: string | null; qr: string | null; human: boolean };
  is_document: boolean | null;
  description: string | null;
  language: string | null;
  pages: PageInfo[];
  text: { full_text: string; lines: TextLine[] };
  entities: { type: string; value: string; normalized: string | null; role: string | null; evidence_ids: string[]; source: string; provenance: Provenance }[];
  objects: { label: string; source: string; verified: boolean | null; verified_by?: string; bounding_box: number[] | null }[];
  codes: Code[];
  fields: Record<string, FieldValue | null>;
  dynamic_fields: (FieldValue & { key: string; label: string })[];
  items: Item[];
  relationships: { type: string; source: string; target: string; description: string | null; derived_by: string }[];
  unreadable: { element: string; reason: string | null; source: string }[];
  inferences: { statement: string; basis: string | null; source: string }[];
  validation: { status: ValidationStatus; checks: CheckResult[]; warnings: string[]; needs_review: string[]; validator: string };
  metadata: {
    model: string | null;
    model_digest: string | null;
    ocr_engine: string | null;
    pipeline_version: string | null;
    processing_time_ms: number | null;
    timings: Record<string, number>;
    schema_id: string | null;
    vlm_status: string;
    vlm_error: string | null;
    vlm_tokens?: Record<string, number | string | null> | null;
    [k: string]: unknown;
  };
}

export type ObsStatus = "queued" | "processing" | "ocr_ready" | "interpreting" | "completed" | "partial" | "failed";

export interface ObservationSummary {
  id: string;
  created_at: string;
  updated_at: string;
  source: string;
  status: ObsStatus;
  stage: string | null;
  kind: string;
  document_type: string | null;
  title: string | null;
  description: string | null;
  validation_status: ValidationStatus | null;
  needs_review_count: number;
  warnings_count: number;
  issuer_ruc: string | null;
  serie_numero: string | null;
  issue_date: string | null;
  total: string | null;
  currency: string | null;
  original_filename: string | null;
  page_count: number;
  thumbnail_asset_id: string | null;
  camera_session_id: string | null;
  supersedes_id: string | null;
  repeat_count: number;
  model_name: string | null;
  processing_ms: number | null;
  deleted_at: string | null;
}

export interface AssetOut {
  id: string;
  kind: string;
  page_index: number;
  mime: string;
  width: number | null;
  height: number | null;
  size_bytes: number;
}

export interface ObservationDetail extends ObservationSummary {
  mode: string;
  error: { code: string; message: string } | null;
  result: ObservationResult;
  assets: AssetOut[];
  model_digest: string | null;
  ocr_engine: string | null;
  pipeline_version: string | null;
  schema_id: string | null;
  original_mime: string | null;
  original_sha256: string | null;
  revisions: number;
}

export interface VieEvent {
  id?: number;
  type: string;
  level: string;
  message: string;
  observation_id: string | null;
  data: Record<string, unknown>;
  ts: string;
  backlog?: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "queued" | "streaming" | "done" | "error";
  region: { page: number; bbox: number[] } | null;
  evidence_ids: string[];
  model: string | null;
  duration_ms: number | null;
  created_at: string;
}
