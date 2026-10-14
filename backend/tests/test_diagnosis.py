from app.services import diagnosis as dg
from app.services import verification as v

REF = "Governance The audit committee chair is Meera Iyer. Revenue 48.2 51.0"
OCR = {0: {"text": "Governance\nThe audit committee chair is Meera lyer.\nRevenue | 48.2 | 51.0", "boxes": [
    {"text": "Governance", "score": 0.99, "x0": 10, "y0": 10, "x1": 200, "y1": 30},
    {"text": "The audit committee chair is Meera lyer.", "score": 0.93, "x0": 10, "y0": 50, "x1": 600, "y1": 70},
    {"text": "Revenue", "score": 0.98, "x0": 10, "y0": 100, "x1": 100, "y1": 120},
    {"text": "48.2", "score": 0.98, "x0": 300, "y0": 100, "x1": 350, "y1": 120},
    {"text": "51.0", "score": 0.98, "x0": 500, "y0": 100, "x1": 550, "y1": 120}]}}


def _res(va, oa, look_closer=None):
    r = {"vlm": {"answer": va, "error": None, "pages": [1], "ms": 1.0}, "ocr": {"answer": oa, "error": None, "pages": [1], "ms": 1.0},
         "verification": v.verify(va, oa)}
    if look_closer:
        r["xai"] = {"look_closer": look_closer}
    return r


def _why(a):
    return {w["who"]: w for w in a["why"]}


def test_near_needs_lookalike_swaps_for_numbers():
    assert dg.near("12000", ["12oo0"]) == "12oo0"
    assert dg.near("1994", ["1993"]) is None          # another year, not a misreading
    assert dg.near("iyer", ["lyer", "layer"]) == "lyer"


def test_ocr_misread_is_explained_with_the_characters_and_the_mechanism():
    a = dg.analyze(_res("Meera Iyer", "The audit committee chair is Meera lyer."), OCR, REF)
    assert a["better"] == "vlm" and a["basis"] == "textlayer"
    w = _why(a)
    assert w["ocr"]["cause"] == "misread"
    assert "“lyer” where the document has “Iyer”" in w["ocr"]["text"] and "“I” as “l”" in w["ocr"]["text"]
    assert "came from OCR, not from the text model" in w["ocr"]["text"]
    assert "could not affect it" in w["vlm"]["text"]
    assert a["why"][0]["who"] == "ocr"                     # the loser's cause comes first
    region = a["regions"][0]
    assert region["better"] == "vlm" and [c["word"] for c in region["words"]] == ["Meera", "Iyer"]
    iyer = region["words"][1]
    assert iyer["vision"]["status"] == "right" and iyer["ocr_text"] == {"status": "misread", "as": "lyer"}


def test_ocr_not_found_because_ocr_garbled_the_answer():
    a = dg.analyze(_res("Meera Iyer", "Not found in document."), OCR, REF)
    w = _why(a)
    assert a["better"] == "vlm" and w["ocr"]["cause"] == "misread" and "could not match it" in w["ocr"]["text"]


def test_both_values_printed_is_a_choice_not_a_reading_error():
    a = dg.analyze(_res("51.0", "48.2"), OCR, REF)
    assert a["better"] == "undecided"
    assert _why(a)["both"]["cause"] == "ambiguous"
    assert {r["better"] for r in a["regions"]} == {"vlm", "ocr"}


def test_without_a_reference_only_the_signature_is_named():
    a = dg.analyze(_res("Meera Iyer", "Meera lyer"), OCR, None)
    assert a["better"] == "undecided" and "likely, not proven" in _why(a)["ocr"]["text"]
    lc = {"transcription": "The audit committee chair is Meera Iyer."}
    b = dg.analyze(_res("Meera Iyer", "Meera lyer", lc), OCR, None)
    assert b["better"] == "vlm" and b["basis"] == "closer_look"


def _item(pred_v, pred_o, gold, *, in_ocr, types=(), v_ok=True, o_ok=False):
    def sc(ok, pred):
        from app.eval.metrics import score_item
        return score_item(pred, gold)
    return {"gold": gold, "vlm_pred": pred_v, "ocr_pred": pred_o, "vlm_scores": sc(v_ok, pred_v), "ocr_scores": sc(o_ok, pred_o),
            "answer_in_ocr": int(in_ocr), "extra": {"types": list(types)}}


def _page(*lines):
    boxes = [{"text": t, "score": 0.97, "x0": 10, "y0": 30 * i, "x1": 400, "y1": 30 * i + 20} for i, t in enumerate(lines)]
    return {"text": "\n".join(lines), "boxes": boxes}


def test_experiment_causes():
    # OCR ran the words together, the text model copied them
    d = dg.diagnose_item(_item("SEPTEMBER 17, 1969", "SEPTEMBER17,1969", ["september 17, 1969"], in_ocr=False),
                         _page("ORIENTATION MEETING", "SEPTEMBER17,1969"))
    assert d["better"] == "vlm" and d["ocr"]["cause"] == "spacing" and d["vlm"]["cause"] == "beyond_ocr"
    assert d["bucket"] == "read with errors by OCR"
    # the answer never reached OCR's text (handwriting)
    d = dg.diagnose_item(_item("412-624-2600", "Not found in document.", ["412-624-2600"], in_ocr=False, types=["handwritten"]),
                         _page("WHILE YOU WERE OUT", "Phone"))
    assert d["ocr"]["cause"] == "lost" and "handwritten" in d["ocr"]["text"] and d["bucket"] == "not read by OCR"
    # another number printed on the page: a wrong value, not a near miss
    d = dg.diagnose_item(_item("270.00", "15.00", ["270.00"], in_ocr=True, types=["table/list"]),
                         _page("Item | Amount", "Weekly report | 15.00", "TOTAL QUOTATION | 270.00"))
    assert d["ocr"]["cause"] == "wrong_value" and "table" in d["ocr"]["text"]
    # look-alike characters
    d = dg.diagnose_item(_item("August 1st, 1945", "August lst, 1945", ["August 1st, 1945"], in_ocr=True), _page("August 1st, 1945"))
    assert d["ocr"]["cause"] == "misread" and "“1” as “l”" in d["ocr"]["text"]


def test_run_explanation_names_causes():
    items = []
    for i in range(6):
        items.append({**_item("SEPTEMBER 17, 1969", "SEPTEMBER17,1969", ["september 17, 1969"], in_ocr=False),
                      "extra": {"types": ["layout"], "diagnosis": dg.diagnose_item(
                          _item("SEPTEMBER 17, 1969", "SEPTEMBER17,1969", ["september 17, 1969"], in_ocr=False),
                          _page("SEPTEMBER17,1969"))}})
    d = dg.diagnose_run(items)
    assert d["outcomes"] == {"vlm": 6} and d["causes"]["ocr"] == {"spacing": 6}
    text = " ".join(e["text"] for e in d["explanation"])
    assert "ran the words together" in text and "The vision model alone was right on 6" in text
    assert d["explanation"][0]["title"] == "The vision model did better"
