import os
import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

# Attempt to wire DB/session and models if available; else fall back to None
try:
    from .database import SessionLocal
    from . import models
except Exception:
    SessionLocal = None
    models = None

logger = logging.getLogger(__name__)


# --- Redis publish / durable RunLog helpers (unchanged) ---------------------

def _publish_redis_event(event: dict):
    """Best-effort publish an event dict to Redis so SSE listeners using
    pub/sub receive real-time updates. Non-fatal: swallow all errors.
    """
    try:
        import redis

        REDIS_URL = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
        client = redis.from_url(REDIS_URL)
        channel = f"run:{event.get('run_id')}:events"
        logger.info("_publish_redis_event attempting publish run_id=%s type=%s channel=%s", event.get("run_id"), event.get("type"), channel)
        res = client.publish(channel, json.dumps(event))
        try:
            logger.info("_publish_redis_event publish result run_id=%s type=%s result=%s", event.get("run_id"), event.get("type"), res)
        except Exception:
            pass

        # If publish reported zero subscribers for a terminal status event,
        # persist a RunLog row as a durable fallback so clients that subscribe
        # after the publish can replay the final status via the DB-backed
        # SSE replay path. Best-effort: swallow all errors.
        try:
            if (not res) and isinstance(event, dict) and event.get("type") == "status":
                if SessionLocal is not None and models is not None:
                    db = None
                    try:
                        db = SessionLocal()
                        # store the structured status event as the message so
                        # SSE replay will emit it with type/status info
                        # Preserve any node_id present on the event; if missing,
                        # attempt to detect a sensible node identifier so persisted
                        # DB rows are not left with a null node_id.
                        node_for_persist = event.get("node_id")
                        logger.debug("_publish_redis_event initial event node_id=%s for run_id=%s", node_for_persist, event.get("run_id"))
                        try:
                            if not node_for_persist:
                                # _detect_node_id is defined below; resolving at
                                # call-time is fine as long as the function exists
                                # before this code path executes.
                                node_for_persist = _detect_node_id()
                                logger.debug("_publish_redis_event detected node_id=%s for run_id=%s via _detect_node_id", node_for_persist, event.get("run_id"))
                        except Exception:
                            node_for_persist = None

                        # Ensure we never persist a NULL node_id: prefer explicit
                        # detection, otherwise use a sensible default depending
                        # on whether a broker is configured.
                        node_source = "explicit"
                        if not node_for_persist:
                            if not os.getenv("CELERY_BROKER_URL"):
                                node_for_persist = "inline"
                                node_source = "default-inline"
                            else:
                                node_for_persist = "worker"
                                node_source = "default-worker"

                        logger.info("_publish_redis_event persisting fallback RunLog for run_id=%s node_id=%s source=%s", event.get("run_id"), node_for_persist, node_source)

                        rl = models.RunLog(
                            run_id=event.get("run_id"),
                            node_id=node_for_persist,
                            level="info",
                            message=json.dumps(event),
                        )
                        db.add(rl)
                        db.commit()
                        try:
                            logger.info("_publish_redis_event persisted status run_id=%s id=%s node_id=%s", event.get("run_id"), getattr(rl, "id", None), rl.node_id)
                        except Exception:
                            pass
                    except Exception:
                        try:
                            if db is not None:
                                db.rollback()
                        except Exception:
                            pass
                    finally:
                        try:
                            if db is not None:
                                db.close()
                        except Exception:
                            pass
        except Exception:
            pass

    except Exception as e:
        # Do not allow Redis problems to affect run processing
        try:
            logger.warning("_publish_redis_event failed run_id=%s type=%s error=%s %s", event.get("run_id"), event.get("type"), e.__class__.__name__, str(e))
        except Exception:
            pass
        return


# --- Minimal runner used for inline execution / fallback --------------------


