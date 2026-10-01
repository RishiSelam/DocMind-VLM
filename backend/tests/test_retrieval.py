from app.services.retrieval import BM25, rank_pages, select_pages, tokenize


def test_tokenize_drops_stopwords_only_when_asked():
    assert tokenize("What is the Total?") == ["what", "is", "the", "total"]
    assert tokenize("What is the Total?", drop_stop=True) == ["total"]


def test_rank_prefers_matching_page():
    texts = {0: "introduction and summary", 1: "warehouse capacity pallets Pune", 2: "headcount attrition people"}
    ranked = rank_pages("What is the warehouse capacity?", texts)
    assert ranked[0][0] == 1 and ranked[0][1] > 0


def test_all_zero_scores_fall_back_to_page_order():
    ranked = rank_pages("zzz", {2: "a", 0: "b", 1: "c"})
    assert [p for p, _ in ranked] == [0, 1, 2]


def test_select_pages_returns_reading_order():
    assert select_pages([(4, 3.0), (1, 2.0), (9, 1.0)], 2) == [1, 4]
    assert select_pages([(4, 3.0)], 0) == [4]  # cap floor of 1


def test_bm25_empty_corpus():
    assert BM25([]).score(["x"]) == []
    assert rank_pages("q", {}) == []
