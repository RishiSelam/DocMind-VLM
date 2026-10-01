"""PDF / image handling. Uploads are streamed to disk in chunks, so there is no size limit."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import BinaryIO, Dict, Tuple

import pymupdf as fitz  # PyMuPDF
from PIL import Image

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
ALLOWED_EXT = {".pdf"} | IMAGE_EXT
CHUNK = 1024 * 1024


def is_image_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXT


def safe_name(name: str) -> str:
    name = Path(name or "upload").name
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name) or "upload"


def save_upload_stream(src: BinaryIO, dest_dir: Path, filename: str, doc_tag: str) -> Tuple[Path, int, str]:
    """Copy `src` to disk in 1 MiB chunks, hashing on the way. Returns (path, size, sha256)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = safe_name(filename)
    path = dest_dir / f"{doc_tag}_{fname}"
    h = hashlib.sha256()
    size = 0
    with open(path, "wb") as out:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            out.write(chunk)
            h.update(chunk)
            size += len(chunk)
    return path, size, h.hexdigest()


def count_pages(path: str | Path) -> int:
    if is_image_path(path):
        with Image.open(path) as im:
            return int(getattr(im, "n_frames", 1))
    with fitz.open(str(path)) as d:
        return d.page_count


def render_page(path: str | Path, page: int, dpi: int = 144) -> Image.Image:
    """Return page `page` (0-based) as an RGB PIL image."""
    if is_image_path(path):
        with Image.open(path) as im:
            try:
                im.seek(page)
            except EOFError as e:
                raise IndexError(f"page {page} out of range") from e
            return im.convert("RGB").copy()
    with fitz.open(str(path)) as d:
        if page < 0 or page >= d.page_count:
            raise IndexError(f"page {page} out of range (0..{d.page_count - 1})")
        pix = d[page].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def text_layer(path: str | Path, page: int) -> str:
    """Embedded text (empty for scans and image files)."""
    if is_image_path(path):
        return ""
    with fitz.open(str(path)) as d:
        if page < 0 or page >= d.page_count:
            return ""
        return d[page].get_text("text").strip()


def all_text_layers(path: str | Path) -> Dict[int, str]:
    if is_image_path(path):
        return {}
    with fitz.open(str(path)) as d:
        return {i: d[i].get_text("text").strip() for i in range(d.page_count)}


def page_features(path: str | Path, page: int) -> Dict[str, float]:
    """Cheap structural features used by the OCR information-loss audit."""
    if is_image_path(path):
        return {"is_image_file": 1, "text_layer_chars": 0, "n_images": 1, "image_area_ratio": 1.0, "n_drawings": 0, "n_tables": 0}
    with fitz.open(str(path)) as d:
        p = d[page]
        area = max(p.rect.width * p.rect.height, 1.0)
        img_area = 0.0
        imgs = p.get_images(full=True)
        for im in imgs:
            try:
                for r in p.get_image_rects(im[0]):
                    img_area += r.width * r.height
            except Exception:
                pass
        try:
            n_draw = len(p.get_drawings())
        except Exception:
            n_draw = 0
        try:
            n_tables = len(p.find_tables().tables)
        except Exception:
            n_tables = 0
        return {
            "is_image_file": 0,
            "text_layer_chars": len(p.get_text("text").strip()),
            "n_images": len(imgs),
            "image_area_ratio": round(min(img_area / area, 1.0), 4),
            "n_drawings": n_draw,
            "n_tables": n_tables,
        }
