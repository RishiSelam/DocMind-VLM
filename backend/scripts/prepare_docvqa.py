"""Convert the DocVQA validation split (Hugging Face `lmms-lab/DocVQA`) into this project's JSONL format.

Needs internet once and `pip install datasets`. The public test split has no answers, so use validation.

    python scripts/prepare_docvqa.py --limit 500
NOTE: written against the dataset's documented columns (questionId, question, answers, image); not exercised offline.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=500)
ap.add_argument("--repo", default="lmms-lab/DocVQA")
ap.add_argument("--config", default="DocVQA")
ap.add_argument("--split", default="validation")
args = ap.parse_args()

from datasets import load_dataset  # noqa: E402

s = get_settings()
out = s.eval_dir / "docvqa_val"
(out / "images").mkdir(parents=True, exist_ok=True)
ds = load_dataset(args.repo, args.config, split=args.split, streaming=True)
n = 0
with open(out / "docvqa_val.jsonl", "w", encoding="utf-8") as f:
    for row in ds:
        qid = str(row.get("questionId", n))
        img_path = out / "images" / f"{qid}.png"
        row["image"].convert("RGB").save(img_path)
        f.write(json.dumps({"qid": qid, "question": row["question"], "answers": list(row["answers"]),
                            "image": f"images/{qid}.png"}) + "\n")
        n += 1
        if n >= args.limit:
            break
print(f"Wrote {n} questions to {out / 'docvqa_val.jsonl'}")
