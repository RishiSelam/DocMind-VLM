"""OCR engines behind one interface, plus a per-document cache and background job runner.

Engines
  rapidocr   default. PaddleOCR-family models via ONNX Runtime: no paddlepaddle, CPU only, models ship in the wheel.
  paddleocr  your original baseline, kept optional (enable_mkldnn=False).
  docling    optional. Layout + TableFormer tables + an OCR backend. Downloads models on first use. EXPERIMENTAL.
  textlayer  embedded PDF text only (no pixels are read). Useful as a sanity check, not as an OCR baseline.
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from ..config import get_settings
from .. import db
from . import pdf as pdfsvc

log = logging.getLogger("docmind.ocr")


@dataclass
class OCRPage:
    page: int
    text: str
    boxes: List[Dict[str, Any]] = field(default_factory=list)
    mean_conf: Optional[float] = None
    ms: float = 0.0


# --------------------------------------------------------------------------- layout heuristics
def boxes_to_text(boxes: List[Dict[str, Any]], col_gap_factor: float = 2.5) -> str:
    """Rebuild reading order from word/line boxes.

    Boxes whose vertical centres are close share a line; wide horizontal gaps inside a line become ' | ',
    which keeps simple tables legible to a text-only LLM. This is a heuristic, not table structure recognition.
    """
    if not boxes:
        return ""
    heights = [max(b["y1"] - b["y0"], 1.0) for b in boxes]
    med_h = statistics.median(heights)
    items = sorted(boxes, key=lambda b: ((b["y0"] + b["y1"]) / 2, b["x0"]))
    lines: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    cur_cy = 0.0
    for b in items:
        cy = (b["y0"] + b["y1"]) / 2
        if cur and abs(cy - cur_cy) > 0.6 * med_h:
            lines.append(cur)
            cur = []
        cur.append(b)
        cur_cy = sum((x["y0"] + x["y1"]) / 2 for x in cur) / len(cur)
    if cur:
        lines.append(cur)
    out_lines = []
    for ln in lines:
        ln.sort(key=lambda b: b["x0"])
        s = ln[0]["text"]
        for prev, nxt in zip(ln, ln[1:]):
            gap = nxt["x0"] - prev["x1"]
            s += (" | " if gap > col_gap_factor * med_h else " ") + nxt["text"]
        out_lines.append(s)
    return "\n".join(out_lines)


def _poly_to_box(poly: Any, text: str, score: float) -> Dict[str, Any]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return {"text": str(text), "score": float(score), "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


# --------------------------------------------------------------------------- engines
class OCREngine:
    name = "base"

    def extract(self, path: str, pages: List[int]) -> Dict[int, OCRPage]:  # pragma: no cover - interface
        raise NotImplementedError


class RapidOCREngine(OCREngine):
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR  # lazy: keeps import errors out of app start

        self._ocr = RapidOCR()
        self._lock = threading.Lock()

    def extract(self, path: str, pages: List[int]) -> Dict[int, OCRPage]:
        s = get_settings()
        out: Dict[int, OCRPage] = {}
        for p in pages:
            img = pdfsvc.render_page(path, p, dpi=s.ocr_render_dpi)
            arr = np.array(img)[:, :, ::-1]  # RGB -> BGR (OpenCV convention used by RapidOCR)
            t0 = time.perf_counter()
            with self._lock:
                result, _ = self._ocr(arr)
            boxes = [_poly_to_box(poly, txt, float(sc)) for poly, txt, sc in (result or [])]
            confs = [b["score"] for b in boxes]
            out[p] = OCRPage(p, boxes_to_text(boxes), boxes, float(np.mean(confs)) if confs else None, (time.perf_counter() - t0) * 1000)
        return out


class PaddleOCREngine(OCREngine):
    name = "paddleocr"

    def __init__(self) -> None:
        from paddleocr import PaddleOCR

        try:
            self._ocr = PaddleOCR(lang="en", enable_mkldnn=False)
        except (TypeError, ValueError):
            self._ocr = PaddleOCR(lang="en")
        self._lock = threading.Lock()

    def _run(self, arr: np.ndarray) -> List[Dict[str, Any]]:
        boxes: List[Dict[str, Any]] = []
        if hasattr(self._ocr, "predict"):  # PaddleOCR 3.x
            for r in self._ocr.predict(arr):
                texts, scores, polys = r["rec_texts"], r["rec_scores"], r["rec_polys"]
                for t, sc, poly in zip(texts, scores, polys):
                    boxes.append(_poly_to_box(poly, t, sc))
        else:  # PaddleOCR 2.x
            res = self._ocr.ocr(arr, cls=False)
            for line in (res[0] or []) if res else []:
                poly, (t, sc) = line
                boxes.append(_poly_to_box(poly, t, sc))
        return boxes

    def extract(self, path: str, pages: List[int]) -> Dict[int, OCRPage]:
        s = get_settings()
        out: Dict[int, OCRPage] = {}
        for p in pages:
            arr = np.array(pdfsvc.render_page(path, p, dpi=s.ocr_render_dpi))[:, :, ::-1].copy()
            t0 = time.perf_counter()
            with self._lock:
                boxes = self._run(arr)
            confs = [b["score"] for b in boxes]
            out[p] = OCRPage(p, boxes_to_text(boxes), boxes, float(np.mean(confs)) if confs else None, (time.perf_counter() - t0) * 1000)
        return out


class TextLayerEngine(OCREngine):
    name = "textlayer"

    def extract(self, path: str, pages: List[int]) -> Dict[int, OCRPage]:
        return {p: OCRPage(p, pdfsvc.text_layer(path, p), [], None, 0.0) for p in pages}


class DoclingEngine(OCREngine):
    """EXPERIMENTAL. Converts the whole file once, then serves per-page markdown (tables become markdown tables).

    Requires `pip install docling`. Its Python API moves between releases; if construction fails the error says why.
    """

    name = "docling"

    def __init__(self) -> None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat

        try:
            from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions

            opts = PdfPipelineOptions()
            opts.do_ocr = True
            opts.do_table_structure = True
            opts.ocr_options = RapidOcrOptions()
            self._conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        except Exception as e:  # fall back to Docling defaults
            log.warning("Docling RapidOCR options unavailable (%s); using Docling defaults", e)
            self._conv = DocumentConverter()
        self._cache: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def extract(self, path: str, pages: List[int]) -> Dict[int, OCRPage]:
        t0 = time.perf_counter()
        with self._lock:
            if path not in self._cache:
                self._cache[path] = self._conv.convert(path).document
            doc = self._cache[path]
        total_ms = (time.perf_counter() - t0) * 1000
        out: Dict[int, OCRPage] = {}
        for p in pages:
            md = doc.export_to_markdown(page_no=p + 1)  # docling pages are 1-based
            out[p] = OCRPage(p, md.strip(), [], None, total_ms / max(len(pages), 1))
        return out


_ENGINES: Dict[str, OCREngine] = {}
_ENGINE_LOCK = threading.Lock()


def get_engine(name: Optional[str] = None) -> OCREngine:
    name = (name or get_settings().ocr_engine).lower()
    with _ENGINE_LOCK:
        if name not in _ENGINES:
            factory = {"rapidocr": RapidOCREngine, "paddleocr": PaddleOCREngine, "docling": DoclingEngine, "textlayer": TextLayerEngine}.get(name)
            if factory is None:
                raise ValueError(f"Unknown OCR_ENGINE '{name}'. Use rapidocr, paddleocr, docling or textlayer.")
            _ENGINES[name] = factory()
        return _ENGINES[name]


# --------------------------------------------------------------------------- cached document OCR
_DOC_LOCKS: Dict[str, threading.Lock] = {}
_DOC_LOCKS_GUARD = threading.Lock()


def _doc_lock(doc_id: str) -> threading.Lock:
    with _DOC_LOCKS_GUARD:
        return _DOC_LOCKS.setdefault(doc_id, threading.Lock())


def cache_key() -> str:
    s = get_settings()
    return f"{s.ocr_engine.lower()}{'+tl' if s.use_text_layer else ''}"


def ocr_pages(doc: Dict[str, Any], pages: Optional[List[int]] = None, progress_cb=None) -> Dict[int, Dict[str, Any]]:
    """Return {page: {text, boxes, mean_conf, ms}} for `pages` (default: all), running OCR only for cache misses."""
    s = get_settings()
    doc_id, path = doc["id"], doc["path"]
    wanted = list(range(doc["n_pages"])) if pages is None else sorted(set(pages))
    key = cache_key()
    with _doc_lock(doc_id):
        cached = db.get_ocr_pages(doc_id, key)
        missing = [p for p in wanted if p not in cached]
        if s.use_text_layer and missing:
            still = []
            for p in missing:
                tl = pdfsvc.text_layer(path, p)
                if tl:
                    db.save_ocr_page(doc_id, p, key, tl, [], None, 0.0)
                else:
                    still.append(p)
            missing = still
        if missing:
            eng = get_engine()
            if eng.name == "docling":  # whole-file engine: convert once
                res = eng.extract(path, missing)
                for p, r in res.items():
                    db.save_ocr_page(doc_id, p, key, r.text, r.boxes, r.mean_conf, r.ms)
                if progress_cb:
                    progress_cb(len(missing), len(missing))
            else:
                for i, p in enumerate(missing):
                    r = eng.extract(path, [p])[p]
                    db.save_ocr_page(doc_id, p, key, r.text, r.boxes, r.mean_conf, r.ms)
                    if progress_cb:
                        progress_cb(i + 1, len(missing))
        cached = db.get_ocr_pages(doc_id, key)
    return {p: cached[p] for p in wanted if p in cached}


# --------------------------------------------------------------------------- background OCR jobs
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_GUARD = threading.Lock()


def job_status(doc: Dict[str, Any]) -> Dict[str, Any]:
    with _JOBS_GUARD:
        j = dict(_JOBS.get(doc["id"], {}))
    done_cached = len(db.get_ocr_pages(doc["id"], cache_key()))
    if j.get("status") == "running":
        return {**j, "cached_pages": done_cached, "total": doc["n_pages"]}
    return {"status": "done" if done_cached >= doc["n_pages"] else j.get("status", "idle"),
            "error": j.get("error"), "cached_pages": done_cached, "total": doc["n_pages"]}


def start_job(doc: Dict[str, Any]) -> Dict[str, Any]:
    with _JOBS_GUARD:
        if _JOBS.get(doc["id"], {}).get("status") == "running":
            return job_status(doc)
        _JOBS[doc["id"]] = {"status": "running", "error": None}

    def run() -> None:
        try:
            ocr_pages(doc)
            with _JOBS_GUARD:
                _JOBS[doc["id"]] = {"status": "done", "error": None}
        except Exception as e:  # noqa: BLE001
            log.exception("OCR job failed")
            with _JOBS_GUARD:
                _JOBS[doc["id"]] = {"status": "error", "error": f"{type(e).__name__}: {e}"}

    threading.Thread(target=run, daemon=True, name=f"ocr-{doc['id']}").start()
    return job_status(doc)
