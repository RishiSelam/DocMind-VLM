from __future__ import annotations

import csv
import io
import json
import logging
import platform
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from .. import db
from ..config import get_settings
from ..eval import runner
from ..eval.docvqa import list_datasets
from ..schemas import AskRequest, ConversationCreate, ExperimentCreate
from ..services import audit as auditsvc
from ..services import history as historysvc
from ..services import monitoring, ocr as ocrsvc, pdf as pdfsvc
from ..services.models import hub
from ..services.pipelines import _retrieval_corpus, answer_config, run_ask
from ..services.retrieval import rank_pages

log = logging.getLogger("docmind.api")
router = APIRouter(prefix="/api")


def _doc_or_404(doc_id: str) -> Dict[str, Any]:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Document {doc_id} not found")
    return doc


def _page_or_404(doc: Dict[str, Any], page: int) -> int:
    if page < 1 or page > doc["n_pages"]:
        raise HTTPException(404, f"Page {page} is out of range (1..{doc['n_pages']})")
    return page - 1


# ------------------------------------------------------------------------------------------------ system
@router.get("/health")
def health() -> Dict[str, Any]:
    s = get_settings()
    return {
        "status": "ok", **hub.status(), "ocr_engine": ocrsvc.cache_key(), "gpu": monitoring.gpu_status(),
        "page_cap": s.vlm_page_cap, "match_pages": s.match_pages, "read_all_pages": s.read_all_pages, "python": platform.python_version(),
    }


@router.get("/system/metrics")
def system_metrics() -> Dict[str, Any]:
    return {"gpu": monitoring.gpu_status(), **monitoring.summary()}


# ------------------------------------------------------------------------------------------------ documents
@router.post("/documents")
def upload_document(file: UploadFile = File(...)) -> Dict[str, Any]:
    s = get_settings()
    ext = Path(file.filename or "").suffix.lower()
    if ext not in pdfsvc.ALLOWED_EXT:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(pdfsvc.ALLOWED_EXT))}")
    tag = db.new_id("f_")
    path, size, digest = pdfsvc.save_upload_stream(file.file, s.data_dir / "uploads", file.filename or "upload", tag)
    # The same file again: reuse the existing document (and its OCR cache) instead of listing a copy.
    same = db.find_document_by_sha256(digest)
    if same and Path(same["path"]).exists():
        path.unlink(missing_ok=True)
        return {**same, "reused": True}
    try:
        n_pages = pdfsvc.count_pages(path)
    except Exception as e:  # noqa: BLE001
        path.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not read the file as a PDF or image: {e}") from e
    if n_pages < 1:
        path.unlink(missing_ok=True)
        raise HTTPException(400, "The file has no pages.")
    return db.add_document(file.filename or path.name, str(path), n_pages, size, digest)


@router.get("/documents")
def documents() -> List[Dict[str, Any]]:
    return db.list_documents()


@router.get("/documents/{doc_id}")
def document(doc_id: str) -> Dict[str, Any]:
    doc = _doc_or_404(doc_id)
    return {**doc, "ocr": ocrsvc.job_status(doc)}


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str) -> Dict[str, str]:
    doc = _doc_or_404(doc_id)
    db.delete_document(doc_id)
    Path(doc["path"]).unlink(missing_ok=True)
    return {"deleted": doc_id}


@router.get("/documents/{doc_id}/history")
def document_history(doc_id: str, format: str = Query("md", pattern="^(json|md)$")):
    """Every question asked about this document, with both answers and the verdict, as a download."""
    h = historysvc.document_history(doc_id)
    if h is None:
        raise HTTPException(404, "Document not found")
    stem = Path(h["document"]["filename"]).stem
    disp = {"Content-Disposition": f'attachment; filename="{stem}-history.{format}"'}
    if format == "json":
        return Response(json.dumps(h, ensure_ascii=False, indent=2), media_type="application/json", headers=disp)
    return PlainTextResponse(historysvc.history_markdown(h), media_type="text/markdown", headers=disp)


@router.get("/documents/{doc_id}/file")
def document_file(doc_id: str):
    doc = _doc_or_404(doc_id)
    return FileResponse(doc["path"], filename=doc["filename"])


@router.get("/documents/{doc_id}/pages/{page}/image")
def page_image(doc_id: str, page: int, dpi: int = Query(110, ge=36, le=300)) -> Response:
    doc = _doc_or_404(doc_id)
    idx = _page_or_404(doc, page)
    img = pdfsvc.render_page(doc["path"], idx, dpi)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/documents/{doc_id}/pages/{page}/crop")
