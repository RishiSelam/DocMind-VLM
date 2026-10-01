import time


def _upload(client, path, name=None):
    with open(path, "rb") as f:
        r = client.post("/api/documents", files={"file": (name or path.name, f)})
    return r


def test_health_reports_demo_mode(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["demo_mode"] is True and h["ocr_engine"] == "rapidocr"


def test_upload_rejects_unsupported_type(client, tmp_path):
    p = tmp_path / "evil.exe"
    p.write_bytes(b"MZ")
    r = _upload(client, p)
    assert r.status_code == 400 and "Unsupported" in r.json()["detail"]


def test_upload_rejects_corrupt_pdf(client, tmp_path):
    p = tmp_path / "broken.pdf"
    p.write_bytes(b"this is not a pdf")
    assert _upload(client, p).status_code == 400


def test_document_lifecycle_and_page_endpoints(client, report_pdf):
    doc = _upload(client, report_pdf).json()
    assert doc["n_pages"] == 6 and doc["filename"] == "report.pdf"
    assert any(d["id"] == doc["id"] for d in client.get("/api/documents").json())
    img = client.get(f"/api/documents/{doc['id']}/pages/1/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG"
    assert client.get(f"/api/documents/{doc['id']}/pages/99/image").status_code == 404
    ocr = client.get(f"/api/documents/{doc['id']}/pages/3/ocr").json()
    assert "Pune" in ocr["text"] and ocr["audit"]["ocr_vs_layer_similarity"] > 0.7 and ocr["boxes"]
    assert ocr["render_dpi"] == 200  # the UI draws box overlays against a render at this dpi
    ret = client.get(f"/api/documents/{doc['id']}/retrieve", params={"q": "employee headcount"}).json()
    assert ret["ranked"][0]["page"] == 5 and ret["corpus"] == "textlayer"
    assert client.delete(f"/api/documents/{doc['id']}").status_code == 200
    assert client.get(f"/api/documents/{doc['id']}").status_code == 404


def test_background_ocr_job_finishes(client, report_pdf):
    doc = _upload(client, report_pdf).json()
    client.post(f"/api/documents/{doc['id']}/ocr")
    for _ in range(120):
        st = client.get(f"/api/documents/{doc['id']}/ocr/status").json()
        if st["status"] == "done":
            break
        time.sleep(0.5)
    assert st["status"] == "done" and st["cached_pages"] == 6


def test_ask_creates_conversation_and_stores_full_history(client, report_pdf):
    doc = _upload(client, report_pdf).json()
    r1 = client.post("/api/ask", json={"doc_id": doc["id"], "question": "What is the employee headcount?"}).json()
    cid = r1["conversation_id"]
    p = r1["assistant_message"]["payload"]
    assert "342" in p["vlm"]["answer"] and p["ocr"]["answer"] and p["verification"]["verdict"]
    assert p["demo"] is True and p["timings"]["total_ms"] > 0 and p["retrieval"]["ranked"]
    for i in range(4):  # follow-ups reuse the conversation; nothing is dropped
        client.post("/api/ask", json={"conversation_id": cid, "question": f"What is the attrition? (#{i})"})
    conv = client.get(f"/api/conversations/{cid}").json()
    assert len(conv["messages"]) == 10 and conv["messages"][0]["role"] == "user"
    md = client.get(f"/api/conversations/{cid}/export", params={"format": "md"})
    assert md.status_code == 200 and "**VLM:**" in md.text and md.text.count("**You:**") == 5
    assert client.get(f"/api/conversations/{cid}/export").json()["id"] == cid
    assert client.delete(f"/api/conversations/{cid}").status_code == 200


def test_ask_validation(client):
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 400          # no document
    assert client.post("/api/ask", json={"doc_id": "nope", "question": "hi"}).status_code == 404
    assert client.post("/api/ask", json={"doc_id": "x", "question": ""}).status_code == 422


def test_ask_mode_vlm_only(client, invoice_png):
    doc = _upload(client, invoice_png).json()
    r = client.post("/api/ask", json={"doc_id": doc["id"], "question": "invoice number", "mode": "vlm"}).json()
    p = r["assistant_message"]["payload"]
    assert p["ocr"] is None and p["vlm"]["answer"]


def test_experiment_end_to_end(client, eval_jsonl):
    ds = client.get("/api/eval/datasets").json()
    assert any(d["name"].endswith("sample.jsonl") and d["n"] == 7 for d in ds)
    r = client.post("/api/experiments", json={"name": "smoke", "dataset": "sample/sample.jsonl", "limit": 4})
    assert r.status_code == 200
    exp = r.json()
    assert exp["id"].startswith("EXP-") and exp["config"]["demo_mode"] is True and exp["config"]["prompt_version"]
    for _ in range(240):
        cur = client.get(f"/api/experiments/{exp['id']}").json()
        if cur["status"] in ("finished", "failed"):
            break
        time.sleep(0.5)
    assert cur["status"] == "finished", cur.get("error")
    assert cur["progress_done"] == 4 and len(cur["items"]) == 4
    m = cur["metrics"]
    assert m["n"] == 4 and {"em", "anls", "latency_ms"} <= set(m["vlm"]) and "anls_vlm_minus_ocr" in m["paired"]
    assert m["ocr_answer_coverage"] is not None
    csv = client.get(f"/api/experiments/{exp['id']}/csv")
    assert csv.status_code == 200 and csv.text.splitlines()[0].startswith("qid,question")
    assert len(csv.text.strip().splitlines()) == 5
    assert client.delete(f"/api/experiments/{exp['id']}").status_code == 200


def test_experiment_missing_dataset(client):
    assert client.post("/api/experiments", json={"name": "x", "dataset": "nope.jsonl"}).status_code == 404


def test_experiment_resume_skips_finished_items(client, eval_jsonl):
    from app import db
    from app.eval import runner

    exp = client.post("/api/experiments", json={"name": "resume", "dataset": "sample/sample.jsonl", "limit": 2}).json()
    for _ in range(240):
        if client.get(f"/api/experiments/{exp['id']}").json()["status"] in ("finished", "failed"):
            break
        time.sleep(0.5)
    before = {i["idx"]: i["vlm_pred"] for i in db.list_experiment_items(exp["id"])}
    runner.run_experiment(exp["id"], resume=True)
    after = {i["idx"]: i["vlm_pred"] for i in db.list_experiment_items(exp["id"])}
    assert before == after and db.get_experiment(exp["id"])["status"] == "finished"


def test_system_metrics_after_requests(client):
    m = client.get("/api/system/metrics").json()
    assert m["n_requests"] > 0 and m["total_ms"]["n"] > 0 and "gpu" in m
