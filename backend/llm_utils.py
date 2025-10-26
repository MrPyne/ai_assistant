import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


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
    try:
        global_flag = _env_bool("ENABLE_LIVE_LLM") or _env_bool("LIVE_LLM")
        # Log the evaluated global flag and provider-specific flag queries
        logger.debug("is_live_llm_enabled: global_flag=%s provider_name=%s", global_flag, provider_name)
        if global_flag:
            return True
    except Exception:
        # Be conservative and fall back to previous behavior on error
        pass

    if not provider_name:
        return False

    # provider-specific fallbacks for backward compatibility
    name = provider_name.strip().lower()
    try:
        if name == "openai":
            val = _env_bool("ENABLE_OPENAI")
            logger.debug("is_live_llm_enabled: provider=openai enabled=%s", val)
            return val
        if name == "ollama":
            val = _env_bool("ENABLE_OLLAMA")
            logger.debug("is_live_llm_enabled: provider=ollama enabled=%s", val)
            return val
    except Exception:
        pass

    return False
