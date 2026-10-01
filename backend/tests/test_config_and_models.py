import pytest

from app.config import Settings, get_settings
from app.services import models


def test_dual_env_lookup_backend_overrides_root(tmp_path, monkeypatch):
    monkeypatch.delenv("VLM_PAGE_CAP", raising=False)  # real env vars outrank .env files, so clear the ones conftest set
    monkeypatch.delenv("OCR_ENGINE", raising=False)
    root, backend = tmp_path / "root.env", tmp_path / "backend.env"
    root.write_text("VLM_PAGE_CAP=7\nOCR_ENGINE=textlayer\n")
    backend.write_text("VLM_PAGE_CAP=9\n")
    s = Settings(_env_file=(str(root), str(backend)))
    assert s.vlm_page_cap == 9          # later file wins
    assert s.ocr_engine == "textlayer"  # value only in the first file still applies


def test_offline_flags_are_set():
    import os

    get_settings()
    assert os.environ.get("HF_HUB_OFFLINE") == "1" and os.environ.get("TRANSFORMERS_OFFLINE") == "1"


def test_real_mode_fails_loudly_without_torch(monkeypatch):
    def no_torch():
        raise models.StartupError("PyTorch is not installed.")

    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(models, "_torch", no_torch)
    hub = models.ModelHub()
    with pytest.raises(models.StartupError):
        hub.load_all()
    monkeypatch.setenv("DEMO_MODE", "true")
    get_settings.cache_clear()


def test_real_mode_requires_at_least_one_model(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("ENABLE_VLM", "false")
    monkeypatch.setenv("ENABLE_LLM", "false")
    get_settings.cache_clear()
    with pytest.raises(models.StartupError):
        models.ModelHub().load_all()
    monkeypatch.undo()
    get_settings.cache_clear()


def test_demo_hub_loads():
    hub = models.ModelHub()
    hub.load_all()
    assert hub.demo and hub.loaded
