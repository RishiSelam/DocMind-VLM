"""Dataset loading. Format: JSONL, one record per question.

  {"qid": "1", "question": "...", "answers": ["a", "b"], "image": "images/x.png"}          # image relative to the JSONL
  {"qid": "2", "question": "...", "answers": ["a"], "doc": "docs/y.pdf", "page": 3}         # 1-based page of a PDF
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..services import pdf as pdfsvc


def list_datasets(eval_dir: Path) -> List[Dict[str, Any]]:
    out = []
    for p in sorted(Path(eval_dir).glob("**/*.jsonl")):
        with open(p, encoding="utf-8") as f:
            n = sum(1 for line in f if line.strip())
        out.append({"name": str(p.relative_to(eval_dir)), "path": str(p), "n": n})
    return out


def load_dataset(path: str | Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    path = Path(path)
    base = path.parent
    items: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            r = json.loads(line)
            src = r.get("image") or r.get("doc")
            if not src:
                raise ValueError(f"{path}:{i + 1} has neither 'image' nor 'doc'")
            p = Path(src)
            p = p if p.is_absolute() else base / p
            if not p.exists():
                raise FileNotFoundError(f"{path}:{i + 1} references missing file {p}")
            answers = r.get("answers") or ([r["answer"]] if "answer" in r else [])
            items.append({"qid": str(r.get("qid", i)), "question": r["question"], "answers": [str(a) for a in answers],
                          "file": str(p), "page": int(r.get("page", 1)) - 1, "types": list(r.get("types") or [])})
            if limit and len(items) >= limit:
                break
    return items


def item_as_document(item: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap one dataset item as a document dict. Multi-page PDFs are evaluated as whole documents (the `page` field is informational)."""
    path = item["file"]
    n_total = pdfsvc.count_pages(path)
    doc_id = "eval_" + hashlib.sha1(path.encode()).hexdigest()[:12]
    return {"id": doc_id, "path": path, "n_pages": n_total, "filename": Path(path).name}
