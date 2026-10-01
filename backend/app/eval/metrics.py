"""DocVQA-style metrics: EM, ANLS (Biten et al., 2019; threshold 0.5), contains-match, plus paired statistics."""
from __future__ import annotations

import math
import random
import re
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

from ..services.prompts import NOT_FOUND


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def normalize(s: str) -> str:
    return _clean(s).strip(" .,:;!?\"'")


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def anls(pred: str, golds: Sequence[str], threshold: float = 0.5) -> float:
    p = _clean(pred)
    if not golds:
        return 0.0
    best = 0.0
    for g in golds:
        g = _clean(g)
        denom = max(len(p), len(g))
        nl = 0.0 if denom == 0 else levenshtein(p, g) / denom
        best = max(best, 1.0 - nl if nl < threshold else 0.0)
    return best


def exact_match(pred: str, golds: Sequence[str]) -> float:
    p = normalize(pred)
    return float(any(p == normalize(g) for g in golds))


def contains_match(pred: str, golds: Sequence[str]) -> float:
    p = normalize(pred)
    return float(any(normalize(g) and normalize(g) in p for g in golds))


def is_abstain(pred: str) -> bool:
    return normalize(NOT_FOUND) in normalize(pred or "")


def score_item(pred: str | None, golds: Sequence[str]) -> Dict[str, float]:
    if pred is None:
        return {"em": 0.0, "anls": 0.0, "contains": 0.0, "abstain": 0.0, "error": 1.0}
    if is_abstain(pred):
        return {"em": 0.0, "anls": 0.0, "contains": 0.0, "abstain": 1.0, "error": 0.0}
    return {"em": exact_match(pred, golds), "anls": anls(pred, golds), "contains": contains_match(pred, golds),
            "abstain": 0.0, "error": 0.0}


def answer_in_text(golds: Sequence[str], text: str) -> bool:
    """Upper bound for OCR+LLM: does any gold answer appear in the OCR text at all (whitespace/case-insensitive)?"""
    t = re.sub(r"[\s|]+", " ", (text or "").lower())
    return any(normalize(g) and re.sub(r"[\s|]+", " ", normalize(g)) in t for g in golds)


def mean(xs: Sequence[float]) -> float:
    return float(statistics.fmean(xs)) if xs else 0.0


