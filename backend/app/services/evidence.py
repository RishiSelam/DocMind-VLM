"""Explainability: where each answer came from, whether it really depended on that place, and how far to trust it.

For short factual answers (a summary has no single place on the page):
  1. Evidence. OCR side: the OCR line boxes that hold the answer's words. Vision side: the region the vision model
     says it read (Qwen2.5-VL grounding). Reference: where the PDF's own text layer prints the answer's words.
  2. Evidence agreement: did the two readers look at the same place?
  3. Look closer: when the answers differ, the evidence region is cropped and enlarged, the vision model transcribes it,
     and the transcription is compared with both answers.
  4. Faithfulness: the evidence is removed (masked in the image, deleted from the OCR text) and the question asked
     again. If the answer survives, the highlighted evidence was not what the answer depended on.
  5. Trust: a transparent score from these signals, with its reasons. It is a heuristic; experiments measure whether
     it predicts wrong answers.
Boxes are {"page": 0-based, "box": [x0, y0, x1, y1]} with coordinates as fractions of the page (0..1).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import fitz
from PIL import Image, ImageDraw

from ..config import get_settings
from . import pdf as pdfsvc
from .verification import _content_tokens, is_not_found, tokens

log = logging.getLogger("docmind.evidence")
MAX_SHORT = 200            # longer answers (summaries, lists) are not pinned to one place


def is_short(answer: Optional[str]) -> bool:
    return bool(answer) and not is_not_found(answer) and len(answer) <= MAX_SHORT and answer.count("\n") <= 1


def _keys(answer: Optional[str]) -> List[str]:
    return [t.lstrip("$") for t in dict.fromkeys(_content_tokens(answer or ""))]


def cover(answer: Optional[str], text: str) -> Optional[float]:
    """Share of the answer's key words and numbers found verbatim in `text` (None: nothing to check)."""
    keys = _keys(answer)
    if not keys:
        return None
    vocab = {t.lstrip("$") for t in tokens(text)}
    return round(sum(k in vocab for k in keys) / len(keys), 3)


def page_px_size(path: str, page: int, dpi: int) -> Tuple[float, float]:
    if pdfsvc.is_image_path(path):
        with Image.open(path) as im:
            return float(im.width), float(im.height)
    with fitz.open(path) as d:
        r = d[page].rect
        return r.width * dpi / 72, r.height * dpi / 72


def _norm(b: Dict[str, Any], w: float, h: float) -> List[float]:
    return [round(max(0.0, min(1.0, v)), 4) for v in (b["x0"] / w, b["y0"] / h, b["x1"] / w, b["y1"] / h)]


def ocr_evidence(path: str, ocr_pages: Dict[int, Dict[str, Any]], answer: Optional[str], limit: int = 3) -> List[Dict[str, Any]]:
    """OCR line boxes holding the most of the answer's key words, best first, all on the best page."""
    keys = set(_keys(answer))
    if not keys:
        return []
    dpi = get_settings().ocr_render_dpi
    scored = []
    for p, pg in ocr_pages.items():
        for b in pg.get("boxes") or []:
            hits = len(keys & {t.lstrip("$") for t in tokens(b.get("text", ""))})
            if hits:
                scored.append((hits, b.get("score") or 0.0, p, b))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], -x[1]))
    best_page = scored[0][2]
    w, h = page_px_size(path, best_page, dpi)
    return [{"page": p, "box": _norm(b, w, h), "text": b["text"], "score": round(float(sc), 3)}
            for hits, sc, p, b in scored if p == best_page][:limit]


def reference_evidence(path: str, answer: Optional[str], limit: int = 4) -> List[Dict[str, Any]]:
    """Where the PDF's own text layer prints the answer's words (the neutral reference). Empty for scans and images."""
    keys = [k for k in _keys(answer) if len(k) >= 2]
    if not keys or pdfsvc.is_image_path(path):
        return []
    best: Tuple[int, int, List[fitz.Rect]] = (0, -1, [])
    with fitz.open(path) as d:
        for i, pg in enumerate(d):
            rects = [r for k in keys for r in pg.search_for(k)]
            found = len({k for k in keys if pg.search_for(k)})
            if found > best[0]:
                best = (found, i, rects)
        if best[1] < 0:
            return []
        W, H = d[best[1]].rect.width, d[best[1]].rect.height
    return [{"page": best[1], "box": [round(r.x0 / W, 4), round(r.y0 / H, 4), round(r.x1 / W, 4), round(r.y1 / H, 4)]} for r in best[2][:limit]]


