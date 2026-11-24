# Eval: claude-haiku-5-5 (2026-11-24)

30 labelled pages, 990 fields, 0 failed calls.

| Metric | Value |
|---|---|
| Field accuracy | 97.3% |
| Pages with every field right | 12/30 (40.0%) |
| Orders missed / invented | 0 / 0 |
| Wrong fields the model flagged | 7.4% |
| Flags that were real errors | 5.3% |
| Error rate if reviewer checks flags only | 2.5% |
| Cost per document | $0.0011 |
| Cost per 1,000 documents | €0.98 (at 0.86 €/$) |
| Latency p50 / p95 | 6338 ms / 7722 ms |

## Accuracy by field

| Field | Accuracy | Right / total |
|---|---|---|
| items | 77.5% | 93/120 |
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
| page-003.jpg | 3/25 | entries[2].items, entries[1].items, entries[0].items |
| page-020.jpg | 3/33 | entries[3].items, entries[2].items, entries[1].items |
| page-030.jpg | 3/33 | entries[3].items, entries[2].items, entries[1].items |
| page-007.jpg | 2/41 | entries[3].items, entries[1].items |
| page-011.jpg | 2/41 | entries[2].items, entries[0].items |

## Dish lists it got wrong

| Page | Model read | Truth |
|---|---|---|
| page-001.jpg | 1x birra, 2x capri, 2x diavola | 1x birra, 2x capricciosa, 2x diavola |
| page-002.jpg | 1x lasagne, 1x napoletana, 4x patatine fritte, 2x quattro formaggi | 1x lasagne, 1x napoli, 4x patatine, 2x quattro formaggi |
| page-003.jpg | 1x acqua, 1x capri, 1x margherita, 1x patatine | 1x acqua, 1x capricciosa, 1x margherita, 1x patatine |
| page-003.jpg | 2x capri, 1x prosciutto e funghi, 1x tiramisù | 2x capricciosa, 1x prosciutto e funghi, 1x tiramisù |
| page-003.jpg | 2x calzone, 3x form, 1x napoletana | 2x calzone, 1x napoli, 3x quattro formaggi |
| page-005.jpg | 1x calzone, 1x coca | 1x calzone, 1x coca cola |
| page-007.jpg | 2x acqua, 1x calzone xl, 1x patatine, 2x prosciutto e funghi | 2x acqua, 1x calzone, 1x patatine, 2x prosciutto e funghi |
| page-007.jpg | 1x 14 form, 2x lasagne | 2x lasagne, 1x quattro formaggi |
| page-008.jpg | 2x acqua, 4x form | 2x acqua, 1x quattro formaggi |
| page-011.jpg | 2x acqua, 2x birra, 1x capri, 2x coca cola | 2x acqua, 2x birra, 1x capricciosa, 2x coca cola |
| page-011.jpg | 1x calzone, 1x capricciosa, 4x formaggio, 2x marinara | 1x calzone, 1x capricciosa, 2x marinara, 1x quattro formaggi |
| page-012.jpg | 1x lasagne, 1x nap | 1x lasagne, 1x napoli |
| page-014.jpg | 2x capri, 2x quattro formaggi | 2x capricciosa, 2x quattro formaggi |
| page-015.jpg | 1x coca | 1x coca cola |
| page-016.jpg | 1x coca | 1x coca cola |
| page-017.jpg | 1x capricciosa, 1x coca, 2x margherita, 2x prosciutto e funghi | 1x capricciosa, 1x coca cola, 2x margherita, 2x prosciutto e funghi |
| page-020.jpg | 1x patatine fritte | 1x patatine |
| page-020.jpg | 4x capri, 1x coca, 3x lasagne, 1x napoli | 4x capricciosa, 1x coca cola, 3x lasagne, 1x napoli |
| page-020.jpg | 1x capri, 2x quattro formaggi | 1x capricciosa, 2x quattro formaggi |
| page-021.jpg | 2x form | 2x quattro formaggi |
| page-021.jpg | 1x capri | 1x capricciosa |
| page-026.jpg | 1x acqua, 2x birra, 2x patatine fritte, 1x tiramisù | 1x acqua, 2x birra, 2x patatine, 1x tiramisù |
| page-027.jpg | 2x coca cola, 1x prosciutto funghi | 2x coca cola, 1x prosciutto e funghi |
| page-028.jpg | 1x nap | 1x napoli |
| page-030.jpg | 2x capri, 1x diavola | 2x capricciosa, 1x diavola |
| page-030.jpg | 1x capricciosa, 1x coca, 1x diavola | 1x capricciosa, 1x coca cola, 1x diavola |
| page-030.jpg | 1x calzone, 1x coca, 2x diavola | 1x calzone, 1x coca cola, 2x diavola |
