"""Event stream generator for run SSE endpoint.

Extracted from backend.routes.runs to reduce that file's size. The
generator mirrors the original behavior and depends only on the
`shared` context and a run_id.
"""

import asyncio
import json
import logging
import threading
import time


async def event_stream_generator(shared, run_id):
    """Async generator that yields SSE events for a run.

    This implementation attempts to subscribe to Redis (if available)
    and falls back to polling the database for RunLog entries. It emits
    existing logs, then streams new messages from Redis or new DB rows.
    """
    logger = logging.getLogger(__name__)

    db = None
    last_id = 0
    last_activity = 0
    heartbeat_interval = 15
    poll_interval = 1

    redis_client = None
    redis_thread = None
    redis_stop = None
    message_queue = None
    REDIS_URL = None

    try:
        # Try to import redis and create a client if possible
        try:
            import redis as _redis

            try:
                import os as _os

                REDIS_URL = _os.getenv("REDIS_URL") or _os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
            except Exception:
                REDIS_URL = "redis://localhost:6379/0"

            try:
                redis_client = _redis.from_url(REDIS_URL)
            except Exception:
                redis_client = None
        except Exception:
            redis_client = None

        if getattr(shared, "_DB_AVAILABLE", False):
            try:
                db = shared.SessionLocal()
            except Exception:
                db = None

        # Replay existing DB logs if DB available
        if db is not None:
            try:
                from backend import models as _models

                rows = (
                    db.query(_models.RunLog)
                    .filter(_models.RunLog.run_id == run_id)
                    .order_by(_models.RunLog.id.asc())
                    .all()
                )

                out = []
                for rr in rows:
                    last_id = max(last_id, getattr(rr, "id", 0))
                    payload = None
                    event_name = "log"
                    try:
                        payload = json.loads(rr.message) if rr.message else None
                        if isinstance(payload, dict) and "type" in payload:
                            event_name = payload.get("type") or "log"
                            payload.setdefault("run_id", rr.run_id)
                            payload.setdefault("node_id", rr.node_id)
                            payload.setdefault(
                                "timestamp", rr.timestamp.isoformat() if rr.timestamp is not None else None
                            )
                            try:
                                payload.setdefault("event_id", getattr(rr, "event_id", None))
                            except Exception:
                                pass
                        else:
                            payload = {
                                "type": "log",
                                "id": rr.id,
                                "run_id": rr.run_id,
                                "node_id": rr.node_id,
                                "event_id": getattr(rr, "event_id", None),
                                "timestamp": rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                "level": rr.level,
                                "message": rr.message,
                            }
                    except Exception:
                        payload = {
                            "type": "log",
                            "id": rr.id,
                            "run_id": rr.run_id,
                            "node_id": rr.node_id,
                            "timestamp": rr.timestamp.isoformat() if rr.timestamp is not None else None,
                            "level": rr.level,
                            "message": rr.message,
                        }
                    out.append((event_name, payload))

                logger.info("SSE replayed %s existing DB logs for run_id=%s", len(out), run_id)

                for event_name, item in out:
                    try:
                        eid = item.get("event_id")
                    except Exception:
                        eid = None
                    if eid:
                        yield f"id: {eid}\n"
                    yield f"event: {event_name}\n"
                    yield f"data: {json.dumps(item)}\n\n"

                    last_activity = asyncio.get_event_loop().time()
            except Exception:
                # If any problem reading logs, continue and try streaming
                pass
        else:
            note_payload = {"note": "in-memory run; no persisted logs"}
            yield "event: log\n"
            yield f"data: {json.dumps(note_payload)}\n\n"
            last_activity = asyncio.get_event_loop().time()

        # If Redis is available, start a background thread to listen and push to an asyncio.Queue
        if redis_client is not None and REDIS_URL is not None:
            try:
                channel_name = f"run:{run_id}:events"
                message_queue = asyncio.Queue()
                redis_stop = threading.Event()
                redis_ready = threading.Event()

                def _redis_listener_loop(redis_url, channel, loop, q, stop_event, ready_event):
                    import json as _json
                    import logging as _logging

                    logger_local = _logging.getLogger(__name__)
                    backoff = 1.0
                    max_backoff = 60.0

                    while not stop_event.is_set():
                        client = None
                        pubsub = None
                        try:
                            try:
                                import redis as _r

                                client = _r.from_url(redis_url)
                            except Exception:
                                client = None

                            if client is None:
                                raise RuntimeError("failed to create redis client")

                            pubsub = client.pubsub(ignore_subscribe_messages=True)
                            pubsub.subscribe(channel)
                            logger_local.info("Subscribed to redis channel %s", channel)

                            try:
                                ready_event.set()
                            except Exception:
                                pass

                            backoff = 1.0

                            while not stop_event.is_set():
                                try:
                                    msg = pubsub.get_message(timeout=1.0)
                                except Exception as exc:
                                    logger_local.warning("Redis get_message error: %s", exc)
                                    break

                                if not msg:
                                    continue
                                if msg.get("type") != "message":
                                    continue
                                data = msg.get("data")
                                try:
                                    if isinstance(data, bytes):
                                        payload = _json.loads(data.decode("utf-8"))
                                    else:
                                        payload = _json.loads(data)
                                except Exception:
                                    payload = {"type": "raw", "raw": data}

                                try:
                                    loop.call_soon_threadsafe(q.put_nowait, payload)
                                except Exception:
                                    continue

                        except Exception as exc:
                            logger_local.warning("Redis listener problem for channel %s: %s", channel, exc)

                        finally:
                            try:
                                if pubsub is not None:
                                    pubsub.close()
                            except Exception:
                                pass
                            try:
                                if client is not None:
                                    try:
                                        client.close()
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                        if stop_event.is_set():
                            break

                        time.sleep(backoff)
                        backoff = min(backoff * 2, max_backoff)

                redis_thread = threading.Thread(
                    target=_redis_listener_loop,
                    args=(REDIS_URL, channel_name, asyncio.get_event_loop(), message_queue, redis_stop, redis_ready),
                    daemon=True,
                )
                redis_thread.start()

                # Wait a short time for the listener to become ready
                try:
                    ok = await asyncio.get_event_loop().run_in_executor(None, redis_ready.wait, 1.0)
                    if not ok:
                        try:
                            redis_stop.set()
                        except Exception:
                            pass
                        try:
                            redis_thread.join(timeout=0.2)
                        except Exception:
                            pass
                        redis_client = None
                        redis_thread = None
                        message_queue = None
                    else:
                        logger.info("SSE redis listener subscribed run_id=%s channel=%s", run_id, channel_name)
                except Exception:
                    redis_client = None
                    redis_thread = None
                    message_queue = None
            except Exception:
                redis_client = None
        else:
            logger.info("SSE redis not available, falling back to DB polling for run_id=%s", run_id)

        # Main loop: read messages from queue or poll DB
        while True:
            sent_any = False

            if message_queue is not None:
                try:
                    msg = await asyncio.wait_for(message_queue.get(), timeout=poll_interval)
                except Exception:
                    msg = None

                if msg:
                    mtype = msg.get("type") if isinstance(msg, dict) else None
                    if mtype == "log":
                        try:
                            eid = msg.get("event_id") if isinstance(msg, dict) else None
                        except Exception:
                            eid = None
                        if eid:
                            yield f"id: {eid}\n"
                        yield "event: log\n"
                        yield f"data: {json.dumps(msg)}\n\n"
                        last_activity = asyncio.get_event_loop().time()
                        sent_any = True
                    elif mtype == "node":
                        try:
                            eid = msg.get("event_id") if isinstance(msg, dict) else None
                        except Exception:
                            eid = None
                        if eid:
                            yield f"id: {eid}\n"
                        yield "event: node\n"
                        yield f"data: {json.dumps(msg)}\n\n"
                        last_activity = asyncio.get_event_loop().time()
                        sent_any = True
                    elif mtype == "status":
                        status_payload = {"run_id": run_id, "status": msg.get("status")}
                        yield "event: status\n"
                        yield f"data: {json.dumps(status_payload)}\n\n"
                        logger.info("SSE emitted final status for run_id=%s status=%s", run_id, msg.get("status"))
                        return
                    else:
                        # Safely format raw payload without f-string literal containing braces
                        raw_payload = {"raw": msg}
                        yield "event: log\n"
                        yield "data: " + json.dumps(raw_payload) + "\n\n"
                        last_activity = asyncio.get_event_loop().time()
                        sent_any = True
            else:
                if db is not None:
                    try:
                        from backend import models as _models

                        rows = (
                            db.query(_models.RunLog)
                            .filter(_models.RunLog.run_id == run_id, _models.RunLog.id > last_id)
                            .order_by(_models.RunLog.id.asc())
                            .all()
                        )
                        for rr in rows:
                            item = {
                                "type": "log",
                                "id": rr.id,
                                "run_id": rr.run_id,
                                "node_id": rr.node_id,
                                "event_id": getattr(rr, "event_id", None),
                                "timestamp": rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                "level": rr.level,
                                "message": rr.message,
                            }
                            last_id = max(last_id, getattr(rr, "id", 0))
                            try:
                                eid = item.get("event_id")
                            except Exception:
                                eid = None
                            if eid:
                                yield f"id: {eid}\n"
                            yield "event: log\n"
                            yield f"data: {json.dumps(item)}\n\n"
                            sent_any = True
                            last_activity = asyncio.get_event_loop().time()
                        if rows:
                            logger.info("SSE polled and emitted %s DB logs for run_id=%s", len(rows), run_id)
                    except Exception:
                        pass

                    try:
                        from backend import models as _models
                        r = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                        if r and getattr(r, "status", None) in ("success", "failed"):
                            status_payload = {"run_id": run_id, "status": r.status}
                            yield "event: status\n"
                            yield f"data: {json.dumps(status_payload)}\n\n"
                            logger.info("SSE emitted final DB status for run_id=%s status=%s", run_id, r.status)
                            return
                    except Exception:
                        pass

            now = asyncio.get_event_loop().time()
            if (now - last_activity) >= heartbeat_interval:
                # SSE comment ping as heartbeat
                yield ":\n\n"
                last_activity = now

    finally:
        # Cleanup resources
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
        if redis_stop is not None:
            try:
                redis_stop.set()
            except Exception:
                pass
        if redis_thread is not None:
            try:
                redis_thread.join(timeout=1)
            except Exception:
                pass
        logger.info("SSE connection cleanup complete for run_id=%s", run_id)
