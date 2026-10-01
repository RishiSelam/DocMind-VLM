"""Page-level OCR information-loss audit.

For PDFs with an embedded text layer, the text layer is a free reference: OCR-vs-layer similarity measures how much
OCR lost or corrupted. Structural features (images, vector drawings, tables) show how much of the page is
non-text content that OCR cannot express as text.
"""
from __future__ import annotations

import difflib
from typing import Any, Dict, Optional

from . import pdf as pdfsvc
from .verification import tokens


def audit_page(path: str, page: int, ocr_text: Optional[str]) -> Dict[str, Any]:
    feats = pdfsvc.page_features(path, page)
    layer = pdfsvc.text_layer(path, page)
    ocr_toks = tokens(ocr_text or "")
    out: Dict[str, Any] = {"page": page, **feats, "ocr_chars": len(ocr_text or ""), "ocr_tokens": len(ocr_toks)}
    if layer and ocr_text is not None:
        lt = tokens(layer)
        # autojunk off: page text is short enough and the default heuristic distorts repetitive text
        sm = difflib.SequenceMatcher(None, lt, ocr_toks, autojunk=False)
        out["ocr_vs_layer_similarity"] = round(sm.ratio(), 4)
        out["layer_tokens_missed_by_ocr"] = max(len(lt) - sum(b.size for b in sm.get_matching_blocks()), 0)
    else:
        out["ocr_vs_layer_similarity"] = None
        out["layer_tokens_missed_by_ocr"] = None
    flags = []
    if feats.get("image_area_ratio", 0) >= 0.3 and not feats.get("is_image_file"):
        flags.append("large image regions: OCR sees only text inside them")
    if feats.get("n_drawings", 0) >= 50:
        flags.append("many vector graphics: charts or diagrams likely lose meaning as text")
    if feats.get("n_tables", 0) > 0:
        flags.append("tables detected: check OCR text preserved the columns")
    if ocr_text is not None and len(ocr_toks) < 5:
        flags.append("almost no OCR text on this page")
    out["flags"] = flags
    return out
