# DocMind v2 run report

Date: 2026-09-30. Machine: this workstation (NVIDIA RTX A4000, Python 3.10.12, Node 20.20.2).
Project location actually used: `~/MMAI/newww/docmind` (see deviations).

**Status: all steps passed, on the second attempt at Phase 2.** The first real-model startup failed because `torchvision` was not installed. You approved installing it and updating the docs, and after that startup, both real questions and the real-model eval all passed. The first attempt is recorded below as a FAIL.

---

## Phase 1: demo mode (DEMO_MODE=true, no GPU)

Every result in this section is **DEMO MODE**. The "models" are heuristic text-matching stand-ins, not Qwen.

| Step | Result | Command | Key output |
|---|---|---|---|
| 1.1 venv + deps | PASS | `python3 -m venv .venv && pip install -r requirements.txt` | Installed cleanly (fastapi 0.142.1, pymupdf 1.28.2, rapidocr-onnxruntime 1.4.4, numpy 2.2.6) |
| 1.2 sample data + doctor | PASS | `python scripts/make_sample_data.py; python scripts/doctor.py` | Wrote the 6-page PDF and `sample.jsonl`. Smoke OCR read "Invoice No: INV-2041" in 1.1 s. Doctor ended with **"All required checks passed."** |
| 1.3 tests | PASS | `python -m pytest` | **56 passed, 1 warning in 31.22 s.** The warning is a Starlette deprecation for `httpx` in TestClient. Needed `pip install -r requirements-dev.txt` first (see deviations). |
| 1.4 backend + API | PASS | `uvicorn app.main:app --port 8000`, then curl | Details below |
| 1.5 frontend | PASS | `npm install`, `npm run lint`, `npm run build`, `npm run dev` | lint (`tsc --noEmit`) exit 0. Build exit 0, with routes `/` (43.8 kB) and `/research` (6.45 kB). Dev server: `GET /` returned 200 and `GET /research` returned 200. CORS preflight from `localhost:3000` to `/api/ask` returned 200. |

### 1.4 details (DEMO MODE)

- `GET /api/health` returned 200: `{"status":"ok","demo_mode":true,"loaded":true,"vlm":"demo-vlm","llm":"demo-llm","ocr_engine":"rapidocr","gpu":{"available":false,"reason":"torch not installed"},"page_cap":3,"match_pages":false}`
- `POST /api/documents` (multipart `file=@data/samples/annual_report.pdf`) returned 200 with `id: doc_75b08a98c4e8`, `n_pages: 6`, `size_bytes: 4366`.
- `POST /api/ask` with `{"doc_id":"doc_75b08a98c4e8","question":"What is the warehouse capacity?"}` returned 200 in 5.89 s wall time. The fields are under `assistant_message.payload`:

| Field | Value |
|---|---|
| `payload.demo` | `true` |
| `vlm.answer` | "The Pune warehouse has a capacity of 12000 pallets." (pages 1, 3, 6) |
| `ocr.answer` | "The Pune warehouse has a capacity of 12oo0 pallets." (pages 1 to 6) |
| `verification.verdict` | `conflict` (agreement 0.0; `numbers_only_vlm: ["12000"]`, `numbers_only_ocr: ["0","12"]`) |
| `timings` | `retrieval_ms 9.5, vlm_ms 0.2, ocr_ms 5581.7, ocr_wall_ms 5776.0, llm_ms 0.4, total_ms 5855.9` |

The "12oo0" is the RapidOCR misread the README describes, and the verifier flags it as a conflict, as documented. Almost all of the time goes to OCR on the first ask; `vlm_ms` and `llm_ms` are near zero because the demo stand-ins do no inference.

### UI

The pages compile, type-check and serve HTTP 200. **I did not see the UI in a browser and cannot say whether the layout looks right.**

---


## Phase 2: real models (DEMO_MODE=false)

Every result in this section is **REAL MODEL** output (`demo_mode: false`): Qwen2.5-VL-7B-Instruct and Qwen2.5-7B-Instruct, both 4-bit nf4, on the A4000.

