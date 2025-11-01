from typing import Optional
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)

# Use auth helpers implemented in this package to avoid importing the
# legacy shared_impls at module import time (prevents circular imports).
from .auth_helpers import _user_from_token, _workspace_for_user, _add_audit


def manual_run_impl(wf_id: int, request, authorization: Optional[str]):
    """Create and enqueue a manual run for workflow wf_id.

    This implementation delegates storage of transient in-memory state to
    the legacy shared_impls module (imported lazily) so we keep a single
    authoritative in-memory view while moving the runtime logic out of
    the large shared_impls module.
    """
    # Import shared_impls lazily to access the in-memory stores and DB
    # availability flags without causing circular imports at module import
    # time (shared_impls imports this module during the migration).
    from .. import shared_impls as _shared

    user_id = _user_from_token(authorization)
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401)

    # ensure the in-memory counter exists on the shared shim
    try:
        _shared._run_counter
    except Exception:
        _shared._run_counter = 0
    _shared._run_counter += 1

    # prepare in-memory run record (used when DB not available or for quick response)
    run_id = _shared._run_counter
    _shared._runs[run_id] = {
        'id': run_id,
        'workflow_id': wf_id,
        'status': 'queued',
        'created_by': user_id,
        'created_at': datetime.utcnow().isoformat(),
    }

    # DB-backed path: persist run and attempt to enqueue execution via Celery
    if getattr(_shared, '_DB_AVAILABLE', False):
        db = None
        try:
            SessionLocal = getattr(_shared, 'SessionLocal', None)
            models = getattr(_shared, 'models', None)
            db = SessionLocal()
            r = models.Run(workflow_id=wf_id, status='queued')
            db.add(r)
            db.commit()
            db.refresh(r)

            # store mapping so in-memory view can reference the DB id
            _shared._runs[run_id]['db_id'] = r.id

            try:
                _add_audit(_workspace_for_user(user_id), user_id, 'create_run', object_type='run', object_id=r.id, detail='manual')
            except Exception:
                pass

            # Attempt to enqueue asynchronously after a small grace period so
            # clients can subscribe to the SSE stream.
            try:
                from .. import tasks as _tasks
            except Exception:
                _tasks = None

            try:
                grace = float(os.environ.get('RUN_START_GRACE', '0.5'))
            except Exception:
                grace = 0.5

            def _determine_start_node_for_run(run_db_id: int):
                try:
                    db_local = SessionLocal()
                except Exception:
                    return None
                try:
                    run_obj = db_local.query(models.Run).filter(models.Run.id == run_db_id).first()
                    if not run_obj or not getattr(run_obj, 'workflow_id', None):
                        return None
                    wf = db_local.query(models.Workflow).filter(models.Workflow.id == run_obj.workflow_id).first()
                    if not wf or not getattr(wf, 'graph', None):
                        return None
                    graph = wf.graph

                    # normalize nodes
                    raw_nodes = graph.get('nodes') if isinstance(graph, dict) else graph
                    nodes_map = {}
                    if isinstance(raw_nodes, dict):
                        nodes_map = raw_nodes
                    else:
                        for n in (raw_nodes or []):
                            if isinstance(n, dict) and 'id' in n:
                                nodes_map[n['id']] = n

                    # build incoming map
                    incoming = {}
                    raw_edges = graph.get('edges') or [] if isinstance(graph, dict) else []
                    for e in (raw_edges or []):
                        try:
                            src = e.get('source')
                            tgt = e.get('target')
                            if src and tgt:
                                incoming.setdefault(tgt, []).append(src)
                        except Exception:
                            pass

                    # prefer cron/timer nodes
                    for nid, nd in nodes_map.items():
                        try:
                            label = (nd.get('data') or {}).get('label') or nd.get('label') or ''
                            ntype = nd.get('type') or (nd.get('data') or {}).get('label')
                            if (isinstance(label, str) and 'cron' in label.lower()) or (isinstance(ntype, str) and ntype.lower() in ('timer', 'cron', 'cron trigger')):
                                return nid
                        except Exception:
                            continue

                    # nodes with no incoming edges
                    starters = [nid for nid in nodes_map.keys() if nid not in incoming]
                    if starters:
                        return starters[0]

                    # fallback to first declared node
                    if nodes_map:
                        return next(iter(nodes_map.keys()))

                except Exception:
                    try:
                        logger.exception('error while determining start node for run %s', run_db_id)
                    except Exception:
                        pass
                finally:
                    try:
                        db_local.close()
                    except Exception:
                        pass
                return None

            def _delayed_enqueue(db_run_id: int):
                # Small grace to allow SSE subscriptions
                try:
                    import time as _time
                    _time.sleep(grace)
                except Exception:
                    pass

                node_id = None
                try:
                    node_id = _determine_start_node_for_run(db_run_id)
                except Exception:
                    node_id = None

                try:
                    logger.info('manual_run enqueue determined node_id=%s for db_run_id=%s', node_id, db_run_id)
                except Exception:
                    pass

                # Best-effort publish of a node.started event scoped to node_id
                if node_id and _tasks is not None:
                    try:
                        _tasks._publish_redis_event({
                            'type': 'node',
                            'run_id': db_run_id,
                            'node_id': node_id,
                            'status': 'started',
                            'timestamp': datetime.utcnow().isoformat(),
                        })
                        logger.info('published node.started event for run=%s node=%s', db_run_id, node_id)
                    except Exception:
                        try:
                            logger.exception('failed to publish node.started event for run %s node %s', db_run_id, node_id)
                        except Exception:
                            pass

                # Try to enqueue via Celery; fall back to inline processing
                if _tasks is not None:
                    try:
                        _tasks.celery_app.send_task('execute_workflow', args=(db_run_id, node_id) if node_id else (db_run_id,))
                        logger.info('scheduled execute_workflow for db_run_id=%s node_id=%s', db_run_id, node_id)
                        return
                    except Exception:
                        try:
                            logger.exception('celery send_task failed for run %s; falling back to inline', db_run_id)
                        except Exception:
                            pass

                # Inline fallback
                try:
                    if node_id:
                        if _tasks is not None:
                            _tasks.process_run(db_run_id, node_id)
                        else:
                            # if tasks not importable, call local process_run if present
                            from ..tasks import process_run as _proc
                            _proc(db_run_id, node_id)
                        logger.info('processed execute_workflow inline for db_run_id=%s node_id=%s', db_run_id, node_id)
                    else:
                        if _tasks is not None:
                            _tasks.process_run(db_run_id)
                        else:
                            from ..tasks import process_run as _proc
                            _proc(db_run_id)
                        logger.info('processed execute_workflow inline for db_run_id=%s', db_run_id)
                except Exception:
                    try:
                        logger.exception('inline process_run failed for db_run_id=%s', db_run_id)
                    except Exception:
                        pass

            # Start background thread for enqueueing (daemon so it doesn't block shutdown)
            try:
                import threading as _threading
                t = _threading.Thread(target=_delayed_enqueue, args=(r.id,), daemon=True)
                t.start()
                try:
                    logger.info('manual_run scheduled run_id=%s delayed_start=%s', r.id, grace)
                except Exception:
                    pass
            except Exception:
                try:
                    logger.exception('failed to start enqueue thread for run %s', r.id)
                except Exception:
                    pass

            # Return DB run id for clients
            return {'run_id': r.id, 'status': 'queued'}

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

    # DB not available path: return in-memory run id
    return {'run_id': run_id, 'status': 'queued'}


def retry_run_impl(run_id: int, authorization: Optional[str]):
    # delegate to legacy shared_impls for now
    from .. import shared_impls as _shared
    return _shared.retry_run_impl(run_id, authorization)


def list_runs_impl(workflow_id, limit, offset, authorization):
    from .. import shared_impls as _shared
    return _shared.list_runs_impl(workflow_id, limit, offset, authorization)


def get_run_detail_impl(run_id: int, authorization: Optional[str]):
    from .. import shared_impls as _shared
    return _shared.get_run_detail_impl(run_id, authorization)
