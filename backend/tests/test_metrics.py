from app.eval import metrics as m


def test_levenshtein():
    assert m.levenshtein("kitten", "sitting") == 3
    assert m.levenshtein("", "abc") == 3
    assert m.levenshtein("same", "same") == 0


def test_anls_threshold_and_best_gold():
    assert m.anls("Room B12", ["room b12"]) == 1.0
    assert m.anls("Room B1", ["room b12"]) > 0.8
    assert m.anls("completely different", ["room b12"]) == 0.0      # NL >= 0.5 -> 0
    assert m.anls("48.2", ["1490", "48.2"]) == 1.0                  # best over golds
    assert m.anls("x", []) == 0.0


def test_em_and_contains():
    assert m.exact_match(" $1,284.50. ", ["$1,284.50"]) == 1.0
    assert m.exact_match("1284.50", ["$1,284.50"]) == 0.0
    assert m.contains_match("The total is $1,284.50 today", ["$1,284.50"]) == 1.0
    assert m.contains_match("nothing here", ["$1,284.50"]) == 0.0


def test_score_item_abstain_and_error():
    assert m.score_item("Not found in document.", ["x"])["abstain"] == 1.0
    assert m.score_item(None, ["x"])["error"] == 1.0
    assert m.score_item("x", ["x"])["em"] == 1.0


def test_answer_in_text_handles_table_pipes():
    assert m.answer_in_text(["Q2 | 48.2"], "Q1 | 41.7\nQ2 | 48.2")
    assert not m.answer_in_text(["99"], "Q1 41.7")


def test_paired_bootstrap_and_mcnemar():
    a, b = [1.0] * 20, [0.0] * 20
    r = m.paired_bootstrap(a, b, n=200)
    assert r["diff"] == 1.0 and r["ci_low"] == 1.0
    z = m.paired_bootstrap([], [])
    assert z["diff"] == 0.0
    t = m.mcnemar([True] * 10 + [False] * 2, [False] * 10 + [True] * 2)
    assert t["a_only"] == 10 and t["b_only"] == 2 and 0 < t["p_value"] < 0.1
    assert m.mcnemar([True], [True])["p_value"] == 1.0


def test_aggregate_shapes():
    it = {"vlm_scores": {"em": 1, "anls": 1, "contains": 1}, "ocr_scores": {"em": 0, "anls": 0, "contains": 0},
          "vlm_ms": 100, "ocr_ms": 50, "answer_in_ocr": False, "agree": False}
    agg = m.aggregate([it, it])
    assert agg["n"] == 2 and agg["vlm"]["anls"] == 1 and agg["ocr"]["anls"] == 0
    assert agg["ocr_answer_coverage"] == 0.0 and agg["ocr_loss_cases"] == 2 and agg["disagreement_rate"] == 1.0
    assert m.aggregate([]) == {"n": 0}
