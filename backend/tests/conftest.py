import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="docmind_test_"))
os.environ.update({
    "DEMO_MODE": "true", "OFFLINE": "true", "DATA_DIR": str(_TMP), "DB_PATH": str(_TMP / "t.sqlite3"),
    "EVAL_DIR": str(_TMP / "eval"), "VLM_PAGE_CAP": "2", "OCR_ENGINE": "rapidocr", "MATCH_PAGES": "false",
    "USE_TEXT_LAYER": "false",
})

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.sample_data import REPORT_PAGES, build_eval_sample, make_pdf, make_png, INVOICE  # noqa: E402


@pytest.fixture(scope="session")
def tmp_dir() -> Path:
    return _TMP


@pytest.fixture(scope="session")
def report_pdf(tmp_dir) -> Path:
    return make_pdf(tmp_dir / "report.pdf", REPORT_PAGES)


@pytest.fixture(scope="session")
def invoice_png(tmp_dir) -> Path:
    return make_png(tmp_dir / "invoice.png", INVOICE)


@pytest.fixture(scope="session")
def eval_jsonl(tmp_dir) -> Path:
    return build_eval_sample(tmp_dir / "eval")


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
def _load_demo_hub():
    """Pipelines use the module-level hub, which the app normally fills in its lifespan."""
    from app import db
    from app.services.models import hub

    db.init_db()
    hub.load_all()
