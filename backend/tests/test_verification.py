from app.services import verification as v


def test_agree_ignores_case_commas_and_punctuation():
    r = v.verify("Total due: $1,284.50", "total due $1284.50.")
    assert r["verdict"] == "consistent" and r["agreement"] == 1.0


def test_numeric_conflict_is_flagged_with_context():
    r = v.verify("Revenue was 48.2 million.", "Revenue was 42.8 million.")
    assert r["verdict"] == "conflict"
    assert "48.2" in r["numbers_only_vlm"] and "42.8" in r["numbers_only_ocr"]


def test_bare_number_mismatch_is_conflict():
    assert v.verify("1490", "1940")["verdict"] == "conflict"


def test_partial_and_only_claims():
    r = v.verify("The meeting is in Room B12. It starts at 10 AM.", "The meeting is in Room B12.")
    labels = [p["label"] for p in r["pairs"]]
    assert "agree" in labels and "only_vlm" in labels
    assert r["verdict"] in ("partial", "disagree")


def test_not_found_handling():
    both = v.verify("Not found in document.", "Not found in document.")
    assert both["verdict"] == "consistent"
    one = v.verify("Not found in document.", "INV-2041")
    assert one["verdict"] == "conflict" and "Only the OCR+LLM pipeline" in one["note"]


def test_ocr_support_found_near_missing():
    text = "Invoice number INV-2O41 total 1284.50 Northwind Traders"
    r = v.ocr_support("Northwind Traders billed INV-2041 and 9999", text)
    assert "northwind" in r["found"] and "traders" in r["found"]
    assert any(n["token"] == "inv-2041" for n in r["near"])       # OCR read 0 as O
    assert "9999" in r["missing"]
    assert 0 < r["coverage"] < 1


def test_split_claims_bullets_and_sentences():
    assert v.split_claims("- one\n- two. Three!") == ["one", "two.", "Three!"]
    assert v.split_claims("") == []


def _p(answer, ms=100.0, pages=(1,), error=None):
    return {"answer": answer, "ms": ms, "pages": list(pages), "error": error}


LAYER = "Pune warehouse capacity 12,000 pallets. Revenue 48.2 million."


def test_reference_support_is_strict_about_misreadings():
    assert v.reference_support("capacity of 12000 pallets", LAYER) == 1.0
    assert v.reference_support("capacity of 12oo0 pallets", LAYER) < 1.0   # a near match is not support
    assert v.reference_support("Not found in document.", LAYER) is None


def test_scorecard_picks_the_answer_the_text_layer_supports():
    c = v.scorecard(_p("12000 pallets", ms=900), _p("12oo0 pallets", ms=1500), LAYER, 0.95, 6)
    assert c["winner"] == "vlm" and c["faster"] == "vlm" and c["reference"] == "textlayer"
    assert c["vlm"]["support"] == 1.0 and c["ocr"]["support"] == 0.5


def test_scorecard_tie_and_one_sided():
    assert v.scorecard(_p("12000 pallets"), _p("12,000 pallets"), LAYER, None, 1)["winner"] == "tie"
    assert v.scorecard(_p("Not found in document."), _p("12000 pallets"), LAYER, None, 1)["winner"] == "ocr"
    assert v.scorecard(_p("Not found in document."), _p("9999 widgets"), LAYER, None, 1)["winner"] == "tie"


def test_scorecard_without_reference_refuses_to_pick():
    c = v.scorecard(_p("12000"), _p("12oo0"), None, None, 1)
    assert c["winner"] == "unknown" and c["vlm"]["support"] is None
    assert v.scorecard(_p("12000"), None, LAYER, None, 1)["winner"] is None
