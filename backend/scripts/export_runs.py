"""Save every experiment run to files, plus a consistent copy of the database.

    python scripts/export_runs.py --out somewhere

Writes, per experiment, <id>.json (config, metrics and every item) and <id>.csv (one row per question),
plus index.md and docmind.sqlite3 (a snapshot taken with SQLite's backup API, safe while the server runs).
Only reads the database; nothing is changed or deleted.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--out", help="output folder (default: data/exports/runs-<timestamp>)")
args = ap.parse_args()

s = get_settings()
out = Path(args.out) if args.out else s.data_dir / "exports" / f"runs-{dt.datetime.now():%Y%m%d-%H%M%S}"
(out / "experiments").mkdir(parents=True, exist_ok=True)

index = [f"# DocMind runs, {dt.datetime.now():%Y-%m-%d %H:%M}", "", "| Experiment | Name | Status | Done | Created | Files |", "|---|---|---|---|---|---|"]
for e in db.list_experiments():
    exp = db.get_experiment(e["id"])
    items = db.list_experiment_items(e["id"])
    base = out / "experiments" / e["id"]
    base.with_suffix(".json").write_text(json.dumps({**exp, "items": items}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["qid", "question", "gold", "vlm_pred", "ocr_pred", "vlm_em", "vlm_anls", "ocr_em", "ocr_anls",
                    "vlm_ms", "ocr_ms", "answer_in_ocr", "pipelines_agree"])
        for it in items:
            w.writerow([it["qid"], it["question"], json.dumps(it["gold"]), it["vlm_pred"], it["ocr_pred"],
                        it["vlm_scores"].get("em"), it["vlm_scores"].get("anls"), it["ocr_scores"].get("em"),
                        it["ocr_scores"].get("anls"), it["vlm_ms"], it["ocr_ms"], it["answer_in_ocr"], it["agree"]])
    created = dt.datetime.fromtimestamp(exp["created_at"]).strftime("%Y-%m-%d %H:%M") if exp.get("created_at") else ""
    index.append(f"| {e['id']} | {exp.get('name') or ''} | {exp.get('status')} | {exp.get('progress_done')}/{exp.get('progress_total')} "
                 f"| {created} | [json](experiments/{e['id']}.json) · [csv](experiments/{e['id']}.csv) |")
(out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

src = sqlite3.connect(str(s.db_path))
dst = sqlite3.connect(str(out / "docmind.sqlite3"))
with dst:
    src.backup(dst)
src.close()
dst.close()
print(f"Saved {len(index) - 4} experiments and a database snapshot to {out}")
