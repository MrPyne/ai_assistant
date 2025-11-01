import os
import json
import logging
from datetime import datetime
import uuid
import hashlib

logger = logging.getLogger(__name__)

from .utils import redact_secrets


def _publish_redis_event(event):
    """
    Persist a RunLog row for the given structured event when possible,
    and publish the (redacted) event to Redis channel `run:{run_id}:events` so
    SSE subscribers receive it in real-time.

    We only persist when the event contains an explicit workflow node_id
    (do not invent host/worker identifiers). Messages are redacted before
    being stored so secrets are not leaked into RunLog.message. For live
    streaming we also publish the same redacted payload to Redis. If Redis
    isn't available we degrade gracefully.
    """
    node_for_persist = event.get("node_id")
    logger.debug("_publish_redis_event initial event node_id=%s for run_id=%s", node_for_persist, event.get("run_id"))
    if not node_for_persist:
        try:
            logger.error("_publish_redis_event refusing to persist RunLog without explicit node_id for run_id=%s", event.get("run_id"))
        except Exception:
            pass
        return

    # Redact secrets from the event before persisting/publishing
    try:
        safe_event = redact_secrets(event)
    except Exception:
        try:
            safe_event = event
        except Exception:
            safe_event = {}

    # Generate a stable deterministic event_id for this event so clients
    # can dedupe across SSE and polling. We compute a namespaced UUID5 over
    # a canonical representation of the event excluding volatile fields like
    # 'timestamp'. This keeps the change small and backwards-compatible.
    try:
        def _canonicalize(ev):
            # Make a shallow copy excluding timestamp
            if not isinstance(ev, dict):
                return str(ev)
            c = {k: ev.get(k) for k in sorted(ev.keys()) if k != 'timestamp'}
            # Ensure determinism for non-JSON-serializable values
            try:
                return json.dumps(c, sort_keys=True, ensure_ascii=False)
            except Exception:
                # Fallback: stringify values
                items = []
                for k in sorted(c.keys()):
                    v = c.get(k)
                    try:
                        items.append(f"{k}:{json.dumps(v, sort_keys=True, default=str)}")
                    except Exception:
                        items.append(f"{k}:{str(v)}")
                return "|".join(items)

        try:
            canon = _canonicalize(safe_event)
            namespace = uuid.NAMESPACE_URL
            eid = str(uuid.uuid5(namespace, canon))
        except Exception:
            # best-effort fallback to a hash-based id
            try:
                h = hashlib.sha1()
                h.update(repr(safe_event).encode('utf-8'))
                eid = h.hexdigest()
            except Exception:
                eid = None
        if eid:
            safe_event['event_id'] = eid
            try:
                # also opportunistically set on the original event dict when
                # it's the same object so callers that reuse the dict can see
                # the generated id. This is best-effort and won't affect
                # callers that passed copies.
                if isinstance(event, dict):
                    event['event_id'] = eid
            except Exception:
                pass
    except Exception:
        # do not fail persistence due to event id generation
        try:
            pass
        except Exception:
            pass

    # Attempt to persist to DB when available; otherwise fall back to a
    # noop/stub behavior (useful for tests that don't use DB persistence).
    persisted = False
    try:
        from .database import SessionLocal
        from . import models as _models
        db = None
        try:
            db = SessionLocal()
            rl = _models.RunLog(
                run_id=safe_event.get("run_id"),
                node_id=safe_event.get("node_id"),
                event_id=safe_event.get('event_id'),
                level=safe_event.get("level", "info"),
                message=json.dumps(safe_event),
                timestamp=safe_event.get("timestamp") or datetime.utcnow(),
            )
            db.add(rl)
            db.commit()
            try:
                # attempt to refresh to get the DB id for better diagnostics
                db.refresh(rl)
                logger.info("_publish_redis_event persisted RunLog id=%s run_id=%s node_id=%s", getattr(rl, 'id', None), safe_event.get('run_id'), safe_event.get('node_id'))
            except Exception:
                logger.info("_publish_redis_event persisted RunLog for run_id=%s node_id=%s", safe_event.get('run_id'), safe_event.get('node_id'))
            persisted = True
        finally:
            try:
                if db is not None:
                    db.close()
            except Exception:
                pass
    except Exception:
        # DB not available or persistence failed; log and continue
        try:
            logger.info("_publish_redis_event could not persist RunLog to DB; event=%s", safe_event)
        except Exception:
            pass

    # Publish to Redis so SSE clients receive live updates. We publish the
    # redacted `safe_event` to avoid leaking secrets in transit/persistence.
    try:
        try:
            import redis as _redis
        except Exception:
            _redis = None
        if _redis is not None:
            REDIS_URL = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
            try:
                rc = _redis.from_url(REDIS_URL)
                channel = f"run:{safe_event.get('run_id')}:events"
                try:
                    rc.publish(channel, json.dumps(safe_event))
                    logger.debug("_publish_redis_event published to %s: %s", channel, safe_event.get('type'))
                except Exception as e:
                    logger.warning("_publish_redis_event publish failed for run %s: %s", safe_event.get('run_id'), e)
            except Exception:
                logger.debug("_publish_redis_event skipping redis publish: could not create client")
    except Exception:
        pass
