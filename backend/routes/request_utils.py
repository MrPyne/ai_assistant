"""Utilities for coercing Request-like bodies into plain dicts.

These helpers encapsulate the repeated logic used across route
implementations to accept either a plain dict or a Request-like object
that exposes a .json() method which may be sync or async.
"""
from typing import Any, Optional


def coerce_body_to_dict(body: Any) -> Optional[dict]:
    """Attempt to coerce `body` into a plain dict.

    If `body` is already a dict it is returned as-is. If it has a
    callable `.json()` method the function will call it (handling
    both sync and async callables) and return the parsed dict when
    possible. Returns None when coercion fails.
    """
    if isinstance(body, dict):
        return body

    if not hasattr(body, "json") or not callable(body.json):
        return None

    try:
        result = body.json()
    except Exception:
        return None

    # If the result is a coroutine, attempt to run it to completion.
    try:
        import asyncio

        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Cannot run a new event loop when one is already running.
                    # Give up rather than blocking the running loop.
                    return None
                return loop.run_until_complete(result)
            except Exception:
                try:
                    return asyncio.run(result)
                except Exception:
                    return None
    except Exception:
        # If asyncio isn't available for some reason, fall through.
        pass

    return result if isinstance(result, dict) else None
