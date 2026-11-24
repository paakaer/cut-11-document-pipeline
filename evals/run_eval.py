"""Score extractors against the labelled pages: accuracy, cost and latency per document.

    uv run python ../evals/run_eval.py --extractor mock
    uv run python ../evals/run_eval.py --extractor claude --model claude-haiku-5-5 --model claude-opus-5-5 --yes

Claude runs spend real money, so they need --yes. Each run writes
evals/results/<date>-<model>.md and .json.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
from app.extract import ClaudeExtractor, Extraction, ExtractionError, MockExtractor  # noqa: E402
from app.pricing import EUR_PER_USD  # noqa: E402
from app.schema import NotebookPage  # noqa: E402
from app.scoring import align, field_equal, score_page, summarise  # noqa: E402

MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def load_pages(data_dir: Path, limit: int | None) -> list[tuple[Path, NotebookPage]]:
    pages = []
    for img in sorted(p for p in data_dir.iterdir() if p.suffix.lower() in MEDIA):
        truth = img.with_suffix(".json")
        if truth.exists():
            pages.append((img, NotebookPage.model_validate_json(truth.read_text())))
    return pages[:limit] if limit else pages


def run(extractor, pages, workers: int) -> dict:
    def one(item):
        img, truth = item
        try:
            ex: Extraction = extractor.extract(img.read_bytes(), MEDIA[img.suffix.lower()], img.name)
        except ExtractionError as e:
            return img.name, None, str(e), truth
        return img.name, ex, None, truth

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, pages))

    ok = [(n, ex, t) for n, ex, err, t in results if ex]
    failures = [(n, err) for n, ex, err, t in results if not ex]
    scores = [score_page(ex.page, t) for _, ex, t in ok]
    costs = [ex.cost_usd for _, ex, _ in ok]
    lat = sorted(ex.latency_ms for _, ex, _ in ok)
    per_page = []
    for (name, ex, truth), s in zip(ok, scores):
        item_errors = [
            {"read": _items(ex.page.entries[pi].items), "truth": _items(truth.entries[ti].items)}
            for pi, ti in align(ex.page, truth)
            if pi is not None and ti is not None
            and not field_equal("items", ex.page.entries[pi].items, truth.entries[ti].items)
        ]
        per_page.append({
            "page": name, "fields": s.total, "wrong": s.total - s.correct,
            "wrong_fields": [f.path for f in s.fields if not f.correct],
            "missed_entries": s.missed_entries, "spurious_entries": s.spurious_entries,
            "flagged": len(ex.page.uncertain_fields), "cost_usd": ex.cost_usd, "latency_ms": ex.latency_ms,
            "input_tokens": ex.input_tokens, "output_tokens": ex.output_tokens,
            "item_errors": item_errors,
            "prediction": ex.page.model_dump(),
        })
    return {
        "extractor": extractor.name,
        "date": date.today().isoformat(),
        "pages_attempted": len(pages),
        "failures": failures,
        "accuracy": summarise(scores),
        "cost_per_document_usd": statistics.mean(costs) if costs else None,
        "cost_per_1000_documents_eur": statistics.mean(costs) * 1000 * EUR_PER_USD if costs else None,
        "total_cost_usd": sum(costs),
        "latency_ms_p50": lat[len(lat) // 2] if lat else None,
        "latency_ms_p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None,
        "per_page": per_page,
    }


def _items(items) -> str:
    return ", ".join(f"{i.quantity}x {i.name}" for i in sorted(items, key=lambda i: i.name))


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def to_markdown(r: dict) -> str:
    a = r["accuracy"]
    lines = [
        f"# Eval: {r['extractor']} ({r['date']})",
        "",
        f"{r['pages_attempted']} labelled pages, {a['fields']} fields, {len(r['failures'])} failed calls.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Field accuracy | {pct(a['field_accuracy'])} |",
        f"| Pages with every field right | {a['perfect_pages']}/{a['pages']} ({pct(a['perfect_page_rate'])}) |",
        f"| Orders missed / invented | {a['missed_entries']} / {a['spurious_entries']} |",
        f"| Wrong fields the model flagged | {pct(a['flag_recall'])} |",
        f"| Flags that were real errors | {pct(a['flag_precision'])} |",
        f"| Error rate if reviewer checks flags only | {pct(a['residual_error_rate'])} |",
        f"| Cost per document | ${r['cost_per_document_usd'] or 0:.4f} |",
        f"| Cost per 1,000 documents | €{r['cost_per_1000_documents_eur'] or 0:.2f} (at {EUR_PER_USD} €/$) |",
        f"| Latency p50 / p95 | {r['latency_ms_p50']} ms / {r['latency_ms_p95']} ms |",
        "",
        "## Accuracy by field",
        "",
        "| Field | Accuracy | Right / total |",
        "|---|---|---|",
    ]
    for name, d in sorted(a["per_field"].items(), key=lambda kv: kv[1]["accuracy"] or 0):
        lines.append(f"| {name} | {pct(d['accuracy'])} | {d['correct']}/{d['total']} |")
    worst = sorted(r["per_page"], key=lambda p: -p["wrong"])[:5]
    lines += ["", "## Worst pages", "", "| Page | Wrong | Fields |", "|---|---|---|"]
    for p in worst:
        lines.append(f"| {p['page']} | {p['wrong']}/{p['fields']} | {', '.join(p['wrong_fields'][:6]) or '-'} |")
    item_errors = [(p["page"], e) for p in r["per_page"] for e in p.get("item_errors", [])]
    if item_errors:
        lines += ["", "## Dish lists it got wrong", "", "| Page | Model read | Truth |", "|---|---|---|"]
        lines += [f"| {n} | {e['read']} | {e['truth']} |" for n, e in item_errors[:40]]
    if r["failures"]:
        lines += ["", "## Failed calls", ""] + [f"- {n}: {e}" for n, e in r["failures"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extractor", choices=["mock", "claude"], default="mock")
    ap.add_argument("--model", action="append", help="repeat to compare models (claude only)")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--yes", action="store_true", help="confirm a paid Claude run")
    args = ap.parse_args()

    pages = load_pages(args.data, args.limit)
    if not pages:
        sys.exit(f"No labelled pages in {args.data}. Run make_dataset.py first.")
    if args.extractor == "mock":
        extractors = [MockExtractor(args.data)]
    else:
        models = args.model or ["claude-opus-5-5"]
        if not args.yes:
            sys.exit(f"This calls the Claude API on {len(pages)} pages x {len(models)} model(s). Re-run with --yes.")
        extractors = [ClaudeExtractor(m, args.effort) for m in models]

    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    for ex in extractors:
        r = run(ex, pages, args.workers)
        stem = f"{r['date']}-{ex.name}"
        (out_dir / f"{stem}.json").write_text(json.dumps(r, indent=2) + "\n")
        md = to_markdown(r)
        (out_dir / f"{stem}.md").write_text(md)
        print(md)


if __name__ == "__main__":
    main()
