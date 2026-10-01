from app import db


def test_all_messages_are_kept_in_order():
    db.init_db()
    conv = db.create_conversation("t", None)
    for i in range(250):
        db.add_message(conv["id"], "user" if i % 2 == 0 else "assistant", f"m{i}", {"i": i})
    msgs = db.list_messages(conv["id"])
    assert len(msgs) == 250
    assert [m["content"] for m in msgs][:3] == ["m0", "m1", "m2"] and msgs[-1]["payload"]["i"] == 249


def test_delete_conversation_removes_messages():
    conv = db.create_conversation("gone", None)
    db.add_message(conv["id"], "user", "x")
    db.delete_conversation(conv["id"])
    assert db.get_conversation(conv["id"]) is None and db.list_messages(conv["id"]) == []


def test_experiment_ids_increment_and_items_roundtrip():
    a = db.create_experiment("a", {"k": 1}, 2)
    b = db.create_experiment("b", {"k": 2}, 2)
    assert a["id"].startswith("EXP-") and int(b["id"][4:]) == int(a["id"][4:]) + 1
    db.add_experiment_item(a["id"], 0, {"qid": "1", "question": "q", "gold": ["x"], "vlm_pred": "x", "ocr_pred": "y",
                                        "vlm_scores": {"em": 1}, "ocr_scores": {"em": 0}, "vlm_ms": 1.0, "ocr_ms": 2.0,
                                        "answer_in_ocr": True, "agree": False})
    items = db.list_experiment_items(a["id"])
    assert items[0]["gold"] == ["x"] and items[0]["answer_in_ocr"] == 1 and items[0]["agree"] == 0
    db.delete_experiment(a["id"])
    assert db.get_experiment(a["id"]) is None and db.list_experiment_items(a["id"]) == []
