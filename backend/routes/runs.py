def register(app, ctx):
    from . import shared_impls as shared
    try:
        from fastapi import HTTPException, Header
        from fastapi.responses import StreamingResponse
        from typing import Optional
        _FASTAPI = True
    except Exception:
        class HTTPException(Exception):
            def __init__(self, status_code: int = 500, detail: str = None):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        def Header(default=None, **kwargs):
            return default

        class StreamingResponse:
            def __init__(self, gen, media_type=None):
                self._gen = gen
                self.media_type = media_type

            def __iter__(self):
                return iter(self._gen)

        from typing import Optional
        _FASTAPI = False

    @app.post('/api/workflows/{wf_id}/run')
    def manual_run(wf_id: int, request: dict, authorization: Optional[str] = Header(None)):
        try:
            from fastapi import Request
        except Exception:
            Request = None
        return shared.manual_run_impl(wf_id, request, authorization)

    @app.post('/api/runs/{run_id}/retry')
    def retry_run(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.retry_run_impl(run_id, authorization)

    @app.get('/api/runs')
    def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None), request: Optional["Request"] = None):
        auth = authorization
        try:
            if (not auth) and request is not None:
                auth = request.query_params.get('token') or auth
        except Exception:
            pass
        return shared.list_runs_impl(workflow_id, limit, offset, auth)

    @app.get('/api/runs/{run_id}/logs')
    def get_run_logs(run_id: int):
        import json
        try:
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
                                try:
                                    payload.setdefault('event_id', getattr(rr, 'event_id', None))
                                except Exception:
                                    pass
                                out.append(payload)
                            else:
                                out.append({
                                    'type': 'log',
                                    'id': rr.id,
                                    'run_id': rr.run_id,
                                    'node_id': rr.node_id,
                                    'event_id': getattr(rr, 'event_id', None),
                                    'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                    'level': rr.level,
                                    'message': rr.message,
                                })
                        except Exception:
                            continue
                    return {'logs': out}
                finally:
                    try:
                        if db is not None:
                            db.close()
                    except Exception:
                        pass

            if hasattr(shared, '_runs') and run_id in shared._runs:
                r = shared._runs.get(run_id)
                return {'logs': r.get('logs', [])}
            return {'logs': []}
        except Exception:
            return {'logs': []}

    @app.get('/api/runs/{run_id}/stream')
    async def stream_run(run_id: int, authorization: Optional[str] = Header(None), request: Optional["Request"] = None):
        import asyncio
        import json
        from datetime import datetime
        import logging

        logger = logging.getLogger(__name__)

        user_id = None
        try:
            auth = authorization
            try:
                if (not auth) and request is not None:
                    auth = request.query_params.get('token') or auth
            except Exception:
                pass
            user_id = shared._user_from_token(auth)
        except Exception:
            user_id = None
        if not user_id:
            raise HTTPException(status_code=401, detail='authorization required')
        logger.info("SSE connect requested run_id=%s user_id=%s", run_id, user_id)

        db = None
        run_row = None
        in_memory = False
        try:
            if getattr(shared, '_DB_AVAILABLE', False):
                try:
                    db = shared.SessionLocal()
                    from backend import models as _models
                    run_row = db.query(_models.Run).filter(_models.Run.id == run_id).first()
                    if not run_row:
                        if hasattr(shared, '_runs') and run_id in shared._runs:
                            in_memory = True
                        else:
                            raise HTTPException(status_code=404, detail='run not found')
                    else:
                        wf = db.query(_models.Workflow).filter(_models.Workflow.id == run_row.workflow_id).first()
                        wsid = None
                        if wf:
                            wsid = getattr(wf, 'workspace_id', None)
                        user_wsid = shared._workspace_for_user(user_id)
                        if wsid is not None and user_wsid != wsid:
                            raise HTTPException(status_code=403, detail='not allowed')
                except HTTPException:
                    raise
                except Exception:
                    raise HTTPException(status_code=500, detail='internal error')
            else:
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
            db = None
            last_id = 0
            last_activity = 0
            heartbeat_interval = 15
            poll_interval = 1

            redis_client = None
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
                            payload = None
                            event_name = 'log'
                            try:
                                payload = json.loads(rr.message) if rr.message else None
                                if isinstance(payload, dict) and 'type' in payload:
                                    event_name = payload.get('type') or 'log'
                                    payload.setdefault('run_id', rr.run_id)
                                    payload.setdefault('node_id', rr.node_id)
                                    payload.setdefault('timestamp', rr.timestamp.isoformat() if rr.timestamp is not None else None)
                                    try:
                                        payload.setdefault('event_id', getattr(rr, 'event_id', None))
                                    except Exception:
                                        pass
                                else:
                                    payload = {
                                        'type': 'log',
                                        'id': rr.id,
                                        'run_id': rr.run_id,
                                        'node_id': rr.node_id,
                                        'event_id': getattr(rr, 'event_id', None),
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
                        logger.info("SSE replayed %s existing DB logs for run_id=%s", len(out), run_id)
                        for event_name, item in out:
                            try:
                                eid = item.get('event_id')
                            except Exception:
                                eid = None
                            if eid:
                                yield f"id: {eid}\n"
                            yield f"event: {event_name}\n"
                            yield f"data: {json.dumps(item)}\n\n"
                            last_activity = asyncio.get_event_loop().time()
                    except Exception:
                        pass
                else:
                    note_payload = {'note': 'in-memory run; no persisted logs'}
                    yield f"event: log\n"
                    yield f"data: {json.dumps(note_payload)}\n\n"
                    last_activity = asyncio.get_event_loop().time()

                if redis_client is not None:
                    try:
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

                                    try:
                                        ready_event.set()
                                    except Exception:
                                        pass

                                    backoff = 1.0

                                    while not stop_event.is_set():
                                        try:
                                            msg = pubsub.get_message(timeout=1.0)
                                        except Exception as exc:
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
                                            try:
                                                client.close()
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass

                                if stop_event.is_set():
                                    break
                                _time.sleep(backoff)
                                backoff = min(backoff * 2, max_backoff)

                        import threading as _threading
                        redis_thread = _threading.Thread(
                            target=_redis_listener_loop,
                            args=(REDIS_URL, channel_name, asyncio.get_event_loop(), message_queue, redis_stop, redis_ready),
                            daemon=True,
                        )
                        redis_thread.start()

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

                while True:
                    sent_any = False

                    if message_queue is not None:
                        try:
                            msg = await asyncio.wait_for(message_queue.get(), timeout=poll_interval)
                        except Exception:
                            msg = None

                        if msg:
                            mtype = msg.get('type') if isinstance(msg, dict) else None
                            if mtype == 'log':
                                try:
                                    eid = msg.get('event_id') if isinstance(msg, dict) else None
                                except Exception:
                                    eid = None
                                if eid:
                                    yield f"id: {eid}\n"
                                yield f"event: log\n"
                                yield f"data: {json.dumps(msg)}\n\n"
                                last_activity = asyncio.get_event_loop().time()
                                sent_any = True
                            elif mtype == 'node':
                                try:
                                    eid = msg.get('event_id') if isinstance(msg, dict) else None
                                except Exception:
                                    eid = None
                                if eid:
                                    yield f"id: {eid}\n"
                                yield f"event: node\n"
                                yield f"data: {json.dumps(msg)}\n\n"
                                last_activity = asyncio.get_event_loop().time()
                                sent_any = True
                            elif mtype == 'status':
                                status_payload = {'run_id': run_id, 'status': msg.get('status')}
                                yield f"event: status\n"
                                yield f"data: {json.dumps(status_payload)}\n\n"
                                logger.info("SSE emitted final status for run_id=%s status=%s", run_id, msg.get('status'))
                                return
                            else:
                                yield f"event: log\n"
                                yield f"data: {json.dumps({'raw': msg})}\n\n"
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
                                        'type': 'log',
                                        'id': rr.id,
                                        'run_id': rr.run_id,
                                        'node_id': rr.node_id,
                                        'event_id': getattr(rr, 'event_id', None),
                                        'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None,
                                        'level': rr.level,
                                        'message': rr.message,
                                    }
                                    last_id = max(last_id, getattr(rr, 'id', 0))
                                    try:
                                        eid = item.get('event_id')
                                    except Exception:
                                        eid = None
                                    if eid:
                                        yield f"id: {eid}\n"
                                    yield f"event: log\n"
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
                                if r and getattr(r, 'status', None) in ('success', 'failed'):
                                    status_payload = {'run_id': run_id, 'status': r.status}
                                    yield f"event: status\n"
                                    yield f"data: {json.dumps(status_payload)}\n\n"
                                    logger.info("SSE emitted final DB status for run_id=%s status=%s", run_id, r.status)
                                    return
                            except Exception:
                                pass

                    now = asyncio.get_event_loop().time()
                    if (now - last_activity) >= heartbeat_interval:
                        yield ':\n\n'
                        last_activity = now

            finally:
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

        return StreamingResponse(event_stream(), media_type='text/event-stream')

    @app.get('/api/runs/{run_id}')
    def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
        return shared.get_run_detail_impl(run_id, authorization)
