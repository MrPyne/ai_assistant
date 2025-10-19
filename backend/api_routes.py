"""Backward-compatible shim for legacy import path backend.api_routes.

The monolithic implementation was refactored into backend.routes.* modules
for better organization. Tests and other code may still import
backend.api_routes.register; this module provides a thin wrapper that
forwards the call to backend.routes.api.register preserving the original
function signature and behavior.
"""

from __future__ import annotations

from typing import Any

# Import the new implementation and expose the same register(app, ctx)
# function so existing call sites remain compatible.
try:
    from .routes import api as _new_api
except Exception:
    # In very constrained test environments the package layout may differ;
    # attempt an alternate import path to be robust.
    try:
        from backend.routes import api as _new_api  # type: ignore
    except Exception:
        _new_api = None  # type: ignore


def register(app: Any, ctx: dict) -> Any:
    """Register API routes.

    This function is a shim that delegates to backend.routes.api.register.
    It preserves the original signature register(app, ctx) used elsewhere.
    """
    if _new_api is None:
        raise RuntimeError("failed to import backend.routes.api; cannot register routes")
    return _new_api.register(app, ctx)
