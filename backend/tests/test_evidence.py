from app.sample_data import make_pdf
from app.services import evidence as ev
from app.services import verification as v
from app.services.prompts import NOT_FOUND


def test_geometry_helpers():
    a = {"page": 0, "box": [0.1, 0.1, 0.5, 0.2]}
    assert ev.same_place(a, [{"page": 0, "box": [0.12, 0.11, 0.45, 0.19]}]) == "same place"
    assert ev.same_place(a, [{"page": 0, "box": [0.1, 0.7, 0.5, 0.8]}]) == "same page"
    assert ev.same_place(a, [{"page": 2, "box": [0.1, 0.1, 0.5, 0.2]}]) == "different pages"
    assert ev.same_place(None, []) is None
    r = ev.region([0.98, 0.99, 0.99, 1.0])
    assert 0 <= r[0] < r[2] <= 1 and 0 <= r[1] < r[3] <= 1 and r[2] - r[0] >= 0.25 - 1e-9
    assert ev.survives("Meera Iyer", "The chair is Meera Iyer.") and not ev.survives("Meera Iyer", NOT_FOUND)
    assert ev.cover("Meera lyer", "the chair is Meera Iyer") == 0.5


class FakeVLM:
    def __init__(self, ref_box):
        self.ref_box = ref_box
    def locate(self, images, pages, question, answer):
        return {"page": pages[-1], "box": self.ref_box, "raw": ""}
    def transcribe(self, image):
        return "The audit committee chair is Meera Iyer."
    def generate(self, images, labels, question, history, short, aux_texts=None, part=None):
        return NOT_FOUND                     # the evidence was masked out: the answer is gone


class FakeLLM:
    def generate(self, context, question, history, short, part=None):
        return "The audit committee chair is Meera lyer."   # unchanged without the evidence line


class Hub:
    def __init__(self, ref_box):
        self.vlm, self.llm, self.demo = FakeVLM(ref_box), FakeLLM(), True


def test_explain_finds_evidence_looks_closer_and_scores_trust(tmp_path):
    path = str(make_pdf(tmp_path / "gov.pdf", [["Cover"], ["Governance", "The audit committee chair is Meera Iyer."]]))
    ref = ev.reference_evidence(path, "Meera Iyer")
    assert ref and ref[0]["page"] == 1
    box = [ref[0]["box"][0] - 0.01, ref[0]["box"][1] - 0.01, ref[0]["box"][2] + 0.01, ref[0]["box"][3] + 0.01]
    va, oa = "Meera Iyer", "The audit committee chair is Meera lyer."
    vlm = {"answer": va, "pages": [1, 2], "batches": [{"pages": [1, 2], "answer": va}], "ms": 1.0, "error": None}
    ocr = {"answer": oa, "pages": [1, 2], "ms": 1.0, "error": None}
    result = {"vlm": vlm, "ocr": ocr, "verification": v.verify(va, oa)}
    layer = "Cover Governance The audit committee chair is Meera Iyer."
    result["scorecard"] = v.scorecard(vlm, ocr, layer, 0.98, 2)
    # OCR boxes in 200-DPI pixels of a 612x792 pt page (1700 x 2200 px)
    ocr_pages = {1: {"text": "Governance\nThe audit committee chair is Meera lyer.",
                     "boxes": [{"text": "The audit committee chair is Meera lyer.", "score": 0.97,
                                "x0": box[0] * 1700, "y0": box[1] * 2200, "x1": box[2] * 1700, "y1": box[3] * 2200}]}}
    x = ev.explain({"path": path}, result, ocr_pages, "Who chairs the audit committee?", False, Hub(box))
    assert x["vision"]["page"] == 1 and x["ocr"][0]["page"] == 1
    assert x["agreement"] == "same place" and x["vision_at_reference"] == "same place"
    assert x["look_closer"]["supports"] == "vlm"
    assert x["faithfulness"]["vlm"]["survived"] is False and x["faithfulness"]["ocr"]["survived"] is True
    t = x["trust"]
    assert t["recommended"] == "vlm" and t["level"] in ("medium", "high") and any("closer look" in r for r in t["reasons"])


def test_long_answers_are_not_located_or_scored(tmp_path):
    path = str(make_pdf(tmp_path / "s.pdf", [["Report"]]))
    long = "This document describes many things. " * 10
    r = {"vlm": {"answer": long}, "ocr": {"answer": long}, "verification": v.verify(long, long)}
    x = ev.explain({"path": path}, r, {}, "Summarize", False, Hub([0, 0, 1, 1]))
    assert x["skipped"] and x["trust"]["level"] == "not rated" and x["vision"] is None


def test_arbitrate_uses_only_the_disputed_words():
    r = ev.arbitrate("Meera Iyer", "The audit committee chair is Meera lyer.", "The audit committee chair is Meera Iyer.")
    assert r["supports"] == "vlm" and r["ocr_not_seen"] == ["lyer"] and r["vision_confirmed"] == ["iyer"]
    assert ev.arbitrate("12000", "12oo0", "capacity of 12oo0 pallets")["supports"] == "ocr"
    assert ev.arbitrate("12000", "12oo0", "capacity unreadable")["supports"] is None
