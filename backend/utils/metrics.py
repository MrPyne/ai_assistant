"""Redaction telemetry helpers extracted from utils.py.

Contains lightweight in-process metrics used by tests and diagnostics.
"""
import threading
from typing import Dict, Any

_REDACTION_METRICS: Dict[str, Any] = {
    "count": 0,
    "patterns": {},
}

_METRICS_LOCK = threading.Lock()


def get_redaction_metrics():
    with _METRICS_LOCK:
        return {k: (dict(v) if isinstance(v, dict) else v) for k, v in _REDACTION_METRICS.items()}


def reset_redaction_metrics():
    with _METRICS_LOCK:
        _REDACTION_METRICS["count"] = 0
        _REDACTION_METRICS["patterns"].clear()
        _REDACTION_METRICS.setdefault("vendor_timeouts", {}).clear()
        _REDACTION_METRICS.setdefault("vendor_errors", {}).clear()
        _REDACTION_METRICS.setdefault("vendor_budget_exceeded", {}).clear()


def _note_redaction(pattern_name: str, n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        _REDACTION_METRICS["count"] += n
        _REDACTION_METRICS["patterns"][pattern_name] = _REDACTION_METRICS["patterns"].get(pattern_name, 0) + n


def _note_vendor_timeout(pattern_name: str, n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault("vendor_timeouts", {})
        d[pattern_name] = d.get(pattern_name, 0) + n


def _note_vendor_error(pattern_name: str, n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault("vendor_errors", {})
        d[pattern_name] = d.get(pattern_name, 0) + n


def _note_vendor_budget_exceeded(key: str = "aggregate", n: int = 1):
    if n <= 0:
        return
    with _METRICS_LOCK:
        d = _REDACTION_METRICS.setdefault("vendor_budget_exceeded", {})
        d[key] = d.get(key, 0) + n
