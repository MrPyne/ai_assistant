"""Shim to provide llm_utils under backend.tasks namespace during refactor.

Some legacy imports reference backend.tasks.llm_utils; export a thin
wrapper that forwards to backend.llm_utils to preserve behavior.
"""
from backend.llm_utils import is_live_llm_enabled  # noqa: F401

__all__ = ["is_live_llm_enabled"]
