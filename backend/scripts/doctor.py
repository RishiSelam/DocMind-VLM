"""Preflight check.  Run before starting the server:   python scripts/doctor.py

Exit code 0 = everything needed for the configured mode is present. Non-zero = fix the FAIL lines first.
"""
import importlib
import importlib.util
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

fails = 0


def ok(msg):  print(f"  [ ok ] {msg}")
def warn(msg): print(f"  [warn] {msg}")


def fail(msg):
    global fails
    fails += 1
    print(f"  [FAIL] {msg}")


print("DocMind doctor\n")
print("Python")
(ok if sys.version_info >= (3, 10) else fail)(f"Python {sys.version.split()[0]} (need 3.10+)")

print("\nSettings")
from app.config import ROOT_DIR, BACKEND_DIR, get_settings  # noqa: E402

s = get_settings()
for envf in (ROOT_DIR / ".env", BACKEND_DIR / ".env"):
    (ok if envf.exists() else warn)(f".env {'found' if envf.exists() else 'not found'}: {envf}")
ok(f"DEMO_MODE={s.demo_mode}  OFFLINE={s.offline}  OCR_ENGINE={s.ocr_engine}")
ok(f"data dir: {s.data_dir}")

print("\nCore packages")
for mod in ("fastapi", "uvicorn", "pydantic_settings", "pymupdf", "PIL", "numpy", "multipart"):
    (ok if importlib.util.find_spec(mod) else fail)(mod)

print("\nOCR engine")
try:
    from app.services import ocr

    eng = ocr.get_engine()
    ok(f"engine '{eng.name}' constructed")
    if eng.name != "textlayer":
        from app.sample_data import make_png
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            png = make_png(Path(td) / "t.png", ["Invoice No: INV-2041"])
            t0 = time.perf_counter()
            res = eng.extract(str(png), [0])[0]
            (ok if "2041" in res.text else fail)(f"smoke OCR read: {res.text!r} in {time.perf_counter() - t0:.1f}s")
except Exception as e:  # noqa: BLE001
    fail(f"OCR engine '{s.ocr_engine}' failed: {type(e).__name__}: {e}")

print("\nDatabase")
try:
    from app import db

    db.init_db()
    ok(f"sqlite ready at {s.db_path}")
except Exception as e:  # noqa: BLE001
    fail(f"database: {e}")

print("\nGPU / models")
if s.demo_mode:
    warn("DEMO_MODE=true: skipping GPU checks. Answers will come from heuristic extractors, not Qwen.")
else:
    try:
        import torch

        ok(f"torch {torch.__version__}")
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            ok(f"CUDA: {torch.cuda.get_device_name(0)}  free {free / 1e9:.1f} / {total / 1e9:.1f} GB")
            (ok if free / 1e9 >= s.min_free_vram_gb else fail)(f"free VRAM vs MIN_FREE_VRAM_GB={s.min_free_vram_gb}")
        else:
            fail("CUDA not available")
    except Exception as e:  # noqa: BLE001
        fail(f"torch: {e}")
    # torchvision: transformers' Qwen2.5-VL processor builds a video processor that needs it
    for pkg in ("torchvision", "transformers", "accelerate", "bitsandbytes"):
        try:
            m = importlib.import_module(pkg)
            ok(f"{pkg} {getattr(m, '__version__', '?')}")
        except Exception as e:  # noqa: BLE001
            fail(f"{pkg}: {type(e).__name__}: {e}")
    try:
        import transformers

        from packaging.version import Version

        (ok if Version(transformers.__version__) >= Version("4.51.3") else fail)("transformers >= 4.51.3 (needed for Qwen2_5_VL)")
        from transformers import Qwen2_5_VLForConditionalGeneration  # noqa: F401

        ok("Qwen2_5_VLForConditionalGeneration importable")
    except Exception as e:  # noqa: BLE001
        fail(f"Qwen2.5-VL support: {type(e).__name__}: {e}")
    try:
        from huggingface_hub import snapshot_download

        for mid in (s.vlm_model_id, s.llm_model_id):
            try:
                p = snapshot_download(mid, local_files_only=True)
                ok(f"weights cached: {mid} -> {p}")
            except Exception:  # noqa: BLE001
                (fail if s.offline else warn)(f"weights NOT in local cache: {mid}  (run scripts/download_models.py while online)")
    except Exception as e:  # noqa: BLE001
        fail(f"huggingface_hub: {e}")

print("\nOptional")
for mod, why in (("docling", "OCR_ENGINE=docling"), ("paddleocr", "OCR_ENGINE=paddleocr"), ("datasets", "prepare_docvqa.py")):
    (ok if importlib.util.find_spec(mod) else warn)(f"{mod}: {'installed' if importlib.util.find_spec(mod) else 'not installed'} ({why})")
if shutil.which("nvidia-smi") is None and not s.demo_mode:
    warn("nvidia-smi not on PATH")

print(f"\n{'All required checks passed.' if not fails else f'{fails} required check(s) failed.'}")
sys.exit(1 if fails else 0)
