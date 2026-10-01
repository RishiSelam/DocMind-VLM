"""SQLite persistence. Every message is stored in full: nothing is ever truncated or pruned."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from .config import get_settings

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL, n_pages INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ocr_pages (
  doc_id TEXT NOT NULL, page INTEGER NOT NULL, engine TEXT NOT NULL, text TEXT NOT NULL,
  boxes_json TEXT NOT NULL DEFAULT '[]', mean_conf REAL, ms REAL, created_at REAL NOT NULL,
  PRIMARY KEY (doc_id, page, engine)
);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, doc_id TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
  FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS experiments (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, config_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL DEFAULT '{}', progress_done INTEGER NOT NULL DEFAULT 0,
  progress_total INTEGER NOT NULL DEFAULT 0, error TEXT, created_at REAL NOT NULL, finished_at REAL
);
CREATE TABLE IF NOT EXISTS experiment_items (
  exp_id TEXT NOT NULL, idx INTEGER NOT NULL, qid TEXT, question TEXT, gold_json TEXT,
  vlm_pred TEXT, ocr_pred TEXT, vlm_scores_json TEXT, ocr_scores_json TEXT,
  vlm_ms REAL, ocr_ms REAL, answer_in_ocr INTEGER, agree INTEGER,
  PRIMARY KEY (exp_id, idx),
  FOREIGN KEY (exp_id) REFERENCES experiments(id) ON DELETE CASCADE
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_settings().db_path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def conn_ctx() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    with conn_ctx() as c:
        c.executescript(SCHEMA)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def _rows(cur: sqlite3.Cursor) -> List[Dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


# ---------------- documents ----------------
def add_document(filename: str, path: str, n_pages: int, size_bytes: int, sha256: str) -> Dict[str, Any]:
    doc_id = new_id("doc_")
    with conn_ctx() as c:
        c.execute(
            "INSERT INTO documents(id, filename, path, n_pages, size_bytes, sha256, created_at) VALUES (?,?,?,?,?,?,?)",
            (doc_id, filename, path, n_pages, size_bytes, sha256, time.time()),
        )
    return get_document(doc_id)  # type: ignore[return-value]


def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    with conn_ctx() as c:
        r = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return dict(r) if r else None


def list_documents() -> List[Dict[str, Any]]:
    with conn_ctx() as c:
        return _rows(c.execute("SELECT * FROM documents ORDER BY created_at DESC"))


def delete_document(doc_id: str) -> None:
    with conn_ctx() as c:
        c.execute("DELETE FROM ocr_pages WHERE doc_id=?", (doc_id,))
        c.execute("UPDATE conversations SET doc_id=NULL WHERE doc_id=?", (doc_id,))
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))


# ---------------- OCR cache ----------------
def save_ocr_page(doc_id: str, page: int, engine: str, text: str, boxes: list, mean_conf: Optional[float], ms: float) -> None:
    with conn_ctx() as c:
        c.execute(
            "INSERT OR REPLACE INTO ocr_pages(doc_id,page,engine,text,boxes_json,mean_conf,ms,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (doc_id, page, engine, text, json.dumps(boxes), mean_conf, ms, time.time()),
        )


def get_ocr_pages(doc_id: str, engine: str) -> Dict[int, Dict[str, Any]]:
    with conn_ctx() as c:
        rows = _rows(c.execute("SELECT * FROM ocr_pages WHERE doc_id=? AND engine=?", (doc_id, engine)))
    out: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        r["boxes"] = json.loads(r.pop("boxes_json") or "[]")
        out[int(r["page"])] = r
    return out


# ---------------- conversations ----------------
def create_conversation(title: str, doc_id: Optional[str]) -> Dict[str, Any]:
    cid = new_id("conv_")
    now = time.time()
    with conn_ctx() as c:
        c.execute("INSERT INTO conversations(id,title,doc_id,created_at,updated_at) VALUES (?,?,?,?,?)", (cid, title, doc_id, now, now))
    return get_conversation(cid)  # type: ignore[return-value]


def get_conversation(cid: str) -> Optional[Dict[str, Any]]:
    with conn_ctx() as c:
        r = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None


def list_conversations() -> List[Dict[str, Any]]:
    with conn_ctx() as c:
        return _rows(c.execute("SELECT * FROM conversations ORDER BY updated_at DESC"))


def delete_conversation(cid: str) -> None:
    with conn_ctx() as c:
        c.execute("DELETE FROM messages WHERE conversation_id=?", (cid,))
        c.execute("DELETE FROM conversations WHERE id=?", (cid,))


def add_message(conversation_id: str, role: str, content: str, payload: Optional[dict] = None) -> Dict[str, Any]:
    mid = new_id("msg_")
    now = time.time()
    with conn_ctx() as c:
        c.execute(
            "INSERT INTO messages(id,conversation_id,role,content,payload_json,created_at) VALUES (?,?,?,?,?,?)",
            (mid, conversation_id, role, content, json.dumps(payload or {}), now),
        )
        c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
    return {"id": mid, "conversation_id": conversation_id, "role": role, "content": content, "payload": payload or {}, "created_at": now}


def list_messages(conversation_id: str) -> List[Dict[str, Any]]:
    with conn_ctx() as c:
        rows = _rows(c.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, rowid", (conversation_id,)))
    for r in rows:
        r["payload"] = json.loads(r.pop("payload_json") or "{}")
    return rows


# ---------------- experiments ----------------
def next_experiment_id() -> str:
    with conn_ctx() as c:
        n = c.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    return f"EXP-{n + 1:04d}"


def create_experiment(name: str, config: dict, total: int) -> Dict[str, Any]:
    with conn_ctx() as c:
        n = c.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
        exp_id = f"EXP-{n + 1:04d}"
        c.execute(
            "INSERT INTO experiments(id,name,status,config_json,progress_total,created_at) VALUES (?,?,?,?,?,?)",
            (exp_id, name, "queued", json.dumps(config), total, time.time()),
        )
    return get_experiment(exp_id)  # type: ignore[return-value]


def update_experiment(exp_id: str, **fields: Any) -> None:
    if not fields:
        return
    for k in ("config", "metrics"):
        if k in fields:
            fields[f"{k}_json"] = json.dumps(fields.pop(k))
    cols = ", ".join(f"{k}=?" for k in fields)
    with conn_ctx() as c:
        c.execute(f"UPDATE experiments SET {cols} WHERE id=?", (*fields.values(), exp_id))


def get_experiment(exp_id: str) -> Optional[Dict[str, Any]]:
    with conn_ctx() as c:
        r = c.execute("SELECT * FROM experiments WHERE id=?", (exp_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["config"] = json.loads(d.pop("config_json") or "{}")
    d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
    return d


def list_experiments() -> List[Dict[str, Any]]:
    with conn_ctx() as c:
        rows = _rows(c.execute("SELECT * FROM experiments ORDER BY created_at DESC"))
    for d in rows:
        d["config"] = json.loads(d.pop("config_json") or "{}")
        d["metrics"] = json.loads(d.pop("metrics_json") or "{}")
    return rows


def delete_experiment(exp_id: str) -> None:
    with conn_ctx() as c:
        c.execute("DELETE FROM experiment_items WHERE exp_id=?", (exp_id,))
        c.execute("DELETE FROM experiments WHERE id=?", (exp_id,))


def add_experiment_item(exp_id: str, idx: int, item: Dict[str, Any]) -> None:
    with conn_ctx() as c:
        c.execute(
            "INSERT OR REPLACE INTO experiment_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                exp_id, idx, item.get("qid"), item.get("question"), json.dumps(item.get("gold", [])),
                item.get("vlm_pred"), item.get("ocr_pred"),
                json.dumps(item.get("vlm_scores", {})), json.dumps(item.get("ocr_scores", {})),
                item.get("vlm_ms"), item.get("ocr_ms"),
                None if item.get("answer_in_ocr") is None else int(bool(item["answer_in_ocr"])),
                None if item.get("agree") is None else int(bool(item["agree"])),
            ),
        )


def list_experiment_items(exp_id: str) -> List[Dict[str, Any]]:
    with conn_ctx() as c:
        rows = _rows(c.execute("SELECT * FROM experiment_items WHERE exp_id=? ORDER BY idx", (exp_id,)))
    for r in rows:
        r["gold"] = json.loads(r.pop("gold_json") or "[]")
        r["vlm_scores"] = json.loads(r.pop("vlm_scores_json") or "{}")
        r["ocr_scores"] = json.loads(r.pop("ocr_scores_json") or "{}")
    return rows
