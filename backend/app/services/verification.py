"""Cross-modal verification: compare the VLM answer with the OCR+LLM answer at claim level,
and audit which parts of the VLM answer the OCR text never contained.

All logic is lexical and deterministic. It is a screening tool: it flags where the two readings differ,
it does not decide which one is right.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from .prompts import NOT_FOUND
from .retrieval import STOP

_NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)          # 1,234 -> 1234
    s = re.sub(r"[^\w\s.%$/-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> List[str]:
    return [t.strip(".-/") for t in norm_text(s).split() if t.strip(".-/")]


def numbers(s: str) -> Set[str]:
    out = set()
    for m in _NUM.findall(norm_text(s)):
        n = m.replace("$", "").rstrip(".")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def is_not_found(s: str) -> bool:
    return norm_text(NOT_FOUND).rstrip(".") in norm_text(s)


def split_claims(answer: str) -> List[str]:
    parts = re.split(r"(?:(?<=[.!?])\s+|\n+)", answer or "")
    claims = [re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", p).strip() for p in parts]
    return [c for c in claims if c]


def token_f1(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    common = sum((Counter(a) & Counter(b)).values())
    if common == 0:
        return 0.0
    p, r = common / len(a), common / len(b)
    return 2 * p * r / (p + r)


def compare_claims(a: str, b: str) -> Tuple[str, float]:
    """Return (label, score): agree | partial | conflict | none."""
    ta, tb = tokens(a), tokens(b)
    f1 = token_f1(ta, tb)
    na, nb = numbers(a), numbers(b)
    words_a = [t for t in ta if t not in na and not _NUM.fullmatch(t)]
    words_b = [t for t in tb if t not in nb and not _NUM.fullmatch(t)]
    ctx = token_f1(words_a, words_b)
    if (na or nb) and na != nb and (ctx >= 0.3 or (not words_a and not words_b)):
        return "conflict", round(f1, 3)
    contained = bool(ta and tb) and (set(ta) <= set(tb) or set(tb) <= set(ta))
    if norm_text(a) == norm_text(b) or contained or f1 >= 0.8:
        return "agree", round(max(f1, 0.8 if contained else f1), 3)
    if f1 >= 0.4:
        return "partial", round(f1, 3)
    return "none", round(f1, 3)


def _content_tokens(answer: str) -> List[str]:
    return [t for t in tokens(answer) if t not in STOP and (len(t) >= 4 or _NUM.fullmatch(t))]


def ocr_support(answer: str, ocr_text: str) -> Dict[str, Any]:
    """Which content tokens of `answer` appear in `ocr_text`? found / near (likely OCR misspelling) / missing."""
    vocab = set(tokens(ocr_text))
    found, near, missing = [], [], []
    for t in dict.fromkeys(_content_tokens(answer)):
        if t in vocab:
            found.append(t)
            continue
        cands = [w for w in vocab if abs(len(w) - len(t)) <= 2][:5000]
        m = difflib.get_close_matches(t, cands, n=1, cutoff=0.8)
        if m:
            near.append({"token": t, "ocr_token": m[0]})
        else:
            missing.append(t)
    total = len(found) + len(near) + len(missing)
    return {
        "found": found, "near": near, "missing": missing,
        "coverage": round((len(found) + len(near)) / total, 3) if total else None,
        "note": ("Tokens in 'missing' were not present in the OCR text. That is either information OCR never "
                 "captured (charts, stamps, handwriting, layout cues) or a VLM error; a reference answer is "
                 "needed to tell which."),
    }


def reference_support(answer: Optional[str], reference: str) -> Optional[float]:
    """Share of the answer's content tokens found verbatim in `reference`. None when there is nothing to score.
    Strict on purpose: against a clean reference, a near match ('12oo0' for '12000') is a misreading, not support."""
    if answer is None or is_not_found(answer):
        return None
    toks = list(dict.fromkeys(_content_tokens(answer)))
    if not toks:
        return None
    vocab = {t.lstrip("$") for t in tokens(reference)}       # "$1284.50" in the answer, "1284.50 USD" on the page
    return round(sum(t.lstrip("$") in vocab for t in toks) / len(toks), 3)


def missing_from_reference(answer: Optional[str], reference: str) -> List[str]:
    """The answer's content tokens that are not printed in `reference` (same matching as reference_support)."""
    if answer is None or is_not_found(answer):
        return []
    vocab = {t.lstrip("$") for t in tokens(reference)}
    return [t for t in dict.fromkeys(_content_tokens(answer)) if t.lstrip("$") not in vocab]