| Step | Result | Command | Key output |
|---|---|---|---|
| 2.1 GPU check | PASS | `nvidia-smi` | NVIDIA RTX A4000. 16376 MiB total, 654 MiB used, **15315 MiB free** (about 14.96 GiB, above the 12 GB limit). Driver 595.91.07, CUDA 13.2. Only display processes were on the GPU (Xorg, gnome-shell, firefox, one other); no other compute jobs, at either attempt. |
| 2.2 torch + GPU deps | PASS (after fix) | `pip install torch --index-url https://download.pytorch.org/whl/cu128; pip install -r requirements-gpu.txt`, and later `pip install torchvision --index-url …/cu128` | torch 2.11.0+cu128, torchvision 0.26.0+cu128, `torch.cuda.is_available()` **True**. transformers 4.57.6, accelerate 1.15.0, bitsandbytes 0.50.2. |
| 2.3 weights | PASS | `doctor.py` + listing `~/.cache/huggingface/hub` | `HF_HOME` is unset, so the default `~/.cache/huggingface/hub` is used. Both cached: `Qwen2.5-VL-7B-Instruct` snapshot `cc594898…` (16 GB on disk), `Qwen2.5-7B-Instruct` snapshot `a09a3545…` (15 GB on disk). **Nothing downloaded.** |
| 2.4 .env | PASS | `cp .env.example .env`, set `DEMO_MODE=false` | The only difference from `.env.example` is `DEMO_MODE=false`. `OFFLINE=true` and `MIN_FREE_VRAM_GB=12` are unchanged. No `backend/.env` exists. |
| 2.5a doctor (real) | PASS | `python scripts/doctor.py` | CUDA A4000, free 15.9 / 16.7 GB (decimal GB), VRAM guard ok, both weights cached. **"All required checks passed."** (It passed at both attempts; see the torchvision note below.) |
| 2.5b startup, attempt 1 | **FAIL** | `uvicorn app.main:app --port 8000` | `ImportError: AutoVideoProcessor requires the Torchvision library`. Details below. |
| 2.5b startup, attempt 2 | PASS | same command, after installing torchvision | Both models loaded in about 36 s (VLM 5 shards in about 14 s, LLM 4 shards in about 12 s). `DocMind ready (demo=False, ocr=rapidocr)`. `/api/health` returned `demo_mode:false` and `allocated_gb: 11.5`. |
| 2.6 real questions | PASS | `/api/documents` then `/api/ask` (details below) | Both answers correct, both verdicts `consistent` |
| 2.7 eval `real-smoke` | PASS | `python scripts/eval_docvqa.py --dataset sample/sample.jsonl --name real-smoke` | EXP-0001, 7/7 done. Stored config has **`"demo_mode": false`**. Metrics below. |

### 2.5b attempt 1: error and diagnosis

```
INFO docmind.models: Loading VLM Qwen/Qwen2.5-VL-7B-Instruct (nf4)...
Loading checkpoint shards: 100%|██████████| 5/5 [00:14<00:00,  2.89s/it]
ERROR:    Traceback (most recent call last):
  File "backend/app/main.py", line 24, in lifespan
    hub.load_all()
  File "backend/app/services/models.py", line 210, in load_all
    self.vlm = QwenVLM(s)
  File "backend/app/services/models.py", line 124, in __init__
    self.processor = AutoProcessor.from_pretrained(
  ...
ImportError:
AutoVideoProcessor requires the Torchvision library but it was not found in your environment.
ERROR:    Application startup failed. Exiting.
```

This was a missing dependency, not a code bug. transformers 4.57 builds the Qwen2.5-VL processor with a video sub-processor, and that sub-processor needs torchvision. Neither the README nor `requirements-gpu.txt` installed it, and `doctor.py` does not catch it. The server exited as designed and released its memory. **Fix, approved by you:** installed `torchvision 0.26.0+cu128`, and made this documentation-only change:

