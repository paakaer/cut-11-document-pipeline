"""Turn a page image into a NotebookPage.

Two extractors share one interface:
- ClaudeExtractor: a vision model reads the page and returns schema-valid JSON.
- MockExtractor: offline stand-in for tests and the demo. It returns the
  page's labelled answer with seeded, realistic misreads. Its accuracy
  numbers mean nothing; it exists so the service and UI run without a key.
"""

from __future__ import annotations

import base64
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anthropic

from .menu import MENU
from .pricing import cost_usd
from .schema import NotebookPage

SYSTEM_PROMPT = """You digitise pages from a small Italian takeaway's handwritten order notebook.

Each page has a date at the top, then one block per order: time, customer surname and name, \
phone, the dishes with quantities, 'ritiro' (pickup) or 'consegna' plus an address (delivery), \
the total in euros, and 'pagato' or a tick when paid.

Rules:
- Read what is written. Do not invent values; use null when a field is absent.
- Skip any order that is crossed out.
- Write every dish exactly as it is named on the menu below, whatever shorthand the page uses \
('marg' -> 'margherita'). A number written before a dish is its quantity; a number inside the dish \
name (as in '4 form' for quattro formaggi) is not. If a dish matches nothing on the menu, write it \
as written and list it in uncertain_fields.
- Italian decimals use a comma: '24,50' is 24.5.
- List in uncertain_fields every value you are not confident you read correctly. A reviewer \
checks those first, so flag honestly: a missed flag costs more than a false one.

Menu:
""" + "\n".join(f"- {d}" for d in MENU)


@dataclass
class Extraction:
    page: NotebookPage
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int


class Extractor(Protocol):
    name: str

    def extract(self, image: bytes, media_type: str, filename: str) -> Extraction: ...


class ExtractionError(RuntimeError):
    pass


class ClaudeExtractor:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.name = model
        self.client = client or anthropic.Anthropic()

    def extract(self, image: bytes, media_type: str, filename: str) -> Extraction:
        started = time.perf_counter()
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                output_config={"effort": self.effort},
                output_format=NotebookPage,
                # On a safety decline the API retries on a substitute model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image).decode(),
                        }},
                        {"type": "text", "text": "Digitise this notebook page."},
                    ],
                }],
            )
        except anthropic.RateLimitError as e:
            raise ExtractionError(f"rate limited: {e.message}") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError(f"network error: {e}") from e

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.stop_reason == "refusal":
            raise ExtractionError("model declined the page")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise ExtractionError(f"no valid output (stop_reason={response.stop_reason})")

        input_tokens, output_tokens, cost = _usage_cost(response.usage, self.model)
        return Extraction(response.parsed_output, self.model, input_tokens, output_tokens, cost, latency_ms)


def _usage_cost(usage, requested_model: str) -> tuple[int, int, float]:
    """Sum tokens and cost across iterations, pricing each at the model that served it."""
    iterations = getattr(usage, "iterations", None) or []
    if not iterations:
        return usage.input_tokens, usage.output_tokens, cost_usd(
            requested_model, usage.input_tokens, usage.output_tokens,
            usage.cache_creation_input_tokens or 0, usage.cache_read_input_tokens or 0,
        )
    inp = out = 0
    cost = 0.0
    for it in iterations:
        if it.type not in ("message", "fallback_message"):
            continue
        model = getattr(it, "model", None) or requested_model
        inp += it.input_tokens
        out += it.output_tokens
        cost += cost_usd(model, it.input_tokens, it.output_tokens, it.cache_creation_input_tokens, it.cache_read_input_tokens)
    return inp, out, cost


class MockExtractor:
    """Labelled answer plus seeded misreads. Looks the answer up by file stem in truth_dir."""

    name = "mock"

    def __init__(self, truth_dir: Path, error_rate: float = 0.06):
        self.truth_dir = truth_dir
        self.error_rate = error_rate

    def extract(self, image: bytes, media_type: str, filename: str) -> Extraction:
        started = time.perf_counter()
        truth_file = self.truth_dir / f"{Path(filename).stem}.json"
        if not truth_file.exists():
            page = NotebookPage(date=None, entries=[], uncertain_fields=["date"])
        else:
            page = _corrupt(NotebookPage.model_validate_json(truth_file.read_text()), random.Random(filename), self.error_rate)
        return Extraction(page, "mock", 0, 0, 0.0, int((time.perf_counter() - started) * 1000))


def _corrupt(page: NotebookPage, rng: random.Random, rate: float) -> NotebookPage:
    data = json.loads(page.model_dump_json())
    flags: list[str] = []

    def hit() -> bool:
        return rng.random() < rate

    for i, e in enumerate(data["entries"]):
        path = f"entries[{i}]"
        if e["phone"] and hit():
            d = list(e["phone"])
            j = rng.randrange(len(d))
            d[j] = str((int(d[j]) + rng.choice([1, 3, 7])) % 10)
            e["phone"] = "".join(d)
            if rng.random() < 0.7:
                flags.append(f"{path}.phone")
        if e["time"] and hit():
            h, m = e["time"].split(":")
            e["time"] = f"{h}:{'15' if m == '45' else '45'}"
            if rng.random() < 0.6:
                flags.append(f"{path}.time")
        if hit():
            e["customer"] = e["customer"].replace("a", "o", 1) if "a" in e["customer"] else e["customer"] + "i"
            if rng.random() < 0.5:
                flags.append(f"{path}.customer")
        if e["items"] and hit():
            item = rng.choice(e["items"])
            item["quantity"] = max(1, item["quantity"] + rng.choice([-1, 1]))
            flags.append(f"{path}.items")
        if e["total_eur"] is not None and hit():
            e["total_eur"] = round(e["total_eur"] + rng.choice([-1, 1, 0.5]), 2)
            if rng.random() < 0.6:
                flags.append(f"{path}.total_eur")
        if hit():
            e["paid"] = not e["paid"]
        if rng.random() < 0.03:  # a false alarm now and then
            flags.append(f"{path}.address")
    data["uncertain_fields"] = flags
    return NotebookPage.model_validate(data)