def _canonicalize_node(raw_hostname: Optional[str]) -> Optional[str]:
    """Map a raw celery/current hostname to a canonical node identifier.

    Rules:
      - If environment var CELERY_NODE_ID or CELERY_WORKER_NAME is set, prefer it.
      - If raw_hostname is a Celery-style name like 'celery@<workerid>', prefer
        CELERY_NODE_ID / HOSTNAME / platform.node() instead of the 'celery@...' string.
      - Otherwise, return raw_hostname as-is.

    This function logs the mapping decisions to help diagnose why nodes look
    like 'celery@abcd1234' in the logs.
    """
    try:
        logger.debug("_canonicalize_node called raw_hostname=%s", raw_hostname)
    except Exception:
        pass

    # Explicit override from environment (recommended for mapping workers to
    # workflow node identifiers). This is useful when a worker should expose a
    # human-friendly name that matches nodes in the workflow graph.
    env_node = os.environ.get("CELERY_NODE_ID") or os.environ.get("CELERY_WORKER_NAME")
    if env_node:
        try:
            logger.info("_canonicalize_node using env override CELERY_NODE_ID/CELERY_WORKER_NAME=%s for raw_hostname=%s", env_node, raw_hostname)
        except Exception:
            pass
        return env_node

    if not raw_hostname:
        return None

    # If Celery gives a value like 'celery@<id>', try to substitute with
    # container/host name so node id can be mapped to workflow nodes.
    if isinstance(raw_hostname, str) and raw_hostname.startswith("celery@"):
        # Prefer container HOSTNAME or a platform node name
        host = os.environ.get("HOSTNAME") or os.environ.get("CELERY_WORKER_NAME")
        if not host:
            try:
                import socket

                host = socket.gethostname()
            except Exception:
                try:
                    import platform

                    host = platform.node()
                except Exception:
                    host = None
        if host:
            try:
                logger.info("_canonicalize_node mapped raw_hostname=%s to host=%s", raw_hostname, host)
            except Exception:
                pass
            return host

    # Default: return raw_hostname unchanged
    try:
        logger.debug("_canonicalize_node returning raw_hostname unchanged=%s", raw_hostname)
    except Exception:
        pass
    return raw_hostname


def _detect_node_id(explicit_node_id: Optional[str] = None) -> Optional[str]:
    """Return a node identifier for the current execution context.

    Priority:
      1. explicit_node_id argument (used by callers that can provide it)
      2. Celery current_task.request.hostname (if running inside a Celery worker)
      3. Celery current_task.request.id (fallback)
      4. None if nothing else is available
    """
    logger.debug("_detect_node_id called explicit_node_id=%s", explicit_node_id)
    if explicit_node_id:
        logger.debug("_detect_node_id returning explicit_node_id=%s", explicit_node_id)
        return explicit_node_id

    try:
        # Attempt to detect Celery runtime task info if Celery is installed
        from celery import current_task  # type: ignore

        ct = current_task  # may be a proxy that is None when not in worker
        logger.debug("_detect_node_id current_task=%s", getattr(ct, "__class__", None))
        if ct is not None:
            req = getattr(ct, "request", None)
            logger.debug("_detect_node_id current_task.request=%s", getattr(req, "__class__", None))
            if req is not None:
                hostname = getattr(req, "hostname", None)
                tid = getattr(req, "id", None)
                logger.debug("_detect_node_id extracted hostname=%s id=%s from request", hostname, tid)
                if hostname:
                    # Map raw Celery hostname into a canonical value if possible
                    mapped = _canonicalize_node(hostname)
                    logger.debug("_detect_node_id returning mapped hostname=%s (raw=%s)", mapped, hostname)
                    return mapped
                if tid:
                    logger.debug("_detect_node_id returning id=%s", tid)
                    return tid
    except Exception as e:
        logger.debug("_detect_node_id celery current_task detection raised %s", e.__class__.__name__)
        pass

    logger.debug("_detect_node_id could not detect a node id; returning None")
    return None


