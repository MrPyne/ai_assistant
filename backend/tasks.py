"""Minimal tasks module for workflow execution and Celery integration.

This file provides a conservative implementation so the Celery worker can
import backend.tasks without raising on startup. It exposes:

- celery_app: a real Celery app when celery is installed and configured, or
  a small fallback object with a send_task(name, args=(), kwargs={}) method
  used by the code that attempts to enqueue runs.
- process_run(run_id): a synchronous helper that performs a minimal run
  processing loop. In the full product this is much more sophisticated; for
  robustness we keep a small, safe implementation here so workers start and
  simple runs can be marked completed.

Notes:
- Tests or other modules may monkeypatch tasks.SessionLocal; to support that
  we attempt to import SessionLocal at module import time but allow it to be
  replaced later.
"""
from datetime import datetime
import threading
import os
import traceback
import json

# Try to import DB/session and models but degrade gracefully to None so this
# module is importable in environments where the DB/ORM isn't available.
try:
    from .database import SessionLocal  # type: ignore
    from . import models  # type: ignore
except Exception:
    SessionLocal = None
    models = None

# Provide a Celery app when celery is installed and broker configured.
# If celery is not available or not configured, expose a lightweight fallback
# object with a send_task() method so code that calls celery_app.send_task()
# won't crash at import time.
celery_app = None
try:
    from celery import Celery

    broker = os.getenv('CELERY_BROKER_URL') or os.getenv('REDIS_URL')
    backend = os.getenv('CELERY_RESULT_BACKEND')
    if not broker:
        # If no broker configured, create a local in-memory Celery app that
        # won't be used for remote workers but keeps the symbol present.
        celery_app = Celery(__name__)
    else:
        celery_app = Celery(__name__, broker=broker, backend=backend)
except Exception:
    # Fallback minimal object
    class _DummyCelery:
        def send_task(self, name, args=None, kwargs=None):
            """Mimic celery.Celery.send_task by dispatching known tasks in a
            background thread so enqueue attempts don't raise errors.
            """
            args = args or ()
            kwargs = kwargs or {}
            # Only handle the expected execute_workflow task; other tasks are
            # ignored but won't raise at import time.
            if name == 'execute_workflow' and len(args) >= 1:
                run_id = args[0]

                def _runner():
                    try:
                        process_run(run_id)
                    except Exception:
                        traceback.print_exc()

                t = threading.Thread(target=_runner, daemon=True)
                t.start()
            return None

    celery_app = _DummyCelery()

# Expose a decorator-like function when Celery available so tests or local
# uses can register tasks if desired. If real celery_app exists it will have
# a task attribute; otherwise we expose a no-op decorator.
try:
    task = celery_app.task
except Exception:
    def task(func=None, **_kwargs):
        if func is None:
            def _wrap(f):
                return f
            return _wrap
        return func


def _now_iso():
    return datetime.utcnow().isoformat()


def _publish_redis_event(event: dict):
    """Best-effort publish an event dict to Redis so SSE listeners using
    pub/sub receive real-time updates. Non-fatal: swallow all errors.
    """
    try:
        import redis
        REDIS_URL = os.getenv('REDIS_URL') or os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
        client = redis.from_url(REDIS_URL)
        channel = f"run:{event.get('run_id')}:events"
        client.publish(channel, json.dumps(event))
    except Exception:
        # Do not allow Redis problems to affect run processing
        pass


