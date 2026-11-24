import { useEffect, useMemo, useRef, useState } from "react";
import { api, DocDetail, Entry, Page } from "./api";
import { fmtUsd } from "./format";

type DraftEntry = Entry & { _orig: number | null }; // index in the extraction, null if added by the reviewer
type Draft = { date: string | null; entries: DraftEntry[] };

const blankEntry = (): DraftEntry => ({
  time: null,
  customer: "",
  phone: null,
  items: [{ name: "", quantity: 1 }],
  fulfilment: "pickup",
  address: null,
  total_eur: null,
  paid: false,
  _orig: null,
});

const toDraft = (p: Page): Draft => ({
  date: p.date,
  entries: p.entries.map((e, i) => ({ ...e, items: e.items.map((it) => ({ ...it })), _orig: i })),
});

const fromDraft = (d: Draft): Page => ({
  date: d.date || null,
  entries: d.entries.map(({ _orig, ...e }) => ({
    ...e,
    customer: e.customer.trim(),
    items: e.items.filter((it) => it.name.trim()).map((it) => ({ name: it.name.trim(), quantity: it.quantity })),
    address: e.fulfilment === "pickup" ? null : e.address,
  })),
  uncertain_fields: [],
});

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function Review({ id }: { id: number }) {
  const [doc, setDoc] = useState<DocDetail | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const started = useRef(Date.now());
  const form = useRef<HTMLFormElement>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .get(id)
        .then((d) => {
          if (!alive) return;
          setDoc(d);
          if (d.status === "queued" || d.status === "processing") {
            setTimeout(load, 1500);
            return;
          }
          const source = d.review?.data ?? d.extraction?.data;
          if (source) {
            setDraft(toDraft(source));
            started.current = Date.now();
          }
        })
        .catch((e) => setError(String(e.message)));
    load();
    return () => {
      alive = false;
    };
  }, [id]);

  const original = doc?.extraction?.data;
  const flagged = useMemo(() => new Set(original?.uncertain_fields ?? []), [original]);

  if (error) return <p className="error">{error}</p>;
  if (!doc) return <p className="muted">Loading…</p>;
  if (doc.status === "queued" || doc.status === "processing") return <p className="muted">Reading the page…</p>;
  if (!draft || !original) {
    return (
      <div className="stack">
        <p className="error">{doc.error ?? "No extraction for this page."}</p>
        <button className="btn" onClick={() => api.reExtract(id).then(() => location.reload())}>
          Try again
        </button>
      </div>
    );
  }

  const isFlag = (e: DraftEntry, f: string) => e._orig !== null && flagged.has(`entries[${e._orig}].${f}`);
  const isChanged = (e: DraftEntry, f: keyof Entry) =>
    e._orig === null || !same(e[f], original.entries[e._orig]?.[f]);
  const flagCount = flagged.size;
  const changedCount =
    draft.entries.reduce(
      (n, e) =>
        n +
        (["time", "customer", "phone", "items", "fulfilment", "address", "total_eur", "paid"] as const).filter((f) =>
          isChanged(e, f),
        ).length,
      0,
    ) +
    (draft.date !== original.date ? 1 : 0) +
    (original.entries.length - draft.entries.filter((e) => e._orig !== null).length);

  const setEntry = (i: number, patch: Partial<DraftEntry>) =>
    setDraft({ ...draft, entries: draft.entries.map((e, j) => (j === i ? { ...e, ...patch } : e)) });

  function nextFlag() {
    const els = Array.from(form.current?.querySelectorAll<HTMLElement>("[data-flag='1']") ?? []);
    if (!els.length) return;
    const cur = els.indexOf(document.activeElement as HTMLElement);
    const next = els[(cur + 1) % els.length];
    next.focus();
    next.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  async function approve() {
    if (!draft) return;
    setSaving(true);
    setError(null);
    try {
      const seconds = Math.round((Date.now() - started.current) / 1000);
      const r = await api.review(id, fromDraft(draft), seconds);
      setDone(`Approved in ${seconds} s · ${r.corrected} of ${r.fields} fields corrected`);
      const next = (await api.list()).filter((d) => d.status === "needs_review" && d.id !== id);
      setTimeout(() => {
        window.location.hash = next.length ? `#/doc/${next[next.length - 1].id}` : "#/";
      }, 900);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setSaving(false);
    }
  }

  const ext = doc.extraction!;

  return (
    <div className="review">
      <section className="viewer">
        <div className="viewer-bar">
          <span className="mono small">{doc.filename}</span>
          <div className="seg">
            {(["fit", 1, 1.5, 2] as const).map((z) => (
              <button key={String(z)} className={zoom === z ? "on" : ""} onClick={() => setZoom(z)}>
                {z === "fit" ? "Fit" : `${z * 100}%`}
              </button>
            ))}
          </div>
        </div>
        <div className="viewer-img">
          <img
            src={api.imageUrl(id)}
            alt={`Scan of ${doc.filename}`}
            style={zoom === "fit" ? { width: "100%" } : { width: `${zoom * 100}%`, maxWidth: "none" }}
          />
        </div>
      </section>

      <form
        className="panel"
        ref={form}
        onSubmit={(e) => {
          e.preventDefault();
          approve();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            approve();
          }
        }}
      >
        <div className="panel-head">
          <div>
            <div className="stats">
              <span className={`pill ${flagCount ? "warn" : "ok"}`}>{flagCount} to check</span>
              <span className="pill">{changedCount} edited</span>
              {doc.status === "approved" && <span className="pill ok">approved</span>}
            </div>
            <div className="muted small mono">
              {ext.model} · {ext.input_tokens.toLocaleString()} in / {ext.output_tokens.toLocaleString()} out ·{" "}
              {fmtUsd(ext.cost_usd)} · {(ext.latency_ms / 1000).toFixed(1)} s
            </div>
          </div>
          <button type="button" className="btn" onClick={nextFlag} disabled={!flagCount}>
            Next to check ↓
          </button>
        </div>

        <label className={`field date ${flagged.has("date") ? "flag" : ""} ${draft.date !== original.date ? "changed" : ""}`}>
          <span>Page date</span>
          <input
            type="date"
            value={draft.date ?? ""}
            data-flag={flagged.has("date") ? "1" : undefined}
            onChange={(e) => setDraft({ ...draft, date: e.target.value || null })}
          />
        </label>

        {draft.entries.map((e, i) => {
          const cls = (f: keyof Entry) => `field ${isFlag(e, f) ? "flag" : ""} ${isChanged(e, f) ? "changed" : ""}`;
          const flagAttr = (f: string) => (isFlag(e, f) ? "1" : undefined);
          return (
            <fieldset key={i} className="entry">
              <legend>
                Order {i + 1}
                {e._orig === null && <em> · added</em>}
              </legend>
              <button
                type="button"
                className="icon remove"
                title="Remove order"
                onClick={() => setDraft({ ...draft, entries: draft.entries.filter((_, j) => j !== i) })}
              >
                ×
              </button>
              <div className="grid">
                <label className={cls("time")}>
                  <span>Time</span>
                  <input
                    value={e.time ?? ""}
                    placeholder="HH:MM"
                    pattern="\d{2}:\d{2}"
                    data-flag={flagAttr("time")}
                    onChange={(ev) => setEntry(i, { time: ev.target.value || null })}
                  />
                </label>
                <label className={`${cls("customer")} wide`}>
                  <span>Customer</span>
                  <input
                    value={e.customer}
                    required
                    data-flag={flagAttr("customer")}
                    onChange={(ev) => setEntry(i, { customer: ev.target.value })}
                  />
                </label>
                <label className={cls("phone")}>
                  <span>Phone</span>
                  <input
                    value={e.phone ?? ""}
                    inputMode="tel"
                    data-flag={flagAttr("phone")}
                    onChange={(ev) => setEntry(i, { phone: ev.target.value.replace(/\D/g, "") || null })}
                  />
                </label>
              </div>

              <div className={`${cls("items")} items`} data-flag={flagAttr("items")} tabIndex={isFlag(e, "items") ? 0 : -1}>
                <span>Items</span>
                {e.items.map((it, k) => (
                  <div className="item" key={k}>
                    <input
                      className="qty"
                      type="number"
                      min={1}
                      value={it.quantity}
                      aria-label="Quantity"
                      onChange={(ev) =>
                        setEntry(i, {
                          items: e.items.map((x, m) => (m === k ? { ...x, quantity: Math.max(1, Number(ev.target.value) || 1) } : x)),
                        })
                      }
                    />
                    <input
                      value={it.name}
                      aria-label="Dish"
                      onChange={(ev) =>
                        setEntry(i, { items: e.items.map((x, m) => (m === k ? { ...x, name: ev.target.value } : x)) })
                      }
                    />
                    <button
                      type="button"
                      className="icon"
                      title="Remove item"
                      onClick={() => setEntry(i, { items: e.items.filter((_, m) => m !== k) })}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  className="link"
                  onClick={() => setEntry(i, { items: [...e.items, { name: "", quantity: 1 }] })}
                >
                  + item
                </button>
              </div>

              <div className="grid">
                <label className={cls("fulfilment")}>
                  <span>Fulfilment</span>
                  <select
                    value={e.fulfilment}
                    data-flag={flagAttr("fulfilment")}
                    onChange={(ev) => setEntry(i, { fulfilment: ev.target.value as Entry["fulfilment"] })}
                  >
                    <option value="pickup">Pickup</option>
                    <option value="delivery">Delivery</option>
                  </select>
                </label>
                {e.fulfilment === "delivery" && (
                  <label className={`${cls("address")} wide`}>
                    <span>Address</span>
                    <input
                      value={e.address ?? ""}
                      data-flag={flagAttr("address")}
                      onChange={(ev) => setEntry(i, { address: ev.target.value || null })}
                    />
                  </label>
                )}
                <label className={cls("total_eur")}>
                  <span>Total €</span>
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    value={e.total_eur ?? ""}
                    data-flag={flagAttr("total_eur")}
                    onChange={(ev) => setEntry(i, { total_eur: ev.target.value === "" ? null : Number(ev.target.value) })}
                  />
                </label>
                <label className={`${cls("paid")} check`}>
                  <input
                    type="checkbox"
                    checked={e.paid}
                    data-flag={flagAttr("paid")}
                    onChange={(ev) => setEntry(i, { paid: ev.target.checked })}
                  />
                  <span>Paid</span>
                </label>
              </div>
            </fieldset>
          );
        })}

        <button
          type="button"
          className="btn ghost"
          onClick={() => setDraft({ ...draft, entries: [...draft.entries, blankEntry()] })}
        >
          + Add a missed order
        </button>

        <div className="approve-bar">
          {error && <span className="error small">{error}</span>}
          {done && <span className="ok-text small">{done}</span>}
          <span className="muted small">⌘/Ctrl + Enter</span>
          <button className="btn primary" type="submit" disabled={saving}>
            {saving ? "Saving…" : doc.status === "approved" ? "Save again" : "Approve page"}
          </button>
        </div>
      </form>
    </div>
  );
}
