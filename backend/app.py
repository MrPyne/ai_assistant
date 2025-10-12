# Lightweight shim that re-exports the full implementation from app_impl.py
# This keeps module-level imports fast and maintains backward compatibility
# for tests and environments that import backend.app directly.
try:
    from .app_impl import *  # noqa: F401,F403
except Exception:
    # If importing the implementation fails we raise the original exception
    # so the surrounding test harness or runtime can diagnose the issue.
    raise
