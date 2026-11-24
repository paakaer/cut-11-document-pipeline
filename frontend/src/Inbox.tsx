import { useCallback, useEffect, useRef, useState } from "react";
import { api, DocSummary } from "./api";
import { fmtUsd } from "./format";

const STATUS_LABEL: Record<DocSummary["status"], string> = {
  queued: "Queued",
  processing: "Reading",
  needs_review: "Needs review",
  approved: "Approved",
  failed: "Failed",
};

export function Inbox() {
  const [docs, setDocs] = useState<DocSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(() => api.list().then(setDocs).catch((e) => setError(String(e.message ?? e))), []);

  useEffect(() => {
    load();
  }, [load]);

  // Poll while anything is still being read.
  const busy = docs?.some((d) => d.status === "queued" || d.status === "processing");
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [busy, load]);

  async function upload(files: File[]) {
    const images = files.filter((f) => f.type.startsWith("image/"));
    if (!images.length) return setError("Drop image files (JPEG, PNG, WebP).");
    setError(null);
    setUploading(true);
    try {
      await api.upload(images);
      await load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setUploading(false);
    }
  }

  const toReview = docs?.filter((d) => d.status === "needs_review") ?? [];

  return (
    <div className="inbox">
      <section
        className={`drop ${dragging ? "over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(Array.from(e.dataTransfer.files));
        }}
      >
        <div>
          <strong>Drop notebook photos here</strong>
          <p>Each page is read by the model, then waits for a person to check it.</p>
        </div>
        <button className="btn" onClick={() => input.current?.click()} disabled={uploading}>
          {uploading ? "Uploading…" : "Choose files"}
        </button>
        <input
          ref={input}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => upload(Array.from(e.target.files ?? []))}
        />
      </section>

      {error && <p className="error">{error}</p>}

      <div className="list-head">
        <h2>Pages</h2>
        {toReview.length > 0 && (
          <a className="btn primary" href={`#/doc/${toReview[toReview.length - 1].id}`}>
            Review next ({toReview.length} waiting)
          </a>
        )}
      </div>

      {docs === null ? (
        <p className="muted">Loading…</p>
      ) : docs.length === 0 ? (
        <p className="muted">No pages yet. Try the samples in <code>evals/data/</code>.</p>
      ) : (
        <div className="table-wrap">
          <table className="docs">
            <thead>
              <tr>
                <th>Page</th>
                <th>Status</th>
                <th className="num">To check</th>
                <th>Model</th>
                <th className="num">Cost</th>
                <th className="num">Time</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} onClick={() => (window.location.hash = `#/doc/${d.id}`)}>
                  <td>
                    <a href={`#/doc/${d.id}`}>{d.filename}</a>
                    {d.error && <div className="error small">{d.error}</div>}
                  </td>
                  <td>
                    <span className={`badge ${d.status}`}>{STATUS_LABEL[d.status]}</span>
                  </td>
                  <td className="num">{d.flagged ?? "–"}</td>
                  <td className="mono">{d.model ?? "–"}</td>
                  <td className="num">{d.cost_usd == null ? "–" : fmtUsd(d.cost_usd)}</td>
                  <td className="num">{d.latency_ms == null ? "–" : `${(d.latency_ms / 1000).toFixed(1)} s`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
