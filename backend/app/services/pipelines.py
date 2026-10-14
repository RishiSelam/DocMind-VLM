"""Ask a document a question through both pipelines and compare them.

  VLM pipeline      pages (images) -> Qwen2.5-VL
  OCR+LLM pipeline  pages -> OCR text -> Qwen2.5-7B-Instruct

Page policy, READ_ALL_PAGES=true (default): both pipelines read every page. The VLM gets batches of at most
VLM_PAGE_CAP consecutive pages (what fits in GPU memory); the LLM gets the OCR text in parts of at most
MAX_CONTEXT_CHARS. Each part is asked the question, and when two or more parts find an answer the same model combines
them (identical combine prompt for both pipelines).

READ_ALL_PAGES=false: the VLM sees only the VLM_PAGE_CAP best pages by BM25, and the LLM gets one call with the
best-ranked OCR text up to MAX_CONTEXT_CHARS (MATCH_PAGES=true gives it the VLM's pages instead).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import db
from ..config import get_settings
from . import audit as auditsvc
from . import diagnosis, evidence, explain, monitoring, ocr as ocrsvc, pdf as pdfsvc, verification
from .models import hub
from .prompts import NOT_FOUND
from .retrieval import rank_pages, select_pages

log = logging.getLogger("docmind.pipelines")
History = List[Tuple[str, str]]


def _usable_text_layers(doc: Dict[str, Any]) -> Optional[Dict[int, str]]:
    """The PDF's embedded text, if at least half the pages have some. None for scans and image files."""
    layers = pdfsvc.all_text_layers(doc["path"])
    if layers and sum(1 for t in layers.values() if len(t) > 20) >= 0.5 * doc["n_pages"]:
        return layers
    return None


