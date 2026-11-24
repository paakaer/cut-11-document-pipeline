# Notebook to data

Photos of handwritten pages in, checked structured data out. A FastAPI service sends each page to a vision model, which returns typed JSON and flags the values it could not read with confidence. A person checks those values in a React review screen and approves the page. Every page records two numbers: how accurate the model was and what the page cost.

The sample domain is a takeaway's handwritten order book: one page per evening, one block per order with time, customer, phone, dishes, pickup or delivery, total and paid. To use a different form, swap the schema in `backend/app/schema.py`; for a different shop, swap the menu in `backend/app/menu.py`.

## What it measures

- **Accuracy per field and per page.** Labelled pages give it offline (`evals/`), and approved reviews give it live. Both use the same scorer (`backend/app/scoring.py`), so the eval number and the dashboard number mean the same thing.
- **Cost per document.** The cost is worked out from the token usage the API returns, at each model's list price. If the server falls back to another model mid-call, each part is priced at the model that served it.
- **All-in cost per document.** Model cost plus the reviewer's time, timed on the review screen and priced at `REVIEWER_EUR_PER_HOUR`.
- **How much the model's flags help.** This is the share of real errors the model flagged, and the error rate left if a reviewer checks only the flagged fields. It shows whether review can be partial.

## Results

30 synthetic pages, 990 fields per model, effort `medium`, run on 2026-11-24. No call failed and no model missed or invented an order. All runs together cost about $2.55.

**With the shop's menu in the prompt** (current code):

| Model | Field accuracy | Dish lists right | Pages with no correction | Cost / 1,000 pages | p50 latency |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | 100% | 100% | 30/30 | €0.93 | 5.7 s |
| `claude-opus-5-5` | 100% | 100% | 30/30 | €27.66 | 7.0 s |

**Without it** (first runs):

| Model | Field accuracy | Dish lists right | Pages with no correction | Errors it flagged | Cost / 1,000 pages | p50 latency |
|---|---|---|---|---|---|---|
| `claude-haiku-5-5` | 97.3% | 77.5% | 12/30 | 7.4% | €0.98 | 6.3 s |
| `claude-sonnet-5-5` | 97.6% | 80.0% | 15/30 | 0% | €11.96 | 3.9 s |
| `claude-opus-5-5` | 98.9% | 90.8% | 21/30 | 0% | €30.47 | 7.9 s |

Full reports are in `evals/results/`; the first runs are the `-no-menu` files.

What the numbers say:

- **The errors were a missing input, not a weak model.** Without the menu, every field except the dish list already scored 100%. Of Haiku's 27 wrong dish lists, 23 kept the page's shorthand ('capri', 'coca', 'nap') or expanded it to a different name ('napoletana', 'patatine fritte'): the model read the page right but could not know the shop's names. The other four took the 4 in '4 form' (quattro formaggi) as a quantity, or read 'calzone' as 'calzone xl'.
- **Giving the model the menu fixed all of it.** The prompt now lists the menu (`backend/app/menu.py`), asks for every dish by its menu name, and says a number inside a dish name is not a quantity. A real shop has a menu, so the deployment would have this. The '4 form' rule, though, was written after seeing that error, so it is partly fitted to this test.
- **On these pages the cheapest model is enough.** Haiku now matches Opus at about a thirtieth of the cost: under €1 per 1,000 pages. Reading the error tables before reaching for a bigger model was worth more than the bigger model.
- **The models' own uncertainty flags cannot be trusted.** In the first runs Sonnet and Opus flagged nothing on pages they got wrong, and Haiku's flags caught under one error in eight. Review should cover every page, not only flagged fields; the review screen is built for that.
- **This test set is now too easy.** At 100% it can no longer tell models or prompts apart. Synthetic pages are rendered in fonts and are cleaner than real handwriting. The next step is a set of real photographed pages with hand-written answers (put `name.jpg` and `name.json` in `evals/data/`); expect errors to return there, and the model comparison with them.

## Layout

```
backend/   FastAPI service, SQLite store, extractor, scorer, tests
frontend/  React + Vite review screen (pages, review, accuracy & cost)
evals/     synthetic page generator, 30 labelled pages, eval runner
```

```
photo ─▶ POST /api/documents ─▶ background extraction (Claude vision, structured output)
                                   │  tokens, cost, latency stored
                                   ▼
                     review screen: flagged fields first ─▶ PUT /review (approved = truth)
                                                                │
                                   GET /api/metrics ◀───────────┘  accuracy, cost, review time
```

## Run it

You need Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 18+.

```bash
cd frontend && npm install && npm run build && cd ..
cd backend && uv sync
ANTHROPIC_API_KEY=sk-ant-... uv run uvicorn app.main:app --port 8000
```

Open http://localhost:8000 and drop in pages from `evals/data/`. Without `ANTHROPIC_API_KEY` the service starts with the mock extractor, which the header says. For frontend work, run `npm run dev` in `frontend/` (it proxies `/api` to port 8000).

Settings (environment variables):

| Variable | Default | Meaning |
|---|---|---|
| `EXTRACTOR` | `claude` if a key is set, else `mock` | which extractor runs |
| `MODEL` | `claude-opus-5-5` | any model in `app/pricing.py` |
| `EFFORT` | `medium` | `low` … `max`; lower is cheaper and faster |
| `DATA_DIR` | `backend/var` | SQLite file and uploaded images |
| `EUR_PER_USD` | `0.86` | for euro figures; the API bills in USD |
| `REVIEWER_EUR_PER_HOUR` | `18` | for all-in cost |

## Eval

```bash
cd backend
uv run python ../evals/make_dataset.py --pages 30 --seed 7     # already done; regenerates evals/data
uv run python ../evals/run_eval.py --extractor mock             # free, checks the plumbing
uv run python ../evals/run_eval.py --extractor claude \
  --model claude-haiku-5-5 --model claude-sonnet-5-5 --model claude-opus-5-5 --yes
```

A paid run needs `--yes`. Each model writes `evals/results/<date>-<model>.md` with accuracy by field, the worst pages, cost and latency.

The 30 pages are synthetic. They are rendered with handwriting-style fonts, slant, blur, uneven light, shorthand dish names, mixed date formats and crossed-out orders the model must skip. That makes them cheap to label and good for comparing models. They are cleaner than real handwriting, though. To add real scans, put `name.jpg` with a hand-written `name.json` in `evals/data/` and they join the eval.

## Tests

```bash
cd backend && uv run pytest
```

The tests cover scoring (normalisation, order alignment, missed and invented orders, flag metrics), cost (per-model pricing, pricing across fallback iterations), refusal handling, and the upload → review → metrics flow through the API.

## Design choices

- **One vision call per page, no separate OCR step.** The model reads the page and fills the schema in one pass through structured outputs (`messages.parse` with a Pydantic model). The response is validated against the schema, so a malformed response fails loudly instead of reaching the database.
- **Approved reviews are the ground truth.** Accuracy in production comes from what reviewers changed, not from a one-off test set, so drift shows up on the dashboard.
- **The model says what it is unsure of.** `uncertain_fields` drives the review order. The eval measures whether those flags can be trusted before anyone relies on them to skip fields.
- **Server-side fallback is on.** If the model declines a page, the API retries on a substitute model in the same call, and the cost accounting follows.

## Limits

- No authentication. Run it behind your own login or VPN.
- Extraction runs as in-process background tasks. Fine for one machine. For volume, move it to a queue and use the Batches API, which costs half.
- Images only (JPEG, PNG, WebP, GIF, up to 10 MB). For PDFs, render pages to images first or add a `document` content block.
