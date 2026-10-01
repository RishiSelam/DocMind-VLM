"""Model backends.

Real:  Qwen2.5-VL-7B-Instruct (vision) and Qwen2.5-7B-Instruct (text), both 4-bit nf4, loaded eagerly at startup.
Demo:  heuristic extractors so the whole app runs on a laptop. They are NOT models and their answers mean nothing
       for research; the UI labels them.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from ..config import Settings, get_settings
from . import prompts
from .retrieval import tokenize

log = logging.getLogger("docmind.models")
GPU_LOCK = threading.Lock()
History = List[Tuple[str, str]]


class StartupError(RuntimeError):
    """Raised at startup when the real models cannot be loaded. The server must not start half-working."""


# ------------------------------------------------------------------------------------------ demo
def _best_line(question: str, text: str, split: str, max_len: int = 200) -> str:
    q = set(tokenize(question, drop_stop=True))
    if not q or not text.strip():
        return prompts.NOT_FOUND
    parts = [p.strip() for p in re.split(split, text) if p.strip()]
    best, best_score = "", 0.0
    for p in parts:
        toks = set(tokenize(p))
        score = len(q & toks) / (len(q) ** 0.5)
        if score > best_score:
            best, best_score = p, score
    if best_score == 0:
        return prompts.NOT_FOUND
    return best[:max_len]


class DemoVLM:
    name = "demo-vlm"

    def generate(self, images: List[Image.Image], page_labels: List[int], question: str, history: History,
                 short: bool, aux_texts: Optional[Dict[int, str]] = None, part: Optional[str] = None) -> str:
        text = "\n".join((aux_texts or {}).get(p, "") for p in page_labels)
        return _best_line(question, text, r"\n+")

    def combine(self, question: str, partials: List[Tuple[str, str]], history: History, short: bool) -> str:
        return _demo_combine(partials)


class DemoLLM:
    name = "demo-llm"

    def generate(self, context: str, question: str, history: History, short: bool, part: Optional[str] = None) -> str:
        body = re.sub(r"^--- Page \d+ ---$", "", context, flags=re.M)  # drop the page markers the prompt adds
        return _best_line(question, body, r"(?<=[.!?])\s+|\n+", max_len=240)

    def combine(self, question: str, partials: List[Tuple[str, str]], history: History, short: bool) -> str:
        return _demo_combine(partials)


def _demo_combine(partials: List[Tuple[str, str]]) -> str:
    found = [a for _, a in partials if prompts.NOT_FOUND.rstrip(".").lower() not in a.lower()]
    return found[0] if found else prompts.NOT_FOUND


# ------------------------------------------------------------------------------------------ real
def _torch():
    try:
        import torch
    except Exception as e:  # noqa: BLE001
        raise StartupError("PyTorch is not installed. Run: pip install torch (see backend/requirements-gpu.txt), "
                           "or set DEMO_MODE=true.") from e
    return torch


def check_vram(min_free_gb: float) -> None:
    torch = _torch()
    if not torch.cuda.is_available():
        raise StartupError("DEMO_MODE=false but CUDA is not available. Run on the GPU workstation, or set DEMO_MODE=true.")
    free, total = torch.cuda.mem_get_info()
    free_gb, total_gb = free / 1e9, total / 1e9
    log.info("GPU %s: %.1f GB free of %.1f GB", torch.cuda.get_device_name(0), free_gb, total_gb)
    if free_gb < min_free_gb:
        raise StartupError(
            f"Only {free_gb:.1f} GB of VRAM is free (need about {min_free_gb:.1f} GB for both 4-bit models). "
            "The GPU is shared: check `nvidia-smi`, wait for the other job, or lower MIN_FREE_VRAM_GB "
            "and set ENABLE_LLM=false / ENABLE_VLM=false to load only one model."
        )


def _quant_config():
    torch = _torch()
    from transformers import BitsAndBytesConfig

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    cfg = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=dtype,
                             bnb_4bit_use_double_quant=True)
    return cfg, dtype


def _oom_guard(what: str, fn):
    torch = _torch()
    try:
        return fn()
    except torch.cuda.OutOfMemoryError as e:
        torch.cuda.empty_cache()
        raise StartupError(f"CUDA out of memory while loading {what}. Free GPU memory or load one model at a time "
                           "(ENABLE_VLM / ENABLE_LLM).") from e


class QwenVLM:
    def __init__(self, s: Settings):
        torch = _torch()
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        self.name = s.vlm_model_id
        self.max_new_tokens = s.max_new_tokens
        qcfg, dtype = _quant_config()
        log.info("Loading VLM %s (nf4)...", s.vlm_model_id)

        def load():
            return Qwen2_5_VLForConditionalGeneration.from_pretrained(
                s.vlm_model_id, quantization_config=qcfg, torch_dtype=dtype, device_map={"": 0},
                local_files_only=s.offline)

        self.model = _oom_guard("the VLM", load)
        self.processor = AutoProcessor.from_pretrained(
            s.vlm_model_id, min_pixels=s.vlm_min_pixels, max_pixels=s.vlm_max_pixels, local_files_only=s.offline)
        self.model.eval()
        self._torch = torch

    def generate(self, images: List[Image.Image], page_labels: List[int], question: str, history: History,
                 short: bool, aux_texts: Optional[Dict[int, str]] = None, part: Optional[str] = None) -> str:
        content: List[dict] = []
        for lab in page_labels:
            content.append({"type": "text", "text": f"Page {lab + 1}:"})
            content.append({"type": "image"})
        content.append({"type": "text", "text": prompts.vlm_user_text(question, history, part)})
        return self._run(content, short, images, part=bool(part))

    def combine(self, question: str, partials: List[Tuple[str, str]], history: History, short: bool) -> str:
        """Text-only call to the same VLM, so the vision pipeline never borrows the text model."""
        return self._run([{"type": "text", "text": prompts.combine_user_text(question, partials, history)}], short, None)

    def locate(self, images: List[Image.Image], page_labels: List[int], question: str, answer: str) -> Optional[Dict[str, Any]]:
        """Where on the pages the answer is written: {"page": 0-based, "box": [x0, y0, x1, y1] as 0..1 fractions} or None.
        Qwen2.5-VL answers in pixels of the image as the processor resized it; image_grid_thw gives that size."""
        content: List[dict] = []
        for lab in page_labels:
            content.append({"type": "text", "text": f"Page {lab + 1}:"})
            content.append({"type": "image"})
        content.append({"type": "text", "text": prompts.locate_text(question, answer, [p + 1 for p in page_labels])})
        text, grids = self._run(content, False, images, system=prompts.SYSTEM_LOCATE, with_grid=True)
        found = prompts.parse_box(text)
        if not found:
            return None
        page, (x0, y0, x1, y1) = found
        idx = page_labels.index(page - 1) if page and (page - 1) in page_labels else (0 if len(page_labels) == 1 else None)
        if idx is None:
            return None
        _, gh, gw = (int(v) for v in grids[idx])
        h, w = gh * 14, gw * 14   # Qwen2.5-VL patch size: resized image = grid x 14 px
        box = [max(0.0, min(1.0, v)) for v in (x0 / w, y0 / h, x1 / w, y1 / h)]
        if box[2] <= box[0] or box[3] <= box[1]:
            return None
        return {"page": page_labels[idx], "box": box, "raw": text}

    def transcribe(self, image: Image.Image) -> str:
        """Exact text of a (zoomed) image region, for the look-closer re-check."""
        content = [{"type": "image"}, {"type": "text", "text": prompts.TRANSCRIBE}]
        return self._run(content, True, [image], system=prompts.SYSTEM_TRANSCRIBE)

    def _run(self, content: List[dict], short: bool, images: Optional[List[Image.Image]], part: bool = False,
             system: Optional[str] = None, with_grid: bool = False):
        torch = self._torch
        messages = [{"role": "system", "content": system or prompts.system_prompt(short, part)}, {"role": "user", "content": content}]
        prompt = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        with GPU_LOCK:
            try:
                inputs = self.processor(text=[prompt], images=images or None, padding=True, return_tensors="pt").to(self.model.device)
                with torch.inference_mode():
                    out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
                new = out[:, inputs["input_ids"].shape[1]:]
                text = self.processor.batch_decode(new, skip_special_tokens=True, clean_up_tokenization_spaces=False)[0].strip()
                if with_grid:
                    return text, inputs["image_grid_thw"].tolist()
                return text
            except torch.cuda.OutOfMemoryError as e:
                raise RuntimeError("CUDA out of memory during VLM generation. Lower VLM_PAGE_CAP (pages per batch) or VLM_MAX_PIXELS.") from e
            finally:
                torch.cuda.empty_cache()


class QwenLLM:
    def __init__(self, s: Settings):
        torch = _torch()
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.name = s.llm_model_id
        self.max_new_tokens = s.max_new_tokens
        qcfg, dtype = _quant_config()
        log.info("Loading LLM %s (nf4)...", s.llm_model_id)

        def load():
            return AutoModelForCausalLM.from_pretrained(
                s.llm_model_id, quantization_config=qcfg, torch_dtype=dtype, device_map={"": 0},
                local_files_only=s.offline)

        self.model = _oom_guard("the LLM", load)
        self.tok = AutoTokenizer.from_pretrained(s.llm_model_id, local_files_only=s.offline)
        self.model.eval()
        self._torch = torch

    def generate(self, context: str, question: str, history: History, short: bool, part: Optional[str] = None) -> str:
        return self._run(prompts.llm_user_text(context, question, history, part), short, part=bool(part))

    def combine(self, question: str, partials: List[Tuple[str, str]], history: History, short: bool) -> str:
        return self._run(prompts.combine_user_text(question, partials, history), short)

    def _run(self, user_text: str, short: bool, part: bool = False) -> str:
        torch = self._torch
        messages = [{"role": "system", "content": prompts.system_prompt(short, part)},
                    {"role": "user", "content": user_text}]
        prompt = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        with GPU_LOCK:
            try:
                inputs = self.tok([prompt], return_tensors="pt").to(self.model.device)
                with torch.inference_mode():
                    out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
                new = out[:, inputs["input_ids"].shape[1]:]
                return self.tok.batch_decode(new, skip_special_tokens=True)[0].strip()
            except torch.cuda.OutOfMemoryError as e:
                raise RuntimeError("CUDA out of memory during LLM generation. Lower MAX_CONTEXT_CHARS.") from e
            finally:
                torch.cuda.empty_cache()


# ------------------------------------------------------------------------------------------ hub
class ModelHub:
    def __init__(self) -> None:
        self.vlm = None
        self.llm = None
        self.demo = True
        self.loaded = False

    def load_all(self) -> None:
        s = get_settings()
        self.demo = s.demo_mode
        if s.demo_mode:
            self.vlm, self.llm = DemoVLM(), DemoLLM()
            self.loaded = True
            log.warning("DEMO_MODE=true: answers come from heuristic extractors, not from Qwen.")
            return
        if not (s.enable_vlm or s.enable_llm):
            raise StartupError("ENABLE_VLM and ENABLE_LLM are both false; nothing to serve.")
        check_vram(s.min_free_vram_gb)
        if s.enable_vlm:
            self.vlm = QwenVLM(s)
        if s.enable_llm:
            self.llm = QwenLLM(s)
        self.loaded = True
        log.info("Models loaded.")

    def status(self) -> Dict[str, object]:
        return {
            "demo_mode": self.demo,
            "loaded": self.loaded,
            "vlm": getattr(self.vlm, "name", None),
            "llm": getattr(self.llm, "name", None),
        }


hub = ModelHub()
