import os
import json
import logging

logger = logging.getLogger(__name__)

# Minimal models stub to ensure this file is self-contained when replaced.
class models:
    class RunLog:
        def __init__(self, run_id, node_id, level, message):
            self.run_id = run_id
            self.node_id = node_id
            self.level = level
            self.message = message

        def save(self):
            # Placeholder save implementation; real project should override.
            return True


def _publish_redis_event(event):
    """
    Persist a RunLog for a Redis-published event only when the event
    explicitly contains a workflow node_id. Do not invent host/worker
    identifiers as RunLog.node_id values.
    """
    # Preserve any node_id present on the event. We must not
    # persist worker/hostname-based identifiers as RunLog.node_id.
    # If the event does not include a node_id, do not invent one
    # (no worker/hostname fallback) — fail fast and log so the
    # caller can be corrected. This ensures persisted RunLog.node_id
    # values are always real workflow node ids.
    node_for_persist = event.get("node_id")
    logger.debug("_publish_redis_event initial event node_id=%s for run_id=%s", node_for_persist, event.get("run_id"))
    if not node_for_persist:
        try:
            logger.error("_publish_redis_event refusing to persist RunLog without explicit node_id for run_id=%s", event.get("run_id"))
        except Exception:
            pass
        # Do not persist a RunLog row without a valid node_id
        return

    logger.info("_publish_redis_event persisting fallback RunLog for run_id=%s node_id=%s", event.get("run_id"), node_for_persist)

    rl = models.RunLog(
        run_id=event.get("run_id"),
        node_id=node_for_persist,
        level="info",
        message=json.dumps(event),
    )

    try:
        rl.save()
    except Exception:
        logger.exception("_publish_redis_event failed to save RunLog")
