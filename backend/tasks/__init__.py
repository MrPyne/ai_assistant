"""Tasks package shim for refactor compatibility.

This module re-exports commonly-used symbols so other modules can
continue importing from backend.tasks while we split implementations into
smaller modules under backend.tasks.*.
"""

from .celery_app import celery_app, celery, CeleryAppStub  # noqa: F401
from .events import _publish_redis_event  # noqa: F401
from . import executor  # noqa: F401
from . import _legacy_process as _legacy  # noqa: F401
from ._legacy_process import process_run  # re-export legacy entrypoint

__all__ = [
    "celery_app",
    "celery",
    "CeleryAppStub",
    "_publish_redis_event",
    "executor",
    "_legacy",
    "process_run",
]
