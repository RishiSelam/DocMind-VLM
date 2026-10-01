"""Save the question-and-answer history of every uploaded document to files.

    python scripts/export_history.py                 # -> data/exports/history-<timestamp>/
    python scripts/export_history.py --out somewhere

Writes one Markdown file (readable) and one JSON file (complete) per document, plus index.md.
Only reads the database; nothing is changed or deleted.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.services.history import document_history, history_markdown  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", help="output folder (default: data/exports/history-<timestamp>)")
args = ap.parse_args()

out = Path(args.out) if args.out else get_settings().data_dir / "exports" / f"history-{dt.datetime.now():%Y%m%d-%H%M%S}"
out.mkdir(parents=True, exist_ok=True)
index = [f"# DocMind history export, {dt.datetime.now():%Y-%m-%d %H:%M}", "", "| Document | Pages | Uploaded | Questions | Files |", "|---|---|---|---|---|"]
for d in sorted(db.list_documents(), key=lambda d: d["created_at"]):
    h = document_history(d["id"])
    name = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', Path(d['filename']).stem)}-{d['id']}"
    (out / f"{name}.md").write_text(history_markdown(h), encoding="utf-8")
    (out / f"{name}.json").write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")
    n_q = sum(len(c["turns"]) for c in h["conversations"])
    up = dt.datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M")
    index.append(f"| {d['filename']} | {d['n_pages']} | {up} | {n_q} | [{name}.md]({name}.md) · [json]({name}.json) |")
(out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
print(f"Saved the history of {len(index) - 4} documents to {out}")