```diff
--- a/backend/requirements-gpu.txt
+++ b/backend/requirements-gpu.txt
-# Real inference (GPU workstation). Install torch first with the right CUDA wheel:
-#   pip install torch --index-url https://download.pytorch.org/whl/cu121
+# Real inference (GPU workstation). Install torch AND torchvision first with the right CUDA wheel:
+#   pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
+# (torchvision is required: transformers' Qwen2.5-VL processor builds a video processor that imports it)
--- a/README.md
+++ b/README.md
-pip install torch --index-url https://download.pytorch.org/whl/cu121     # pick the wheel that matches `nvidia-smi`
+pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128   # pick the wheel that matches `nvidia-smi`; torchvision is required
```

No Python source file was changed. After the change, `python -m pytest` gave **56 passed, 1 warning in 33.53 s**. The tests force `DEMO_MODE=true` in `conftest.py`, so the real `.env` does not affect them.

### 2.6 details (REAL MODEL)

Peak GPU memory comes from `nvidia-smi --query-gpu=memory.used` sampled every 0.5 s over each call. It is whole-GPU usage, including about 652 MiB of display processes.

| | annual_report.pdf | invoice.png |
|---|---|---|
| Question | "What is the warehouse capacity?" | "What is the total due?" |
| doc id | `doc_a7d5c950fa47` (6 pages) | `doc_21ce4110c092` (1 page) |
| `vlm.answer` | "The Pune warehouse has a capacity of 12000 pallets." (pages 1, 3, 6) | "$1,284.50" (page 1) |
| `ocr.answer` | "The Pune warehouse has a capacity of 12000 pallets." (pages 1 to 6) | "$1,284.50" (page 1) |
| `verification.verdict` | `consistent`, agreement 1.0 | `consistent`, agreement 1.0 |
| `ocr_support` | coverage 0.8, **missing `["12000"]`** | coverage 1.0, found `$1284.50` |
| retrieval_ms | 9.6 | 0.0 |
| vlm_ms | 4382.7 | 1232.1 |
| ocr_ms (OCR engine) / ocr_wall_ms | 5701.2 / 5898.0 | 849.6 / 898.8 |
| llm_ms | 825.4 | 461.1 |
| total_ms | 11170.5 | 2622.1 |
| HTTP wall time | 11.21 s | 2.67 s |
| Peak GPU memory.used during call | **13460 MiB** | **12422 MiB** |
| Max GPU utilisation | 100% | 100% |

**Observation on the PDF answer.** The OCR pipeline answered "12000", but the verifier lists "12000" as missing from the OCR text. In demo mode the same page was read as "12oo0". It looks like the text LLM corrected the OCR error from context. The verdict is `consistent`, so this repaired OCR error is not visible in the verdict, only in `ocr_support.missing`. That matters when comparing the "OCR pipeline" against the "OCR text" in the analysis. I did not change anything for this; it is just an observation.

### 2.7 metrics (REAL MODEL, EXP-0001 `real-smoke`)

The CLI loads its own copy of both models (`hub.load_all()`). Before running it I stopped my own uvicorn server, so the GPU did not need to hold two copies. The run took 51 s wall time including model load. Peak GPU memory.used during the run was **12430 MiB**.

```json
{
  "n": 7,
  "vlm": {"em": 1.0, "anls": 1.0, "contains": 1.0, "abstain_rate": 0.0, "error_rate": 0.0,
          "latency_ms": {"mean": 1112.54, "p50": 1015.4, "p95": 1534.3}},
  "ocr": {"em": 1.0, "anls": 1.0, "contains": 1.0, "abstain_rate": 0.0, "error_rate": 0.0,
          "latency_ms": {"mean": 1455.77, "p50": 1363.0, "p95": 1725.7}},
  "paired": {"anls_vlm_minus_ocr": {"diff": 0.0, "ci_low": 0.0, "ci_high": 0.0},
             "em_mcnemar": {"a_only": 0, "b_only": 0, "p_value": 1.0}},
  "ocr_answer_coverage": 1.0,
  "disagreement_rate": 0.0,
  "ocr_loss_cases": 0
}
```

Stored `config_json`: `demo_mode: false`, `vlm_model: Qwen/Qwen2.5-VL-7B-Instruct`, `llm_model: Qwen/Qwen2.5-7B-Instruct`, `ocr_engine: rapidocr`, `prompt_version: v1`, `vlm_page_cap: 3`, `match_pages: false`, `vlm_max_pixels: 1003520`, `decoding: greedy`.

