"""Field-level accuracy of an extraction against the right answer.

The right answer is either a labelled page (offline eval) or the version a
reviewer approved (live). Both go through score_page, so the number on the
metrics screen and the number in the eval report mean the same thing.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .schema import ENTRY_FIELDS, NotebookPage


@dataclass
class FieldResult:
    path: str  # e.g. "entries[1].phone" or "date"
    field: str  # e.g. "phone"
    correct: bool
    flagged: bool


@dataclass
class PageScore:
    fields: list[FieldResult] = field(default_factory=list)
    missed_entries: int = 0  # in the answer, not extracted
    spurious_entries: int = 0  # extracted, not in the answer

    @property
    def total(self) -> int:
        return len(self.fields)

    @property
    def correct(self) -> int:
        return sum(f.correct for f in self.fields)

    @property
    def perfect(self) -> bool:
        return self.correct == self.total and self.spurious_entries == 0


def norm_text(s: str | None) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _items_key(items) -> list[tuple[str, int]]:
    return sorted((norm_text(i.name), i.quantity) for i in items)


def field_equal(name: str, pred, truth) -> bool:
    if name in ("customer", "address"):
        return norm_text(pred) == norm_text(truth)
    if name == "phone":
        return _digits(pred) == _digits(truth)
    if name == "total_eur":
        if pred is None or truth is None:
            return pred is truth
        return abs(pred - truth) < 0.005
    if name == "items":
        return _items_key(pred) == _items_key(truth)
    return pred == truth


def _similarity(a, b) -> float:
    key = lambda e: f"{e.time or ''} {norm_text(e.customer)}"
    return SequenceMatcher(None, key(a), key(b)).ratio()


def align(pred: NotebookPage, truth: NotebookPage) -> list[tuple[int | None, int | None]]:
    """Pair truth entries with extracted entries, greedy on time + customer similarity."""
    pairs = sorted(
        ((_similarity(p, t), pi, ti) for pi, p in enumerate(pred.entries) for ti, t in enumerate(truth.entries)),
        reverse=True,
    )
    used_p, used_t, out = set(), set(), []
    for sim, pi, ti in pairs:
        if sim < 0.5 or pi in used_p or ti in used_t:
            continue
        used_p.add(pi)
        used_t.add(ti)
        out.append((pi, ti))
    out += [(None, ti) for ti in range(len(truth.entries)) if ti not in used_t]
    out += [(pi, None) for pi in range(len(pred.entries)) if pi not in used_p]
    return out


def score_page(pred: NotebookPage, truth: NotebookPage) -> PageScore:
    flagged = set(pred.uncertain_fields)
    score = PageScore()
    score.fields.append(FieldResult("date", "date", pred.date == truth.date, "date" in flagged))
    for pi, ti in align(pred, truth):
        if ti is None:
            score.spurious_entries += 1
            continue
        t = truth.entries[ti]
        if pi is None:
            score.missed_entries += 1
            for f in ENTRY_FIELDS:
                score.fields.append(FieldResult(f"entries[{ti}].{f}", f, False, False))
            continue
        p = pred.entries[pi]
        for f in ENTRY_FIELDS:
            path = f"entries[{pi}].{f}"
            score.fields.append(FieldResult(path, f, field_equal(f, getattr(p, f), getattr(t, f)), path in flagged))
    return score


def summarise(scores: list[PageScore]) -> dict:
    """Aggregate page scores into the numbers the report and the metrics screen show."""
    fields = [f for s in scores for f in s.fields]
    total = len(fields)
    wrong = [f for f in fields if not f.correct]
    flagged = [f for f in fields if f.flagged]
    per_field: dict[str, dict] = {}
    for f in fields:
        d = per_field.setdefault(f.field, {"total": 0, "correct": 0})
        d["total"] += 1
        d["correct"] += f.correct
    for d in per_field.values():
        d["accuracy"] = d["correct"] / d["total"] if d["total"] else None
    missed_by_flags = sum(1 for f in wrong if not f.flagged)
    return {
        "pages": len(scores),
        "fields": total,
        "field_accuracy": (total - len(wrong)) / total if total else None,
        "perfect_pages": sum(s.perfect for s in scores),
        "perfect_page_rate": sum(s.perfect for s in scores) / len(scores) if scores else None,
        "missed_entries": sum(s.missed_entries for s in scores),
        "spurious_entries": sum(s.spurious_entries for s in scores),
        # How useful the model's own uncertainty flags are to a reviewer.
        "flag_recall": (len(wrong) - missed_by_flags) / len(wrong) if wrong else None,
        "flag_precision": sum(1 for f in flagged if not f.correct) / len(flagged) if flagged else None,
        # Error rate left if a reviewer checks only the flagged fields.
        "residual_error_rate": missed_by_flags / total if total else None,
        "per_field": per_field,
    }
