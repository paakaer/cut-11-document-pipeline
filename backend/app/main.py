"""FastAPI service: upload pages, extract, review, measure."""

from __future__ import annotations

import os
import statistics
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .extract import ClaudeExtractor, Extractor, ExtractionError, MockExtractor
from .pricing import EUR_PER_USD
from .schema import NotebookPage
from .scoring import score_page, summarise
from .store import Store

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "backend" / "var"))
TRUTH_DIR = Path(os.environ.get("TRUTH_DIR", ROOT / "evals" / "data"))
FRONTEND_DIST = ROOT / "frontend" / "dist"
# What an hour of reviewer time costs, for the all-in cost per document.
REVIEWER_EUR_PER_HOUR = float(os.environ.get("REVIEWER_EUR_PER_HOUR", "18"))
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ReviewIn(BaseModel):
    data: dict
    review_seconds: int = 0


def make_extractor() -> Extractor:
    kind = os.environ.get("EXTRACTOR", "claude" if os.environ.get("ANTHROPIC_API_KEY") else "mock")
    if kind == "mock":
        return MockExtractor(TRUTH_DIR)
    return ClaudeExtractor(model=os.environ.get("MODEL", "claude-opus-5-5"), effort=os.environ.get("EFFORT", "medium"))


def create_app(store: Store | None = None, extractor: Extractor | None = None) -> FastAPI:
    app = FastAPI(title="Document-to-data pipeline")
    app.state.store = store or Store(DATA_DIR / "pipeline.sqlite")
    app.state.extractor = extractor or make_extractor()
    images_dir = DATA_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    def run_extraction(doc_id: int) -> None:
        st: Store = app.state.store
        doc = st.document(doc_id)
        st.set_status(doc_id, "processing")
        try:
            result = app.state.extractor.extract(Path(doc["image_path"]).read_bytes(), doc["media_type"], doc["filename"])
        except ExtractionError as e:
            st.set_status(doc_id, "failed", str(e))
            return
        st.add_extraction(doc_id, result.model, result.page.model_dump_json(), result.input_tokens,
                          result.output_tokens, result.cost_usd, result.latency_ms)
        st.set_status(doc_id, "needs_review")

    @app.get("/api/config")
    def config():
        return {"extractor": app.state.extractor.name, "eur_per_usd": EUR_PER_USD,
                "reviewer_eur_per_hour": REVIEWER_EUR_PER_HOUR}

    @app.post("/api/documents", status_code=202)
    async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...)):
        ids = []
        for f in files:
            if f.content_type not in ALLOWED_TYPES:
                raise HTTPException(415, f"{f.filename}: unsupported type {f.content_type}")
            body = await f.read()
            if len(body) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"{f.filename}: larger than 10 MB")
            path = images_dir / f"{uuid.uuid4().hex}{Path(f.filename or '').suffix.lower()}"
            path.write_bytes(body)
            doc_id = app.state.store.add_document(f.filename or path.name, f.content_type, str(path))
            background.add_task(run_extraction, doc_id)
            ids.append(doc_id)
        return {"ids": ids}

    @app.get("/api/documents")
    def list_documents():
        out = []
        for r in app.state.store.list_documents():
            flagged = len(NotebookPage.model_validate_json(r["extraction"]).uncertain_fields) if r["extraction"] else None
            out.append({"id": r["id"], "filename": r["filename"], "status": r["status"], "error": r["error"],
                        "created_at": r["created_at"], "model": r["model"], "cost_usd": r["cost_usd"],
                        "latency_ms": r["latency_ms"], "flagged": flagged})
        return out

    @app.get("/api/documents/{doc_id}")
    def get_document(doc_id: int):
        st: Store = app.state.store
        doc = st.document(doc_id)
        if not doc:
            raise HTTPException(404)
        ext = st.latest_extraction(doc_id)
        rev = st.review(doc_id)
        return {
            "id": doc["id"], "filename": doc["filename"], "status": doc["status"], "error": doc["error"],
            "extraction": None if not ext else {
                "id": ext["id"], "model": ext["model"], "data": NotebookPage.model_validate_json(ext["data"]).model_dump(),
                "input_tokens": ext["input_tokens"], "output_tokens": ext["output_tokens"],
                "cost_usd": ext["cost_usd"], "latency_ms": ext["latency_ms"],
            },
            "review": None if not rev else {"data": NotebookPage.model_validate_json(rev["data"]).model_dump(),
                                            "review_seconds": rev["review_seconds"], "reviewed_at": rev["reviewed_at"]},
        }

    @app.get("/api/documents/{doc_id}/image")
    def get_image(doc_id: int):
        doc = app.state.store.document(doc_id)
        if not doc:
            raise HTTPException(404)
        return FileResponse(doc["image_path"], media_type=doc["media_type"])

    @app.post("/api/documents/{doc_id}/extract", status_code=202)
    def re_extract(doc_id: int, background: BackgroundTasks):
        if not app.state.store.document(doc_id):
            raise HTTPException(404)
        app.state.store.set_status(doc_id, "queued")
        background.add_task(run_extraction, doc_id)
        return {"id": doc_id}

    @app.put("/api/documents/{doc_id}/review")
    def review(doc_id: int, body: ReviewIn):
        st: Store = app.state.store
        ext = st.latest_extraction(doc_id)
        if not ext:
            raise HTTPException(409, "document has no extraction to review")
        try:
            approved = NotebookPage.model_validate({**body.data, "uncertain_fields": []})
        except ValidationError as e:
            raise HTTPException(422, e.errors())
        st.save_review(doc_id, ext["id"], approved.model_dump_json(), max(0, body.review_seconds))
        s = score_page(NotebookPage.model_validate_json(ext["data"]), approved)
        return {"fields": s.total, "corrected": s.total - s.correct + s.spurious_entries}

    @app.get("/api/metrics")
    def metrics():
        st: Store = app.state.store
        extractions = st.all_extractions()
        pairs = st.reviewed_pairs()
        scores = [score_page(NotebookPage.model_validate_json(p["extracted"]), NotebookPage.model_validate_json(p["approved"]))
                  for p in pairs]
        costs = [e["cost_usd"] for e in extractions]
        latencies = sorted(e["latency_ms"] for e in extractions)
        review_secs = [p["review_seconds"] for p in pairs]
        model_cost = statistics.mean(costs) if costs else None
        review_eur = statistics.mean(review_secs) / 3600 * REVIEWER_EUR_PER_HOUR if review_secs else None
        by_model: dict[str, list] = {}
        for p, s in zip(pairs, scores):
            by_model.setdefault(p["model"], []).append(s)
        return {
            "documents": len(st.list_documents()),
            "extractions": len(extractions),
            "reviewed": len(pairs),
            "accuracy": summarise(scores),
            "accuracy_by_model": {m: summarise(ss) for m, ss in by_model.items()},
            "cost_per_document_usd": model_cost,
            "cost_per_document_eur": model_cost * EUR_PER_USD if model_cost is not None else None,
            "total_cost_usd": sum(costs),
            "latency_ms_p50": latencies[len(latencies) // 2] if latencies else None,
            "latency_ms_p95": latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None,
            "review_seconds_mean": statistics.mean(review_secs) if review_secs else None,
            "review_cost_per_document_eur": review_eur,
            "all_in_cost_per_document_eur": (model_cost * EUR_PER_USD + review_eur)
            if model_cost is not None and review_eur is not None else None,
        }

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
    return app


app = create_app()
