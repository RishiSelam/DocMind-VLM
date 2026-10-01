"""Experiment runner: both pipelines over a dataset, per-item checkpointing, resumable."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from .. import db
from ..config import get_settings
from ..services import ocr as ocrsvc
from ..services.models import hub
from ..services.pipelines import run_ask
from ..services.prompts import PROMPT_VERSION
from ..services.verification import verify
from . import metrics
from .docvqa import item_as_document, load_dataset

log = logging.getLogger("docmind.eval")
_RUN_LOCK = threading.Lock()  # one experiment at a time: they share one GPU


def snapshot_config(dataset: str, limit: Optional[int], mode: str, notes: str = "") -> Dict[str, Any]:
    s = get_settings()
    return {
        "dataset": dataset, "limit": limit, "mode": mode, "notes": notes, "prompt_version": PROMPT_VERSION,
        "demo_mode": s.demo_mode, "vlm_model": s.vlm_model_id, "llm_model": s.llm_model_id, "ocr_engine": ocrsvc.cache_key(),
        "read_all_pages": s.read_all_pages, "vlm_page_cap": s.vlm_page_cap, "match_pages": s.match_pages, "max_context_chars": s.max_context_chars,
        "vlm_max_pixels": s.vlm_max_pixels, "ocr_render_dpi": s.ocr_render_dpi, "max_new_tokens": s.max_new_tokens,
        "decoding": "greedy",
    }


def _single_page_doc(item: Dict[str, Any]) -> Dict[str, Any]:
    doc = item_as_document(item)
    return doc


def run_experiment(exp_id: str, resume: bool = True) -> None:
    with _RUN_LOCK:
        exp = db.get_experiment(exp_id)
        if not exp:
            return
        cfg = exp["config"]
        try:
            db.update_experiment(exp_id, status="running", error=None)
            items = load_dataset(cfg["dataset"], cfg.get("limit"))
            done = {r["idx"] for r in db.list_experiment_items(exp_id)} if resume else set()
            db.update_experiment(exp_id, progress_total=len(items), progress_done=len(done))
            for idx, it in enumerate(items):
                if idx in done:
                    continue
                doc = _single_page_doc(it)
                res = run_ask(doc, it["question"], mode=cfg.get("mode", "both"), short=True, with_audit=False, return_context=True)
                vp = (res.get("vlm") or {}).get("answer")
                op = (res.get("ocr") or {}).get("answer")
                ctx = res.pop("_ocr_context", "")
                gold = it["answers"]
                record = {
                    "qid": it["qid"], "question": it["question"], "gold": gold, "vlm_pred": vp, "ocr_pred": op,
                    "vlm_scores": metrics.score_item(vp, gold) if res.get("vlm") else {},
                    "ocr_scores": metrics.score_item(op, gold) if res.get("ocr") else {},
                    "vlm_ms": (res.get("vlm") or {}).get("ms"), "ocr_ms": (res.get("ocr") or {}).get("ms"),
                    "answer_in_ocr": metrics.answer_in_text(gold, ctx) if res.get("ocr") else None,
                    "agree": (verify(vp, op)["verdict"] == "consistent") if (vp is not None and op is not None) else None,
                }
                db.add_experiment_item(exp_id, idx, record)  # written immediately: a crash loses at most one item
                db.update_experiment(exp_id, progress_done=len(db.list_experiment_items(exp_id)))
            finalize(exp_id, "finished")
        except Exception as e:  # noqa: BLE001
            log.exception("experiment %s failed", exp_id)
            finalize(exp_id, "failed", error=f"{type(e).__name__}: {e}")


def finalize(exp_id: str, status: str, error: Optional[str] = None) -> None:
    items = db.list_experiment_items(exp_id)
    usable = [i for i in items if i["vlm_scores"] and i["ocr_scores"]]
    db.update_experiment(exp_id, status=status, error=error, finished_at=time.time(),
                         metrics=metrics.aggregate(usable) if usable else {"n": 0})


def start_in_background(exp_id: str, resume: bool = True) -> None:
    threading.Thread(target=run_experiment, args=(exp_id, resume), daemon=True, name=f"exp-{exp_id}").start()


def create_and_start(name: str, dataset: str, limit: Optional[int], mode: str = "both", notes: str = "") -> Dict[str, Any]:
    items = load_dataset(dataset, limit)
    exp = db.create_experiment(name, snapshot_config(dataset, limit, mode, notes), len(items))
    start_in_background(exp["id"])
    return exp
