# DocMind v2

Ask a document a question two ways and see where the answers differ.

- **Vision pipeline:** page images go to Qwen2.5-VL-7B-Instruct.
- **OCR pipeline:** OCR text goes to Qwen2.5-7B-Instruct. OCR is RapidOCR by default (Paddle-family models on ONNX Runtime, so no `paddlepaddle` install).
- **Three-Section Output Architecture:**
  1. **Section 1 · VLM:** Direct multimodal visual reading, visual evidence crops, coordinates, and faithfulness testing.
  2. **Section 2 · OCR Text:** OCR model answer, complete latency split, and an interactive **Extracted OCR Text Viewer** displaying raw extracted text with page headers and keyword highlights.
  3. **Section 3 · Combined Output & Explainability:** A **Unified Combined Summary** merging the information from both methods into a single coherent answer, accompanied by side-by-side contrast cards, causal diagnostic analysis, look-closer verification, and comparative performance charts.
- **Verification & Diagnosis:** Answers are verified claim by claim, audited for OCR text loss, and evaluated across root cause taxonomies (glyph misreads, layout flattening, LLM repairs).
- **Evaluation:** DocVQA-style runs with EM, ANLS, paired bootstrap, McNemar, and an OCR answer-coverage ceiling. Runs are saved after every question and can be resumed.

```
docmind/
  backend/    FastAPI + SQLite (app/, scripts/, tests/)
  frontend/   Next.js 14 + Tailwind (Workbench at /ask, Research at /research, History at /history)
  data/       uploads, sqlite file, eval sets, sample PDF
  .env.example
```

## 1. Try it on any machine (demo mode, no GPU)

`DEMO_MODE=true` is the default. PDF parsing, OCR, BM25 page retrieval, verification, the database and the UI are all real. The two "models" are text-matching stand-ins, and the UI says so. Use this to check the app runs, not to judge Qwen.

**Linux / macOS**
```bash
cd docmind/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_data.py      # sample 6-page PDF + 7-question eval set
python scripts/doctor.py                # must end with "All required checks passed."
uvicorn app.main:app --port 8000
```

**Windows (PowerShell)**
```powershell
cd docmind\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1            # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python scripts\make_sample_data.py
python scripts\doctor.py
uvicorn app.main:app --port 8000
```

**Second terminal, frontend** (Node 18.17+):
```bash
cd docmind/frontend
npm install
npm run dev
```
Open http://localhost:3000, upload `data/samples/annual_report.pdf`, and ask "What is the warehouse capacity?". Switch to **Detailed** view (or Research at `/research`) for the claim ledger, page-retrieval bars, OCR audit and timings.

Under every question, outputs are organized into three dedicated sections:
- **Section 1 (VLM Output):** Multimodal answer, visual attention coordinates on the page image, high-resolution crop inspection, and counterfactual faithfulness verification.
- **Section 2 (OCR Text Output):** OCR pipeline answer, latency breakdown (OCR extraction vs text LLM), and the **Extracted OCR Text Viewer** showing the exact text extracted by RapidOCR with page demarcations and matching keyword highlights.
- **Section 3 (Combined Output & Explainability):**
  - **Unified Combined Summary:** An intelligent synthesis merging all information, figures, and details extracted by both methods into one complete answer.
  - **Verdict & Recommendation:** Recommended answer and transparent rule-based trust score (High / Medium / Low).
  - **Side-by-Side Comparison:** Direct contrast cards highlighting word-level differences.
  - **Causal Diagnosis & Look-Closer:** Explains why one method did better (misread glyphs, dropped tokens, repaired text), accompanied by zoomed crop inspection and word-by-word truth tables.
  - **Comparative Charts:** Grounding support %, document read coverage %, OCR text similarity %, and latency breakdown.

Same check without the UI (from the repo root):
```bash
curl -F file=@data/samples/annual_report.pdf localhost:8000/api/documents     # returns {"id": "doc_...", "n_pages": 6, ...}
curl -H 'Content-Type: application/json' -d '{"doc_id":"doc_...","question":"What is the warehouse capacity?"}' localhost:8000/api/ask
```
`/api/ask` returns `{conversation_id, user_message, assistant_message}`. The results are in `assistant_message.payload`: `vlm`, `ocr`, `combined_summary`, `verification`, `scorecard`, `timings`.

## 2. Real models on the GPU workstation

