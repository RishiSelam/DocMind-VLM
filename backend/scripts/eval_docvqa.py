"""Run an evaluation without the web server (same code path as the UI's Research tab).

    python scripts/eval_docvqa.py --dataset sample/sample.jsonl --limit 7 --name smoke
    python scripts/eval_docvqa.py --dataset docvqa_val/docvqa_val.jsonl --limit 200 --name docvqa-200
    python scripts/eval_docvqa.py --resume EXP-0003
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app import db  # noqa: E402
from app.eval import runner  # noqa: E402
from app.services import ocr as ocrsvc  # noqa: E402
from app.services.models import hub  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--dataset")
ap.add_argument("--limit", type=int)
ap.add_argument("--name", default="cli-run")
ap.add_argument("--mode", default="both", choices=["both", "vlm", "ocr"])
ap.add_argument("--resume")
args = ap.parse_args()

s = get_settings()
db.init_db()
hub.load_all()
ocrsvc.get_engine()
if s.demo_mode:
    print("WARNING: DEMO_MODE=true. Scores below come from heuristic extractors and are NOT research results.\n")

if args.resume:
    exp_id = args.resume
else:
    if not args.dataset:
        ap.error("--dataset is required")
    p = Path(args.dataset)
    p = p if p.is_absolute() else s.eval_dir / p
    items = runner.load_dataset(str(p), args.limit)
    exp = db.create_experiment(args.name, runner.snapshot_config(str(p), args.limit, args.mode), len(items))
    exp_id = exp["id"]
runner.run_experiment(exp_id, resume=True)
exp = db.get_experiment(exp_id)
print(f"{exp_id}: {exp['status']}  ({exp['progress_done']}/{exp['progress_total']})")
if exp.get("error"):
    print("error:", exp["error"])
print(json.dumps(exp["metrics"], indent=2))
