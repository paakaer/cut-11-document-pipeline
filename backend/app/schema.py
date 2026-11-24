"""The data a notebook page turns into.

The domain is a small takeaway's handwritten order book (quaderno delle
ordinazioni): one page per day, one block per order. The same pipeline works
for any handwritten form once this schema is swapped.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str = Field(description="Dish as written, normalised to its full name, lower case. e.g. 'margherita', 'tiramisù'.")
    quantity: int = Field(description="How many. '2x', '2 ×' and 'x2' all mean 2. Default 1 when no number is written.")


class Entry(BaseModel):
    time: str | None = Field(description="Pickup or delivery time as HH:MM, 24h. null if not written.")
    customer: str = Field(description="Customer name as written, Surname Name order kept.")
    phone: str | None = Field(description="Digits only, no spaces. null if not written.")
    items: list[Item]
    fulfilment: Literal["pickup", "delivery"] = Field(description="'ritiro' = pickup, 'consegna' or an address = delivery.")
    address: str | None = Field(description="Delivery address as written. null for pickup.")
    total_eur: float | None = Field(description="Total in euros as a number, 24,50 -> 24.5. null if not written.")
    paid: bool = Field(description="true only if the order is marked paid ('pagato', a tick).")


class NotebookPage(BaseModel):
    date: str | None = Field(description="Page date as YYYY-MM-DD. null if not written.")
    entries: list[Entry] = Field(description="Every order on the page, top to bottom. Skip crossed-out orders.")
    uncertain_fields: list[str] = Field(
        description="Paths of values you could not read with confidence, e.g. 'entries[2].phone', 'date'. Empty if none."
    )


# Paths a reviewer can correct, used by scoring and by the review screen.
ENTRY_FIELDS = ("time", "customer", "phone", "items", "fulfilment", "address", "total_eur", "paid")