def page_crop(doc_id: str, page: int, x0: float = Query(ge=0, le=1), y0: float = Query(ge=0, le=1),
              x1: float = Query(ge=0, le=1), y1: float = Query(ge=0, le=1), dpi: int = Query(200, ge=72, le=300)) -> Response:
    """An enlarged region of a page (box as fractions of the page): what the look-closer re-check read."""
    if x1 <= x0 or y1 <= y0:
        raise HTTPException(400, "Empty region")
    doc = _doc_or_404(doc_id)
    idx = _page_or_404(doc, page)
    img = pdfsvc.render_page(doc["path"], idx, dpi)
    W, H = img.size
    buf = io.BytesIO()
    img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))).save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/documents/{doc_id}/pages/{page}/ocr")
def page_ocr(doc_id: str, page: int) -> Dict[str, Any]:
    """Raw OCR text, boxes and the information-loss audit for one page (1-based)."""
    doc = _doc_or_404(doc_id)
    idx = _page_or_404(doc, page)
    res = ocrsvc.ocr_pages(doc, [idx])[idx]
    return {"page": page, "engine": ocrsvc.cache_key(), "text": res["text"], "boxes": res["boxes"],
            "render_dpi": get_settings().ocr_render_dpi,  # box coordinates are in pixels of the page rendered at this dpi
            "mean_conf": res["mean_conf"], "ms": res["ms"], "audit": auditsvc.audit_page(doc["path"], idx, res["text"])}


@router.post("/documents/{doc_id}/ocr")
def start_ocr(doc_id: str) -> Dict[str, Any]:
    return ocrsvc.start_job(_doc_or_404(doc_id))


@router.get("/documents/{doc_id}/ocr/status")
def ocr_status(doc_id: str) -> Dict[str, Any]:
    return ocrsvc.job_status(_doc_or_404(doc_id))


@router.get("/documents/{doc_id}/retrieve")
def retrieve(doc_id: str, q: str = Query(min_length=1)) -> Dict[str, Any]:
    """BM25 ranking of pages for a query (for the retrieval visualisation)."""
    doc = _doc_or_404(doc_id)
    s = get_settings()
    if doc["n_pages"] == 1:
        return {"corpus": "none", "ranked": [{"page": 1, "score": 0.0}], "selected": [1], "page_cap": s.vlm_page_cap}
    corpus, name = _retrieval_corpus(doc)
    ranked = rank_pages(q, corpus)
    sel = sorted(p + 1 for p, _ in ranked[: s.vlm_page_cap])
    return {"corpus": name, "ranked": [{"page": p + 1, "score": sc} for p, sc in ranked], "selected": sel, "page_cap": s.vlm_page_cap}


# ------------------------------------------------------------------------------------------------ conversations
@router.post("/conversations")
def create_conversation(body: ConversationCreate) -> Dict[str, Any]:
    if body.doc_id:
        _doc_or_404(body.doc_id)
    return db.create_conversation(body.title, body.doc_id)


@router.get("/conversations")
def conversations() -> List[Dict[str, Any]]:
    return db.list_conversations()


@router.get("/conversations/{cid}")
def conversation(cid: str) -> Dict[str, Any]:
    conv = db.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return {**conv, "messages": db.list_messages(cid)}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str) -> Dict[str, str]:
    if not db.get_conversation(cid):
        raise HTTPException(404, "Conversation not found")
    db.delete_conversation(cid)
    return {"deleted": cid}


@router.get("/conversations/{cid}/export")
def export_conversation(cid: str, format: str = Query("json", pattern="^(json|md)$")):
    conv = db.get_conversation(cid)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    msgs = db.list_messages(cid)
    if format == "json":
        return {**conv, "messages": msgs}
    lines = [f"# {conv['title']}", ""]
    for m in msgs:
        if m["role"] == "user":
            lines += [f"**You:** {m['content']}", ""]
        else:
            p = m["payload"]
            lines.append(f"**VLM:** {(p.get('vlm') or {}).get('answer')}")
            lines.append(f"**OCR+LLM:** {(p.get('ocr') or {}).get('answer')}")
            v = p.get("verification")
            if v:
                lines.append(f"*Verdict: {v['verdict']} (agreement {v['agreement']})*")
            lines.append("")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


def _history(cid: str, limit: int) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    msgs = db.list_messages(cid)
    hv: List[Tuple[str, str]] = []
    ho: List[Tuple[str, str]] = []
    last_q = None
    for m in msgs:
        if m["role"] == "user":
            last_q = m["content"]
        elif m["role"] == "assistant" and last_q:
            p = m["payload"]
            va, oa = (p.get("vlm") or {}).get("answer"), (p.get("ocr") or {}).get("answer")
            if va:
                hv.append((last_q, va))
            if oa:
                ho.append((last_q, oa))
            last_q = None
    return hv[-limit:], ho[-limit:]


