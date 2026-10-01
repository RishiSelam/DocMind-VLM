from app.services import verification as v
from app.services.explain import explain

LAYER = "Pune warehouse capacity 12,000 pallets. Revenue 48.2 million."


def _result(vlm_ans, ocr_ans, reference, *, vlm_ms=900.0, ocr_ms=1500.0, n=6, vlm_pages=(1, 2, 3), acc=0.97, missed=4):
    vlm = {"answer": vlm_ans, "ms": vlm_ms, "pages": list(vlm_pages), "error": None}
    ocr = {"answer": ocr_ans, "ms": ocr_ms, "pages": list(range(1, n + 1)), "error": None}
    audit = [{"page": 0, "ocr_vs_layer_similarity": acc, "layer_tokens_missed_by_ocr": missed}] if reference else []
    r = {"vlm": vlm, "ocr": ocr, "audit": audit, "verification": v.verify(vlm_ans, ocr_ans),
         "timings": {"ocr_ms": ocr_ms - 400, "ocr_wall_ms": ocr_ms - 400, "llm_ms": 400.0}}
    r["scorecard"] = v.scorecard(vlm, ocr, reference, acc if reference else None, n)
    return r


def _by_kind(fs):
    return {f["kind"]: f for f in fs}


def test_ocr_misread_repaired_by_text_model_is_explained():
    r = _result("12000 pallets", "12000 pallets", LAYER)
    f = _by_kind(explain(r, "Pune warehouse capacity 12oo0 pallets", LAYER))
    assert f["verdict"]["title"].startswith("Both methods agree, and the document backs them")
    assert "repaired the OCR error" in f["recognition"]["text"] and "“12000”" in f["recognition"]["text"]
    assert "The vision model read “12000”" in f["recognition"]["text"]
    assert "97.0%" in f["recognition"]["text"] and "4 words" in f["recognition"]["text"]


def test_vision_winner_and_partial_pages():
    r = _result("12000 pallets", "12oo0 pallets", LAYER)
    f = _by_kind(explain(r, "Pune warehouse capacity 12oo0 pallets", LAYER))
    assert f["verdict"]["title"] == "The vision model gave the better-supported answer"
    assert "100%" in f["verdict"]["text"] and "50%" in f["verdict"]["text"]
    assert "saw 3 of 6 pages" in f["pages"]["text"]
    assert "The vision model was 0.6 s faster" in f["speed"]["text"]


def test_image_without_reference_does_not_claim_a_winner():
    r = _result("$1,284.50", "$1,284.50", None, n=1, vlm_pages=(1,))
    f = _by_kind(explain(r, "Total due $1,284.50", None))
    assert "cannot be checked" in f["verdict"]["title"]
    assert "pages" not in f                       # single page: nothing to say about coverage
    r = _result("$1,284.50", "$1,824.50", None, n=1, vlm_pages=(1,))
    f = _by_kind(explain(r, "Total due $1,824.50", None))
    assert "disagree" in f["verdict"]["title"] and "Either OCR missed it or the vision model is wrong" in f["recognition"]["text"]


def test_invented_value_is_flagged():
    r = _result("12000 pallets", "15000 pallets", LAYER)
    f = _by_kind(explain(r, "Pune warehouse capacity 12000 pallets", LAYER))
    assert "“15000”" in f["recognition"]["text"] and "unsupported" in f["recognition"]["text"]


def test_similar_times_are_not_called_faster():
    r = _result("$1,284.50", "$1,284.50", None, vlm_ms=1250.0, ocr_ms=1320.0, n=1, vlm_pages=(1,))
    f = _by_kind(explain(r, "Total due $1,284.50", None))
    assert "about the same time" in f["speed"]["text"] and "faster" not in f["speed"]["text"].split("OCR is cached")[0]


def test_both_not_found_is_reported_as_such():
    nf = "Not found in document."
    f = _by_kind(explain(_result(nf, nf, LAYER), "Pune warehouse", LAYER))
    assert f["verdict"]["title"] == "Both methods say the answer is not in the document"
    assert "n/a" not in f["verdict"]["text"]


