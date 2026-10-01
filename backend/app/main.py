"""DocMind API entry point.   Run from backend/:   uvicorn app.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings  # must come before anything that imports transformers (sets offline flags)
from . import db
from .api.routes import router
from .services import ocr as ocrsvc
from .services.models import hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    logging.basicConfig(level=getattr(logging, s.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("docmind")
    db.init_db()
    hub.load_all()          # raises StartupError -> the server refuses to start half-working
    ocrsvc.get_engine()     # loads the OCR engine now so a broken install fails at startup, not on the first question
    log.info("DocMind ready (demo=%s, ocr=%s)", hub.demo, ocrsvc.cache_key())
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="DocMind", version="2.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()