```bash
cd ~/MMAI/docmind/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # pick the wheel that matches `nvidia-smi`; torchvision is required
pip install -r requirements-gpu.txt
cp ../.env.example ../.env                                               # then edit: DEMO_MODE=false
python scripts/doctor.py                                                 # checks CUDA, free VRAM, library versions, cached weights
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Weights are read from the normal Hugging Face cache with `OFFLINE=true`. If they are somewhere else, `export HF_HOME=/path/to/cache` first. To fetch them on a machine with internet: `python scripts/download_models.py`.
- Both models load in 4-bit nf4 **at startup**. If less than `MIN_FREE_VRAM_GB` (default 12) is free, or the load runs out of memory, the server exits with a message instead of starting half-working. The A4000 is shared, so check `nvidia-smi` first. To run one model at a time set `ENABLE_LLM=false` or `ENABLE_VLM=false` and lower `MIN_FREE_VRAM_GB`.
- If a question runs out of memory, lower `VLM_PAGE_CAP` or `VLM_MAX_PIXELS`; the error is shown in the UI and the other pipeline still answers.
- Frontend from another machine: set `NEXT_PUBLIC_API_URL=http://<workstation>:8000` in `frontend/.env.local` and add the UI's address to `CORS_ORIGINS` (see `.env.example`).

### Saving the history of your documents

Every question and both answers are kept in the database (`data/docmind.sqlite3`), and the history belongs to the file's content, not to one upload:
- Uploading a file you have used before opens it with all its earlier conversations, including ones from copies you have since deleted.
- Asking a question you already asked about that file, with the same settings, shows the saved answer instantly ("Answered from history", with **Ask again** to recompute). Follow-up questions inside a conversation are always computed fresh, because they depend on what came before. Changing a model, the prompt version, the OCR engine or the page settings means old answers are no longer reused.

To keep a copy outside the database:
- In the app: open a document and press **Download history** (Markdown; **JSON** next to it has every field).
- For all documents at once: `cd backend && python scripts/export_history.py` writes one `.md` and one `.json` per document plus `index.md` to `data/exports/history-<date>/`. It only reads the database.

`data/exports/` is in `.gitignore`, because it contains your documents' content.

### Explainability: where each answer came from, and how far to trust it

For short factual answers (a summary has no single place on the page), each answer gets a **Where the answer came from** card:
- **Evidence on the page.** The vision model is asked where it read the answer (Qwen2.5-VL grounding; with several pages it first picks the page, then marks the region on that page alone). OCR's evidence is the OCR lines holding the answer's words. For PDFs with embedded text, a dashed box marks where the document itself prints the answer.
- **Evidence agreement.** Did both methods look at the same place?
- **Look closer.** When the answers differ, the region is enlarged and the vision model transcribes it; only the disputed words are compared ("12oo0" vs "12000").
- **Faithfulness.** The evidence is removed (masked in the image, deleted from the OCR text) and the question asked again. If the answer survives, the highlight was not what it relied on.
- **Trust.** A transparent score from these signals, listed as reasons under the verdict (High / Medium / Low). It is a rule, not a learned model; experiments measure whether it predicts wrong answers (AUROC and accuracy of the most-trusted answers, on the Experiments page).

This adds about 4–10 s per short question. Turn parts off with `EXPLAIN`, `LOOK_CLOSER`, `FAITHFULNESS` in `.env`.

### Which method did better, and why

Every answer, and every question in an experiment, says which method did better, the cause behind the other one's failure, and which part of the page it happened on (`backend/app/services/diagnosis.py`):
- **Causes.** Misread characters ("lyer" for "Iyer", with the look-alike characters named), words run together ("SEPTEMBER17,1969"), answer never reached the OCR text (handwriting, figures, photos), picked another value printed on the page (tables and forms lose their row/column structure in OCR text), said not found, only part of the answer, not printed on the page. Each comes with the mechanism that produces it, not just the score.
- **Part of the page.** For a question: the OCR line holding the answer, cropped from the page, with what the vision model, OCR's text and the OCR pipeline's answer made of each word. For an experiment: accuracy split by how OCR read the answer's place (clearly, low confidence, with errors, not at all), by the layout around it (table row, label and value, running text) and by DocVQA question type, with each method's main failure.
- **Judge.** In experiments, the correct answers. For a single question, the PDF's own text, or the closer look's re-reading on scans; with neither, the analysis names what the difference looks like but does not pick a side.

Causes are assigned by fixed rules and are the most likely mechanism, not a proof. Older runs and saved answers get the analysis when opened, from the cached OCR; no model is re-run. Experiment CSVs have `better`, `vlm_cause`, `ocr_cause`, `answer_region` and the explanations.

### The website

`/` is a landing page; the workspace is `/ask`, plus `/history`, `/research` (Experiments) and `/about` (How it works). There is a light/dark switch in the header (it follows the system setting until you choose), and fonts are self-hosted, so the site works offline.

## 3. VS Code

