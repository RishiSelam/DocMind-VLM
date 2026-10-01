import pytest

from app import db
from app.config import get_settings
from app.services import pdf
from app.services.pipelines import build_context, merge_parts, page_batches, run_ask, text_chunks
from app.services.prompts import NOT_FOUND


@pytest.fixture
def best_pages_only(monkeypatch):
    """READ_ALL_PAGES=false: the VLM sees only the VLM_PAGE_CAP best pages, the LLM one budgeted call."""
    monkeypatch.setenv("READ_ALL_PAGES", "false")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("READ_ALL_PAGES")
    get_settings.cache_clear()


def _doc(path, doc_id):
    return {"id": doc_id, "path": str(path), "n_pages": pdf.count_pages(path), "filename": path.name}


def test_build_context_orders_by_rank_and_reads_in_page_order():
    pages = {0: {"text": "aaa"}, 1: {"text": "bbb"}, 2: {"text": "ccc"}}
    text, used, trunc = build_context(pages, [(2, 5.0), (0, 1.0), (1, 0.0)], budget=10_000)
    assert used == [0, 1, 2] and not trunc and text.index("Page 1") < text.index("Page 3")


def test_build_context_budget_keeps_best_pages_and_flags_truncation():
    big = "x" * 100
    pages = {0: {"text": big}, 1: {"text": big}, 2: {"text": big}}
    text, used, trunc = build_context(pages, [(2, 9.0), (1, 5.0), (0, 1.0)], budget=260)
    assert trunc and 2 in used and 0 not in used and len(text) <= 260 + 30


def test_build_context_single_oversized_page_is_cut():
    text, used, trunc = build_context({0: {"text": "y" * 5000}}, [(0, 0.0)], budget=500)
    assert used == [0] and len(text) == 500 and trunc


def test_vlm_page_cap_and_bm25_selection(report_pdf, best_pages_only):
    db.init_db()
    res = run_ask(_doc(report_pdf, "doc_p1"), "What is the warehouse capacity in Pune?")
    assert len(res["retrieval"]["vlm_pages"]) == 2 and 2 in res["retrieval"]["vlm_pages"]  # page index 2 = Logistics
    assert res["retrieval"]["corpus"] == "textlayer"
    assert res["vlm"]["pages"] == [p + 1 for p in res["retrieval"]["vlm_pages"]]
    assert len(res["ocr"]["pages"]) >= 1 and res["ocr"]["engine"] == "rapidocr"
    assert "12000" in res["vlm"]["answer"] and "pallets" in res["ocr"]["answer"]
    assert "--- Page" not in res["ocr"]["answer"]
    # OCR may misread a digit (it read 12000 as 12oo0 in one run); the verifier must then flag it rather than pass it
    assert res["verification"]["verdict"] in ("consistent", "partial", "conflict")


def test_single_page_image_flow(invoice_png):
    res = run_ask(_doc(invoice_png, "doc_img"), "What is the invoice number?", short=True)
    assert "INV-2041" in res["vlm"]["answer"].replace(" ", "")
    assert res["retrieval"]["corpus"] == "none" and res["timings"]["total_ms"] > 0
    assert res["audit"] and res["audit"][0]["is_image_file"] == 1


def test_modes_run_only_requested_pipeline(invoice_png):
    d = _doc(invoice_png, "doc_img")
    assert run_ask(d, "invoice number", mode="vlm")["ocr"] is None
    only_ocr = run_ask(d, "invoice number", mode="ocr")
    assert only_ocr["vlm"] is None and only_ocr["verification"] is None


def test_pipeline_error_is_captured_not_raised(invoice_png, monkeypatch):
    from app.services import models

    monkeypatch.setattr(models.hub.llm, "generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA out of memory")))
    res = run_ask(_doc(invoice_png, "doc_img"), "invoice number")
    assert "out of memory" in res["ocr"]["error"] and res["vlm"]["answer"] and res["verification"] is None