def process_run(run_db_id: int, node_id: Optional[str] = None) -> Optional[dict]:
    """Minimal compatibility implementation of the job runner.

    This function is intentionally minimal: it marks the Run as running,
    emits a start RunLog, then marks the Run as finished and emits a final
    RunLog. It also attempts to notify any SSE listeners via Redis pub/sub.

    If a richer job runner is present in your deployment, replace/extend
    this with the full implementation. The purpose here is to avoid
    AttributeError in the web process and to ensure run log rows are
    written so clients can replay them.
    """
    if SessionLocal is None or models is None:
        logger.warning("process_run: DB/session/models not available; cannot process run %s", run_db_id)
        return None

    # Determine node_id: prefer explicit arg, else try to detect from Celery
    detected_node = _detect_node_id(node_id)
    try:
        logger.info("process_run start run_id=%s detected_node=%s explicit_arg=%s", run_db_id, detected_node, node_id)
    except Exception:
        pass

    # If detection failed, choose a sensible default so RunLog.node_id is
    # never left null. If there's no broker configured we'll mark node as
    # 'inline' (local execution); if a broker exists but worker didn't
    # provide a hostname, mark as 'worker' as a generic indicator.
    node_source = "detected"
    if detected_node is None:
        if not os.getenv("CELERY_BROKER_URL"):
            detected_node = "inline"
            node_source = "default-inline"
        else:
            detected_node = "worker"
            node_source = "default-worker"

    try:
        logger.info("process_run using node_id=%s source=%s for run_id=%s", detected_node, node_source, run_db_id)
    except Exception:
        pass

    db = None
    try:
        db = SessionLocal()
        r = db.query(models.Run).filter(models.Run.id == run_db_id).first()
        if not r:
            logger.warning("process_run: run id %s not found", run_db_id)
            return None

        # mark running
        try:
            r.status = "running"
            r.started_at = datetime.utcnow()
            r.attempts = (getattr(r, "attempts", 0) or 0) + 1
            db.add(r)
            db.commit()
            db.refresh(r)
            logger.debug("process_run marked run running run_id=%s attempts=%s", run_db_id, r.attempts)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        start_event = {
            "run_id": run_db_id,
            "type": "status",
            "status": "running",
            "timestamp": datetime.utcnow().isoformat(),
            "node_id": detected_node,
        }
        try:
            # Preserve node context if present on the event dict; otherwise
            # use defaulted detected_node. This lets UI replay show the
            # node-specific status.
            rl = models.RunLog(
                run_id=run_db_id, node_id=start_event.get("node_id"), level="info", message=json.dumps(start_event)
            )
            logger.debug("persist_run_log run_id=%s node_id=%s level=%s msg_snippet=%s", run_db_id, rl.node_id, rl.level, (start_event.get("status") or str(start_event))[:200])
            db.add(rl)
            db.commit()
            try:
                logger.info("_write_run_log wrote db run_id=%s id=%s node_id=%s", run_db_id, getattr(rl, "id", None), rl.node_id)
            except Exception:
                pass
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        # notify listeners
        try:
            _publish_redis_event(start_event)
        except Exception:
            pass

        # Note: real workflow execution would happen here. This minimal
        # implementation skips node execution and simply marks the run as
        # finished so that UI can show a terminal status and replayable logs.

        try:
            r.status = "finished"
            r.finished_at = datetime.utcnow()
            db.add(r)
            db.commit()
            db.refresh(r)
            logger.debug("process_run marked run finished run_id=%s", run_db_id)
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        finish_event = {
            "run_id": run_db_id,
            "type": "status",
            "status": "finished",
            "timestamp": datetime.utcnow().isoformat(),
            "node_id": detected_node,
        }
        try:
            rl2 = models.RunLog(
                run_id=run_db_id, node_id=finish_event.get("node_id"), level="info", message=json.dumps(finish_event)
            )
            logger.debug("persist_run_log run_id=%s node_id=%s level=%s msg_snippet=%s", run_db_id, rl2.node_id, rl2.level, (finish_event.get("status") or str(finish_event))[:200])
            db.add(rl2)
            db.commit()
            try:
                logger.info("_write_run_log wrote db run_id=%s id=%s node_id=%s", run_db_id, getattr(rl2, "id", None), rl2.node_id)
            except Exception:
                pass
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

        try:
            _publish_redis_event(finish_event)
        except Exception:
            pass

        try:
            logger.info("process_run finished run_id=%s node_id=%s", run_db_id, detected_node)
        except Exception:
            pass

        return {"status": "finished"}
    except Exception:
        logger.exception("process_run unexpected error for run %s", run_db_id)
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:
            pass


# --- Celery app selection: real app when broker configured, else a CLI-safe
#     dummy that falls back to inline execution. --------------------------------

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or None

celery_app = None
execute_workflow: Callable[..., Any]


class _DummyAsyncResult:
    def __init__(self, result: Any):
        self._result = result

    def get(self, timeout: Optional[float] = None) -> Any:
        return self._result


class _DummyCelery:
    """Lightweight fallback Celery-like object that is safe for the
    Celery CLI to import (provides user_options) and that supports
    send_task by executing the task inline. This lets the web process
    call send_task when no broker is configured and still get the
    fallback inline behavior.
    """

    def __init__(self) -> None:
        # Celery CLI expects app.user_options.get('worker', []) to exist
        self.user_options = {"worker": []}

    def task(self, *args, **kwargs):
        # Decorator: return identity decorator so functions can still be
        # defined with @celery_app.task(...)
        def _decorator(f: Callable) -> Callable:
            return f

        return _decorator

    def send_task(self, name: str, args: Optional[list] = None, kwargs: Optional[dict] = None, **opts):
        args = args or []
        kwargs = kwargs or {}
        if name == "execute_workflow":
            try:
                # When running inline via the dummy, tag the node as 'inline'
                # unless the caller provided an explicit node_id via kwargs.
                explicit_node = kwargs.get("node_id")
                if explicit_node is None:
                    kwargs["node_id"] = "inline"
                    explicit_node = "inline"
                try:
                    logger.info("DummyCelery.send_task executing execute_workflow inline args=%s kwargs=%s chosen_node=%s", args, kwargs, explicit_node)
                except Exception:
                    pass
                res = process_run(*args, **kwargs)
                return _DummyAsyncResult(res)
            except Exception as e:
                raise RuntimeError("DummyCelery failed to execute task inline: %s" % e)
        raise RuntimeError("No broker configured; cannot send_task for '%s' in DummyCelery" % name)