Open the `docmind/` folder. Select the interpreter `backend/.venv`. `Terminal > Run Task`:

| Task | Does |
|---|---|
| `docmind: run both` | backend on :8000 and frontend on :3000 |
| `backend: tests` | `python -m pytest` |
| `backend: doctor` | preflight check |

`Run and Debug` has "Backend (debug)" and "Eval CLI (sample)".

## 4. Evaluation

From the UI: **Research > New experiment**. From a terminal (same code path). The CLI loads its own copy of both models, so with real models on a 16 GB card stop the backend first, or use the UI, which reuses the loaded models:
```bash
cd backend
python scripts/eval_docvqa.py --dataset sample/sample.jsonl --name smoke
python scripts/eval_docvqa.py --resume EXP-0001            # continue an interrupted run
```
Real DocVQA (from the local Hugging Face cache, or with `pip install datasets` and internet once):
```bash
pip install pyarrow                                        # reads the DocVQA copy in ~/.cache/huggingface (no network needed then)
python scripts/prepare_docvqa.py --limit 200               # random sample (fixed seed) -> data/eval/docvqa_val/, keeps question types
python scripts/eval_docvqa.py --dataset docvqa_val/docvqa_val.jsonl --limit 200 --name docvqa-200
```
Dataset format is JSONL: `{"qid","question","answers":[...],"image":"images/x.png"}` (or `"doc":"file.pdf"`).

### Read this before reporting numbers

1. **Demo scores mean nothing.** Runs made with `DEMO_MODE=true` are labelled in the UI and stored with `demo_mode: true`.
2. **Page policy.** By default (`READ_ALL_PAGES=true`) both pipelines read every page, so they get the same input. With `READ_ALL_PAGES=false` the vision model sees at most `VLM_PAGE_CAP` BM25-selected pages. By default the OCR pipeline reads every page, so the two pipelines do not get the same input on multi-page PDFs. For a fair modality comparison set `MATCH_PAGES=true`. For scanned PDFs, BM25 runs on OCR text, so the vision model's page choice depends on OCR. DocVQA is single-page, so neither matters there.
3. **Ceiling.** Check "reference answer appears in the OCR text". If that is near 100% and both scores are near the top, the set cannot separate the pipelines.
4. **OCR errors are expected.** RapidOCR read "12000" as "12oo0" in testing. The verifier flags that as a conflict; it is not a bug.
5. Prompts are versioned (`PROMPT_VERSION` in `app/services/prompts.py`) and stored with every run, together with model ids, OCR engine, page cap and decoding.

## 5. Tests

```bash
cd backend && pip install -r requirements-dev.txt    # pytest + httpx are not in requirements.txt
python -m pytest                        # 101 tests, ~60 s (real OCR runs inside them); always runs in demo mode
cd frontend && npm run lint && npm run build
```

## 6. Settings (`.env` at repo root or `backend/.env`; backend wins)

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_MODE` | `true` | `false` loads the real Qwen models |
| `OFFLINE` | `true` | never touch the Hugging Face network |
| `OCR_ENGINE` | `rapidocr` | `rapidocr`, `paddleocr`, `docling` (experimental), `textlayer` |
| `USE_TEXT_LAYER` | `false` | `true` uses a PDF's embedded text instead of OCR when present |
| `READ_ALL_PAGES` | `true` | both pipelines read every page: the vision model in batches of `VLM_PAGE_CAP` pages, the text model in parts of `MAX_CONTEXT_CHARS`; parts that find an answer are combined by the same model. `false` = old behaviour (vision sees only the `VLM_PAGE_CAP` best pages, OCR text is cut at `MAX_CONTEXT_CHARS`) |
| `VLM_PAGE_CAP` / `MATCH_PAGES` | `3` / `false` | pages per vision call (GPU memory). On the A4000, 3 pages peaked at about 13.5 GB and 6 pages at about 15.0 GB with both models loaded. `MATCH_PAGES` applies only with `READ_ALL_PAGES=false` (see section 4) |
| `MAX_CONTEXT_CHARS` | `24000` | OCR text budget for the text model, best-ranked pages first |
| `HISTORY_TURNS` | `6` | earlier turns given to the models. The database keeps every message. |
| `MIN_FREE_VRAM_GB` | `12` | startup guard |

Uploads stream to disk in 1 MiB chunks; there is no size limit.

## 7. Not verified

Verified since: real Qwen inference on an RTX A4000 (see `RUN_REPORT.md`), `prepare_docvqa.py` reading the local cache, and the UI in headless Chrome at desktop and phone width, light and dark. Still not verified: the Docling and PaddleOCR engines, and the UI on browsers other than Chrome.