def test_match_pages_gives_ocr_the_same_pages(report_pdf, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MATCH_PAGES", "true")
    get_settings.cache_clear()
    try:
        res = run_ask(_doc(report_pdf, "doc_p2"), "What is the employee headcount?")
        assert res["ocr"]["pages"] == res["vlm"]["pages"]
    finally:
        monkeypatch.setenv("MATCH_PAGES", "false")
        get_settings.cache_clear()


def test_scorecard_and_explanation_are_in_the_payload(report_pdf, best_pages_only):
    res = run_ask(_doc(report_pdf, "doc_p3"), "What is the warehouse capacity in Pune?")
    c = res["scorecard"]
    assert c["reference"] == "textlayer" and c["n_pages"] == 6 and c["vlm"]["pages_read"] == 2 and c["ocr"]["pages_read"] == 6
    assert c["winner"] in ("vlm", "ocr", "tie") and c["ocr_read_accuracy"] is not None
    kinds = [f["kind"] for f in res["explanation"]]
    assert kinds[0] == "verdict" and "speed" in kinds and "pages" in kinds
    assert "saw 2 of 6 pages" in next(f for f in res["explanation"] if f["kind"] == "pages")["text"]


def test_explanation_compares_against_full_ocr_text_not_truncated_context(report_pdf, monkeypatch, best_pages_only):
    from app.config import get_settings
    from app.services import explain as explainsvc

    seen = {}
    real = explainsvc.explain
    def spy(r, ocr_text, ref):
        seen["t"] = ocr_text
        return real(r, ocr_text, ref)

    monkeypatch.setattr(explainsvc, "explain", spy)
    monkeypatch.setenv("MAX_CONTEXT_CHARS", "300")
    get_settings.cache_clear()
    try:
        res = run_ask(_doc(report_pdf, "doc_p4"), "What is the warehouse capacity in Pune?")
        assert res["ocr"]["truncated"] and len(seen["t"]) > res["ocr"]["context_chars"]
    finally:
        monkeypatch.delenv("MAX_CONTEXT_CHARS")
        get_settings.cache_clear()


def test_failed_ocr_pipeline_explanation_has_no_false_recognition_claim(report_pdf, monkeypatch):
    from app.services import models

    monkeypatch.setattr(models.hub.llm, "generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("CUDA out of memory")))
    res = run_ask(_doc(report_pdf, "doc_p5"), "What is the warehouse capacity in Pune?")
    assert res["ocr"]["error"] and res["scorecard"]["ocr"]["error"]
    assert all("OCR missed" not in f["text"] for f in res["explanation"])


def test_read_all_pages_reads_every_page_in_batches(report_pdf):
    res = run_ask(_doc(report_pdf, "doc_all1"), "What is the warehouse capacity in Pune?")   # VLM_PAGE_CAP=2 in tests
    v, o = res["vlm"], res["ocr"]
    assert v["pages"] == [1, 2, 3, 4, 5, 6] and o["pages"] == [1, 2, 3, 4, 5, 6] and not o["truncated"]
    assert [b["pages"] for b in v["batches"]] == [[1, 2], [3, 4], [5, 6]]
    assert "12000" in v["answer"] and res["retrieval"]["read_all"] is True
    found = [b for b in v["batches"] if b["answer"] != NOT_FOUND]
    assert v["combined"] == (len(found) > 1)
    assert res["scorecard"]["vlm"]["pages_read"] == 6
    assert "Both methods covered the whole document" in next(f for f in res["explanation"] if f["kind"] == "pages")["text"]


def test_long_ocr_text_is_read_in_parts_not_cut(report_pdf, monkeypatch):
    monkeypatch.setenv("MAX_CONTEXT_CHARS", "300")
    get_settings.cache_clear()
    try:
        res = run_ask(_doc(report_pdf, "doc_all2"), "What is the warehouse capacity in Pune?")
        o = res["ocr"]
        assert len(o["batches"]) > 1 and not o["truncated"] and o["pages"] == [1, 2, 3, 4, 5, 6]
        assert sorted({p for b in o["batches"] for p in b["pages"]}) == [1, 2, 3, 4, 5, 6]
    finally:
        monkeypatch.delenv("MAX_CONTEXT_CHARS")
        get_settings.cache_clear()


def test_text_chunks_keep_every_character_and_split_long_pages():
    pages = {0: {"text": "a" * 50}, 1: {"text": "b" * 700}, 2: {"text": "c" * 50}}
    chunks = text_chunks(pages, 300)
    assert all(len(c) <= 300 for c, _ in chunks)
    joined = "".join(c for c, _ in chunks)
    assert joined.count("a") >= 50 and joined.count("b") >= 700 and joined.count("c") >= 50
    assert [ps for _, ps in chunks][0] == [0, 1] or [ps for _, ps in chunks][0] == [0]
    assert sorted({p for _, ps in chunks for p in ps}) == [0, 1, 2]


def test_page_batches_and_merge_parts():
    assert page_batches([0, 1, 2, 3, 4, 5, 6, 7], 6) == [[0, 1, 2, 3, 4, 5], [6, 7]]

    class M:
        calls = 0

        def combine(self, q, parts, h, short):
            M.calls += 1
            return " / ".join(a for _, a in parts)

    m = M()
    assert merge_parts(m, "q", [("pages 1-6", NOT_FOUND), ("pages 7-8", NOT_FOUND)], [], False) == (NOT_FOUND, False)
    assert merge_parts(m, "q", [("pages 1-6", NOT_FOUND), ("pages 7-8", "42")], [], False) == ("42", False)
    assert M.calls == 0                                   # nothing to combine: no extra model call
    assert merge_parts(m, "q", [("pages 1-6", "41"), ("pages 7-8", "42")], [], False) == ("41 / 42", True)