This is a smoke test only. Seven synthetic, clean questions and an OCR answer coverage of 1.0 mean the set is at its ceiling and cannot separate the two pipelines (README section 4, point 3).

---

## (a) Real-model latency and VRAM

| Measure | Value |
|---|---|
| Startup (both models, nf4, from local cache) | about 36 s |
| GPU memory after load (idle server) | 12130 MiB total used (about 11.5 GB from DocMind, per `/api/health` `allocated_gb`), leaving 3839 MiB free |
| Peak during 6-page PDF ask | 13460 MiB (the highest seen) |
| Peak during 1-page image ask | 12422 MiB |
| Peak during eval run | 12430 MiB |
| PDF ask, "What is the warehouse capacity?" | total 11.17 s: VLM 4.38 s (3 pages), OCR 5.70 s (6 pages, first time), LLM 0.83 s |
| Invoice ask, "What is the total due?" | total 2.62 s: VLM 1.23 s, OCR 0.85 s, LLM 0.46 s |
| Eval latency per question (7 questions) | VLM mean 1.11 s (p95 1.53 s). OCR pipeline mean 1.46 s (p95 1.73 s). |

Headroom: at peak, about 2.9 GB of the 16 GB card was still free. Someone else starting a GPU job of more than about 3 GB while DocMind is running could cause an out-of-memory error during a multi-page VLM call.

## (b) Deviations from the instructions

1. **Project location.** `~/MMAI/docmind.zip` (Sep 10, 113 files) is an older project with a different layout (`evaluation/`, no `backend/` or `frontend/`). The v2 zip is `~/MMAI/newww/docmind.zip` (Sep 30), and it was already extracted at `~/MMAI/newww/docmind`. I checked that the extracted tree matches that zip file for file and ran everything there. I did not create `~/MMAI/docmind` and did not re-extract or overwrite anything. This report is at `~/MMAI/newww/docmind/RUN_REPORT.md`.
2. **Installed `requirements-dev.txt`** (pytest, httpx) before step 1.3, because `requirements.txt` does not include pytest.
3. **Torch wheel: cu128, not the README's cu121.** The driver supports CUDA 13.2. I chose cu128 because bitsandbytes support for it is mature.
4. **Installed torchvision and edited `backend/requirements-gpu.txt` and `README.md`** (comments and docs only) after the startup failure, with your approval. Tests were rerun afterwards: 56 passed.
5. **Backend bound to 127.0.0.1**, not the README's `--host 0.0.0.0`, following your step 2.5 command.
6. **Stopped my own real-model server before step 7**, because the eval CLI loads a second copy of the models in its own process and two copies would not fit on the GPU. After that I stopped my GPU sampler; nothing of mine is left running, and the GPU is back to 652 MiB used.
7. Before Phase 2 I stopped my own Phase 1 demo backend and Next dev server. One `pkill -f` pattern matched my own shell and killed only that shell; no other user's process was touched. I never signalled any process I did not start.
8. For the invoice question I chose "What is the total due?", taken from the sample eval set, because you did not name one.
9. Did not run `npm audit fix`. `npm audit` reports 1 critical and 1 high advisory against `next@14.2.35`.

## (c) README issues

