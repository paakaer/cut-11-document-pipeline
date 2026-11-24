import { useEffect, useState } from "react";
import { api, Metrics } from "./api";
import { fmtEur, fmtUsd, pct } from "./format";

const FIELD_LABEL: Record<string, string> = {
  date: "Page date",
  time: "Time",
  customer: "Customer",
  phone: "Phone",
  items: "Items",
  fulfilment: "Pickup / delivery",
  address: "Address",
  total_eur: "Total",
  paid: "Paid",
};

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

export function MetricsView() {
  const [m, setM] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.metrics().then(setM).catch((e) => setError(String(e.message)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!m) return <p className="muted">Loading…</p>;
  const a = m.accuracy;
  const fields = Object.entries(a.per_field).sort((x, y) => (x[1].accuracy ?? 0) - (y[1].accuracy ?? 0));

  return (
    <div className="metrics">
      <p className="lede">
        Accuracy is measured against what reviewers approved: every correction counts as a model error. {m.reviewed} of{" "}
        {m.documents} pages reviewed so far.
      </p>

      <div className="tiles">
        <Tile label="Field accuracy" value={pct(a.field_accuracy)} sub={`${a.fields} fields on ${a.pages} pages`} />
        <Tile
          label="Pages needing no correction"
          value={pct(a.perfect_page_rate)}
          sub={`${a.perfect_pages} of ${a.pages}`}
        />
        <Tile
          label="Model cost per page"
          value={fmtEur(m.cost_per_document_eur)}
          sub={m.cost_per_document_usd == null ? undefined : `${fmtUsd(m.cost_per_document_usd)} billed`}
        />
        <Tile
          label="All-in cost per page"
          value={fmtEur(m.all_in_cost_per_document_eur)}
          sub={
            m.review_seconds_mean == null ? "needs reviews" : `incl. ${Math.round(m.review_seconds_mean)} s of review`
          }
        />
        <Tile
          label="Model latency"
          value={m.latency_ms_p50 == null ? "–" : `${(m.latency_ms_p50 / 1000).toFixed(1)} s`}
          sub={m.latency_ms_p95 == null ? undefined : `p95 ${(m.latency_ms_p95 / 1000).toFixed(1)} s`}
        />
        <Tile
          label="Errors the model flagged"
          value={pct(a.flag_recall)}
          sub={`${pct(a.flag_precision)} of flags were real`}
        />
      </div>

      <div className="two-col">
        <section className="card">
          <h3>Accuracy by field</h3>
          {fields.length === 0 ? (
            <p className="muted">Approve a page to see this.</p>
          ) : (
            <ul className="bars">
              {fields.map(([name, d]) => (
                <li key={name}>
                  <span className="bar-label">{FIELD_LABEL[name] ?? name}</span>
                  <span className="bar-track">
                    <span className="bar-fill" style={{ width: `${(d.accuracy ?? 0) * 100}%` }} />
                  </span>
                  <span className="bar-value">{pct(d.accuracy)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <h3>What review catches</h3>
          <dl className="facts">
            <dt>Orders the model missed</dt>
            <dd>{a.missed_entries}</dd>
            <dt>Orders it invented</dt>
            <dd>{a.spurious_entries}</dd>
            <dt>Error rate if only flagged fields are checked</dt>
            <dd>{pct(a.residual_error_rate)}</dd>
            <dt>Total model spend</dt>
            <dd>{fmtUsd(m.total_cost_usd)}</dd>
          </dl>
          {Object.keys(m.accuracy_by_model).length > 1 && (
            <>
              <h3>By model</h3>
              <table className="docs compact">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th className="num">Pages</th>
                    <th className="num">Accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(m.accuracy_by_model).map(([model, s]) => (
                    <tr key={model}>
                      <td className="mono">{model}</td>
                      <td className="num">{s.pages}</td>
                      <td className="num">{pct(s.field_accuracy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
