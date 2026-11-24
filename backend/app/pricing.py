"""Cost of one extraction, from the token usage the API returns.

Prices are Anthropic first-party list prices in USD per million tokens
(checked 2026-11-24). Cache writes bill at 1.25x input, cache reads at the
listed rate. Update this table when prices change; nothing else needs to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_read: float


PRICES_USD_PER_MTOK: dict[str, Price] = {
    "claude-opus-5-5": Price(4.00, 20.00, 0.20),
    "claude-sonnet-5-5": Price(2.00, 10.00, 0.10),
    "claude-haiku-5-5": Price(0.10, 0.50, 0.01),  # prompts up to 100K tokens; cache read assumed 10%
    # Fallback targets the server may route to. Cache-read rates here assume 10% of input.
    "claude-opus-5": Price(5.00, 25.00, 0.50),
    "claude-opus-4-8": Price(5.00, 25.00, 0.50),
    "claude-sonnet-5": Price(2.00, 10.00, 0.20),
    "mock": Price(0.0, 0.0, 0.0),
}

# Anthropic bills in USD. Reports also show euros at this rate.
EUR_PER_USD = float(os.environ.get("EUR_PER_USD", "0.86"))


def cost_usd(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    p = PRICES_USD_PER_MTOK.get(model)
    if p is None:
        raise KeyError(f"No price for model {model!r}; add it to PRICES_USD_PER_MTOK")
    return (
        input_tokens * p.input
        + cache_write * p.input * 1.25
        + cache_read * p.cache_read
        + output_tokens * p.output
    ) / 1_000_000
