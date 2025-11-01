import os
import logging

logger = logging.getLogger(__name__)


class CeleryAppStub:
    """Minimal stub for environments without a configured Celery.

    The stub exposes send_task which raises so callers can detect
    Celery is unavailable and fall back to inline processing.
    """

    def send_task(self, name, args=None, kwargs=None):
        raise RuntimeError("Celery not configured in this environment")


# Expose a celery_app attribute so imports like
# `from backend.tasks import celery_app` don't fail.
celery_app = CeleryAppStub()


# Backwards compatibility: provide a module-level `celery` name. Try to
# construct a real Celery app if the package is available and a broker
# URL is provided in the environment; otherwise keep the stub.
try:
    from celery import Celery as _Celery  # type: ignore

    celery = _Celery("backend.tasks")
    _broker = os.environ.get("CELERY_BROKER_URL") or os.environ.get("BROKER_URL")
    if _broker:
        try:
            celery.conf.broker_url = _broker
        except Exception:
            logger.exception("failed to set celery broker_url from env")
except Exception:
    celery = celery_app
