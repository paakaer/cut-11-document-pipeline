from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.extract import ClaudeExtractor, MockExtractor
from app.main import create_app
from app.pricing import cost_usd
from app.schema import Entry, Item, NotebookPage
from app.scoring import score_page, summarise
from app.store import Store

DATA = Path(__file__).resolve().parents[2] / "evals" / "data"


def entry(**kw) -> Entry:
    base = dict(time="18:30", customer="Rossi Marco", phone="3331234567", items=[Item(name="margherita", quantity=2)],
                fulfilment="pickup", address=None, total_eur=12.0, paid=False)
    return Entry(**{**base, **kw})


def page(*entries, date="2026-10-02", flags=()) -> NotebookPage:
    return NotebookPage(date=date, entries=list(entries), uncertain_fields=list(flags))


# --- scoring ---------------------------------------------------------------

def test_identical_page_is_perfect():
    p = page(entry(), entry(customer="Bianchi Anna", time="19:00"))
    s = score_page(p, p)
    assert s.total == 17 and s.correct == 17 and s.perfect


def test_normalisation_forgives_case_accents_and_phone_spacing():
    truth = page(entry(customer="Zanetti Francesca", items=[Item(name="tiramisù", quantity=1)]))
    pred = page(entry(customer="zanetti  francesca", phone="333 123 4567", items=[Item(name="Tiramisu", quantity=1)]))
    assert score_page(pred, truth).perfect


def test_wrong_quantity_fails_items_and_flag_counts():
    truth = page(entry())
    pred = page(entry(items=[Item(name="margherita", quantity=3)]), flags=["entries[0].items"])
    s = score_page(pred, truth)
    wrong = [f for f in s.fields if not f.correct]
    assert [f.field for f in wrong] == ["items"] and wrong[0].flagged


def test_entries_align_by_content_not_position():
    a, b = entry(customer="Rossi Marco", time="18:30"), entry(customer="Greco Elena", time="19:15")
    assert score_page(page(b, a), page(a, b)).perfect


def test_missed_and_invented_entries():
    a, b = entry(), entry(customer="Greco Elena", time="19:15")
    missed = score_page(page(a), page(a, b))
    assert missed.missed_entries == 1 and missed.correct == 9 and missed.total == 17
    invented = score_page(page(a, b), page(a))
    assert invented.spurious_entries == 1 and not invented.perfect


def test_summary_flag_metrics():
    truth = page(entry())
    pred = page(entry(phone="3331234568", paid=True), flags=["entries[0].phone", "entries[0].time"])
    s = summarise([score_page(pred, truth)])
    assert s["flag_recall"] == 0.5          # phone flagged, paid not
    assert s["flag_precision"] == 0.5       # time flag was a false alarm
    assert s["residual_error_rate"] == pytest.approx(1 / 9)


# --- cost ------------------------------------------------------------------

def test_cost_table():
    assert cost_usd("claude-opus-5-5", 1_000_000, 0) == pytest.approx(4.0)
    assert cost_usd("claude-haiku-5-5", 2000, 1000) == pytest.approx(0.0007)
    with pytest.raises(KeyError):
        cost_usd("unknown-model", 1, 1)


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def fake_client(response):
    msgs = FakeMessages(response)
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs)), msgs


def test_claude_extractor_prices_each_iteration_at_its_own_model():
    parsed = page(entry())
    usage = SimpleNamespace(
        input_tokens=0, output_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=0,
        iterations=[
            SimpleNamespace(type="message", model="claude-opus-5-5", input_tokens=1500, output_tokens=10,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0),
            SimpleNamespace(type="fallback_message", model="claude-opus-4-8", input_tokens=1500, output_tokens=400,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0),
        ],
    )
    client, msgs = fake_client(SimpleNamespace(stop_reason="end_turn", parsed_output=parsed, usage=usage))
    ex = ClaudeExtractor("claude-opus-5-5", client=client).extract(b"img", "image/jpeg", "p.jpg")
    expected = cost_usd("claude-opus-5-5", 1500, 10) + cost_usd("claude-opus-4-8", 1500, 400)
    assert ex.cost_usd == pytest.approx(expected)
    assert ex.input_tokens == 3000 and ex.output_tokens == 410
    assert msgs.kwargs["output_format"] is NotebookPage
    assert msgs.kwargs["messages"][0]["content"][0]["type"] == "image"


def test_claude_extractor_raises_on_refusal():
    from app.extract import ExtractionError
    usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, iterations=None)
    client, _ = fake_client(SimpleNamespace(stop_reason="refusal", parsed_output=None, usage=usage))
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=client).extract(b"img", "image/jpeg", "p.jpg")


# --- API -------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.DATA_DIR", tmp_path)
    app = create_app(store=Store(tmp_path / "t.sqlite"), extractor=MockExtractor(DATA, error_rate=0.3))
    return TestClient(app)


def test_upload_review_metrics_flow(client):
    img = (DATA / "page-001.jpg").read_bytes()
    r = client.post("/api/documents", files=[("files", ("page-001.jpg", io.BytesIO(img), "image/jpeg"))])
    assert r.status_code == 202
    doc_id = r.json()["ids"][0]

    doc = client.get(f"/api/documents/{doc_id}").json()  # background task has run under TestClient
    assert doc["status"] == "needs_review"
    assert client.get(f"/api/documents/{doc_id}/image").content == img

    truth = json.loads((DATA / "page-001.json").read_text())
    r = client.put(f"/api/documents/{doc_id}/review", json={"data": truth, "review_seconds": 40})
    assert r.status_code == 200
    corrected = r.json()["corrected"]

    m = client.get("/api/metrics").json()
    assert m["reviewed"] == 1 and m["review_seconds_mean"] == 40
    acc = m["accuracy"]
    assert acc["fields"] - round(acc["field_accuracy"] * acc["fields"]) == corrected
    assert client.get(f"/api/documents/{doc_id}").json()["status"] == "approved"


def test_rejects_non_images_and_bad_reviews(client):
    r = client.post("/api/documents", files=[("files", ("x.pdf", io.BytesIO(b"%PDF"), "application/pdf"))])
    assert r.status_code == 415
    img = (DATA / "page-002.jpg").read_bytes()
    doc_id = client.post("/api/documents", files=[("files", ("page-002.jpg", io.BytesIO(img), "image/jpeg"))]).json()["ids"][0]
    r = client.put(f"/api/documents/{doc_id}/review", json={"data": {"date": None, "entries": [{"customer": "x"}]}})
    assert r.status_code == 422