def iou(a: List[float], b: List[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _center_in(a: List[float], b: List[float], pad: float = 0.02) -> bool:
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    return b[0] - pad <= cx <= b[2] + pad and b[1] - pad <= cy <= b[3] + pad


def same_place(a: Optional[Dict[str, Any]], bs: List[Dict[str, Any]]) -> Optional[str]:
    """'same place' | 'same page' | 'different pages' | None (nothing to compare)."""
    if not a or not bs:
        return None
    on_page = [b for b in bs if b["page"] == a["page"]]
    if not on_page:
        return "different pages"
    if any(iou(a["box"], b["box"]) >= 0.2 or _center_in(b["box"], a["box"]) or _center_in(a["box"], b["box"]) for b in on_page):
        return "same place"
    return "same page"


def region(box: List[float], pad: float = 0.02, min_w: float = 0.25, min_h: float = 0.05) -> List[float]:
    """The evidence box with a margin, at least min_w x min_h of the page, kept inside the page."""
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    if x1 - x0 < min_w:
        c = (x0 + x1) / 2; x0, x1 = c - min_w / 2, c + min_w / 2
    if y1 - y0 < min_h:
        c = (y0 + y1) / 2; y0, y1 = c - min_h / 2, c + min_h / 2
    dx, dy = max(0.0, -x0) - max(0.0, x1 - 1), max(0.0, -y0) - max(0.0, y1 - 1)
    return [round(max(0.0, x0 + dx), 4), round(max(0.0, y0 + dy), 4), round(min(1.0, x1 + dx), 4), round(min(1.0, y1 + dy), 4)]


def crop(path: str, page: int, box: List[float], dpi: int = 300, min_width: int = 900) -> Image.Image:
    img = pdfsvc.render_page(path, page, dpi)
    W, H = img.size
    c = img.crop((int(box[0] * W), int(box[1] * H), int(box[2] * W), int(box[3] * H)))
    if c.width < min_width:   # enlarge small regions: that is the point of looking closer
        c = c.resize((min_width, max(1, round(c.height * min_width / c.width))), Image.LANCZOS)
    return c


def mask(img: Image.Image, box: List[float], pad: float = 0.01) -> Image.Image:
    out = img.copy()
    W, H = out.size
    ImageDraw.Draw(out).rectangle(((box[0] - pad) * W, (box[1] - pad) * H, (box[2] + pad) * W, (box[3] + pad) * H), fill="white")
    return out


def arbitrate(va: Optional[str], oa: Optional[str], text: str) -> Dict[str, Any]:
    """Compare only the disputed words (in one answer, not the other) with a close re-reading of the region.
    A side loses when one of its disputed words is not actually there."""
    kv, ko = set(_keys(va)), set(_keys(oa))
    seen = {t.lstrip("$") for t in tokens(text)}
    mv, mo = sorted((kv - ko) - seen), sorted((ko - kv) - seen)
    pick = "vlm" if (mo and not mv) else "ocr" if (mv and not mo) else None
    return {"supports": pick, "vision_not_seen": mv, "ocr_not_seen": mo,
            "vision_confirmed": sorted((kv - ko) & seen), "ocr_confirmed": sorted((ko - kv) & seen)}


def survives(original: Optional[str], new: Optional[str]) -> bool:
    """Did the same answer come back? (Most of the original's key words, and not 'not found'.)"""
    if not new or is_not_found(new):
        return False
    c = cover(original, new)
    return c is not None and c >= 0.8


# ------------------------------------------------------------------------------------------------ orchestration
def explain(doc: Dict[str, Any], result: Dict[str, Any], ocr_pages: Dict[int, Dict[str, Any]], question: str,
            short: bool, hub: Any) -> Dict[str, Any]:
    s = get_settings()
    t0 = time.perf_counter()
    path = doc["path"]
    v, o = result.get("vlm") or {}, result.get("ocr") or {}
    va, oa = v.get("answer"), o.get("answer")
    x: Dict[str, Any] = {"vision": None, "ocr": [], "reference": [], "agreement": None, "vision_at_reference": None,
                         "ocr_at_reference": None, "look_closer": None, "faithfulness": {}, "skipped": None}
    if not (is_short(va) or is_short(oa)):
        x["skipped"] = "Long answers such as summaries are not tied to one place on the page, so they are not located."
        x["trust"] = {"score": None, "level": "not rated", "recommended": None,
                      "reasons": ["Summaries and other long answers are not given a trust score; compare them with the claim table."]}
        return x

    # 1. evidence
    if is_short(oa) and not o.get("error"):
        x["ocr"] = ocr_evidence(path, ocr_pages, oa)
    x["reference"] = reference_evidence(path, va if is_short(va) else oa)
    if is_short(va) and not v.get("error") and hub.vlm is not None and hasattr(hub.vlm, "locate"):
        found = [b for b in v.get("batches") or [] if not is_not_found(b.get("answer"))]
        pages = [p - 1 for p in (found[0]["pages"] if found else v.get("pages") or [])][: s.vlm_page_cap]
        try:
            imgs = [pdfsvc.render_page(path, p, s.page_render_dpi) for p in pages]
            found_at = hub.vlm.locate(imgs, pages, question, va)
            # With several page images in one call the model picks the right page but its box drifts (seen on a 6-page
            # batch: right page, wrong line). So the multi-page call only chooses the page; the box comes from that page alone.
            if found_at and len(pages) > 1:
                p = found_at["page"]
                found_at = hub.vlm.locate([imgs[pages.index(p)]], [p], question, va) or found_at
            if found_at:
                found_at.pop("raw", None)
            x["vision"] = found_at
        except Exception as e:  # noqa: BLE001
            log.warning("vision grounding failed: %s", e)

    # 2. agreement between the readers, and with where the PDF prints the answer
    x["agreement"] = same_place(x["vision"], x["ocr"])
    x["vision_at_reference"] = same_place(x["vision"], x["reference"])
    x["ocr_at_reference"] = same_place(x["ocr"][0] if x["ocr"] else None, x["reference"])

    # 3. look closer when the answers differ
    verdict = (result.get("verification") or {}).get("verdict")
    target = x["vision"] or (x["ocr"][0] if x["ocr"] else None)
    if s.look_closer and verdict and verdict != "consistent" and target and hub.vlm is not None and hasattr(hub.vlm, "transcribe"):
        try:
            box = region(target["box"])
            text = hub.vlm.transcribe(crop(path, target["page"], box))
            x["look_closer"] = {"page": target["page"], "box": box, "transcription": text[:400], **arbitrate(va, oa, text)}
        except Exception as e:  # noqa: BLE001
            log.warning("look closer failed: %s", e)

    # 4. faithfulness: remove the evidence and ask again
    if s.faithfulness:
        if x["vision"] and hub.vlm is not None:
            try:
                p = x["vision"]["page"]
                img = mask(pdfsvc.render_page(path, p, s.page_render_dpi), x["vision"]["box"])
                again = hub.vlm.generate([img], [p], question, [], short, part=f"page {p + 1}")
                x["faithfulness"]["vlm"] = {"answer_without_evidence": again, "survived": survives(va, again)}
            except Exception as e:  # noqa: BLE001
                log.warning("vision faithfulness test failed: %s", e)
        if x["ocr"] and hub.llm is not None:
            try:
                p = x["ocr"][0]["page"]
                txt = ocr_pages[p]["text"]
                for b in x["ocr"]:
                    txt = txt.replace(b["text"], "")
                ctx = f"--- Page {p + 1} ---\n{txt}\n"
                again = hub.llm.generate(ctx, question, [], short, part=f"page {p + 1}")
                x["faithfulness"]["ocr"] = {"answer_without_evidence": again, "survived": survives(oa, again)}
            except Exception as e:  # noqa: BLE001
                log.warning("OCR faithfulness test failed: %s", e)

    x["trust"] = trust(result, x)
    x["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return x


def trust(result: Dict[str, Any], x: Dict[str, Any]) -> Dict[str, Any]:
    """How far to trust the recommended answer: a transparent sum of signals, each listed as a reason."""
    ver = (result.get("verification") or {}).get("verdict")
    card = result.get("scorecard") or {}
    lc = x.get("look_closer") or {}
    rec = card.get("winner") if card.get("winner") in ("vlm", "ocr") else None
    if not rec and lc.get("supports"):
        rec = lc["supports"]
    if not rec and ver == "consistent":
        rec = "vlm"
    if not rec:
        return {"score": None, "level": "unknown", "recommended": None,
                "reasons": ["The two answers differ and nothing settles which is right: read the page."]}

    score, reasons = 0.35, []
    def add(delta: float, why: str) -> None:
        nonlocal score
        score += delta
        reasons.append(("+" if delta >= 0 else "−") + f" {why}")

    if ver == "consistent":
        add(0.35, "both methods gave the same answer")
    elif ver == "partial":
        add(0.1, "the answers partly agree")
    elif ver:
        add(-0.25, "the two answers differ")
    side = (card.get(rec) or {})
    if card.get("reference") and side.get("support") is not None:
        add(round(0.25 * side["support"] - 0.1, 3), f"{round(side['support'] * 100)}% of the answer is printed in the document")
    if x.get("agreement") == "same place":
        add(0.15, "both methods found it in the same place")
    elif x.get("agreement") == "different pages":
        add(-0.1, "the methods pointed to different pages")
    if lc.get("supports"):
        add(0.15 if lc["supports"] == rec else -0.25, "a closer look at the region " + ("confirms it" if lc["supports"] == rec else "favours the other answer"))
    f = (x.get("faithfulness") or {}).get(rec)
    if f is not None:
        add(0.1 if not f["survived"] else -0.05, "removing the evidence " + ("changes the answer, so it relied on it" if not f["survived"] else "does not change the answer"))
    score = round(max(0.0, min(1.0, score)), 3)
    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return {"score": score, "level": level, "recommended": rec, "reasons": reasons}