# Try to create a real Celery app when broker URL configured and Celery is available
if CELERY_BROKER_URL:
    try:
        from celery import Celery  # type: ignore

        real_celery = Celery("backend", broker=CELERY_BROKER_URL)
        # Optional: you may want to configure result backend, serializers, etc.
        celery_app = real_celery
        try:
            logger.info("Celery app created broker=%s", CELERY_BROKER_URL)
        except Exception:
            pass

        # Register the process_run function as a real Celery task named
        # 'execute_workflow' so workers importing this module will register
        # a task with that canonical name and receive messages sent to it.
        try:
            # Wrap process_run in a thin task wrapper that extracts a node_id
            # from the Celery request and passes it as the second argument.
            @celery_app.task(name="execute_workflow")
            def _execute_workflow_wrapper(run_db_id: int, node_id: Optional[str] = None):
                """
                Celery task wrapper for execute_workflow.

                Accepts an optional explicit node_id (the workflow node id being
                executed). If provided, prefer it. Otherwise attempt to detect
                the worker identity from the Celery request / environment and
                canonicalize that value.

                We also attempt a best-effort validation: if an explicit node_id
                is provided we check the associated workflow graph (via the
                DB) to see if a node with that id exists and log the result.
                """
                explicit = node_id

                # If caller provided explicit node id, log and attempt to
                # validate it against the workflow graph for the run. This helps
                # catch cases where callers accidentally pass the worker hostname
                # instead of the workflow node id.
                if explicit:
                    try:
                        logger.info("Celery task execute_workflow received explicit node_id=%s for run_id=%s", explicit, run_db_id)
                    except Exception:
                        pass
                    try:
                        if SessionLocal is not None and models is not None:
                            db = SessionLocal()
                            try:
                                r = db.query(models.Run).filter(models.Run.id == run_db_id).first()
                                if r and getattr(r, 'workflow_id', None):
                                    wf = db.query(models.Workflow).filter(models.Workflow.id == r.workflow_id).first()
                                    if wf and getattr(wf, 'graph', None) and isinstance(wf.graph, dict):
                                        nodes = wf.graph.get('nodes') or []
                                        found = any(str(n.get('id')) == str(explicit) for n in nodes if isinstance(n, dict))
                                        if found:
                                            logger.info("explicit node_id %s validated against workflow %s for run %s", explicit, getattr(wf, 'id', None), run_db_id)
                                        else:
                                            logger.warning("explicit node_id %s NOT found in workflow %s for run %s", explicit, getattr(wf, 'id', None), run_db_id)
                            finally:
                                try:
                                    db.close()
                                except Exception:
                                    pass
                    except Exception:
                        # Non-fatal: validation/logging best-effort only
                        pass

                # If no explicit node id, try to detect Celery worker identity
                node = None
                raw_host = None
                if not explicit:
                    try:
                        from celery import current_task  # type: ignore
                        req = getattr(current_task, "request", None)
                        if req is not None:
                            raw_host = getattr(req, "hostname", None)
                            node = getattr(req, "hostname", None) or getattr(req, "id", None)
                    except Exception:
                        node = None

                    # Additional fallbacks: container/host environment or socket
                    if not node:
                        node = os.environ.get("HOSTNAME") or os.environ.get("CELERY_WORKER_NAME")
                    if not node:
                        try:
                            import socket

                            node = socket.gethostname()
                        except Exception:
                            try:
                                import platform

                                node = platform.node()
                            except Exception:
                                node = None

                # Prefer explicit node id if present; otherwise canonicalize
                # the discovered worker/node identity.
                if explicit:
                    mapped = explicit
                    try:
                        logger.info("Celery task execute_workflow using explicit node_id=%s for run_id=%s", mapped, run_db_id)
                    except Exception:
                        pass
                else:
                    try:
                        mapped = _canonicalize_node(raw_host or node)
                        logger.info("Celery task execute_workflow called run_id=%s raw_node=%s mapped_node=%s", run_db_id, raw_host, mapped)
                    except Exception:
                        mapped = node

                return process_run(run_db_id, mapped)

            execute_workflow = _execute_workflow_wrapper
            try:
                logger.info("Celery task 'execute_workflow' registered")
            except Exception:
                pass
        except Exception:
            # Fall back to exposing process_run directly if registration fails
            execute_workflow = process_run
            logger.warning("Failed to register Celery task 'execute_workflow'; falling back to direct process_run")
    except Exception as e:
        # If Celery import or creation fails, fall back to the dummy below.
        logger.warning("Failed to create real Celery app (broker=%s): %s %s", CELERY_BROKER_URL, e.__class__.__name__, str(e))
        celery_app = _DummyCelery()
        execute_workflow = process_run
else:
    # No broker configured: use dummy that won't crash the Celery CLI and
    # that executes the task inline when send_task is called.
    celery_app = _DummyCelery()
    execute_workflow = process_run

# Expose aliases expected by Celery CLI and other code
celery = celery_app
app = celery_app
