"""Prompt text. Both pipelines get the SAME instructions so that only the input modality differs."""
from __future__ import annotations

from typing import List, Optional, Tuple

PROMPT_VERSION = "v2"  # v2: documents are read in parts, then the parts are combined
NOT_FOUND = "Not found in document."

SYSTEM_CHAT = (
    "You are a careful document assistant. Answer only from the document provided. "
    f"If the document does not contain the answer, reply exactly: {NOT_FOUND} "
    "Copy figures, names and dates exactly as printed. Be concise."
)
SYSTEM_SHORT = (
    "Answer the question using only the document provided. Reply with the exact answer text as it appears in "
    f"the document, as briefly as possible, with no explanation. If it is absent, reply exactly: {NOT_FOUND}"
)


# --- explainability: where the answer is, and an exact transcription for the look-closer re-check ---
SYSTEM_LOCATE = "You locate text in document page images. Reply with JSON only."
SYSTEM_TRANSCRIBE = "You transcribe text from images exactly as printed. Reply with the text only."
TRANSCRIBE = "Transcribe all the text in this image exactly as printed, character by character, keeping numbers and spelling as they appear."


def locate_text(question: str, answer: str, pages: List[int]) -> str:
    which = f"page {pages[0]}" if len(pages) == 1 else f"one of pages {', '.join(map(str, pages))}"
    return (f"Question: {question}\nAnswer: {answer}\n\nFind where on {which} the text that answers the question is printed. "
            'Output JSON: {"page": <page number>, "bbox_2d": [x1, y1, x2, y2]} for that region, in pixel coordinates of that page image.')


def parse_box(text: str) -> Optional[Tuple[Optional[int], Tuple[float, float, float, float]]]:
    """Read {"page": n, "bbox_2d": [x1, y1, x2, y2]} (or a list of them; the first counts) from a model reply."""
    import json
    import re
    m = re.search(r"\{[^{}]*bbox_2d[^{}]*\}", text or "")
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        x1, y1, x2, y2 = (float(v) for v in obj["bbox_2d"][:4])
    except Exception:  # noqa: BLE001
        return None
    page = obj.get("page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    return page, (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


# Used when the model sees only some pages: a partial answer is wanted, not "not found".
SYSTEM_PART = (
    "You are a careful document assistant reading SOME pages of a longer document; other pages are read separately "
    "and the answers are merged afterwards. Answer only from the pages provided. If they answer only part of the "
    "question, give that part and nothing else; never say that something is missing or not mentioned. "
    f"Only if they answer no part of the question, reply exactly: {NOT_FOUND} "
    "Copy figures, names and dates exactly as printed. Be concise."
)


def system_prompt(short: bool, part: bool = False) -> str:
    if part:
        return SYSTEM_PART + (" Reply with the exact answer text only, with no explanation." if short else "")
    return SYSTEM_SHORT if short else SYSTEM_CHAT


def history_block(history: List[Tuple[str, str]]) -> str:
    if not history:
        return ""
    lines = ["Earlier in this conversation:"]
    for q, a in history:
        lines.append(f"Q: {q}\nA: {a}")
    return "\n".join(lines) + "\n\n"


def part_note(part: Optional[str]) -> str:
    """Tells the model it sees only part of the document, so it says NOT_FOUND instead of guessing."""
    if not part:
        return ""
    return (f"You are seeing only {part} of the document; other pages are read separately. "
            "Answer whatever part of the question these pages answer. "
            f"If they answer no part of it, reply exactly: {NOT_FOUND}\n\n")


def vlm_user_text(question: str, history: List[Tuple[str, str]], part: Optional[str] = None) -> str:
    return f"{part_note(part)}{history_block(history)}Question: {question}"


def llm_user_text(context: str, question: str, history: List[Tuple[str, str]], part: Optional[str] = None) -> str:
    return f"Document text (from OCR):\n{context}\n\n{part_note(part)}{history_block(history)}Question: {question}"


def combine_user_text(question: str, partials: List[Tuple[str, str]], history: List[Tuple[str, str]]) -> str:
    """Same text for both pipelines: each part's answer, then the question. No document content is added here."""
    notes = "\n".join(f"- From {label}: {ans}" for label, ans in partials)
    return (f"The document was read in parts. These are the answers each part gave to the question:\n{notes}\n\n"
            "Each part saw only its own pages, so together they may answer different pieces of the question. "
            "Using only these answers, give one final answer that brings the pieces together. If parts give different "
            f"values for the same thing, report each with its pages. If no part contains the answer, reply exactly: {NOT_FOUND}\n\n"
            f"{history_block(history)}Question: {question}")
