from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    doc_id: Optional[str] = None
    conversation_id: Optional[str] = None
    mode: Literal["both", "vlm", "ocr"] = "both"
    short: bool = False  # True = terse, extractive answers (evaluation style)
    reuse: bool = True   # the same question about the same file with the same settings: return the saved answer


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    doc_id: Optional[str] = None


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset: str  # path relative to EVAL_DIR, or absolute
    limit: Optional[int] = Field(default=None, ge=1)
    mode: Literal["both", "vlm", "ocr"] = "both"
    notes: str = ""
