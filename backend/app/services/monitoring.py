"""In-memory request timings + GPU status. Persisted history lives in the messages table."""
from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List

_EVENTS: Deque[Dict[str, Any]] = deque(maxlen=500)
_LOCK = threading.Lock()
STARTED = time.time()


def record(event: Dict[str, Any]) -> None:
    with _LOCK:
        _EVENTS.append({"t": time.time(), **event})


def _pct(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    v = sorted(values)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def summary() -> Dict[str, Any]:
    with _LOCK:
        ev = list(_EVENTS)
    out: Dict[str, Any] = {"n_requests": len(ev), "uptime_s": round(time.time() - STARTED, 1)}
    for key in ("vlm_ms", "ocr_ms", "llm_ms", "retrieval_ms", "total_ms"):
        vals = [e[key] for e in ev if isinstance(e.get(key), (int, float))]
        out[key] = {
            "n": len(vals),
            "mean": round(statistics.fmean(vals), 1) if vals else 0.0,
            "p50": round(_pct(vals, 0.5), 1),
            "p95": round(_pct(vals, 0.95), 1),
        }
    out["recent"] = ev[-20:][::-1]
    return out


def gpu_status() -> Dict[str, Any]:
    try:
        import torch  # noqa: WPS433 (optional dependency)
    except Exception:
        return {"available": False, "reason": "torch not installed"}
    if not torch.cuda.is_available():
        return {"available": False, "reason": "CUDA not available"}
    free, total = torch.cuda.mem_get_info()
    return {
        "available": True,
        "name": torch.cuda.get_device_name(0),
        "total_gb": round(total / 1e9, 2),
        "free_gb": round(free / 1e9, 2),
        "allocated_gb": round(torch.cuda.memory_allocated(0) / 1e9, 2),
    }