def _reusable_answer(doc: Dict[str, Any], req: AskRequest) -> Dict[str, Any] | None:
    """The newest saved answer to this question about this file, made with today's settings and without errors."""
    now = answer_config()
    for prev in db.previous_answers(doc["sha256"], req.question):
        p = prev["answer"]["payload"]
        if p.get("mode") != req.mode or bool(p.get("short")) != req.short:
            continue
        if "config" in p:
            if p["config"] != now:
                continue
        else:  # saved before settings were recorded: compare what those answers did record
            r = p.get("retrieval") or {}
            if (p.get("demo") != now["demo"] or r.get("read_all") != now["read_all_pages"] or r.get("page_cap") != now["vlm_page_cap"]
                    or (p.get("ocr") and p["ocr"].get("engine") != now["ocr_engine"])):
                continue
        if any((p.get(k) or {}).get("error") for k in ("vlm", "ocr")):
            continue
        return prev
    return None


@router.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    s = get_settings()
    conv = db.get_conversation(req.conversation_id) if req.conversation_id else None
    if req.conversation_id and not conv:
        raise HTTPException(404, "Conversation not found")
    doc_id = req.doc_id or (conv or {}).get("doc_id")
    if not doc_id:
        raise HTTPException(400, "Provide doc_id (or a conversation that already has a document).")
    doc = _doc_or_404(doc_id)
    if not conv:
        conv = db.create_conversation(req.question[:60], doc_id)
    elif conv.get("doc_id") != doc_id and conv.get("doc_sha256") == doc["sha256"]:
        db.attach_conversation(conv["id"], doc_id)   # continuing an earlier conversation about this same file
    hv, ho = _history(conv["id"], s.history_turns)
    user_msg = db.add_message(conv["id"], "user", req.question, {"doc_id": doc_id})
    # A follow-up depends on the conversation so far, so only an opening question can reuse a saved answer.
    prev = _reusable_answer(doc, req) if (req.reuse and not hv and not ho) else None
    if prev:
        result = {**prev["answer"]["payload"], "reused_from": {
            "message_id": prev["answer"]["id"], "conversation_id": prev["answer"]["conversation_id"],
            "asked_at": prev["question"]["created_at"]}}
    else:
        result = run_ask(doc, req.question, mode=req.mode, short=req.short, history_vlm=hv, history_ocr=ho)
    summary = " | ".join(f"{k.upper()}: {(result[k] or {}).get('answer') or (result[k] or {}).get('error')}"
                         for k in ("vlm", "ocr") if result.get(k))
    assistant_msg = db.add_message(conv["id"], "assistant", summary, result)
    return {"conversation_id": conv["id"], "user_message": user_msg, "assistant_message": assistant_msg}


# ------------------------------------------------------------------------------------------------ experiments
@router.get("/eval/datasets")
def datasets() -> List[Dict[str, Any]]:
    return list_datasets(get_settings().eval_dir)


@router.get("/experiments")
def experiments() -> List[Dict[str, Any]]:
    return db.list_experiments()


@router.post("/experiments")
def create_experiment(body: ExperimentCreate) -> Dict[str, Any]:
    s = get_settings()
    p = Path(body.dataset)
    p = p if p.is_absolute() else s.eval_dir / p
    if not p.exists():
        raise HTTPException(404, f"Dataset not found: {p}")
    try:
        return runner.create_and_start(body.name, str(p), body.limit, body.mode, body.notes)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(400, str(e)) from e


@router.get("/experiments/{exp_id}")
def experiment(exp_id: str) -> Dict[str, Any]:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return {**exp, "items": db.list_experiment_items(exp_id)}


@router.post("/experiments/{exp_id}/resume")
def resume_experiment(exp_id: str) -> Dict[str, Any]:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp["status"] == "running":
        raise HTTPException(409, "Experiment is already running")
    runner.start_in_background(exp_id, resume=True)
    return {"resumed": exp_id}


@router.delete("/experiments/{exp_id}")
def delete_experiment(exp_id: str) -> Dict[str, str]:
    exp = db.get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp["status"] == "running":
        raise HTTPException(409, "Experiment is running")
    db.delete_experiment(exp_id)
    return {"deleted": exp_id}


@router.get("/experiments/{exp_id}/csv")
def experiment_csv(exp_id: str) -> PlainTextResponse:
    if not db.get_experiment(exp_id):
        raise HTTPException(404, "Experiment not found")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["qid", "question", "gold", "vlm_pred", "ocr_pred", "vlm_em", "vlm_anls", "ocr_em", "ocr_anls",
                "vlm_ms", "ocr_ms", "answer_in_ocr", "pipelines_agree"])
    for it in db.list_experiment_items(exp_id):
        w.writerow([it["qid"], it["question"], json.dumps(it["gold"]), it["vlm_pred"], it["ocr_pred"],
                    it["vlm_scores"].get("em"), it["vlm_scores"].get("anls"), it["ocr_scores"].get("em"),
                    it["ocr_scores"].get("anls"), it["vlm_ms"], it["ocr_ms"], it["answer_in_ocr"], it["agree"]])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{exp_id}.csv"'})
