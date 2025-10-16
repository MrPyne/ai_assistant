def register(app, ctx):
    from . import shared_impls as shared
    from fastapi import HTTPException, Header
    from typing import Optional
    from fastapi.responses import StreamingResponse

    @app.post('/api/workflows/{wf_id}/run')
    def manual_run(wf_id: int, request: dict, authorization: Optional[str] = Header(None)):
        return shared.manual_run_impl(wf_id, request, authorization)

    @app.post('/api/runs/{run_id}/retry')
    def retry_run(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.retry_run_impl(run_id, authorization)

    @app.get('/api/runs')
    def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None)):
        return shared.list_runs_impl(workflow_id, limit, offset, authorization)

    @app.get('/api/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        """Return persisted RunLog rows for a run.

        This used to be a placeholder that returned an empty list; restore a
        realistic implementation so UI code that fetches historical logs works
        again.
        """
        import json
        try:
            # DB-backed path
            if getattr(shared, '_DB_AVAILABLE', False):
                db = None
                try:
                    db = shared.SessionLocal()
                    from backend import models as _models

                    rows = (
                        db.query(_models.RunLog)
                        .filter(_models.RunLog.run_id == run_id)
                        .order_by(_models.RunLog.id.asc())
                        .all()
                    )
                    out = []
                    for rr in rows:
                        try:
                            payload = None
                            try:
                                payload = json.loads(rr.message) if rr.message else None
                            except Exception:
                                payload = None

                            if isinstance(payload, dict) and 'type' in payload:
                                payload.setdefault('run_id', rr.run_id)
                                payload.setdefault('node_id', rr.node_id)
                                payload.setdefault('timestamp', rr.timestamp.isoformat() if rr.timestamp is not None else None)
                                out.append(payload)
                            else:
                                out.append({
                                    'type': 'log',
                                    'id': rr.id,
                                    'run_id': rr.run_id,
                                    'node_id': rr.node_id,
                                    'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                    'level': rr.level,
                                    'message': rr.message,
                                })
                        except Exception:
                            # skip problematic rows but continue
                            continue
                    return {'logs': out}
                finally:
                    try:
                        if db is not None:
                            db.close()
                    except Exception:
                        pass

            # In-memory fallback
            if hasattr(shared, '_runs') and run_id in shared._runs:
                r = shared._runs.get(run_id)
                return {'logs': r.get('logs', [])}
            return {'logs': []}
        except Exception:
            return {'logs': []}

    @app.get('/api/runs/{run_id}/stream')
    async def stream_run(run_id: int, authorization: Optional[str] = Header(None)):
        """SSE endpoint that streams RunLog rows for a run in real-time.

        Behavior:
        - Requires Authorization header (token-based) and verifies the user owns
          the workspace containing the run (DB) or is the creator for in-memory
          runs.
        - Streams existing logs on connect and then polls for new RunLog rows
          every 1s, yielding them as SSE "data: <json>\n\n" messages.
        - Emits periodic comment heartbeats when idle to keep EventSource alive.
        - Closes the connection when the run reaches a terminal state
          (success/failed) and all logs have been sent.
        """
        import asyncio
        import json
        from datetime import datetime

        # authenticate
        user_id = None
        try:
            user_id = shared._user_from_token(authorization)
        except Exception:
            user_id = None
        if not user_id:
            raise HTTPException(status_code=401, detail='authorization required')

        # Authorization / run existence checks
        db = None
        run_row = None
        in_memory = False
        try:
            if getattr(shared, '_DB_AVAILABLE', False):
                try:
                    db = shared.SessionLocal()
                    # load run and workflow to check workspace ownership
                    from backend import models as _models
                    run_row = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                    if not run_row:
                        # fall back to in-memory store
                        if hasattr(shared, '_runs') and run_id in shared._runs:
                            in_memory = True
                        else:
                            raise HTTPException(status_code=404, detail='run not found')
                    else:
                        # verify workspace ownership via workflow
                        wf = db.query(_models.Workflow).filter(_models.Workflow.id == run_row.workflow_id).first()
                        wsid = None
                        if wf:
                            wsid = getattr(wf, 'workspace_id', None)
                        # fallback: try shared._workspace_for_user to find user's workspace
                        user_wsid = shared._workspace_for_user(user_id)
                        if wsid is not None and user_wsid != wsid:
                            raise HTTPException(status_code=403, detail='not allowed')
                except HTTPException:
                    raise
                except Exception:
                    # if DB queries fail for any reason, deny access conservatively
                    raise HTTPException(status_code=500, detail='internal error')
            else:
                # DB not available: check in-memory run
                if hasattr(shared, '_runs') and run_id in shared._runs:
                    r = shared._runs.get(run_id)
                    if r.get('created_by') != user_id:
                        raise HTTPException(status_code=403, detail='not allowed')
                    in_memory = True
                else:
                    raise HTTPException(status_code=404, detail='run not found')
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        async def event_stream():
            """Stream RunLog rows and status using Redis pub/sub when available,
            falling back to DB polling if Redis isn't available.

            Behavior:
            - On connect, replay existing DB logs (if DB available).
            - If REDIS is configured and redis-py is importable, subscribe to
              channel `run:{run_id}:events` and stream incoming events.
              Expected messages are JSON dicts with a 'type' key: 'log' or 'status'.
            - If Redis not available, fall back to the original 1s DB polling.
            - Heartbeats are emitted when idle to keep EventSource alive.
            """
            db = None
            last_id = 0
            last_activity = 0
            heartbeat_interval = 15
            poll_interval = 1

            # Attempt to initialize Redis subscription support (best-effort).
            redis_client = None
            redis_pubsub = None
            redis_thread = None
            redis_stop = None
            message_queue = None
            try:
                try:
                    import redis

                    REDIS_URL = None
                    try:
                        import os as _os

                        REDIS_URL = _os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
                    except Exception:
                        REDIS_URL = 'redis://localhost:6379/0'

                    try:
                        redis_client = redis.from_url(REDIS_URL)
                    except Exception:
                        redis_client = None
                except Exception:
                    redis_client = None

                if getattr(shared, '_DB_AVAILABLE', False):
                    db = shared.SessionLocal()

                # on connect, send existing logs (if DB available)
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
                            last_id = max(last_id, getattr(rr, 'id', 0))
                            # Try to parse message as JSON to see if it encodes a structured event
                            payload = None
                            event_name = 'log'
                            try:
                                payload = json.loads(rr.message) if rr.message else None
                                if isinstance(payload, dict) and 'type' in payload:
                                    event_name = payload.get('type') or 'log'
                                    # ensure run_id and node_id are present for consistency
                                    payload.setdefault('run_id', rr.run_id)
                                    payload.setdefault('node_id', rr.node_id)
                                    payload.setdefault('timestamp', rr.timestamp.isoformat() if rr.timestamp is not None else None)
                                else:
                                    payload = {
                                        'type': 'log',
                                        'id': rr.id,
                                        'run_id': rr.run_id,
                                        'node_id': rr.node_id,
                                        'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                        'level': rr.level,
                                        'message': rr.message,
                                    }
                            except Exception:
                                payload = {
                                    'type': 'log',
                                    'id': rr.id,
                                    'run_id': rr.run_id,
                                    'node_id': rr.node_id,
                                    'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                    'level': rr.level,
                                    'message': rr.message,
                                }
                            out.append((event_name, payload))
                        for event_name, item in out:
                            # emit explicit SSE event name for structured DB rows
                            yield f"event: {event_name}\n"
                            yield f"data: {json.dumps(item)}\n\n"
                            last_activity = asyncio.get_event_loop().time()
                    except Exception:
                        # ignore initial read errors but continue streaming
                        pass
                else:
                    # no DB: for in-memory runs there are no persisted logs; just send a note
                    note_payload = {'note': 'in-memory run; no persisted logs'}
                    yield f"event: log\n"
                    yield f"data: {json.dumps(note_payload)}\n\n"
                    last_activity = asyncio.get_event_loop().time()

                # If Redis is available, subscribe and stream events from it.
                if redis_client is not None:
                    try:
                        # We'll run a resilient listener in a dedicated thread. The
                        # listener will manage its own redis client and pubsub and
                        # will reconnect on transient errors.
                        channel_name = f"run:{run_id}:events"
                        message_queue = asyncio.Queue()
                        redis_stop = __import__('threading').Event()
                        redis_ready = __import__('threading').Event()

                        def _redis_listener_loop(redis_url, channel, loop, q, stop_event, ready_event):
                            import time as _time
                            import logging as _logging
                            import json as _json
                            logger = _logging.getLogger(__name__)
                            backoff = 1.0
                            max_backoff = 60.0

                            while not stop_event.is_set():
                                client = None
                                pubsub = None
                                try:
                                    try:
                                        client = redis.from_url(redis_url)
                                    except Exception:
                                        client = None

                                    if client is None:
                                        raise RuntimeError('failed to create redis client')

                                    pubsub = client.pubsub(ignore_subscribe_messages=True)
                                    pubsub.subscribe(channel)
                                    logger.info('Subscribed to redis channel %s', channel)

                                    # signal that we've successfully subscribed so the
                                    # main loop can rely on the listener being functional
                                    try:
                                        ready_event.set()
                                    except Exception:
                                        pass

                                    # reset backoff after a successful subscribe
                                    backoff = 1.0

                                    # loop reading messages using get_message so we can timeout
                                    while not stop_event.is_set():
                                        try:
                                            msg = pubsub.get_message(timeout=1.0)
                                        except Exception as exc:
                                            # socket errors / connection closed -> break to reconnect
                                            logger.warning('Redis get_message error: %s', exc)
                                            break

                                        if not msg:
                                            continue
                                        if msg.get('type') != 'message':
                                            continue
                                        data = msg.get('data')
                                        try:
                                            if isinstance(data, bytes):
                                                payload = _json.loads(data.decode('utf-8'))
                                            else:
                                                payload = _json.loads(data)
                                        except Exception:
                                            payload = {'type': 'raw', 'raw': data}

                                        try:
                                            loop.call_soon_threadsafe(q.put_nowait, payload)
                                        except Exception:
                                            # queue likely closed or full; ignore and continue
                                            continue

                                except Exception as exc:
                                    logger.warning('Redis listener problem for channel %s: %s', channel, exc)

                                finally:
                                    try:
                                        if pubsub is not None:
                                            pubsub.close()
                                    except Exception:
                                        pass
                                    try:
                                        if client is not None:
                                            # redis-py may not have explicit close on client for older versions
                                            try:
                                                client.close()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                # if we're here, sleep with backoff before reconnecting
                                if stop_event.is_set():
                                    break
                                _time.sleep(backoff)
                                backoff = min(backoff * 2, max_backoff)

                        # start the thread; it will manage reconnects internally
                        import threading as _threading
                        redis_thread = _threading.Thread(
                            target=_redis_listener_loop,
                            args=(REDIS_URL, channel_name, asyncio.get_event_loop(), message_queue, redis_stop, redis_ready),
                            daemon=True,
                        )
                        redis_thread.start()

                        # wait briefly for the listener to confirm subscription
                        try:
                            ok = await asyncio.get_event_loop().run_in_executor(None, redis_ready.wait, 1.0)
                            if not ok:
                                # Listener didn't subscribe quickly -> assume Redis not usable and fall back
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
                        except Exception:
                            redis_client = None
                            redis_thread = None
                            message_queue = None
                    except Exception:
                        # can't subscribe; fall back to DB polling below
                        redis_client = None

                # Main loop: prefer Redis events when available, otherwise DB poll
                while True:
                    sent_any = False

                    if message_queue is not None:
                        # wait for a message with a short timeout so we can emit heartbeats
                        try:
                            msg = await asyncio.wait_for(message_queue.get(), timeout=poll_interval)
                        except Exception:
                            msg = None

                        if msg:
                            # msg expected to be a dict with 'type'
                            mtype = msg.get('type') if isinstance(msg, dict) else None
                            if mtype == 'log':
                                # emit as SSE event 'log'
                                yield f"event: log\n"
                                yield f"data: {json.dumps(msg)}\n\n"
                                last_activity = asyncio.get_event_loop().time()
                                sent_any = True
                            elif mtype == 'status':
                                # emit final status as SSE event 'status' and close
                                status_payload = {'run_id': run_id, 'status': msg.get('status')}
                                yield f"event: status\n"
                                yield f"data: {json.dumps(status_payload)}\n\n"
                                return
                            else:
                                # unknown type: emit as 'log' with raw payload
                                yield f"event: log\n"
                                yield f"data: {json.dumps({'raw': msg})}\n\n"
                                last_activity = asyncio.get_event_loop().time()
                                sent_any = True
                    else:
                        # Redis unavailable: fall back to DB polling (existing behavior)
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
                                        'type': 'log',
                                        'id': rr.id,
                                        'run_id': rr.run_id,
                                        'node_id': rr.node_id,
                                        'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                        'level': rr.level,
                                        'message': rr.message,
                                    }
                                    last_id = max(last_id, getattr(rr, 'id', 0))
                                    # emit explicit SSE event name 'log' for each DB row
                                    yield f"event: log\n"
                                    yield f"data: {json.dumps(item)}\n\n"
                                    sent_any = True
                                    last_activity = asyncio.get_event_loop().time()
                            except Exception:
                                # swallow transient DB errors
                                pass

                            # check run terminal state and close if finished and no pending logs
                            try:
                                from backend import models as _models
                                r = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                                if r and getattr(r, 'status', None) in ('success', 'failed'):
                                    status_payload = {'run_id': run_id, 'status': r.status}
                                    yield f"event: status\n"
                                    yield f"data: {json.dumps(status_payload)}\n\n"
                                    return
                            except Exception:
                                pass

                    # heartbeats when idle
                    now = asyncio.get_event_loop().time()
                    if (now - last_activity) >= heartbeat_interval:
                        yield ':\n\n'
                        last_activity = now

            finally:
                # cleanup DB and Redis listener thread
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

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.get_run_detail_impl(run_id, authorization)
