"""Which method did better, why, and on which part of the page.

The two pipelines fail in different ways, so every wrong answer is given a cause from one vocabulary:
  misread      characters read wrong ("lyer" for "Iyer", "12oo0" for "12000")
  lost         the answer never reached the OCR text, so the text model could not see it
  wrong_value  a different value that is printed on the page was chosen (row, column or label mixed up)
  missed       said "not found" although the answer was available to it
  partial      only part of the answer
  near_miss    close to the right answer, but not exact
  format       the same value written differently (a scoring artefact, not a reading error)
  unsupported  not printed on the page at all
  failed       the pipeline raised an error
and every right answer one of: correct, repaired (OCR text was wrong but the text model fixed it), beyond_ocr
(vision got an answer that OCR never read).

Each cause is stated with its evidence (which characters, which line, what OCR's confidence was) and the mechanism
that produces it (why OCR, or a vision model, fails that way). The rules are deterministic and run on stored data:
in experiments the judge is the correct answer; for a single question it is the PDF's own text layer, or the closer
look's re-reading of the region when the file has no text layer.
"""
from __future__ import annotations

import difflib
import re
import statistics
import unicodedata
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .verification import _content_tokens, is_not_found, tokens

WHO = {"vlm": "the vision model", "ocr": "the OCR pipeline"}
LOW_CONF = 0.9          # about the lowest-scoring 10% of RapidOCR lines on DocVQA

# Character pairs that OCR engines are known to confuse (shape-alike glyphs).
_CONFUSABLE = {frozenset(p) for p in [
    ("I", "l"), ("l", "1"), ("I", "1"), ("i", "l"), ("O", "0"), ("o", "0"), ("D", "0"), ("Q", "O"), ("S", "5"),
    ("s", "5"), ("B", "8"), ("Z", "2"), ("z", "2"), ("G", "6"), ("g", "9"), ("q", "9"), ("rn", "m"), ("cl", "d"),
    ("vv", "w"), ("ii", "u"), (",", "."), ("e", "c"), ("h", "b"), ("n", "h"), ("u", "v"), ("t", "f"), ("i", "j"),
    ("A", "4"), ("T", "7"), ("E", "F"), ("C", "G"), ("U", "V"), ("a", "o"), ("ri", "n"), ("m", "nn"),
]}

_CONFUSABLE |= {frozenset((a.lower(), b.lower())) for a, b in (tuple(sorted(p)) for p in list(_CONFUSABLE) if len(p) == 2)}

CAUSE_LABEL = {
    "correct": "Right", "repaired": "Right: text model fixed OCR's error", "beyond_ocr": "Right: read what OCR missed",
    "misread": "Misread characters", "lost": "Answer never reached the OCR text", "wrong_value": "Picked another value on the page",
    "missed": "Said not found", "partial": "Only part of the answer", "near_miss": "Close, but not exact",
    "format": "Same value, written differently", "unsupported": "Not printed on the page", "failed": "Failed",
    "ambiguous": "Both values are on the page", "caution": "Caution", "spacing": "Words run together",
}
WRONG = ("misread", "spacing", "lost", "wrong_value", "missed", "partial", "near_miss", "format", "unsupported", "failed")


# ------------------------------------------------------------------------------------------------ text helpers
def _raw_words(s: Optional[str]) -> List[str]:
    """Words as written (case kept), outer punctuation removed: the forms quoted back to the reader."""
    s = unicodedata.normalize("NFKC", s or "")
    return [w for w in (t.strip(".,;:!?\"'()[]{}“”‘’") for t in s.split()) if w]


def _keys(s: Optional[str]) -> List[str]:
    return [t.lstrip("$") for t in dict.fromkeys(_content_tokens(s or ""))]


def _vocab(text: Optional[str]) -> set:
    return {t.lstrip("$") for t in tokens(text or "")}


def _orig(key: str, source: Optional[str]) -> str:
    """`key` (a lowercased match key) as `source` writes it."""
    for w in _raw_words(source):
        if tokens(w) and tokens(w)[0].lstrip("$") == key:
            return w.lstrip("$")
    return key