def add_analysis(payload: Dict[str, Any], doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Answers saved before the analysis existed get one from the cached OCR and the PDF's own text. No model is run,
    nothing is saved, and the answer is returned unchanged if that is not possible."""
    if not doc or not payload.get("ocr"):
        return payload
    cached = None
    if not payload["ocr"].get("ocr_text"):
        try:
            cached = db.get_ocr_pages(doc["id"], ocrsvc.cache_key())
            used_pages = [p - 1 for p in payload["ocr"].get("pages") or [] if p - 1 in cached]
            if not used_pages:
                used_pages = sorted(cached.keys())
            if used_pages:
                payload["ocr"]["ocr_text"] = "\n".join(f"--- Page {p + 1} ---\n{cached[p]['text']}" for p in sorted(used_pages))
        except Exception as e:  # noqa: BLE001
            log.debug("could not attach ocr_text in add_analysis: %s", e)
    if payload.get("vlm") and payload.get("ocr") and not payload.get("combined_summary"):
        va = (payload.get("vlm") or {}).get("answer")
        oa = (payload.get("ocr") or {}).get("answer")
        if va and oa:
            try:
                payload["combined_summary"] = synthesize_summary(
                    payload.get("question", ""),
                    va, oa,
                    payload.get("verification"),
                    payload.get("analysis"),
                    model=None,
                )
            except Exception as e:  # noqa: BLE001
                log.debug("could not attach combined_summary in add_analysis: %s", e)
    if "analysis" in payload or not payload.get("vlm"):
        return payload
    try:
        if cached is None:
            cached = db.get_ocr_pages(doc["id"], ocrsvc.cache_key())
        used = {p - 1: cached[p - 1] for p in payload["ocr"].get("pages") or [] if p - 1 in cached}
        if not used:
            return payload
        layers = _usable_text_layers(doc)
        reference = "\n".join(layers.values()) if layers else None
        dpi = get_settings().ocr_render_dpi
        analyzed = diagnosis.analyze(payload, used, reference, lambda p: pdfsvc.region_kinds(doc["path"], p),
                                     lambda p: evidence.page_px_size(doc["path"], p, dpi))
        out_payload = {**payload, "analysis": analyzed}
        if not out_payload.get("combined_summary") and va and oa:
            out_payload["combined_summary"] = synthesize_summary(
                payload.get("question", ""), va, oa,
                payload.get("verification"), analyzed, model=None
            )
        return out_payload
    except Exception as e:  # noqa: BLE001
        log.warning("could not add an analysis to a saved answer: %s", e)
        return payload


def _retrieval_corpus(doc: Dict[str, Any]) -> Tuple[Dict[int, str], str]:
    layers = _usable_text_layers(doc)
    if layers:
        return layers, "textlayer"
    pages = ocrsvc.ocr_pages(doc)
    return {p: v["text"] for p, v in pages.items()}, "ocr"


def build_context(pages: Dict[int, Dict[str, Any]], ranked: List[Tuple[int, float]], budget: int) -> Tuple[str, List[int], bool]:
    order = [p for p, _ in ranked if p in pages] or sorted(pages)
    for p in sorted(pages):
        if p not in order:
            order.append(p)
    included: Dict[int, str] = {}
    used = 0
    truncated = False
    for p in order:
        block = f"--- Page {p + 1} ---\n{pages[p]['text']}\n"
        if used + len(block) > budget:
            if not included:
                included[p] = block[:budget]
                used = budget
            truncated = True
            break
        included[p] = block
        used += len(block)
    if len(included) < len(pages):
        truncated = True
    text = "\n".join(included[p] for p in sorted(included))
    return text, sorted(included), truncated


def text_chunks(pages: Dict[int, Dict[str, Any]], budget: int) -> List[Tuple[str, List[int]]]:
    """All OCR text, in page order, cut into pieces of at most `budget` characters. Nothing is dropped:
    a page longer than the budget is split across pieces."""
    budget = max(budget, 200)
    chunks: List[Tuple[str, List[int]]] = []
    cur, cur_pages = "", []
    for p in sorted(pages):
        block = f"--- Page {p + 1} ---\n{pages[p]['text']}\n"
        while len(block) > budget:
            if cur:
                chunks.append((cur, cur_pages))
                cur, cur_pages = "", []
            chunks.append((block[:budget], [p]))
            block = f"--- Page {p + 1} (continued) ---\n" + block[budget:]
        if cur and len(cur) + 1 + len(block) > budget:
            chunks.append((cur, cur_pages))
            cur, cur_pages = "", []
        cur = f"{cur}\n{block}" if cur else block
        if p not in cur_pages:
            cur_pages.append(p)
    if cur:
        chunks.append((cur, cur_pages))
    return chunks


def page_batches(pages: List[int], size: int) -> List[List[int]]:
    """Consecutive pages in groups of `size`, so a table running across two pages usually stays together."""
    size = max(size, 1)
    return [pages[i:i + size] for i in range(0, len(pages), size)]


def pages_label(pages: List[int]) -> str:
    """0-based page indices -> 'page 3' / 'pages 1-6' (1-based, for prompts and the UI)."""
    a, b = min(pages) + 1, max(pages) + 1
    return f"page {a}" if a == b else f"pages {a}-{b}"


def merge_parts(model: Any, question: str, partials: List[Tuple[str, str]], history: History, short: bool) -> Tuple[str, bool]:
    """Final answer from per-part answers. Only parts that found something are combined, and the model is only
    called when two or more did. Returns (answer, combined)."""
    found = [(label, a) for label, a in partials if not verification.is_not_found(a)]
    if not found:
        return NOT_FOUND, False
    if len(found) == 1:
        return found[0][1], False
    return model.combine(question, found, history, short), True

def synthesize_summary(
    question: str,
    vlm_ans: Optional[str],
    ocr_ans: Optional[str],
    verification_res: Optional[Dict[str, Any]] = None,
    analysis_res: Optional[Dict[str, Any]] = None,
    model: Any = None,
) -> Dict[str, Any]:
    """Generates a unified summary containing the information from both the VLM and OCR pipelines."""
    v_ans = (vlm_ans or "").strip()
    o_ans = (ocr_ans or "").strip()
    if not v_ans and not o_ans:
        return {"summary": "No information returned by either method."}
    if not v_ans:
        return {"summary": f"Information extracted by OCR pipeline: {o_ans}", "ocr_unique": [o_ans]}
    if not o_ans:
        return {"summary": f"Information extracted by Vision model: {v_ans}", "vlm_unique": [v_ans]}

    v_nf = verification.is_not_found(v_ans)
    o_nf = verification.is_not_found(o_ans)

    if v_nf and o_nf:
        return {
            "summary": "Both methods agree that this information is not found in the document.",
            "consensus": ["Not found in document."],
        }
    if v_nf and not o_nf:
        return {
            "summary": f"The OCR pipeline extracted: \"{o_ans}\". (The vision model did not find it in the inspected pages).",
            "ocr_unique": [o_ans],
        }
    if o_nf and not v_nf:
        return {
            "summary": f"The Vision model extracted: \"{v_ans}\". (The OCR text did not contain this information, likely due to layout or visual formatting).",
            "vlm_unique": [v_ans],
        }

    pairs = (verification_res or {}).get("pairs") or []
    consensus = [p["vlm"] for p in pairs if p.get("label") == "agree" and p.get("vlm")]
    vlm_unique = [p["vlm"] for p in pairs if p.get("label") == "only_vlm" and p.get("vlm")]
    ocr_unique = [p["ocr"] for p in pairs if p.get("label") == "only_ocr" and p.get("ocr")]
    discrepancies = [f"Vision reported '{p['vlm']}' while OCR reported '{p['ocr']}'" for p in pairs if p.get("label") == "conflict"]

    llm_summary = None
    if model is not None and hasattr(model, "generate") and getattr(model, "name", "") != "demo-llm":
        try:
            synth_ctx = (
                f"Question about the document: {question}\n\n"
                f"Vision Model Answer:\n{v_ans}\n\n"
                f"OCR + Text Pipeline Answer:\n{o_ans}\n\n"
                "Write a clear, comprehensive summary that combines the information from BOTH answers into a single unified response. "
                "Preserve all facts, figures, numbers, dates, and names mentioned in either answer. "
                "If both agree, state the verified fact. If they provide complementary details, synthesize them together. "
                "If they conflict on a value, mention both clearly."
            )
            llm_summary = model.generate(synth_ctx, question, history=[], short=False)
            if verification.is_not_found(llm_summary) or len(llm_summary.strip()) < 5:
                llm_summary = None
        except Exception as e:  # noqa: BLE001
            log.warning("LLM summary synthesis error: %s", e)

    verdict = (verification_res or {}).get("verdict")
    better = (analysis_res or {}).get("better")

    if not llm_summary:
        if verdict == "consistent" or v_ans.lower() == o_ans.lower():
            llm_summary = (
                f"**Consensus Finding:** {v_ans}\n\n"
                "Both the Vision Language Model (analyzing the page image directly) and the OCR text pipeline "
                "confirm this information, providing strong cross-modal verification."
            )
        else:
            bullets = [
                f"- **Vision Model Findings:** {v_ans}",
                f"- **OCR Pipeline Findings:** {o_ans}",
            ]
            if better == "vlm":
                bullets.append("*Synthesis Note:* The Vision model provides the better-supported reading of the page image.")
            elif better == "ocr":
                bullets.append("*Synthesis Note:* The OCR pipeline provides the better-supported textual match.")
            if discrepancies:
                bullets.append(f"*Discrepancies Noted:* {'; '.join(discrepancies)}.")

            llm_summary = "\n".join(bullets)

    return {
        "summary": llm_summary,
        "consensus": consensus,
        "vlm_unique": vlm_unique,
        "ocr_unique": ocr_unique,
        "discrepancies": discrepancies,
    }


def answer_config() -> Dict[str, Any]:
    """Everything that changes an answer. Saved with each answer, so a saved answer is reused only when all of it matches."""
    from .prompts import PROMPT_VERSION
    s = get_settings()
    return {"prompt_version": PROMPT_VERSION, "demo": hub.demo, "explain": [s.explain, s.look_closer, s.faithfulness], "vlm_model": getattr(hub.vlm, "name", None),
            "llm_model": getattr(hub.llm, "name", None), "ocr_engine": ocrsvc.cache_key(), "read_all_pages": s.read_all_pages,
            "vlm_page_cap": s.vlm_page_cap, "match_pages": s.match_pages, "max_context_chars": s.max_context_chars,
            "vlm_max_pixels": s.vlm_max_pixels, "max_new_tokens": s.max_new_tokens}


def run_ask(
    doc: Dict[str, Any],
    question: str,
    *,
    mode: str = "both",
    short: bool = False,
    history_vlm: Optional[History] = None,
    history_ocr: Optional[History] = None,
    with_audit: bool = True,
    return_context: bool = False,
) -> Dict[str, Any]:
    s = get_settings()
    t_start = time.perf_counter()
    n, path = doc["n_pages"], doc["path"]
    history_vlm, history_ocr = history_vlm or [], history_ocr or []
    want_vlm, want_ocr = mode in ("both", "vlm"), mode in ("both", "ocr")

    # ---- retrieval -------------------------------------------------------------------------------
    t0 = time.perf_counter()
    ranked: List[Tuple[int, float]] = [(p, 0.0) for p in range(n)]
    corpus_name = "none"
    if n > 1 and (n > s.vlm_page_cap or want_ocr):
        corpus, corpus_name = _retrieval_corpus(doc)
        ranked = rank_pages(question, corpus)
    if s.read_all_pages or n <= s.vlm_page_cap:
        vlm_pages = list(range(n))
    else:
        vlm_pages = select_pages(ranked, s.vlm_page_cap)
    retrieval_ms = (time.perf_counter() - t0) * 1000

    result: Dict[str, Any] = {
        "question": question, "mode": mode, "demo": hub.demo, "short": short,
        "retrieval": {"ranked": [{"page": p, "score": sc} for p, sc in ranked], "vlm_pages": vlm_pages,
                      "corpus": corpus_name, "page_cap": s.vlm_page_cap, "match_pages": s.match_pages,
                      "read_all": s.read_all_pages},
        "vlm": None, "ocr": None, "verification": None, "audit": [], "config": answer_config(),
    }

    # ---- VLM pipeline ----------------------------------------------------------------------------
    vlm_ms = 0.0
    if want_vlm:
        out: Dict[str, Any] = {"answer": None, "pages": [p + 1 for p in vlm_pages], "ms": 0.0, "error": None,
                               "batches": [], "combined": False}
        try:
            if hub.vlm is None:
                raise RuntimeError("VLM is disabled (ENABLE_VLM=false).")
            # One call per batch of at most VLM_PAGE_CAP pages (what fits in GPU memory), then combine the answers.
            groups = page_batches(vlm_pages, s.vlm_page_cap)
            partials: List[Tuple[str, str]] = []
            for g in groups:
                images = [pdfsvc.render_page(path, p, s.page_render_dpi) for p in g]
                aux = None
                if hub.demo:  # demo VLM cannot see pixels; give it text so the UI has something to show
                    aux = {p: (pdfsvc.text_layer(path, p) or ocrsvc.ocr_pages(doc, [p])[p]["text"]) for p in g}
                t1 = time.perf_counter()
                ans = hub.vlm.generate(images, g, question, history_vlm, short, aux_texts=aux,
                                       part=pages_label(g) if len(groups) > 1 else None)
                ms = (time.perf_counter() - t1) * 1000
                vlm_ms += ms
                out["batches"].append({"pages": [p + 1 for p in g], "answer": ans, "ms": round(ms, 1)})
                partials.append((pages_label(g), ans))
            t1 = time.perf_counter()
            out["answer"], out["combined"] = merge_parts(hub.vlm, question, partials, history_vlm, short)
            vlm_ms += (time.perf_counter() - t1) * 1000
            out["ms"] = round(vlm_ms, 1)
        except Exception as e:  # noqa: BLE001
            log.exception("VLM pipeline failed")
            out["error"] = f"{type(e).__name__}: {e}"
        result["vlm"] = out

    # ---- OCR + LLM pipeline ------------------------------------------------------------------------
    ocr_cost_ms = llm_ms = ocr_wall_ms = 0.0
    context = ""
    ocr_full_text: Optional[str] = None  # every OCR'd page, untruncated; None if OCR did not complete
    ocr_used: Dict[int, Dict[str, Any]] = {}  # OCR pages with their boxes, for locating the OCR answer's evidence
    if want_ocr:
        out = {"answer": None, "pages": [], "ms": 0.0, "ocr_ms": 0.0, "llm_ms": 0.0, "engine": ocrsvc.cache_key(),
               "context_chars": 0, "truncated": False, "error": None, "batches": [], "combined": False, "ocr_text": None}
        try:
            if hub.llm is None:
                raise RuntimeError("LLM is disabled (ENABLE_LLM=false).")
            want_pages = vlm_pages if s.match_pages else list(range(n))
            t1 = time.perf_counter()
            pages = ocrsvc.ocr_pages(doc, want_pages)
            ocr_wall_ms = (time.perf_counter() - t1) * 1000
            ocr_cost_ms = sum(float(v.get("ms") or 0.0) for v in pages.values())
            ocr_full_text = "\n".join(pages[p]["text"] for p in sorted(pages))
            ocr_used = pages
            if s.read_all_pages:   # every page's text, in as many parts as the context budget needs
                chunks = text_chunks(pages, s.max_context_chars)
                truncated = False
            else:                  # one call: best-ranked pages until the budget runs out
                ctx, used, truncated = build_context(pages, ranked, s.max_context_chars)
                chunks = [(ctx, used)]
            used_pages = sorted({p for _, ps in chunks for p in ps})
            context = "\n".join(c for c, _ in chunks)
            out.update(pages=[p + 1 for p in used_pages], truncated=truncated, context_chars=len(context),
                       ocr_text=context or ocr_full_text)
            partials = []
            for ctx, ps in chunks:
                t2 = time.perf_counter()
                ans = hub.llm.generate(ctx, question, history_ocr, short, part=pages_label(ps) if len(chunks) > 1 else None)
                ms = (time.perf_counter() - t2) * 1000
                llm_ms += ms
                out["batches"].append({"pages": [p + 1 for p in ps], "answer": ans, "ms": round(ms, 1)})
                partials.append((pages_label(ps), ans))
            t2 = time.perf_counter()
            out["answer"], out["combined"] = merge_parts(hub.llm, question, partials, history_ocr, short)
            llm_ms += (time.perf_counter() - t2) * 1000
            out.update(ocr_ms=round(ocr_cost_ms, 1), llm_ms=round(llm_ms, 1), ms=round(ocr_cost_ms + llm_ms, 1))
        except Exception as e:  # noqa: BLE001
            log.exception("OCR+LLM pipeline failed")
            out["error"] = f"{type(e).__name__}: {e}"
        result["ocr"] = out

    # ---- verification + audit --------------------------------------------------------------------
    v, o = result["vlm"], result["ocr"]
    if v and o and v.get("answer") is not None and o.get("answer") is not None:
        result["verification"] = verification.verify(v["answer"], o["answer"], ocr_text=context)
    if with_audit:
        ocr_text_by_page: Dict[int, str] = {}
        if want_ocr and not (o or {}).get("error"):
            cached = ocrsvc.ocr_pages(doc, vlm_pages)
            ocr_text_by_page = {p: cached[p]["text"] for p in cached}
        for p in vlm_pages:
            try:
                result["audit"].append(auditsvc.audit_page(path, p, ocr_text_by_page.get(p)))
            except Exception as e:  # noqa: BLE001
                log.warning("audit failed for page %s: %s", p, e)

    layers = _usable_text_layers(doc) if (v and o) else None
    reference = "\n".join(layers.values()) if layers else None
    sims = [a["ocr_vs_layer_similarity"] for a in result["audit"] if a.get("ocr_vs_layer_similarity") is not None]
    result["scorecard"] = verification.scorecard(v, o, reference, round(sum(sims) / len(sims), 4) if sims else None, n)
    xai_ms = 0.0
    if s.explain and v and o and v.get("answer") is not None and o.get("answer") is not None:
        t_x = time.perf_counter()
        result["xai"] = evidence.explain(doc, result, ocr_used, question, short, hub)
        xai_ms = (time.perf_counter() - t_x) * 1000

    total_ms = (time.perf_counter() - t_start) * 1000
    result["timings"] = {"retrieval_ms": round(retrieval_ms, 1), "vlm_ms": round(vlm_ms, 1), "ocr_ms": round(ocr_cost_ms, 1),
                         "ocr_wall_ms": round(ocr_wall_ms, 1), "llm_ms": round(llm_ms, 1), "xai_ms": round(xai_ms, 1),
                         "total_ms": round(total_ms, 1)}
    result["explanation"] = explain.explain(result, ocr_full_text, reference)
    if v and o and ocr_used:
        try:
            result["analysis"] = diagnosis.analyze(result, ocr_used, reference, lambda p: pdfsvc.region_kinds(path, p),
                                                   lambda p: evidence.page_px_size(path, p, s.ocr_render_dpi))
        except Exception as e:  # noqa: BLE001
            log.warning("diagnosis failed: %s", e)
    if v and o and v.get("answer") is not None and o.get("answer") is not None:
        try:
            result["combined_summary"] = synthesize_summary(
                question, v.get("answer"), o.get("answer"),
                result.get("verification"), result.get("analysis"),
                model=hub.llm if (not hub.demo and hub.llm) else None,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("synthesis failed: %s", e)
    monitoring.record({**result["timings"], "mode": mode, "doc": doc["id"], "pages": n})
    if return_context:
        result["_ocr_context"] = context
    return result
