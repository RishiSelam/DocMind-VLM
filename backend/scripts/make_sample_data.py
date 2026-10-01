"""Create sample documents and a 7-question eval set:  python scripts/make_sample_data.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import get_settings  # noqa: E402
from app.sample_data import build_eval_sample, build_report_pdf  # noqa: E402

s = get_settings()
jsonl = build_eval_sample(s.eval_dir)
pdf = build_report_pdf(s.data_dir / "samples" / "annual_report.pdf")
print(f"eval set : {jsonl}")
print(f"6-page PDF: {pdf}")
