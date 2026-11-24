# Eval: claude-opus-5-5 (2026-11-24)

30 labelled pages, 990 fields, 0 failed calls.

| Metric | Value |
|---|---|
| Field accuracy | 98.9% |
| Pages with every field right | 21/30 (70.0%) |
| Orders missed / invented | 0 / 0 |
| Wrong fields the model flagged | 0.0% |
| Flags that were real errors | 0.0% |
| Error rate if reviewer checks flags only | 1.1% |
| Cost per document | $0.0354 |
| Cost per 1,000 documents | €30.47 (at 0.86 €/$) |
| Latency p50 / p95 | 7871 ms / 10565 ms |

## Accuracy by field

| Field | Accuracy | Right / total |
|---|---|---|
| items | 90.8% | 109/120 |
| date | 100.0% | 30/30 |
| time | 100.0% | 120/120 |
| customer | 100.0% | 120/120 |
| phone | 100.0% | 120/120 |
| fulfilment | 100.0% | 120/120 |
| address | 100.0% | 120/120 |
| total_eur | 100.0% | 120/120 |
| paid | 100.0% | 120/120 |

## Worst pages

| Page | Wrong | Fields |
|---|---|---|
| page-007.jpg | 2/41 | entries[2].items, entries[0].items |
| page-020.jpg | 2/33 | entries[2].items, entries[1].items |
| page-001.jpg | 1/25 | entries[2].items |
| page-002.jpg | 1/25 | entries[0].items |
| page-003.jpg | 1/25 | entries[0].items |
