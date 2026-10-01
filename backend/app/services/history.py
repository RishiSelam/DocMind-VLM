"""A document's full question-and-answer history, as data (JSON) or a readable record (Markdown).

Used by GET /api/documents/{id}/history and scripts/export_history.py, so both give the same content.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from .. import db


def _when(ts: Optional[float]) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "?"


def _turns(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair each question with the answer that followed it; keep only the fields a reader needs."""
    turns: List[Dict[str, Any]] = []
    for m in messages:
        if m["role"] == "user":
            turns.append({"question": m["content"], "asked_at": m["created_at"], "answer": None})
        elif turns and turns[-1]["answer"] is None:
            p = m.get("payload") or {}
            side = lambda k: None if not p.get(k) else {  # noqa: E731
                "answer": p[k].get("answer"), "error": p[k].get("error"), "pages": p[k].get("pages"), "ms": p[k].get("ms")}
            verdict = next((f for f in p.get("explanation") or [] if f.get("kind") == "verdict"), None)
            turns[-1]["answer"] = {
                "demo_mode": p.get("demo"), "mode": p.get("mode"),
                "vision": side("vlm"), "ocr": side("ocr"),
                "agreement": (p.get("verification") or {}).get("verdict"),
                "better_supported": (p.get("scorecard") or {}).get("winner"),
                "verdict": verdict, "findings": [f for f in p.get("explanation") or [] if f.get("kind") != "verdict"],
                "total_ms": (p.get("timings") or {}).get("total_ms"),
                "trust": (p.get("xai") or {}).get("trust"),
                "evidence_agreement": (p.get("xai") or {}).get("agreement"),
            }
    return turns


def document_history(doc_id: str) -> Optional[Dict[str, Any]]:
    doc = db.get_document(doc_id)
    if not doc:
        return None
    # every conversation about this file's content: this copy, other copies, and copies since deleted
    convs = sorted((c for c in db.list_conversations() if c.get("doc_id") == doc_id or c.get("doc_sha256") == doc["sha256"]),
                   key=lambda c: c["created_at"])
    return {
        "document": {k: doc[k] for k in ("id", "filename", "n_pages", "size_bytes", "sha256", "created_at")},
        "exported_at": dt.datetime.now().isoformat(timespec="seconds"),
        "conversations": [{"id": c["id"], "title": c["title"], "created_at": c["created_at"],
                           "turns": _turns(db.list_messages(c["id"]))} for c in convs],
    }


def _sec(ms: Optional[float]) -> str:
    return "" if ms is None else f" ({ms / 1000:.1f} s)"


def history_markdown(h: Dict[str, Any]) -> str:
    d = h["document"]
    n_q = sum(len(c["turns"]) for c in h["conversations"])
    out = [f"# {d['filename']}", "",
           f"{d['n_pages']} pages · uploaded {_when(d['created_at'])} · {len(h['conversations'])} conversations, {n_q} questions",
           f"Exported {h['exported_at']} from DocMind.", ""]
    if not h["conversations"]:
        out += ["No questions have been asked about this document yet.", ""]
    for c in h["conversations"]:
        out += [f"## {c['title']}", f"Started {_when(c['created_at'])}", ""]
        for t in c["turns"]:
            out += [f"### Q: {t['question']}", f"*Asked {_when(t['asked_at'])}*", ""]
            a = t["answer"]
            if not a:
                out += ["No answer was saved for this question.", ""]
                continue
            if a.get("demo_mode"):
                out += ["> Demo mode: these answers came from text-matching stand-ins, not from the Qwen models.", ""]
            for label, s in (("Vision model", a["vision"]), ("OCR + text model", a["ocr"])):
                if s is None:
                    continue
                pages = f", pages {s['pages'][0]}–{s['pages'][-1]}" if s.get("pages") else ""
                body = f"failed: {s['error']}" if s.get("error") else (s.get("answer") or "").strip()
                out += [f"**{label}**{_sec(s.get('ms'))}{pages}:", "", body, ""]
            if a.get("verdict"):
                out += [f"**Verdict:** {a['verdict']['title']}. {a['verdict']['text']}", ""]
            t = a.get("trust") or {}
            if t.get("score") is not None:
                out += [f"**Trust:** {t['level']} ({round(t['score'] * 100)}/100): " + "; ".join(t.get("reasons") or []), ""]
            if a.get("evidence_agreement"):
                out += [f"**Evidence:** {a['evidence_agreement']} (where the two methods found the answer)", ""]
            elif a.get("agreement"):
                out += [f"**Agreement:** {a['agreement']}", ""]
            for f in a.get("findings") or []:
                out += [f"- *{f['title']}:* {f['text']}"]
            if a.get("findings"):
                out.append("")
    return "\n".join(out).rstrip() + "\n"