def near(key: str, vocab: Sequence[str], cutoff: float = 0.75) -> Optional[str]:
    """The closest word in `vocab` that is not `key` itself, if it is a likely misreading of it.
    With digits involved, only look-alike swaps count: "12oo0" misreads "12000", but "1993" is another year than "1994"."""
    if len(key) < 3:
        return None
    cands = [w for w in vocab if w != key and abs(len(w) - len(key)) <= 2]
    for m in cands:   # only look-alike characters differ: a misreading however low the plain similarity ("12oo0")
        pairs = swaps(key, m)
        if pairs and len(pairs) <= max(2, len(key) // 2) and all(frozenset(pr) in _CONFUSABLE for pr in pairs):
            return m
    for m in difflib.get_close_matches(key, cands, n=3, cutoff=cutoff):
        if not (re.search(r"\d", key) or re.search(r"\d", m)) or all(frozenset(pr) in _CONFUSABLE for pr in swaps(key, m)):
            return m
    return None


def near_in(key: str, *pools: Sequence[str]) -> Optional[str]:
    """`near`, trying the most specific pool first (the other answer, the answer's own line) before the whole page."""
    for pool in pools:
        m = near(key, list(pool))
        if m:
            return m
    return None


def swaps(true: str, read: str) -> List[Tuple[str, str]]:
    """The character edits that turn `true` into `read`, as (true, read) pairs; equal-length edits split per character."""
    if len(true) == len(read):   # OCR substitutes characters in place; align by position ("12000" / "12oo0")
        return [(a, b) for a, b in zip(true, read) if a != b]
    out: List[Tuple[str, str]] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, true, read, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        a, b = true[i1:i2], read[j1:j2]
        if len(a) == len(b) and len(a) > 1:
            out.extend((x, y) for x, y in zip(a, b) if x != y)
        else:
            out.append((a, b))
    return out


def confusable(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [(a, b) for a, b in pairs if frozenset((a, b)) in _CONFUSABLE]


def _q(s: str) -> str:
    return f"“{s}”"


def _swap_text(pairs: List[Tuple[str, str]]) -> str:
    shown = []
    for a, b in pairs[:3]:
        shown.append(f"{_q(a)} as {_q(b)}" if a and b else f"dropped {_q(a)}" if a else f"added {_q(b)}")
    return ", ".join(shown)


def _alnum(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", s or "").lower())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "").lower()).strip(" .,:;!?\"'")


# ------------------------------------------------------------------------------------------------ mechanisms
def misread_why(side: str, pairs: List[Tuple[str, str]]) -> str:
    conf = confusable(pairs)
    if side == "ocr":
        if conf:
            return (f"{_swap_text(conf)}: these characters have almost the same shape in many fonts, and OCR decides each "
                    "character from its shape alone, without knowing what word or number would make sense there. "
                    "The text model only receives OCR's text, so it repeats the error.")
        return ("OCR recognises text character by character from the pixels; small, faint or unusual print produces wrong "
                "characters, and the text model only receives OCR's text, so the error reaches the answer.")
    return ("The vision model sees each page at a limited resolution (a fixed budget of image patches), so small or faint "
            "characters can blur together; it then writes the most plausible reading"
            + (f", here {_swap_text(conf)}, a pair of look-alike characters." if conf else "."))


def lost_why(region: Optional[Dict[str, Any]], types: Sequence[str] = ()) -> str:
    t = {x.lower() for x in types}
    if "handwritten" in t:
        why = "The answer is handwritten. OCR models are trained mostly on printed text, and they drop or garble handwriting"
    elif "figure/diagram" in t:
        why = ("The answer is inside a chart or diagram. Text there is small, rotated or scattered, and its meaning comes from "
               "its position (axes, legends, arrows), which a list of text lines cannot carry")
    elif "image/photo" in t:
        why = "The answer is text inside a photo or logo, whose stylised lettering OCR does not recognise"
    elif region and region.get("kind") == "image":
        why = "The answer sits inside an embedded image, which OCR reads poorly or not at all"
    else:
        why = "The text was too small, faint or stylised for OCR to produce it"
    return why + ". The text model only sees OCR's output, so it had nothing to find. The vision model reads the pixels directly."


def wrong_value_why(side: str, layout: Optional[str], types: Sequence[str] = ()) -> str:
    t = {x.lower() for x in types}
    table = layout == "table" or "table/list" in t
    form = layout == "form" or "form" in t
    if side == "ocr":
        if table:
            return ("OCR writes a table out as lines of text, one row after another, so the text model no longer sees which "
                    "column header or row label a number sits under; it picked a value from a neighbouring cell or row.")
        if form:
            return ("On a form, a value's meaning comes from the box or label next to it. OCR's text keeps the words but "
                    "not where they sit, so the text model attached the question to a different field.")
        return ("OCR's text keeps the words but not the page layout (headings, columns, what is next to what), so the "
                "text model matched the question to another value printed on the page.")
    if table:
        return ("The vision model read the table but attached the question to the wrong row or column, a known weakness "
                "of vision-language models on dense tables.")
    return "The vision model read the page but chose a different value than the question asks for."


def missed_why(side: str, layout: Optional[str]) -> str:
    if side == "ocr":
        return ("The answer was in OCR's text, but the text model did not connect it to the question. Without the layout, "
                + ("a value in a table cell is separated from its header" if layout == "table"
                   else "a value is separated from the label that says what it is") + ", so it looked unrelated.")
    return ("The answer is on the page, but the vision model did not find it; this happens when the answer is small "
            "relative to the page or worded differently from the question.")


SPACING = ("OCR recognises a whole line at a time and predicts the spaces as characters; in tightly set, all-caps or "
           "spaced-out print it often leaves them out. The text model copies OCR's text, and the run-together words no "
           "longer match the question's words or the expected answer.")

MECH = {
    "partial": "It gives only part of the answer (for example one of several items, or a value without its unit or name).",
    "near_miss": "It is close to the right answer but not exact: extra or missing words or characters.",
    "format": "The value is right but written differently, so exact-match scoring counts it wrong. This is a formatting "
              "difference, not a reading error.",
    "repaired": "OCR misread or missed this, but the text model restored it from context. It helped here, but it also "
                "means the OCR pipeline can state values OCR never read.",
    "beyond_ocr": "The vision model read it from the pixels; OCR's text does not contain it.",
}


def unsupported_why(side: str, judge: str) -> str:
    return (f"Its words are not printed on the page ({judge}). Either the model reworded or reformatted what is printed "
            "(a date written out, a name corrected), or it worked something out that the page does not say (a count, a day "
            "of the week), or it answered from general knowledge. None of these is reading the page.")


# ------------------------------------------------------------------------------------------------ where on the page
def _page_dims(boxes: List[Dict[str, Any]]) -> Tuple[float, float]:
    return max([b["x1"] for b in boxes] + [1.0]), max([b["y1"] for b in boxes] + [1.0])


def layout_of(box: Dict[str, Any], boxes: List[Dict[str, Any]]) -> str:
    """'table' | 'form' | 'text': how many separate text boxes share this box's line (a heuristic from OCR geometry)."""
    hs = [max(b["y1"] - b["y0"], 1.0) for b in boxes] or [1.0]
    med = statistics.median(hs)
    cy = (box["y0"] + box["y1"]) / 2
    band = [b for b in boxes if abs((b["y0"] + b["y1"]) / 2 - cy) < 0.6 * med]
    # A table repeats that structure on nearby lines too.
    above = [b for b in boxes if 0.6 * med <= abs((b["y0"] + b["y1"]) / 2 - cy) < 3 * med]
    if len(band) >= 3 and len(above) >= 3:
        return "table"
    if len(band) >= 2:
        return "form"
    return "text"


def locate_in_ocr(answer: str, boxes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The OCR box that holds most of `answer`'s words, exactly, as a near misreading, or with the spaces between words
    lost ("SEPTEMBER17,1969"). None: OCR did not read it."""
    keys = _keys(answer) or [t.lstrip("$") for t in tokens(answer)]   # "no", "yes": short answers have no key words
    if not keys or not boxes:
        return None
    best: Tuple[float, float, Optional[Dict[str, Any]], List[Tuple[str, str]]] = (0.0, 0.0, None, [])
    for b in boxes:
        voc = list(_vocab(b.get("text")))
        hits, misreads = 0.0, []
        for k in keys:
            if k in voc:
                hits += 1
            else:
                m = near(k, voc)
                if m:
                    hits += 0.75
                    misreads.append((k, m))
        if hits and (hits, b.get("score") or 0) > (best[0], best[1]):
            best = (hits, b.get("score") or 0.0, b, misreads)
    merged = False
    if best[2] is None or best[0] / len(keys) < 0.5:
        flat = _alnum(answer)
        glued = [b for b in boxes if len(flat) >= 4 and flat in _alnum(b.get("text"))]
        if not glued:
            return None
        best, merged = (1.0, glued[0].get("score") or 0.0, glued[0], []), True
    b = best[2]
    hs = [max(x["y1"] - x["y0"], 1.0) for x in boxes]
    W, H = _page_dims(boxes)
    return {"text": b.get("text", ""), "conf": round(float(b.get("score") or 0.0), 3), "layout": layout_of(b, boxes),
            "small": (b["y1"] - b["y0"]) < 0.75 * statistics.median(hs), "misreads": best[3], "merged": merged,
            "box": [round(b["x0"] / W, 4), round(b["y0"] / H, 4), round(b["x1"] / W, 4), round(b["y1"] / H, 4)]}


def region_bucket(loc: Optional[Dict[str, Any]]) -> str:
    if not loc:
        return "not read by OCR"
    if loc["misreads"] or loc.get("merged"):
        return "read with errors by OCR"
    return "read clearly by OCR" if loc["conf"] >= LOW_CONF else "read with low confidence by OCR"


# ------------------------------------------------------------------------------------------------ experiments
def _right(sc: Dict[str, Any]) -> bool:
    return bool(sc) and sc.get("contains") == 1


def _closest_gold(pred: str, golds: Sequence[str]) -> str:
    return max(golds, key=lambda g: difflib.SequenceMatcher(None, _norm(pred), _norm(g)).ratio()) if golds else ""


def _nums(s: str) -> List[str]:
    return re.findall(r"\d+(?:[.,]\d+)*", s or "")


def diagnose_side(side: str, pred: Optional[str], scores: Dict[str, Any], golds: Sequence[str], ocr_text: str,
                  loc: Optional[Dict[str, Any]], types: Sequence[str] = (), in_ocr: bool = False) -> Dict[str, Any]:
    """Cause and explanation for one pipeline's answer to one question with known answers.
    `loc`: where OCR read the answer (None: not found in OCR's boxes); `in_ocr`: the answer is in OCR's text as written."""
    if not scores or pred is None or scores.get("error"):
        return {"cause": "failed", "text": "This pipeline failed on the question."}
    absent = loc is None and not in_ocr
    ocr_vocab = _vocab(ocr_text)
    gold = _closest_gold(pred, golds)
    layout = loc["layout"] if loc else None
    garbled = bool(loc and (loc["misreads"] or loc.get("merged"))) and not in_ocr   # OCR has it, but not as written

    if _right(scores):
        if side == "ocr" and (absent or garbled):
            return {"cause": "repaired", "text": MECH["repaired"]}
        if side == "vlm" and (absent or garbled):
            return {"cause": "beyond_ocr", "text": MECH["beyond_ocr"]}
        return {"cause": "correct", "text": ""}

    def ocr_misread() -> Dict[str, Any]:
        if loc.get("merged"):
            return {"cause": "spacing", "text": f"OCR's text has the answer with the spaces between words dropped ({_q(loc['text'][:60])}). "
                    + SPACING}
        k, m = loc["misreads"][0]
        return {"cause": "misread", "text": f"OCR read {_q(_orig(k, gold))} as {_q(m)}. " + misread_why("ocr", swaps(_orig(k, gold), m))}

    if scores.get("abstain"):
        if side == "ocr" and absent:
            return {"cause": "lost", "text": lost_why(loc, types)}
        if side == "ocr" and garbled:
            r = ocr_misread()
            r["text"] += " Written that way, the text model could not match it to the question and said it was not there."
            return r
        return {"cause": "missed", "text": missed_why(side, layout)}

    pa, ga = _alnum(pred), _alnum(gold)
    # Same characters, different spaces or punctuation: glued words are an OCR reading error; the rest is formatting.
    if pa and any(_alnum(g) == pa for g in golds) or (ga and ga in pa and len(pa) - len(ga) <= 12 and len(pred.split()) < len(gold.split())):
        if side == "ocr" and len(pred.split()) < len(gold.split()):
            return {"cause": "spacing", "text": f"It wrote {_q(pred.strip()[:60])} for {_q(gold)}: the words run together. " + SPACING}
        return {"cause": "format", "text": MECH["format"]}
    pk, gk = set(_keys(pred)), set(_keys(gold))
    if pk and gk and pk < gk:
        return {"cause": "partial", "text": MECH["partial"]}
    if side == "ocr" and absent:
        return {"cause": "lost", "text": lost_why(loc, types)}
    if side == "ocr" and garbled:
        return ocr_misread()
    pairs = swaps(_norm(gold).replace(" ", ""), _norm(pred).replace(" ", ""))
    other_number = bool(_nums(pred)) and bool(_nums(gold)) and set(_nums(pred)) != set(_nums(gold))
    if pairs and all(frozenset(pr) in _CONFUSABLE for pr in pairs):
        return {"cause": "misread", "text": f"It wrote {_q(pred.strip())} for {_q(gold)}. " + misread_why(side, pairs)}
    if (scores.get("anls") or 0) > 0 and not other_number:
        if side == "vlm" and sum(len(a) + len(b) for a, b in pairs) <= 3:
            return {"cause": "misread", "text": f"It wrote {_q(pred.strip())} for {_q(gold)}. " + misread_why("vlm", pairs)}
        return {"cause": "near_miss", "text": f"It wrote {_q(pred.strip()[:60])} for {_q(gold)}. " + MECH["near_miss"]}
    if pk and all(k in ocr_vocab for k in pk):
        return {"cause": "wrong_value", "text": f"{_q(pred.strip()[:60])} is printed on the page, but it is not the answer. "
                + wrong_value_why(side, layout, types)}
    return {"cause": "unsupported", "text": unsupported_why(side, "not in OCR's reading of the page either")}


def diagnose_item(item: Dict[str, Any], ocr_page: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Who did better on one experiment question, why, and where on the page the answer is."""
    golds = item.get("gold") or []
    boxes = (ocr_page or {}).get("boxes") or []
    text = (ocr_page or {}).get("text") or ""
    loc = None
    for g in golds:
        loc = locate_in_ocr(g, boxes)
        if loc and not loc["misreads"]:
            break
    types = (item.get("extra") or {}).get("types") or []
    in_ocr = bool(item.get("answer_in_ocr"))
    out: Dict[str, Any] = {"region": None if loc is None else {k: loc[k] for k in ("conf", "layout", "small", "text")},
                           "bucket": region_bucket(loc) if (loc or not in_ocr) else "read clearly by OCR"}
    for side in ("vlm", "ocr"):
        if item.get(f"{side}_scores"):
            out[side] = diagnose_side(side, item.get(f"{side}_pred"), item[f"{side}_scores"], golds, text, loc, types, in_ocr)
    v, o = _right(item.get("vlm_scores") or {}), _right(item.get("ocr_scores") or {})
    out["better"] = "both" if v and o else "vlm" if v else "ocr" if o else "neither"
    return out


def _main(c: Counter) -> Optional[Tuple[str, int]]:
    return c.most_common(1)[0] if c else None


def diagnose_run(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """items carry `extra.diagnosis` (from diagnose_item). Totals by cause, by kind of question and by how well OCR read
    the answer's region, plus a written explanation of why one method did better."""
    rows = [{**it, "diagnosis": (it.get("extra") or {}).get("diagnosis")} for it in items]
    rows = [it for it in rows if it["diagnosis"] and it["diagnosis"].get("vlm") and it["diagnosis"].get("ocr")]
    if not rows:
        return None
    outcomes = Counter(it["diagnosis"]["better"] for it in rows)
    causes = {s: Counter(it["diagnosis"][s]["cause"] for it in rows) for s in ("vlm", "ocr")}
    # Why the winner won: the losing side's causes on the questions only the winner got right.
    lost_to = {s: Counter(it["diagnosis"]["ocr" if s == "vlm" else "vlm"]["cause"] for it in rows if it["diagnosis"]["better"] == s)
               for s in ("vlm", "ocr")}

    def group(key) -> Dict[str, Dict[str, Any]]:
        g: Dict[str, List[Dict[str, Any]]] = {}
        for it in rows:
            for k in key(it):
                g.setdefault(k, []).append(it)
        out = {}
        for k, its in sorted(g.items(), key=lambda kv: -len(kv[1])):
            vr = sum(_right(i["vlm_scores"]) for i in its) / len(its)
            orr = sum(_right(i["ocr_scores"]) for i in its) / len(its)
            oc = Counter(i["diagnosis"]["ocr"]["cause"] for i in its if i["diagnosis"]["ocr"]["cause"] in WRONG)
            vc = Counter(i["diagnosis"]["vlm"]["cause"] for i in its if i["diagnosis"]["vlm"]["cause"] in WRONG)
            out[k] = {"n": len(its), "vlm_right": round(vr, 4), "ocr_right": round(orr, 4),
                      "better": "vlm" if vr - orr >= 0.05 else "ocr" if orr - vr >= 0.05 else "same",
                      "ocr_main_cause": (_main(oc) or (None,))[0], "vlm_main_cause": (_main(vc) or (None,))[0]}
        return out

    by_type = group(lambda it: (it.get("extra") or {}).get("types") or [])
    by_region = group(lambda it: [it["diagnosis"]["bucket"]])
    by_layout = group(lambda it: [{"table": "table row", "form": "label and value", "text": "running text"}[it["diagnosis"]["region"]["layout"]]]
                      if it["diagnosis"].get("region") else [it["diagnosis"]["bucket"] if it["diagnosis"]["bucket"] == "not read by OCR"
                                                             else "in OCR's text, place not found"])
    d = {"n": len(rows), "outcomes": dict(outcomes), "causes": {s: dict(c) for s, c in causes.items()},
         "lost_to": {s: dict(c) for s, c in lost_to.items()}, "by_type": by_type, "by_region": by_region, "by_layout": by_layout}
    d["explanation"] = explain_run(d)
    return d


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:]


def _pc(k: int, n: int) -> str:
    return f"{round(100 * k / n)}%" if n else "0%"


def _cause_list(c: Dict[str, int], total: int) -> str:
    parts = [f"{_lc(CAUSE_LABEL[k])} ({v})" for k, v in sorted(c.items(), key=lambda kv: -kv[1]) if v and k in WRONG]
    return "; ".join(parts) if parts else "none"


RUN_MECH = {
    ("ocr", "lost"): "the answer never reached the OCR text (handwriting, text in figures, photos and logos, small or faint print), "
                     "so the text model had nothing to find",
    ("ocr", "wrong_value"): "the answer was in OCR's text, but the text model picked another value printed on the page: OCR "
                            "flattens tables and forms into lines, so which label or column a value belongs to is lost",
    ("ocr", "missed"): "the answer was in OCR's text, but the text model said it was not there: separated from its label or "
                       "column header, the value did not look related to the question",
    ("ocr", "misread"): "OCR misread characters of the answer (look-alike characters such as I/l, 0/O), and the text model "
                        "repeated the error",
    ("ocr", "spacing"): "OCR ran the words together (\u201cSEPTEMBER17,1969\u201d), and the text model copied them that way",
    ("ocr", "format"): "the value was right but written differently from the expected answer (a scoring artefact)",
    ("ocr", "near_miss"): "the answer was close but not exact (extra or missing words)",
    ("ocr", "unsupported"): "the text model gave something not printed on the page: a reworded value, or a count or "
                            "inference the page does not state",
    ("vlm", "wrong_value"): "the vision model read the page but picked a value from the wrong row, column or field",
    ("vlm", "unsupported"): "the vision model gave something not printed on the page: a reworded value, or a count or "
                            "inference the page does not state",
    ("vlm", "format"): "the value was right but written differently from the expected answer (a scoring artefact)",
    ("vlm", "partial"): "the vision model gave only part of the answer",
    ("ocr", "partial"): "the text model gave only part of the answer",
    ("vlm", "near_miss"): "the vision model was close but not exact (extra or missing words)",
    ("vlm", "misread"): "the vision model misread characters, usually in small print, at its limited image resolution",
    ("vlm", "missed"): "the vision model did not find an answer that is on the page",
}


def explain_run(d: Dict[str, Any]) -> List[Dict[str, str]]:
    n, oc = d["n"], d["outcomes"]
    v_only, o_only, both, neither = oc.get("vlm", 0), oc.get("ocr", 0), oc.get("both", 0), oc.get("neither", 0)
    out: List[Dict[str, str]] = []
    if v_only == o_only:
        head = "Neither method did better overall"
    else:
        head = f"{'The vision model' if v_only > o_only else 'The OCR pipeline'} did better"
    out.append({"title": head, "text":
                f"On {n} questions, both methods were right on {both} and both wrong on {neither}. The vision model alone was "
                f"right on {v_only}, the OCR pipeline alone on {o_only}. Those {v_only + o_only} questions are the whole "
                "difference between the two, so the reasons below come from them."})
    for w in ("vlm", "ocr"):
        c = d["lost_to"][w]
        k = sum(c.values())
        if not k:
            continue
        loser = "ocr" if w == "vlm" else "vlm"
        top = [x for x in sorted(c.items(), key=lambda kv: -kv[1]) if x[0] in WRONG][:3]
        reasons = []
        for cause, cnt in top:
            mech = RUN_MECH.get((loser, cause))
            reasons.append(f"{cnt} ({_pc(cnt, k)}) because {mech}" if mech else f"{cnt} {_lc(CAUSE_LABEL[cause])}")
        out.append({"title": f"Why {WHO[w]} won {k} {'question' if k == 1 else 'questions'}",
                    "text": f"On these, {WHO[loser]} failed: " + "; ".join(reasons) + "."})
    reg = d["by_region"]
    if len(reg) > 1:
        bits = []
        for name in ("read clearly by OCR", "read with low confidence by OCR", "read with errors by OCR", "not read by OCR"):
            r = reg.get(name)
            if r:
                bits.append(f"where the answer was {name} ({r['n']} questions), vision was right on {round(100 * r['vlm_right'])}% "
                            f"and OCR on {round(100 * r['ocr_right'])}%")
        clear = reg.get("read clearly by OCR")
        tail = ""
        if clear and clear["vlm_right"] - clear["ocr_right"] >= 0.05:
            tail = (" Even where OCR read the answer perfectly, the OCR pipeline still trails: there the gap comes from the text "
                    "model choosing among values without the layout, not from reading.")
        out.append({"title": "Which parts of the page each method handled better",
                    "text": "Split by how OCR read the place on the page where the answer is: " + "; ".join(bits) + "." + tail})
    types = [(k, r) for k, r in d["by_type"].items() if r["n"] >= 5]
    if types:
        lead = sorted(types, key=lambda kr: kr[1]["ocr_right"] - kr[1]["vlm_right"])
        lines = []
        for k, r in lead[:3]:
            gap = round(100 * (r["vlm_right"] - r["ocr_right"]))
            if gap >= 5:
                cause = r["ocr_main_cause"]
                lines.append(f"{k} (vision +{gap} points; OCR's main failure there: {_lc(CAUSE_LABEL[cause]) if cause else 'none'})")
        o_lead = [(k, r) for k, r in types if r["ocr_right"] - r["vlm_right"] >= 0.05]
        text = ("The vision model's largest leads are on " + ", ".join(lines) + "." if lines else "No question type shows a clear vision lead.")
        if o_lead:
            text += " OCR leads on " + ", ".join(f"{k} (+{round(100 * (r['ocr_right'] - r['vlm_right']))} points)" for k, r in o_lead) + "."
        out.append({"title": "Which kinds of content each method handled better", "text": text +
                    " Types with fewer than 5 questions are left out."})
    vc = {k: v for k, v in d["causes"]["vlm"].items() if k in WRONG}
    occ = {k: v for k, v in d["causes"]["ocr"].items() if k in WRONG}
    out.append({"title": "How each method fails", "text":
                f"Vision's wrong answers: {_cause_list(vc, n)}. OCR pipeline's wrong answers: {_cause_list(occ, n)}. "
                f"The text model also repaired {d['causes']['ocr'].get('repaired', 0)} answers OCR had misread, and the vision "
                f"model got {d['causes']['vlm'].get('beyond_ocr', 0)} answers right that OCR's text did not contain as written."})
    out.append({"title": "How these causes were assigned", "text":
                "By fixed rules from each question's answers, the correct answers and OCR's text and boxes (is the answer in "
                "OCR's text, misspelt in it, or absent; is the wrong answer printed elsewhere on the page). They show the most "
                "likely mechanism, not a proof; each question's row shows the evidence."})
    return out


# ------------------------------------------------------------------------------------------------ one question
def _support(ans: Optional[str], vocab: set) -> Optional[float]:
    keys = _keys(ans)
    if not keys or not ans or is_not_found(ans):
        return None
    return sum(k in vocab for k in keys) / len(keys)


def _ocr_regions(ocr_pages: Dict[int, Dict[str, Any]], keys: List[str],
                 size: Optional[Callable[[int], Tuple[float, float]]] = None) -> List[Dict[str, Any]]:
    """OCR lines holding (or misreading) the given keys, as fractions of the page (`size(page)`: the page in OCR pixels)."""
    out = []
    for p, pg in ocr_pages.items():
        boxes = pg.get("boxes") or []
        if not boxes:
            continue
        W, H = size(p) if size else _page_dims(boxes)
        for b in boxes:
            voc = list(_vocab(b.get("text")))
            hit = [k for k in keys if k in voc or near(k, voc)]
            if hit:
                out.append({"page": p, "keys": hit, "exact": sum(k in voc for k in hit), "text": b.get("text", ""), "conf": round(float(b.get("score") or 0.0), 3),
                            "layout": layout_of(b, boxes),
                            "box": [round(b["x0"] / W, 4), round(b["y0"] / H, 4), round(b["x1"] / W, 4), round(b["y1"] / H, 4)]})
    out.sort(key=lambda r: (-len(r["keys"]), -r["exact"], -r["conf"]))
    return out


def _status(key: str, answer: Optional[str]) -> Dict[str, Optional[str]]:
    """How an answer renders `key`: 'right', 'misread' (as what), or 'absent'."""
    if not answer or is_not_found(answer):
        return {"status": "absent", "as": None}
    voc = list(_vocab(answer))
    if key in voc:
        return {"status": "right", "as": _orig(key, answer)}
    m = near(key, voc)
    return {"status": "misread", "as": _orig(m, answer)} if m else {"status": "absent", "as": None}


def analyze(result: Dict[str, Any], ocr_pages: Dict[int, Dict[str, Any]], reference: Optional[str],
            kinds: Optional[Callable[[int], List[Dict[str, Any]]]] = None,
            page_size: Optional[Callable[[int], Tuple[float, float]]] = None) -> Optional[Dict[str, Any]]:
    """Which method did better on this question, why (cause + mechanism), and which part of the page each read right.

    `reference` is the PDF's own text (None for scans and images). `kinds(page)` returns that page's table/image rectangles
    (normalised), used to say what kind of region the answer is in.
    """
    v, o = result.get("vlm") or {}, result.get("ocr") or {}
    if not (result.get("vlm") and result.get("ocr")):
        return None
    va, oa = v.get("answer"), o.get("answer")
    x = result.get("xai") or {}
    lc = x.get("look_closer") or None
    if reference:
        judge_text, basis = reference, "textlayer"
    elif lc and lc.get("transcription"):
        judge_text, basis = lc["transcription"], "closer_look"
    else:
        judge_text, basis = None, None
    judge_vocab = _vocab(judge_text) if judge_text else set()
    ocr_text = "\n".join(pg.get("text") or "" for _, pg in sorted(ocr_pages.items()))
    ocr_vocab = _vocab(ocr_text)
    judge_name = {"textlayer": "the text embedded in the PDF", "closer_look": "an enlarged re-reading of the region"}.get(basis or "", "")

    # --- regions: the lines that hold the answer's words, with what each method made of them
    kv = _keys(va) if va and not is_not_found(va) else []
    ko = _keys(oa) if oa and not is_not_found(oa) else []
    # The answer's core: the shorter answer's words (a full-sentence answer adds context words that are not in dispute).
    core = (kv if len(kv) <= len(ko) else ko) if (kv and ko) else (kv or ko)
    if kv and ko and not set(kv) & set(ko) and not any(near(k, ko) for k in kv):
        core = kv + ko         # two different values: each has its own place on the page
    truth = []
    for k in core:   # as the page prints it: "lyer" in an answer is checked as the "Iyer" the page has
        if judge_text and k not in judge_vocab:
            k = near_in(k, kv + ko, judge_vocab) or k
        truth.append(k)
    truth = list(dict.fromkeys(truth))
    regions = []
    covered: set = set()
    for r in _ocr_regions(ocr_pages, truth, page_size):
        keys = [k for k in r["keys"] if k not in covered]   # each word in its best line only
        if not keys or len(regions) == 3:
            continue
        covered.update(keys)
        cells = []
        for k in keys:
            ocr_line = list(_vocab(r["text"]))
            ocr_read = {"status": "right", "as": _orig(k, r["text"])} if k in ocr_line else {"status": "misread", "as": near(k, ocr_line)}
            cells.append({"word": _orig(k, judge_text or va or oa), "in_page": (k in judge_vocab) if judge_text else None,
                          "vision": _status(k, va), "ocr_text": ocr_read, "ocr_answer": _status(k, oa)})
        kind = r["layout"]
        for rect in (kinds(r["page"]) if kinds else []):
            cx, cy = (r["box"][0] + r["box"][2]) / 2, (r["box"][1] + r["box"][3]) / 2
            if rect["box"][0] <= cx <= rect["box"][2] and rect["box"][1] <= cy <= rect["box"][3]:
                kind = rect["kind"]
        right = lambda c, s: c[s]["status"] == "right" and c["in_page"] is not False  # noqa: E731
        vr = all(right(c, "vision") for c in cells) if judge_text else None
        orr = all(right(c, "ocr_answer") for c in cells) if judge_text else None
        regions.append({"page": r["page"], "box": r["box"], "kind": kind, "ocr_line": r["text"], "conf": r["conf"], "words": cells,
                        "better": None if vr is None else "both" if vr and orr else "vlm" if vr else "ocr" if orr else "neither"})

    # --- who did better
    sides = {}
    for s, p in (("vlm", v), ("ocr", o)):
        sides[s] = {"error": bool(p.get("error")), "nf": p.get("answer") is not None and is_not_found(p["answer"]),
                    "support": _support(p.get("answer"), judge_vocab) if judge_text else None}
    ver = (result.get("verification") or {}).get("verdict")
    better, why_basis = "undecided", None
    if sides["vlm"]["error"] != sides["ocr"]["error"]:
        better = "ocr" if sides["vlm"]["error"] else "vlm"
    elif judge_text:
        a, b = sides["vlm"]["support"], sides["ocr"]["support"]
        if a is None and b is None:
            better = "same" if sides["vlm"]["nf"] and sides["ocr"]["nf"] else "undecided"
        elif b is None or (a is not None and a - b >= 0.1):
            better = "vlm" if (a or 0) >= 0.5 else "undecided"
        elif a is None or b - a >= 0.1:
            better = "ocr" if (b or 0) >= 0.5 else "undecided"
        elif ver == "consistent":
            better = "same"
        else:
            only = {k: [pr for pr in (result.get("verification") or {}).get("pairs") or [] if pr.get("label") == f"only_{k}"] for k in ("vlm", "ocr")}
            better = "ocr" if only["ocr"] and not only["vlm"] else "vlm" if only["vlm"] and not only["ocr"] else "undecided"
        why_basis = basis
    elif ver == "consistent":
        better = "same"

    # --- why: one cause per side, with the evidence and the mechanism
    why: List[Dict[str, str]] = []

    def add(who: str, cause: str, text: str) -> None:
        why.append({"who": who, "cause": cause, "label": CAUSE_LABEL.get(cause, cause), "text": text})

    for s, ans, other in (("vlm", va, oa), ("ocr", oa, va)):
        p = v if s == "vlm" else o
        if p.get("error"):
            add(s, "failed", f"{WHO[s][0].upper() + WHO[s][1:]} failed: {p['error']}")
            continue
        if ans is None:
            continue
        if is_not_found(ans):
            other_ok = other and not is_not_found(other) and (not judge_text or (_support(other, judge_vocab) or 0) >= 0.5)
            if other_ok:
                ok = _keys(other)
                gone = [k for k in ok if k not in ocr_vocab]
                garbled = [(k, near(k, list(ocr_vocab))) for k in gone]
                garbled = [(k, m) for k, m in garbled if m]
                if s == "ocr" and gone and garbled:
                    k, m = garbled[0]
                    add(s, "misread", f"OCR's text has {_q(m)} where the page has {_q(_orig(k, other))}, so the text model could not "
                        "match it to the question and said it was not there. " + misread_why("ocr", swaps(_orig(k, other), m)))
                elif s == "ocr" and ok and len(gone) == len(ok):
                    add(s, "lost", f"{_q(other.strip())} is not in OCR's text. " + lost_why(regions[0] if regions else None))
                else:
                    add(s, "missed", missed_why(s, regions[0]["kind"] if regions else None))
            continue
        keys = _keys(ans)
        if judge_text:
            bad = [k for k in keys if k not in judge_vocab]
            other_side = "ocr" if s == "vlm" else "vlm"
            if not bad:
                miss_ocr = [k for k in keys if k not in ocr_vocab]
                if s == "ocr" and miss_ocr:
                    add(s, "repaired", MECH["repaired"])
                elif s == "vlm" and miss_ocr:
                    add(s, "beyond_ocr", f"{_q(_orig(miss_ocr[0], ans))} is printed in {judge_name}, but OCR's text does not have it; "
                        "the vision model read it from the page image.")
                elif better == other_side:
                    add(s, "partial", "Everything in this answer is printed in the document, but the other answer covers more of "
                        "what the question asks. " + MECH["partial"])
                elif better in (s, "same"):
                    add(s, "correct", f"Every key word and number in this answer is printed in {judge_name}.")
                continue
            k = bad[0]
            line_vocab = [w for r in regions for w in _vocab(r["ocr_line"])]
            m = near_in(k, [w for w in _keys(other) if w in judge_vocab], line_vocab, judge_vocab)
            if m:
                pairs = swaps(_orig(m, judge_text), _orig(k, ans))
                src = ""
                if s == "ocr":
                    src = (" OCR's own text has it the same way, so the error came from OCR, not from the text model."
                           if k in ocr_vocab else "")
                add(s, "misread", f"It has {_q(_orig(k, ans))} where the document has {_q(_orig(m, judge_text))}.{src} "
                    + misread_why(s, pairs))
            else:
                add(s, "unsupported", f"{_q(_orig(k, ans))} is not in {judge_name}. " + unsupported_why(s, f"not in {judge_name}"))
        else:
            # No neutral reference: say what differs and what it looks like, without picking a side.
            ok = _keys(other) if other and not is_not_found(other) else []
            for k in keys:
                if k in ok:
                    continue
                m = near(k, ok)
                if m:
                    pairs = confusable(swaps(_orig(m, other), _orig(k, ans)))
                    if pairs and s == "ocr" and m not in ocr_vocab:
                        add(s, "misread", f"It has {_q(_orig(k, ans))} where the vision model has {_q(_orig(m, other))}; they differ only in "
                            f"look-alike characters ({_swap_text(pairs)}), the typical signature of an OCR misreading. "
                            + misread_why("ocr", pairs) + " Without embedded text this is likely, not proven: check the page.")
                    break
                if s == "vlm" and k not in ocr_vocab:
                    add(s, "beyond_ocr", f"{_q(_orig(k, ans))} is not in OCR's text. Either OCR missed it, so only the vision model "
                        "could read it, or the vision model is wrong; with no embedded text, only reading the page settles it.")
                    break

    if (judge_text and better == "undecided" and ver != "consistent" and all(
            sides[k]["support"] == 1.0 for k in ("vlm", "ocr"))):
        add("both", "ambiguous", "Both answers are printed in the document, so neither misread anything: they disagree on which "
            "printed value answers the question. " + wrong_value_why("ocr", regions[0]["kind"] if regions else None)
            + " Read the question against the page to choose.")
    causes = {w["who"]: w["cause"] for w in why}
    for w in why:
        if w["who"] == better == "vlm" and w["cause"] in ("correct", "beyond_ocr") and causes.get("ocr") in ("misread", "lost", "missed", "wrong_value"):
            w["text"] += (" The vision model reads the page image itself, not OCR's text, so " +
                          ("OCR's misreading" if causes["ocr"] == "misread" else "what OCR lost" if causes["ocr"] == "lost"
                           else "the flattened layout of OCR's text") + " could not affect it.")
        if w["who"] == better == "ocr" and w["cause"] == "correct" and causes.get("vlm") == "misread":
            w["text"] += " OCR read these characters correctly here, and the text model copied them from OCR's text."

    # A recommended answer that survived having its evidence removed was not grounded where it says.
    f = (x.get("faithfulness") or {}).get(better) if better in ("vlm", "ocr") else None
    if f and f.get("survived"):
        add(better, "caution", "With the highlighted evidence removed, this answer stays the same, so the highlight may not be "
            "what it relied on (it may come from elsewhere on the page, or from the question).")

    if better in ("vlm", "ocr"):
        loser = "ocr" if better == "vlm" else "vlm"
        why.sort(key=lambda w: (w["who"] != loser, w["cause"] in ("correct",)))
    head = {"vlm": "The vision model did better", "ocr": "The OCR pipeline did better", "same": "Both did equally well",
            "undecided": "Cannot tell which did better"}[better]
    if better == "undecided" and not judge_text:
        sub = ("This file has no embedded text and the answers were not settled by a closer look, so there is nothing neutral to "
               "judge them against. The causes below say how they differ.")
    elif better == "undecided":
        sub = f"Checked against {judge_name}, neither answer is clearly better supported."
    elif better == "same":
        sub = (f"Both answers are supported by {judge_name}." if judge_text else
               "The two answers agree. Two independent ways of reading reaching the same answer is good evidence, but not proof.")
    else:
        sub = f"Judged against {judge_name}." if judge_text else "One method failed."
    if better in ("vlm", "ocr") and judge_text:
        sub = ""   # the basis is shown next to the headline; the causes say the rest
    # One sentence for the verdict: the cause that decided it, not a restated score.
    reason = None
    lose = next((w for w in why if better in ("vlm", "ocr") and w["who"] != better and w["cause"] in WRONG), None)
    if lose:
        first = re.split(r"(?<=[.!?])\s+", lose["text"])[0]
        reason = f"{WHO[lose['who']][0].upper()}{WHO[lose['who']][1:]}: {_lc(CAUSE_LABEL[lose['cause']])}. {first}"
    return {"better": better, "basis": why_basis or basis, "headline": head, "summary": sub, "reason": reason, "why": why,
            "regions": regions}