def _write_run_log(db, run_id, node_id, level, message):
    """Create a RunLog row and attempt to publish the corresponding Redis
    event. This centralizes error handling around DB writes and pub/sub.
    """
    try:
        rl = models.RunLog(run_id=run_id, node_id=node_id, level=level, message=message)
        db.add(rl)
        db.commit()
        try:
            payload = {
                'type': 'log',
                'id': rl.id,
                'run_id': run_id,
                'node_id': node_id,
                'timestamp': rl.timestamp.isoformat() if rl.timestamp is not None else None,
                'level': level,
                'message': message,
            }
            _publish_redis_event(payload)
        except Exception:
            pass
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def process_run(run_id):
    """Process a run id in a minimal, safe manner.

    Behavior:
    - If a SQLAlchemy SessionLocal and models are available, update the Run
      row setting started_at/finished_at/status and attempt a lightweight
      execution of LLM nodes so we exercise adapter integration. This is
      conservative: only LLM nodes are evaluated and external network calls
      remain gated by adapters' live flags.
    - If DB components aren't available, return a simple dict describing the
      simulated result.

    The implementation intentionally keeps node-level execution small but
    ensures that node.config.model (when present) is forwarded to adapters
    via the kwargs key 'node_model'. This restores node-level model selection
    coming from the UI.
    """
    # No-DB fallback
    if SessionLocal is None or models is None:
        return {'status': 'success', 'run_id': run_id, 'output': {}}

    db = None
    try:
        db = SessionLocal()
        r = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not r:
            return {'status': 'not_found', 'run_id': run_id}

        # mark started
        try:
            r.started_at = datetime.utcnow()
        except Exception:
            pass
        try:
            r.attempts = (getattr(r, 'attempts', 0) or 0) + 1
        except Exception:
            pass
        r.status = 'running'
        db.add(r)
        db.commit()

        # Attempt a minimal execution of workflow nodes (LLM nodes only).
        outputs = {}
        try:
            wf = db.query(models.Workflow).filter(models.Workflow.id == r.workflow_id).first()
            graph = getattr(wf, 'graph', {}) or {}
            nodes = graph.get('nodes') if isinstance(graph, dict) else None
            if not isinstance(nodes, list):
                nodes = []
        except Exception:
            nodes = []

        for node in nodes:
            try:
                if not isinstance(node, dict):
                    continue
                ntype = node.get('type')
                nid = node.get('id')

                if ntype != 'llm':
                    # only handle llm nodes in this minimal runner
                    continue

                # Resolve prompt and provider id from common shapes used by
                # tests and the UI. Support top-level fields and nested
                # data/config shapes.
                node_config = node.get('config') or (node.get('data') or {}).get('config') or {}
                if not isinstance(node_config, dict):
                    node_config = {}
                prompt = node.get('prompt') or node_config.get('prompt') or (node.get('data') or {}).get('prompt') or ''
                provider_id = node.get('provider_id') or node_config.get('provider_id') or (node.get('data') or {}).get('config', {}).get('provider_id')
                node_model = node_config.get('model') if isinstance(node_config, dict) else None

                if not provider_id:
                    # no provider specified; log and skip
                    try:
                        msg = f"LLM node {nid or '<unknown>'} skipped: no provider configured"
                        _write_run_log(db, run_id, nid, 'warning', msg)
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                    continue

                prov = db.query(models.Provider).filter(models.Provider.id == provider_id).first()
                if not prov:
                    try:
                        msg = f"LLM node {nid or '<unknown>'} skipped: provider id {provider_id} not found"
                        _write_run_log(db, run_id, nid, 'warning', msg)
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                    continue

                # Instantiate appropriate adapter based on provider.type. Import
                # adapters lazily to avoid import-time side effects in worker
                # startup.
                adapter = None
                ptype = (getattr(prov, 'type', '') or '').lower()
                try:
                    if ptype == 'openai':
                        from .adapters.openai_adapter import OpenAIAdapter

                        adapter = OpenAIAdapter(prov, db=db)
                    elif ptype == 'ollama':
                        from .adapters.ollama_adapter import OllamaAdapter

                        adapter = OllamaAdapter(prov, db=db)
                    else:
                        # unknown provider type: skip gracefully
                        adapter = None
                except Exception:
                    adapter = None

                if adapter is None:
                    try:
                        msg = f"LLM node {nid or '<unknown>'} skipped: no adapter for provider type {ptype}"
                        _write_run_log(db, run_id, nid, 'warning', msg)
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                    continue

                # Call adapter.generate and forward node-level model preference
                # via the 'node_model' kwarg so adapters can honor it.
                try:
                    resp = adapter.generate(prompt or '', node_model=node_model)
                except Exception as e:
                    resp = {'error': str(e)}

                # Normalize response text for logs/output
                text = None
                if isinstance(resp, dict):
                    text = resp.get('text') or (resp.get('meta') or {}).get('model') or None
                if text is None:
                    try:
                        text = str(resp)
                    except Exception:
                        text = ''

                outputs[nid or str(provider_id)] = text

                try:
                    _write_run_log(db, run_id, nid, 'info', text)
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

            except Exception as e:
                traceback.print_exc()
                try:
                    _write_run_log(db, run_id, node.get('id') if isinstance(node, dict) else None, 'error', str(e))
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                continue

        # mark finished
        try:
            r.finished_at = datetime.utcnow()
        except Exception:
            pass
        r.status = 'success'
        try:
            r.output_payload = outputs
        except Exception:
            pass
        db.add(r)
        db.commit()

        # publish final status to Redis so live SSE clients close promptly
        try:
            _publish_redis_event({'type': 'status', 'run_id': run_id, 'status': r.status})
        except Exception:
            pass

        return {'status': 'success', 'run_id': run_id, 'output': outputs}

    except Exception:
        traceback.print_exc()
        try:
            if db is not None and r is not None:
                r.status = 'failed'
                db.add(r)
                db.commit()
                try:
                    _publish_redis_event({'type': 'status', 'run_id': run_id, 'status': r.status})
                except Exception:
                    pass
        except Exception:
            try:
                if db is not None:
                    db.rollback()
            except Exception:
                pass
        return {'status': 'failed', 'run_id': run_id}
    finally:
        try:
            if db is not None:
                db.close()
        except Exception:
            pass


# Register a Celery task wrapper when we have a real celery app so external
# workers can invoke execute_workflow by name. If celery isn't installed the
# decorator above is a no-op and execute_workflow will just be a plain
# function.
@task(name='execute_workflow')
def execute_workflow(run_id):
    return process_run(run_id)