1. **torchvision was missing** from the GPU install steps and `requirements-gpu.txt`, so real-model startup failed. This is now fixed in both files. `doctor.py` still passes without torchvision, so "doctor passed" does not guarantee startup. Suggested follow-up (not applied): have doctor `import torchvision`, or construct the VLM `AutoProcessor`.
2. **The cu121 example wheel was stale.** Current torch (2.11) is not published for cu121. The docs now say cu128; any CUDA version up to the driver's maximum works.
3. The README section 2 path is `~/MMAI/docmind/backend`, which does not match where the v2 zip actually is on this machine.
4. **pytest is not in `requirements.txt`.** Section 5 should say `pip install -r requirements-dev.txt`.
5. **Response shape is undocumented.** The upload returns `id`, not `doc_id`. `/api/ask` returns `{conversation_id, user_message, assistant_message}`, with `vlm`, `ocr`, `verification` and `timings` under `assistant_message.payload`.
6. **The eval CLI loads its own models.** It cannot run while the backend server is up on a 16 GB card. The README should say to stop the server first, or to use Research > New experiment in the UI, which reuses the loaded models.
7. The weights are about 31 GB on disk in the HF cache (bf16 safetensors), not about 16 GB. They are quantized to nf4 at load time.
8. The test time is "~45 s on one CPU core". Here it took 31 to 34 s wall time using several cores.
9. Minor: startup logs deprecation warnings (`torch_dtype` should be `dtype`, and the fast image-processor default has changed). Generation also warns that `temperature/top_p/top_k` are ignored under greedy decoding. None of these stopped the run.

## Follow-up changes (after the run, with your go-ahead)

| Change | File | Verified by |
|---|---|---|
| Doctor now checks `torchvision` (listed as required with the GPU packages) | `backend/scripts/doctor.py` (1 line, plus a comment) | Normal run: `[ ok ] torchvision 0.26.0+cu128`, "All required checks passed." With torchvision hidden: `[FAIL] torchvision`, "2 required check(s) failed." (the other failure is the Qwen class import, which also needs it) |
| README: curl example and where the `/api/ask` fields live (`assistant_message.payload`) | `README.md` section 1 | text only |
| README: the eval CLI loads its own models, so stop the backend first or use the UI | `README.md` section 4 | text only |
| README: `pip install -r requirements-dev.txt` before pytest; tests always run in demo mode | `README.md` section 5 | text only |

After these changes, `python -m pytest` gave **56 passed, 1 warning in 33.28 s**.

**Not changed: the Next.js advisories.** `next@14.2.35` is already the latest 14.x release, so the only fix `npm audit` offers is a new major version (15 or 16). That is a breaking change and would need someone to check the UI in a browser, so I left it alone. The app binds to localhost here, which limits exposure.

**Still open:** nobody has looked at the UI in a browser yet.

## Later changes (2026-09-30 to 2026-10-01, on request)

These came after the run above and change the configuration it describes.

**Configuration.** `.env` now differs from `.env.example` in two lines: `DEMO_MODE=false` and **`VLM_PAGE_CAP=6`** (was 3), so the vision model can read up to 6 pages. Measured on the 6-page sample PDF (REAL MODEL): vision time 4.4 s → 5.8–6.1 s; peak GPU memory 13.5 GB → about 15.0 GB of 16 GB, which leaves about 1.4 GB for other users of the shared card.

