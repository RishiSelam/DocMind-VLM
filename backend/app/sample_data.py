"""Tiny synthetic documents for smoke tests and the demo. Clean printed text, so real OCR reads them reliably."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Sequence, Union

import pymupdf as fitz

Line = Union[str, Sequence[str]]  # a str is one text line; a sequence is table cells placed in columns


def _draw(page, lines: List[Line]) -> None:
    y = 100.0
    for ln in lines:
        cells = [ln] if isinstance(ln, str) else list(ln)
        for i, cell in enumerate(cells):
            page.insert_text((72 + 190 * i, y), cell, fontsize=18, fontname="helv")
        y += 34


def make_pdf(path: Path, pages: List[List[Line]]) -> Path:
    doc = fitz.open()
    for lines in pages:
        _draw(doc.new_page(), lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


def make_png(path: Path, lines: List[Line], dpi: int = 200) -> Path:
    doc = fitz.open()
    _draw(doc.new_page(), lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False).save(str(path))
    doc.close()
    return path


INVOICE = ["ACME SUPPLY CO.", "Invoice No: INV-2041", "Date: 12 March 2024", "Bill To: Northwind Traders", "Total Due: $1,284.50"]
MEMO = ["MEMORANDUM", "To: Priya Sharma", "From: Dr. Anil Rao", "Subject: Lab safety review", "Meeting on 5 June 2025 in Room B12"]
TABLE = [["Quarter", "Revenue", "Units"], ["Q1", "41.7", "1200"], ["Q2", "48.2", "1350"], ["Q3", "52.9", "1490"]]

REPORT_PAGES: List[List[Line]] = [
    ["Annual Operations Report", "Executive summary of the fiscal year."],
    ["Finance", "Total revenue for the year was 143 million rupees.", "Operating margin was 11 percent."],
    ["Logistics", "The Pune warehouse has a capacity of 12000 pallets.", "Average dispatch time is 26 hours."],
    ["Sustainability", "Solar panels supply 38 percent of plant electricity."],
    ["People", "Total employee headcount is 342.", "Attrition was 9 percent."],
    ["Outlook", "A second warehouse is planned for Nagpur in 2027."],
]

SAMPLE_QA = [
    ("invoice.png", "What is the invoice number?", ["INV-2041"]),
    ("invoice.png", "What is the total due?", ["$1,284.50"]),
    ("invoice.png", "Who is the invoice billed to?", ["Northwind Traders"]),
    ("memo.png", "Who is the memo addressed to?", ["Priya Sharma"]),
    ("memo.png", "Which room is the meeting in?", ["Room B12"]),
    ("table.png", "What was the revenue in Q2?", ["48.2"]),
    ("table.png", "How many units were sold in Q3?", ["1490"]),
]


def build_eval_sample(eval_dir: Path) -> Path:
    """Write data/eval/sample/{images,sample.jsonl}. Returns the JSONL path."""
    root = eval_dir / "sample"
    img = root / "images"
    make_png(img / "invoice.png", INVOICE)
    make_png(img / "memo.png", MEMO)
    make_png(img / "table.png", TABLE)
    jsonl = root / "sample.jsonl"
    with open(jsonl, "w", encoding="utf-8") as f:
        for i, (im, q, a) in enumerate(SAMPLE_QA):
            f.write(json.dumps({"qid": f"s{i + 1}", "question": q, "answers": a, "image": f"images/{im}"}) + "\n")
    return jsonl


def build_report_pdf(out: Path) -> Path:
    return make_pdf(out, REPORT_PAGES)
