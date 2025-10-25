import os
from typing import Optional


def _env_bool(var: str) -> bool:
    """Return True for common truthy env values.

    Accepts: '1', 'true', 'yes' (case-insensitive). Defaults to False.
    This makes docker-compose/service defaults that use 0/1 work as expected.
    """
    val = os.getenv(var, "false").strip().lower()
    return val in ("1", "true", "yes")


def is_live_llm_enabled(provider_name: Optional[str] = None) -> bool:
    """Return whether live LLM calls are enabled.

    Priority:
    - Global opt-in via ENABLE_LIVE_LLM or LIVE_LLM
    - Provider-specific opt-in (e.g. ENABLE_OPENAI, ENABLE_OLLAMA)

    This central helper is intended to make it easier to keep a consistent
    guard across adapters. It intentionally mirrors the previous per-adapter
    logic so behavior is unchanged.
    """
    if _env_bool("ENABLE_LIVE_LLM") or _env_bool("LIVE_LLM"):
        return True

    if not provider_name:
        return False

    # provider-specific fallbacks for backward compatibility
    name = provider_name.strip().lower()
    if name == "openai":
        return _env_bool("ENABLE_OPENAI")
    if name == "ollama":
        return _env_bool("ENABLE_OLLAMA")

    return False
