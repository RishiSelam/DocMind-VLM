"""Download model weights into the local Hugging Face cache (needs internet, ~16 GB + ~15 GB).

    python scripts/download_models.py                # both models
    python scripts/download_models.py --only vlm     # just Qwen2.5-VL
After this, the server runs fully offline (OFFLINE=true).
"""
import argparse
import os
import sys
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from huggingface_hub import snapshot_download  # noqa: E402

from app.config import get_settings  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--only", choices=["vlm", "llm"])
args = ap.parse_args()
s = get_settings()
os.environ["HF_HUB_OFFLINE"] = "0"
targets = {"vlm": s.vlm_model_id, "llm": s.llm_model_id}
for key, mid in targets.items():
    if args.only and key != args.only:
        continue
    print(f"Downloading {mid} ...")
    print("  ->", snapshot_download(mid, allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.tiktoken", "merges.txt", "vocab.json"]))
print("Done.")
