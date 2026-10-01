"""Plain-language interpretation of one ask: what the numbers in the scorecard mean for the reader.

Every sentence is derived from measured values in the result. Nothing here judges correctness; the only neutral
reference is the PDF's embedded text, and without it the findings say so.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .verification import _content_tokens, is_not_found, tokens

WHO = {"vlm": "the vision model", "ocr": "the OCR pipeline"}


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]   # str.capitalize() would lowercase "OCR"


def _s(ms: Optional[float]) -> str:
    return "n/a" if ms is None else f"{ms / 1000:.1f} s"


def _p(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def _quote(words: List[str], source: Optional[str] = None) -> str:
    """Quote matched tokens; with `source`, as written there ("Iyer", not the lowercased match key "iyer")."""
    def orig(w: str) -> str:
        m = re.search(re.escape(w), source or "", flags=re.I)
        return m.group(0) if m else w
    return ", ".join(f"“{orig(w)}”" for w in words[:4])


def _answer_tokens(answer: Optional[str]) -> List[str]:
    if not answer or is_not_found(answer):
        return []
    return list(dict.fromkeys(_content_tokens(answer)))


def _verdict(card: Dict[str, Any], ver: Optional[Dict[str, Any]]) -> Dict[str, str]:
    sv, so, w = card["vlm"], card["ocr"], card["winner"]
    verdict = (ver or {}).get("verdict")
    if w in ("vlm", "ocr"):
        loser = "ocr" if w == "vlm" else "vlm"
        a, b, ls = card[w]["support"], card[loser]["support"], card[loser]
        other = ("failed" if ls["error"] else "said the answer is not in the document" if not ls["answered"] else None)
        return {"title": f"{_cap(WHO[w])} gave the better-supported answer",
                "text": f"{_p(a)} of the key words and numbers in {WHO[w]}'s answer are printed in the document"
                        + (f", while {WHO[loser]} {other}." if other else f", against {_p(b)} for {WHO[loser]}.")
                        + f" Prefer {WHO[w]}'s answer, and open the page to confirm it."}
    if w == "tie" and sv["support"] is None and so["support"] is None:
        if not sv["answered"] and not so["answered"] and not sv["error"] and not so["error"]:
            return {"title": "Both methods say the answer is not in the document",
                    "text": "Neither method found an answer. Either the document does not contain it, or the question needs "
                            "rewording to match how the document puts it."}
        return {"title": "Neither answer could be checked", "text": card["reason"]}
    if w == "tie" and (sv["support"] is None or so["support"] is None):
        return {"title": "Only one method answered, and the document barely supports it", "text":
                f"{'The vision model' if sv['support'] is not None else 'The OCR pipeline'}'s answer has only "
                f"{_p(sv['support'] if sv['support'] is not None else so['support'])} of its key words and numbers in the "
                "document, and the other method gave no answer. Treat it with caution and check the page."}
    only = {k: [pr[k] for pr in (ver or {}).get("pairs") or [] if pr.get("label") == f"only_{k}"] for k in ("vlm", "ocr")}
    if w == "tie" and (only["vlm"]) != (only["ocr"]) and (only["vlm"] or only["ocr"]):
        more, less = ("ocr", "vlm") if only["ocr"] else ("vlm", "ocr")
        return {"title": f"{_cap(WHO[more])} gave the more complete answer",
                "text": f"Everything both answers say is printed in the document, but {WHO[less]}'s answer leaves out: "
                        f"“{only[more][0]}”. Prefer {WHO[more]}'s answer, and check that page."}
    if w == "tie":
        if sv["support"] == 1.0 and so["support"] == 1.0 and verdict == "consistent":
            return {"title": "Both methods agree, and the document backs them",
                    "text": "The two answers match, and every key word and number in them is printed in the document. "
                            "Either answer can be trusted to the same degree."}
        return {"title": "Neither method is clearly better here",
                "text": f"The document supports the two answers about equally ({_p(sv['support'])} for vision, "
                        f"{_p(so['support'])} for OCR). {'They agree with each other.' if verdict == 'consistent' else 'Compare the claim table and check the page.'}"}
    if w == "unknown":
        if verdict == "consistent":
            return {"title": "Both methods agree, but the answer cannot be checked",
                    "text": "This file is an image or a scan, so there is no embedded text to check against. Two different "
                            "methods reaching the same answer is good evidence, but not proof."}
        return {"title": "The methods disagree, and there is nothing neutral to settle it",
                "text": "This file is an image or a scan, so neither answer can be checked automatically. Open the page "
                        "and read the value yourself; the claim table shows exactly where the answers differ."}
    return {"title": "Only one method ran", "text": "There is nothing to compare."}


def explain(result: Dict[str, Any], ocr_text: Optional[str], reference: Optional[str]) -> List[Dict[str, str]]:
    """`ocr_text` is the full OCR text of the pages read, or None when OCR failed (then nothing is compared with it)."""
    card = result.get("scorecard") or {}
    v, o = result.get("vlm"), result.get("ocr")
    if not (card.get("vlm") and card.get("ocr") and v and o):
        return []
    ver = result.get("verification")
    out = [{"kind": "verdict", **_verdict(card, ver)}]

    # Recognition: which method read the characters that matter correctly.
    vlm_saw: List[str] = []
    ocr_fixed: List[str] = []
    ocr_invented: List[str] = []
    if ocr_text is not None and not o.get("error"):
        ocr_vocab = {t.lstrip("$") for t in tokens(ocr_text)}
        ref_vocab = {t.lstrip("$") for t in tokens(reference)} if reference else set()
        not_in_ocr = lambda ans: [t for t in _answer_tokens(ans) if t.lstrip("$") not in ocr_vocab]  # noqa: E731
        vlm_saw = [t for t in not_in_ocr(v.get("answer")) if not reference or t.lstrip("$") in ref_vocab]
        if reference:
            ocr_fixed = [t for t in not_in_ocr(o.get("answer")) if t.lstrip("$") in ref_vocab]
            ocr_invented = [t for t in not_in_ocr(o.get("answer")) if t.lstrip("$") not in ref_vocab]
    acc = card.get("ocr_read_accuracy")
    missed = sum(a.get("layer_tokens_missed_by_ocr") or 0 for a in result.get("audit") or [])
    checked = len([a for a in result.get("audit") or [] if a.get("ocr_vs_layer_similarity") is not None])
    parts: List[str] = []
    if acc is not None:
        grade = ("excellent" if acc >= 0.98 else "good, with a few misread words" if acc >= 0.9
                 else "fair: expect misread words" if acc >= 0.75 else "poor: the vision model is likely more reliable on these pages")
        parts.append(f"OCR's text was {acc * 100:.1f}% similar to the document's own text, word by word, on the "
                     f"{_n(checked, 'page')} checked; about {_n(missed, 'word')} of the document's text {'was' if missed == 1 else 'were'} missed or misread. "
                     f"That is {grade}.")
    if vlm_saw and reference:
        parts.append(f"The vision model read {_quote(vlm_saw, v.get('answer'))}, which the OCR text does not contain but the document does. "
                     "Here the vision model recognised something OCR missed.")
    elif vlm_saw:
        parts.append(f"The vision model's answer contains {_quote(vlm_saw, v.get('answer'))}, which the OCR text does not. Either OCR missed it "
                     "or the vision model is wrong; with no embedded text, only reading the page settles it.")
    if ocr_fixed:
        parts.append(f"The OCR text does not contain {_quote(ocr_fixed, o.get('answer'))} (OCR misread or missed it), yet the OCR pipeline's answer does. "
                     "The text model repaired the OCR error from context. That helped here, but it also means the OCR pipeline "
                     "can state values OCR never read.")
    if ocr_invented:
        parts.append(f"The OCR pipeline's answer contains {_quote(ocr_invented, o.get('answer'))}, which appears neither in the OCR text nor in the "
                     "document. Treat that part as unsupported.")
    if parts:
        out.append({"kind": "recognition", "title": "Which method read the document better", "text": " ".join(parts)})

    # Speed, with where the OCR pipeline's time goes.
    t = result.get("timings") or {}
    sv, so = card["vlm"], card["ocr"]
    if sv["ms"] and so["ms"]:
        fast, slow = ("vlm", "ocr") if sv["ms"] < so["ms"] else ("ocr", "vlm")
        diff = abs(sv["ms"] - so["ms"])
        text = (f"The vision model took {_s(sv['ms'])} and the OCR pipeline {_s(so['ms'])} "
                f"({_s(t.get('ocr_ms'))} reading pages with OCR, {_s(t.get('llm_ms'))} for the text model). "
                + (f"{_cap(WHO[fast])} was {_s(diff)} faster." if diff >= max(300.0, 0.15 * max(sv["ms"], so["ms"]))
                   else "The two took about the same time."))
        reused = bool(t.get("ocr_ms")) and t.get("ocr_wall_ms") is not None and t["ocr_wall_ms"] < 0.5 * t["ocr_ms"]
        ranked_by_ocr = (result.get("retrieval") or {}).get("corpus") == "ocr" and (t.get("retrieval_ms") or 0) >= 0.5 * (t.get("ocr_ms") or 0)
        if reused and ranked_by_ocr:
            # Scans: OCR runs first, inside page ranking, and the OCR pipeline then finds it done.
            text += (f" This file has no embedded text, so OCR ran at the start of this request to rank the pages "
                     f"({_s(t.get('retrieval_ms'))}), and the OCR pipeline reused that work.")
            if sv["pages_read"] < card["n_pages"]:
                text += " The vision model also waited for it, because that ranking chose which pages it saw."
        elif reused:
            text += (f" OCR results were reused from the cache this time (it actually took {_s(t['ocr_wall_ms'])}); the OCR "
                     "time shown is the one-time cost of reading these pages.")
        elif t.get("ocr_ms"):
            text += " OCR is cached per document, so follow-up questions on this file mostly cost the text model's time."
        out.append({"kind": "speed", "title": "Speed", "text": text})

    # Page coverage: the vision model only sees what retrieval hands it.
    n, pv, po = card["n_pages"], sv["pages_read"], so["pages_read"]
    if n > 1:
        if pv < n:
            text = (f"The vision model saw {pv} of {n} pages ({', '.join(str(p) for p in v.get('pages') or [])}), picked by keyword "
                    f"ranking; the OCR pipeline read {po}. If the answer is on a page the vision model did not see, it cannot "
                    "find it. Raise VLM_PAGE_CAP to show it more pages, at the cost of GPU memory and time.")
        else:
            text = f"Both methods covered the whole document ({n} pages), so neither had an information advantage."
            parts = []
            for who, p in (("vision model", v), ("OCR pipeline", o)):
                k = len(p.get("batches") or [])
                if k > 1:
                    parts.append(f"the {who} in {k} parts")
            if parts:
                combined = [who for who, p in (("vision model", v), ("OCR pipeline", o)) if p.get("combined")]
                text += (f" Long documents are read in parts that fit the GPU and the text model's context: {' and '.join(parts)}. "
                         "Each part was asked the question; "
                         + (f"the {' and the '.join(combined)} combined the answers of the parts that found something."
                            if combined else "only one part found an answer, so it was used as is."))
        out.append({"kind": "pages", "title": "Pages each method saw", "text": text})
    return out