**Comparison panel under every answer** (`backend/app/services/verification.py` `scorecard`, new `backend/app/services/explain.py`, new `frontend/components/BarChart.tsx` and `CompareChart.tsx`):
- Two SVG charts: "How each method did" (answer found in the document's text, share of the document read, OCR text similarity, on a 0–100% axis) and "Time to answer" (OCR pipeline split into OCR reading and text model). Both have axes, a legend, value labels, hover/keyboard tooltips and a table view.
- A plain-language explanation built from the measured values: the verdict, which method read the document better, speed and page coverage.
- The judge is the PDF's embedded text, which neither method produced. With no embedded text (scans, images) it does not pick a winner. It checks grounding, not correctness.

**Research page:** the same charts for accuracy and latency, a "More accurate on this set" headline that names a winner only when the bootstrap interval excludes zero, and a "What the results mean" section.

**Review fixes (2026-10-01):** a thorough pass found and fixed six problems before they reached a user: (1) a false "vision recognised something OCR missed" claim whenever the OCR pipeline failed; (2) OCR comparisons made against the truncated text-model context instead of the full OCR text; (3) "n/a" text in the verdict when both answers were "not found" or only one answered; (4) a `$` sign deciding whether a number counted as found; (5) the OCR similarity score described as "share of words matched"; (6) a failed pipeline still drawn with page and time bars. Also fixed: a scanned PDF's OCR (done during page ranking) described as a cache hit, singular/plural wording, and screen-reader access to the chart bars.

**Verification (2026-10-01):**
- Backend: **73 passed** (was 56; 17 new tests for the scorecard, explanations and the fixes above).
- Frontend: `npm run lint` and `npm run build` pass.
- REAL MODEL edge cases through `/api/ask`, all correct: sample PDF (tie, both answers fully in the document, OCR similarity 99.0%); unanswerable question (both "Not found in document.", reported as such); scanned copy of the PDF with no text layer (both answers "12000 pallets", "cannot be checked"); invoice image ($1,284.50 from both, "cannot be checked"); vision-only mode (no comparison panel). Peak GPU memory during these: 14981 MiB.
- UI checked in headless Chrome at 1400 px and 390 px: charts render, fit the phone width, and tooltips show; no page errors. The only console error is a missing `favicon.ico` (404).

**Known limits:**
- Explanations are stored with each answer when it is asked, so older answers keep older wording, and answers from before the panel existed show no panel.
- "Answer found in the document" is lexical: a correct paraphrase can score lower than a verbatim answer.
- The OCR similarity covers only the pages the vision model saw.
- During this work I twice killed my own processes by mistake with a `pkill -f` / `pgrep -f` pattern that matched my own shell. No one else's process was affected, and later stops used exact PIDs.

## Reading every page (2026-10-01, on request)

**Problem reported:** on an 8-page PDF the vision model read only pages 1–6, because `VLM_PAGE_CAP=6` limited it to the 6 best-ranked pages. The OCR side also had a hidden limit: its text was cut at `MAX_CONTEXT_CHARS` (24,000 characters) on long documents.

**Change:** new setting `READ_ALL_PAGES=true` (default). Both pipelines now read every page of any document:
- **Vision:** batches of up to `VLM_PAGE_CAP` consecutive pages. That is the GPU memory limit, so a whole long document cannot go in one call.
- **OCR:** text split into parts of up to `MAX_CONTEXT_CHARS`, with nothing cut.
- Each part is told it sees only some pages, and answers what it can or says "not found". If two or more parts find something, the same model combines them, using an identical combine prompt for both pipelines.
- `READ_ALL_PAGES=false` restores the old best-pages-only mode.
- `PROMPT_VERSION` is now `v2`, and `read_all_pages` is stored with every experiment.

**Tests:** 80 backend tests pass (7 new). The frontend type check passes; the last production build passed before two cosmetic label edits.

**REAL MODEL results** (vision batches of 6 pages):

| Document | Question | Vision | OCR pipeline | Vision time | Total |
|---|---|---|---|---|---|
| 8 pages, fact on p.8 | Nagpur depot capacity | 4500 pallets (part 7–8) | 4500 pallets | 7.1–7.7 s | ~17 s |
| 8 pages, fact on p.7 | audit committee chair | Meera Iyer | "Meera **l**yer" (OCR misread I as l) | 6.5 s | 14.9 s |
| 20 pages, fact on p.19 | procurement head | Arjun Rao (part 19–20) | Arjun Rao | 16.2–17.8 s | ~36 s |
| 20 pages, fact on p.5 | employee headcount | 342 (part 1–6) | 342 | 16.9 s | ~36 s |
| 8 pages | unanswerable question | Not found (both parts) | Not found | 6.6 s | ~14 s |
| 6-page sample | warehouse capacity | 12000 pallets (1 batch) | 12000 pallets | 5.3 s | 12 s |

Peak GPU memory stayed at about 14.9 GB of 16 GB for every document size, because each batch is the same size. Time grows roughly linearly with pages: about 0.8 s per page for vision, and about 0.9 s per page for OCR the first time a document is read.

**Known limitation:** a question whose answer is split across two vision batches can lose a piece. On "capacities of the Pune warehouse **and** the Nagpur depot", the vision part with pages 7–8 answered "Not found" instead of giving the Nagpur half, even with prompts asking for partial answers. The final vision answer gave only Pune. The comparison panel flags this ("The OCR pipeline gave the more complete answer… leaves out: Nagpur…"). Workaround: ask about one thing per question.
