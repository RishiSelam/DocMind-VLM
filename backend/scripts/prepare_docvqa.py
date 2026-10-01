"""Turn the DocVQA validation split into this project's JSONL format (validation: the test split has no answers).

    python scripts/prepare_docvqa.py --limit 200          # random sample, fixed seed, from the local Hugging Face cache

Reads the cached Parquet files of `lmms-lab/DocVQA` with pyarrow (`pip install pyarrow`), so no network is needed
once the dataset is in the cache. Without a cached copy it falls back to `datasets` (`pip install datasets`, internet once).
Each line keeps DocVQA's question types (figure/diagram, layout, table/list, handwritten, ...) for per-type analysis.
"""
import argparse
import glob
import io
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=200)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--repo", default="lmms-lab/DocVQA")
ap.add_argument("--config", default="DocVQA")
ap.add_argument("--split", default="validation")
ap.add_argument("--name", default="docvqa_val")
args = ap.parse_args()

out = get_settings().eval_dir / args.name
(out / "images").mkdir(parents=True, exist_ok=True)
hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
files = sorted(glob.glob(str(hf_home / "hub" / f"datasets--{args.repo.replace('/', '--')}" / "snapshots" / "*" / args.config / f"{args.split}-*.parquet")))


def rows_from_cache():
    import pyarrow.parquet as pq
    meta = [(f, pq.ParquetFile(f).metadata.num_rows) for f in files]
    index = [(f, i) for f, n in meta for i in range(n)]
    pick = sorted(random.Random(args.seed).sample(index, min(args.limit, len(index))))
    by_file = {}
    for f, i in pick:
        by_file.setdefault(f, []).append(i)
    for f, idxs in by_file.items():
        t = pq.read_table(f, columns=["questionId", "question", "answers", "question_types", "image"])
        for i in idxs:
            r = t.slice(i, 1).to_pylist()[0]
            from PIL import Image
            r["image"] = Image.open(io.BytesIO(r["image"]["bytes"]))
            yield r


def rows_from_hub():
    from datasets import load_dataset
    for k, r in enumerate(load_dataset(args.repo, args.config, split=args.split, streaming=True)):
        if k >= args.limit:
            break
        yield r


n = 0
with open(out / f"{args.name}.jsonl", "w", encoding="utf-8") as f:
    for row in (rows_from_cache() if files else rows_from_hub()):
        qid = str(row.get("questionId", n))
        row["image"].convert("RGB").save(out / "images" / f"{qid}.png")
        f.write(json.dumps({"qid": qid, "question": row["question"], "answers": list(row["answers"]),
                            "types": list(row.get("question_types") or []), "image": f"images/{qid}.png"}) + "\n")
        n += 1
print(f"Wrote {n} questions to {out / (args.name + '.jsonl')} ({'local cache' if files else 'Hugging Face hub'})")
