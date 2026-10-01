"""Central settings.

`.env` lookup is dual: repo root first, then backend/ (backend wins on conflicts).
Offline flags are applied here, at import time, BEFORE transformers is ever imported.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    # --- mode -----------------------------------------------------------
    demo_mode: bool = True          # True: no GPU models; heuristic answers, real PDF/OCR/BM25
    offline: bool = True            # sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE
    log_level: str = "INFO"

    # --- paths ----------------------------------------------------------
    data_dir: Path = ROOT_DIR / "data"
    db_path: Path = ROOT_DIR / "data" / "docmind.sqlite3"
    eval_dir: Path = ROOT_DIR / "data" / "eval"

    # --- models ---------------------------------------------------------
    vlm_model_id: str = "Qwen/Qwen2.5-VL-7B-Instruct"
    llm_model_id: str = "Qwen/Qwen2.5-7B-Instruct"
    enable_vlm: bool = True
    enable_llm: bool = True
    min_free_vram_gb: float = 12.0  # startup fails loudly below this (both 4-bit models)
    max_new_tokens: int = 256
    vlm_max_pixels: int = 1003520   # 1280*28*28 -> bounds visual tokens per page
    vlm_min_pixels: int = 200704    # 256*28*28

    # --- OCR ------------------------------------------------------------
    ocr_engine: str = "rapidocr"    # rapidocr | docling | paddleocr | textlayer
    ocr_render_dpi: int = 200
    use_text_layer: bool = False    # False keeps the baseline honest: always OCR the pixels

    # --- retrieval / page policy ---------------------------------------
    explain: bool = True            # locate each short answer's evidence on the page and score trust
    look_closer: bool = True        # when the answers differ, enlarge the evidence region and re-read it
    faithfulness: bool = True       # remove the evidence and ask again: did the answer depend on it?
    read_all_pages: bool = True     # True: both pipelines read every page, in batches that fit the GPU / context
    vlm_page_cap: int = 3           # pages per VLM call (read_all_pages) or the only pages it sees (false)
    match_pages: bool = False       # read_all_pages=false only: OCR pipeline sees the same BM25 pages as the VLM
    page_render_dpi: int = 144      # render size for VLM + UI
    max_context_chars: int = 24000  # text budget for the OCR+LLM prompt
    history_turns: int = 6          # prior Q/A turns injected into prompts (DB keeps all)

    # --- server ---------------------------------------------------------
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    (s.data_dir / "uploads").mkdir(parents=True, exist_ok=True)
    s.eval_dir.mkdir(parents=True, exist_ok=True)
    s.db_path.parent.mkdir(parents=True, exist_ok=True)
    if s.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    return s
