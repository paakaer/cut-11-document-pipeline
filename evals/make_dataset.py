"""Render synthetic handwritten order-book pages with their right answers.

Each page is a JPEG plus a JSON file holding the NotebookPage it should turn
into. Pages vary in handwriting font, slant, ink, paper, blur, rotation,
shorthand and crossed-out orders, so the eval has something to get wrong.

Synthetic pages measure the pipeline end to end and let any model be
re-scored for free. Real scans score differently: add them to the same folder
with a hand-written JSON answer and they join the eval.

    uv run python ../evals/make_dataset.py --pages 30 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.menu import MENU as APP_MENU  # noqa: E402
from app.schema import Entry, Item, NotebookPage  # noqa: E402

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
]

# full name -> (shorthand a cook would write, price in euros)
MENU = {
    "margherita": ("marg", 6.0), "marinara": ("marin.", 5.0), "diavola": ("diav", 7.5),
    "capricciosa": ("capri", 8.5), "quattro formaggi": ("4 form", 8.0), "napoli": ("nap", 7.0),
    "prosciutto e funghi": ("prosc funghi", 8.0), "calzone": ("calz", 8.0),
    "lasagne": ("lasagne", 9.0), "patatine": ("patat", 3.5), "tiramisù": ("tiramisù", 4.5),
    "coca cola": ("coca", 2.5), "birra": ("birra", 3.5), "acqua": ("acqua", 1.5),
}
assert set(MENU) == set(APP_MENU), "keep evals/make_dataset.py MENU in step with backend/app/menu.py"
SURNAMES = ["Rossi", "Bianchi", "Ferrari", "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Gallo",
            "Conti", "Costa", "Giordano", "Mancini", "Lombardi", "Moretti", "Barbieri", "Fontana", "Zanetti"]
NAMES = ["Marco", "Giulia", "Luca", "Sara", "Paolo", "Anna", "Davide", "Elena", "Andrea", "Chiara",
         "Matteo", "Francesca", "Stefano", "Laura", "Simone", "Federica"]
STREETS = ["Via Roma", "Via Garibaldi", "Via Mazzini", "Corso Zanardelli", "Via Milano", "Viale Venezia",
           "Via Verdi", "Piazza Loggia", "Via Trieste", "Via Cavour"]
WEEKDAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
INKS = [(25, 35, 120), (20, 20, 25), (40, 40, 60), (90, 20, 30)]


def random_entry(rng: random.Random, t: int) -> Entry:
    items = []
    for dish in rng.sample(list(MENU), rng.randint(1, 4)):
        items.append(Item(name=dish, quantity=rng.choices([1, 2, 3, 4], [6, 3, 1, 0.5])[0]))
    delivery = rng.random() < 0.45
    total = round(sum(MENU[i.name][1] * i.quantity for i in items) + (2.0 if delivery else 0), 2)
    has_total = rng.random() < 0.9
    return Entry(
        time=f"{t // 60:02d}:{t % 60:02d}" if rng.random() < 0.95 else None,
        customer=f"{rng.choice(SURNAMES)} {rng.choice(NAMES)}",
        phone=("3" + "".join(rng.choice("0123456789") for _ in range(9))) if rng.random() < 0.85 else None,
        items=items,
        fulfilment="delivery" if delivery else "pickup",
        address=f"{rng.choice(STREETS)} {rng.randint(1, 120)}" if delivery else None,
        total_eur=total if has_total else None,
        paid=rng.random() < 0.4,
    )


def entry_lines(rng: random.Random, e: Entry) -> list[str]:
    head = " ".join(x for x in [e.time, e.customer] if x)
    if e.phone:
        p = e.phone
        head += "   " + rng.choice([f"{p[:3]} {p[3:]}", f"{p[:3]} {p[3:6]} {p[6:]}", p])
    dishes = []
    for i in e.items:
        name = MENU[i.name][0] if rng.random() < 0.5 else i.name
        q = rng.choice(["{q}x {n}", "{q} {n}", "{n} x{q}"]) if i.quantity > 1 or rng.random() < 0.5 else "{n}"
        dishes.append(q.format(q=i.quantity, n=name))
    lines = [head, "   " + ", ".join(dishes)]
    lines.append("   " + (f"consegna {e.address}" if e.fulfilment == "delivery" else "ritiro"))
    tail = []
    if e.total_eur is not None:
        tail.append(rng.choice(["tot. € ", "€ ", "tot "]) + f"{e.total_eur:.2f}".replace(".", ","))
    if e.paid:
        tail.append(rng.choice(["pagato", "PAGATO", "pag. ok"]))
    if tail:
        lines.append("   " + "   ".join(tail))
    return lines


def render(rng: random.Random, page_date: date, entries: list[Entry], decoy: Entry | None, fonts: list[str]) -> Image.Image:
    W, H = 1240, 1754  # A4 at 150 dpi
    paper = rng.choice([(250, 248, 240), (245, 242, 230), (252, 252, 250)])
    img = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(img)
    line_h = 42
    for y in range(140, H - 60, line_h):
        d.line([(60, y), (W - 60, y)], fill=(185, 205, 230), width=1)
    d.line([(130, 0), (130, H)], fill=(230, 160, 160), width=2)

    font_path = rng.choice(fonts)
    size = rng.randint(28, 34)
    font = ImageFont.truetype(font_path, size)
    ink = rng.choice(INKS)

    def write(x: int, y: int, text: str, strike: bool = False) -> None:
        jx = x + rng.randint(-4, 4)
        pos = (jx, y - size + 6 + rng.randint(-2, 2))
        d.text(pos, text, font=font, fill=ink)
        if strike:
            left, top, right, bottom = d.textbbox(pos, text, font=font)
            mid = (top + bottom) // 2
            d.line([(left, mid + rng.randint(-3, 3)), (right, mid + rng.randint(-3, 3))], fill=ink, width=3)

    header = rng.choice([
        f"{WEEKDAYS[page_date.weekday()]} {page_date.day}/{page_date.month}/{page_date.year}",
        f"{page_date.day}/{page_date.month:02d}/{str(page_date.year)[2:]}",
        f"{WEEKDAYS[page_date.weekday()]} {page_date.day:02d}-{page_date.month:02d}-{page_date.year}",
    ])
    write(150, 130, header)
    y = 130 + line_h * 2
    blocks = [(e, False) for e in entries]
    if decoy is not None:
        blocks.insert(rng.randint(0, len(blocks)), (decoy, True))
    for e, struck in blocks:
        for line in entry_lines(rng, e):
            assert y < H - 60, "page overflow: fewer entries or a smaller line height"
            write(150, y, line, strike=struck)
            y += line_h
        y += line_h // 2 if rng.random() < 0.5 else line_h

    img = img.rotate(rng.uniform(-1.8, 1.8), resample=Image.BICUBIC, expand=False, fillcolor=paper)
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.1)))
    # Uneven light from a phone photo.
    shade = Image.linear_gradient("L").rotate(rng.choice([0, 90, 180, 270])).resize((W, H))
    img = Image.composite(img, Image.new("RGB", (W, H), (205, 200, 190)), shade.point(lambda v: 255 - v // rng.randint(4, 8)))
    return img


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=30)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    args = ap.parse_args()

    fonts = [f for f in FONT_CANDIDATES if Path(f).exists()]
    if not fonts:
        sys.exit("No handwriting-style font found; edit FONT_CANDIDATES.")
    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    start = date(2026, 10, 1)
    for n in range(1, args.pages + 1):
        page_date = start + timedelta(days=n)
        t = rng.randint(18 * 60, 19 * 60)
        entries = []
        for _ in range(rng.randint(3, 5)):
            entries.append(random_entry(rng, t))
            t += rng.choice([15, 15, 30, 45])
        decoy = random_entry(rng, t) if rng.random() < 0.3 else None
        page = NotebookPage(date=page_date.isoformat(), entries=entries, uncertain_fields=[])
        stem = f"page-{n:03d}"
        render(rng, page_date, entries, decoy, fonts).save(args.out / f"{stem}.jpg", quality=rng.randint(70, 90))
        (args.out / f"{stem}.json").write_text(page.model_dump_json(indent=2) + "\n")
    print(f"Wrote {args.pages} pages to {args.out}")


if __name__ == "__main__":
    main()