def percentile(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    v = sorted(xs)
    return float(v[min(len(v) - 1, int(round(q * (len(v) - 1))))])


def paired_bootstrap(a: Sequence[float], b: Sequence[float], n: int = 1000, seed: int = 0) -> Dict[str, float]:
    """Mean(a - b) with a 95% percentile bootstrap CI over items."""
    assert len(a) == len(b)
    if not a:
        return {"diff": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = random.Random(seed)
    d = [x - y for x, y in zip(a, b)]
    m = len(d)
    boots = sorted(mean([d[rng.randrange(m)] for _ in range(m)]) for _ in range(n))
    return {"diff": mean(d), "ci_low": boots[int(0.025 * n)], "ci_high": boots[min(int(0.975 * n), n - 1)]}


def mcnemar(a_correct: Sequence[bool], b_correct: Sequence[bool]) -> Dict[str, float]:
    """Exact two-sided McNemar test on discordant pairs. b01 = A right & B wrong, b10 = A wrong & B right."""
    b01 = sum(1 for x, y in zip(a_correct, b_correct) if x and not y)
    b10 = sum(1 for x, y in zip(a_correct, b_correct) if y and not x)
    n = b01 + b10
    if n == 0:
        return {"a_only": b01, "b_only": b10, "p_value": 1.0}
    k = min(b01, b10)
    p = min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"a_only": b01, "b_only": b10, "p_value": p}


def aggregate(items: List[Dict]) -> Dict:
    """items: experiment item dicts with vlm_scores, ocr_scores, vlm_ms, ocr_ms, answer_in_ocr, agree."""
    n = len(items)
    out: Dict = {"n": n}
    if not n:
        return out
    for side in ("vlm", "ocr"):
        sc = [it[f"{side}_scores"] for it in items]
        ms = [float(it[f"{side}_ms"]) for it in items if it.get(f"{side}_ms") is not None]
        out[side] = {
            "em": mean([s.get("em", 0) for s in sc]), "anls": mean([s.get("anls", 0) for s in sc]),
            "contains": mean([s.get("contains", 0) for s in sc]),
            "abstain_rate": mean([s.get("abstain", 0) for s in sc]), "error_rate": mean([s.get("error", 0) for s in sc]),
            "latency_ms": {"mean": mean(ms), "p50": percentile(ms, 0.5), "p95": percentile(ms, 0.95)},
        }
    va = [it["vlm_scores"].get("anls", 0) for it in items]
    oa = [it["ocr_scores"].get("anls", 0) for it in items]
    out["paired"] = {
        "anls_vlm_minus_ocr": paired_bootstrap(va, oa),
        "em_mcnemar": mcnemar([it["vlm_scores"].get("em", 0) == 1 for it in items],
                              [it["ocr_scores"].get("em", 0) == 1 for it in items]),
    }
    known = [it for it in items if it.get("answer_in_ocr") is not None]
    out["ocr_answer_coverage"] = mean([1.0 if it["answer_in_ocr"] else 0.0 for it in known]) if known else None
    both = [it for it in items if it.get("agree") is not None]
    out["disagreement_rate"] = mean([0.0 if it["agree"] else 1.0 for it in both]) if both else None
    # OCR-loss cases: VLM answered correctly (contains) while the gold answer never appeared in the OCR text
    loss = [it for it in known if not it["answer_in_ocr"] and it["vlm_scores"].get("contains", 0) == 1]
    out["ocr_loss_cases"] = len(loss)
    out["trust"] = selective(items)
    out["by_type"] = by_type(items)
    return out


def by_type(items: List[Dict]) -> Optional[Dict]:
    """Vision vs OCR accuracy per question type (DocVQA tags: layout, table/list, handwritten, figure/diagram, ...)."""
    groups: Dict[str, List[Dict]] = {}
    for it in items:
        for t in (it.get("extra") or {}).get("types") or []:
            groups.setdefault(t, []).append(it)
    if not groups:
        return None
    return {t: {"n": len(g), "vlm_anls": round(mean([i["vlm_scores"].get("anls", 0) for i in g]), 4),
                "ocr_anls": round(mean([i["ocr_scores"].get("anls", 0) for i in g]), 4)}
            for t, g in sorted(groups.items(), key=lambda kv: -len(kv[1]))}


def auroc(scores: Sequence[float], labels: Sequence[bool]) -> Optional[float]:
    """Probability that a random correct item scores higher than a random wrong one (ties count half).
    0.5 = no better than chance, 1.0 = separates them perfectly. None when one class is missing."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def selective(items: List[Dict]) -> Optional[Dict]:
    """Does the trust score predict wrong answers? Accuracy of the recommended answer when only the most-trusted
    share of questions is answered (risk-coverage), and AUROC for trust and for plain agreement."""
    rows = [it for it in items if (it.get("extra") or {}).get("trust") is not None and it["extra"].get("recommended_correct") is not None]
    if not rows:
        return None
    t = [r["extra"]["trust"] for r in rows]
    y = [bool(r["extra"]["recommended_correct"]) for r in rows]
    ranked = [ok for _, ok in sorted(zip(t, y), key=lambda z: -z[0])]
    curve = []
    for cov in (0.25, 0.5, 0.75, 1.0):
        k = max(1, round(cov * len(ranked)))
        curve.append({"coverage": cov, "n": k, "accuracy": round(sum(ranked[:k]) / k, 4)})
    agree = [1.0 if r.get("agree") else 0.0 for r in rows]
    unrated = sum(1 for it in items if (it.get("extra") or {}).get("trust_level") in ("unknown", "not rated"))
    return {"n": len(rows), "unrated": unrated, "accuracy": round(sum(y) / len(y), 4),
            "auroc_trust": auroc(t, y), "auroc_agreement": auroc(agree, y), "risk_coverage": curve}