def scorecard(vlm: Optional[Dict[str, Any]], ocr: Optional[Dict[str, Any]], reference: Optional[str],
              ocr_read_accuracy: Optional[float], n_pages: int, margin: float = 0.1) -> Dict[str, Any]:
    """Side-by-side numbers for the two pipelines on one question, plus a cautious verdict.

    The judge is the PDF's embedded text layer, which neither pipeline produced. Without one (scans, image files)
    there is no neutral reference: the OCR text cannot judge the OCR pipeline's own answer, so the verdict is 'unknown'.
    This checks that an answer is grounded in the document, not that it answers the question correctly.
    """
    def side(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not p:
            return None
        ok = p.get("answer") is not None and not p.get("error")
        answered = ok and not is_not_found(p["answer"])
        return {"answered": answered, "error": bool(p.get("error")), "ms": p.get("ms"), "pages_read": len(p.get("pages") or []),
                "support": reference_support(p["answer"], reference) if (answered and reference) else None,
                "missing": missing_from_reference(p["answer"], reference) if (answered and reference) else []}

    sv, so = side(vlm), side(ocr)
    faster = None
    if sv and so and not sv["error"] and not so["error"] and sv["ms"] and so["ms"]:
        faster = "vlm" if sv["ms"] < so["ms"] else "ocr"
    card: Dict[str, Any] = {"reference": "textlayer" if reference else None, "n_pages": n_pages, "vlm": sv, "ocr": so,
                            "ocr_read_accuracy": ocr_read_accuracy, "faster": faster}
    if not (sv and so):
        return {**card, "winner": None, "reason": "Only one pipeline ran, so there is nothing to compare."}
    if not reference:
        return {**card, "winner": "unknown", "reason": "This file has no embedded text to check the answers against (a scan or an "
                "image), so neither answer can be scored. Use how much the two answers agree as the signal."}
    a, b = sv["support"], so["support"]
    if a is None and b is None:
        return {**card, "winner": "tie", "reason": "Neither pipeline gave an answer that could be checked."}
    if (b is None and a is not None and a >= 0.5) or (a is not None and b is not None and a - b >= margin):
        return {**card, "winner": "vlm", "reason": "The vision model's answer is better supported by the document's own text."}
    if (a is None and b is not None and b >= 0.5) or (a is not None and b is not None and b - a >= margin):
        return {**card, "winner": "ocr", "reason": "The OCR pipeline's answer is better supported by the document's own text."}
    if a is None or b is None:
        return {**card, "winner": "tie", "reason": "Only one pipeline answered, and the document's text barely supports that answer."}
    return {**card, "winner": "tie", "reason": "Both answers are equally supported by the document's own text."}


def verify(vlm_answer: str, ocr_answer: str, ocr_text: Optional[str] = None) -> Dict[str, Any]:
    nf_v, nf_o = is_not_found(vlm_answer), is_not_found(ocr_answer)
    if nf_v and nf_o:
        return {"verdict": "consistent", "agreement": 1.0, "pairs": [], "note": "Both pipelines report the answer is not in the document.",
                "numbers_only_vlm": [], "numbers_only_ocr": [], "ocr_support": None}
    if nf_v != nf_o:
        who = "the OCR+LLM pipeline" if nf_v else "the VLM"
        return {"verdict": "conflict", "agreement": 0.0,
                "pairs": [{"vlm": vlm_answer, "ocr": ocr_answer, "label": "conflict", "score": 0.0}],
                "note": f"Only {who} found an answer.", "numbers_only_vlm": sorted(numbers(vlm_answer)),
                "numbers_only_ocr": sorted(numbers(ocr_answer)),
                "ocr_support": ocr_support(vlm_answer, ocr_text) if (ocr_text is not None and not nf_v) else None}

    ca, cb = split_claims(vlm_answer), split_claims(ocr_answer)
    used_b: Set[int] = set()
    pairs: List[Dict[str, Any]] = []
    rank = {"agree": 3, "partial": 2, "conflict": 1, "none": 0}
    for a in ca:
        best: Tuple[int, str, float, int] = (-1, "none", 0.0, -1)
        for j, b in enumerate(cb):
            label, sc = compare_claims(a, b)
            key = (rank[label], sc)
            if key > (best[0], best[2]):
                best = (rank[label], label, sc, j)
        if best[3] >= 0 and best[1] != "none":
            used_b.add(best[3])
            pairs.append({"vlm": a, "ocr": cb[best[3]], "label": best[1], "score": best[2]})
        else:
            pairs.append({"vlm": a, "ocr": None, "label": "only_vlm", "score": 0.0})
    for j, b in enumerate(cb):
        if j not in used_b:
            pairs.append({"vlm": None, "ocr": b, "label": "only_ocr", "score": 0.0})

    w = {"agree": 1.0, "partial": 0.5}
    agreement = sum(w.get(p["label"], 0.0) for p in pairs) / len(pairs) if pairs else 0.0
    labels = {p["label"] for p in pairs}
    if labels == {"agree"}:
        verdict = "consistent"
    elif "conflict" in labels:
        verdict = "conflict"
    elif agreement >= 0.5:
        verdict = "partial"
    else:
        verdict = "disagree"
    nv, no = numbers(vlm_answer), numbers(ocr_answer)
    return {
        "verdict": verdict, "agreement": round(agreement, 3), "pairs": pairs,
        "numbers_only_vlm": sorted(nv - no), "numbers_only_ocr": sorted(no - nv),
        "ocr_support": ocr_support(vlm_answer, ocr_text) if ocr_text is not None else None,
        "note": "",
    }