def test_failed_ocr_pipeline_makes_no_recognition_claims():
    r = _result("12000 pallets", None, LAYER)
    r["ocr"]["error"] = "RuntimeError: CUDA out of memory"
    r["scorecard"] = v.scorecard(r["vlm"], r["ocr"], LAYER, None, 6)
    f = _by_kind(explain(r, None, LAYER))
    assert f["verdict"]["title"] == "The vision model gave the better-supported answer" and "the OCR pipeline failed" in f["verdict"]["text"]
    assert "recognition" not in f


def test_currency_sign_does_not_decide_support():
    assert v.reference_support("Total due: $1,284.50", "Total due 1,284.50 USD") == 1.0


def test_one_missed_word_is_singular():
    r = _result("12000 pallets", "12000 pallets", LAYER, missed=1)
    assert "about 1 word of the document's text was missed" in _by_kind(explain(r, "12000 pallets", LAYER))["recognition"]["text"]


def test_scan_ocr_done_during_ranking_is_not_called_a_cache_hit():
    r = _result("12000 pallets", "12000 pallets", None, vlm_ms=5500.0, ocr_ms=6400.0, vlm_pages=(1, 2, 3))
    r["retrieval"] = {"corpus": "ocr"}
    r["timings"] = {"retrieval_ms": 6264.7, "ocr_ms": 5491.2, "ocr_wall_ms": 2.6, "llm_ms": 941.3}
    text = _by_kind(explain(r, "12oo0 pallets", None))["speed"]["text"]
    assert "reused from the cache" not in text and "OCR ran at the start of this request to rank the pages (6.3 s)" in text
    assert "The vision model also waited for it" in text
    r["timings"] = {"retrieval_ms": 5.0, "ocr_ms": 5491.2, "ocr_wall_ms": 2.6, "llm_ms": 941.3}
    r["retrieval"] = {"corpus": "textlayer"}
    assert "reused from the cache" in _by_kind(explain(r, "12oo0 pallets", None))["speed"]["text"]


def test_pages_finding_mentions_parts_when_read_in_batches():
    r = _result("12000 pallets", "12000 pallets", LAYER, n=8, vlm_pages=range(1, 9))
    r["vlm"]["batches"] = [{"pages": [1, 2, 3, 4, 5, 6]}, {"pages": [7, 8]}]
    r["ocr"]["batches"] = [{"pages": list(range(1, 9))}]
    r["scorecard"] = v.scorecard(r["vlm"], r["ocr"], LAYER, None, 8)
    text = _by_kind(explain(r, "12000 pallets", LAYER))["pages"]["text"]
    assert "whole document (8 pages)" in text and "the vision model in 2 parts" in text and "OCR pipeline in" not in text
    assert "only one part found an answer" in text
    r["vlm"]["combined"] = True
    assert "the vision model combined the answers" in _by_kind(explain(r, "12000 pallets", LAYER))["pages"]["text"]


def test_ocr_is_capitalised_correctly_in_titles():
    r = _result("12oo0 pallets", "12000 pallets", LAYER)
    assert _by_kind(explain(r, "12000 pallets", LAYER))["verdict"]["title"] == "The OCR pipeline gave the better-supported answer"


def test_incomplete_answer_is_called_out():
    r = _result("The Pune warehouse has a capacity of 12000 pallets.",
                "The Pune warehouse has a capacity of 12000 pallets. Revenue was 48.2 million.", LAYER)
    f = _by_kind(explain(r, LAYER, LAYER))
    assert f["verdict"]["title"] == "The OCR pipeline gave the more complete answer"
    assert "leaves out: “Revenue was 48.2 million.”" in f["verdict"]["text"]


def test_quoted_words_keep_the_answer_s_capitalisation():
    ref = "The audit committee chair is Meera Iyer."
    r = _result("Meera Iyer", "The audit committee chair is Meera lyer.", ref)
    text = _by_kind(explain(r, "The audit committee chair is Meera lyer.", ref))["recognition"]["text"]
    assert "The vision model read “Iyer”" in text
