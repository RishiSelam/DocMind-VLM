"""BM25 page ranking. Small, dependency-free, deterministic."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

_TOKEN = re.compile(r"[A-Za-z0-9]+")
STOP = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "is", "are", "was", "were", "be", "what", "which",
    "who", "whom", "whose", "when", "where", "how", "does", "do", "did", "and", "or", "by", "with", "this",
    "that", "it", "its", "as", "from", "there", "their", "has", "have", "had", "please", "tell", "me",
}


def tokenize(text: str, drop_stop: bool = False) -> List[str]:
    toks = [t.lower() for t in _TOKEN.findall(text or "")]
    return [t for t in toks if t not in STOP] if drop_stop else toks


class BM25:
    def __init__(self, docs: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0.0
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, query: List[str]) -> List[float]:
        out = []
        for i, d in enumerate(self.docs):
            dl = len(d) or 1
            s = 0.0
            for t in query:
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            out.append(s)
        return out


def rank_pages(question: str, page_texts: Dict[int, str]) -> List[Tuple[int, float]]:
    """Return [(page, score)] sorted best-first. Ties and all-zero scores fall back to page order."""
    pages = sorted(page_texts)
    if not pages:
        return []
    bm = BM25([tokenize(page_texts[p]) for p in pages])
    scores = bm.score(tokenize(question, drop_stop=True))
    ranked = sorted(zip(pages, scores), key=lambda x: (-x[1], x[0]))
    return [(p, round(s, 4)) for p, s in ranked]


def select_pages(ranked: List[Tuple[int, float]], cap: int) -> List[int]:
    """Top-`cap` pages, returned in reading order."""
    return sorted(p for p, _ in ranked[: max(cap, 1)])
