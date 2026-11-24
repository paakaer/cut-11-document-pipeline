export type Item = { name: string; quantity: number };
export type Entry = {
  time: string | null;
  customer: string;
  phone: string | null;
  items: Item[];
  fulfilment: "pickup" | "delivery";
  address: string | null;
  total_eur: number | null;
  paid: boolean;
};
export type Page = { date: string | null; entries: Entry[]; uncertain_fields: string[] };

export type DocStatus = "queued" | "processing" | "needs_review" | "approved" | "failed";

export type DocSummary = {
  id: number;
  filename: string;
  status: DocStatus;
  error: string | null;
  created_at: string;
  model: string | null;
  cost_usd: number | null;
  latency_ms: number | null;
  flagged: number | null;
};

export type DocDetail = {
  id: number;
  filename: string;
  status: DocStatus;
  error: string | null;
  extraction: null | {
    id: number;
    model: string;
    data: Page;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    latency_ms: number;
  };
  review: null | { data: Page; review_seconds: number; reviewed_at: string };
};

export type Summary = {
  pages: number;
  fields: number;
  field_accuracy: number | null;
  perfect_pages: number;
  perfect_page_rate: number | null;
  missed_entries: number;
  spurious_entries: number;
  flag_recall: number | null;
  flag_precision: number | null;
  residual_error_rate: number | null;
  per_field: Record<string, { total: number; correct: number; accuracy: number | null }>;
};

export type Metrics = {
  documents: number;
  extractions: number;
  reviewed: number;
  accuracy: Summary;
  accuracy_by_model: Record<string, Summary>;
  cost_per_document_usd: number | null;
  cost_per_document_eur: number | null;
  total_cost_usd: number;
  latency_ms_p50: number | null;
  latency_ms_p95: number | null;
  review_seconds_mean: number | null;
  review_cost_per_document_eur: number | null;
  all_in_cost_per_document_eur: number | null;
};

export type Config = { extractor: string; eur_per_usd: number; reviewer_eur_per_hour: number };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, init);
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${r.status}: ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  config: () => call<Config>("/api/config"),
  list: () => call<DocSummary[]>("/api/documents"),
  get: (id: number) => call<DocDetail>(`/api/documents/${id}`),
  imageUrl: (id: number) => `/api/documents/${id}/image`,
  upload: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return call<{ ids: number[] }>("/api/documents", { method: "POST", body: fd });
  },
  reExtract: (id: number) => call<{ id: number }>(`/api/documents/${id}/extract`, { method: "POST" }),
  review: (id: number, data: Page, review_seconds: number) =>
    call<{ fields: number; corrected: number }>(`/api/documents/${id}/review`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ data, review_seconds }),
    }),
  metrics: () => call<Metrics>("/api/metrics"),
};
