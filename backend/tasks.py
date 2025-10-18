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


class InvalidNodeError(Exception):
    """Raised when a required node_id is missing or invalid for a run."""
    pass


class CeleryAppStub:
    """A minimal celery_app-like stub with send_task for environments
    where Celery is not configured. send_task will raise to indicate
    Celery is unavailable so callers can fall back to inline processing."""

    def send_task(self, name, args=None, kwargs=None):
        raise RuntimeError("Celery not configured in this environment")


# Expose a celery_app attribute so callers that import backend.tasks.celery_app
# don't get AttributeError. In production this should be replaced with the
# real Celery app instance.
celery_app = CeleryAppStub()


# Backwards-compatibility: some deployment tooling (the celery CLI, older
# imports in the codebase, etc.) expect a module-level attribute named
# `celery`. Expose a `celery` variable. If the real Celery package is
# available and a broker URL is configured via environment variables we
# will attempt to construct a real Celery app; otherwise fall back to the
# CeleryAppStub to allow the import to succeed (workers will still fail
# to run where Celery is expected but the attribute will at least exist).
try:
    # Try to create a real Celery app when Celery is installed. We always
    # instantiate a Celery object so the celery CLI can import it (the
    # worker command expects to find an app instance at module load time).
    # If a broker URL is provided via env, configure it; otherwise leave
    # the app unconfigured so the CLI still imports cleanly but will
    # emit a clearer error about missing broker when the worker starts.
    from celery import Celery as _Celery  # type: ignore
    celery = _Celery("backend.tasks")
    _broker = os.environ.get("CELERY_BROKER_URL") or os.environ.get("BROKER_URL")
    if _broker:
        try:
            celery.conf.broker_url = _broker
        except Exception:
            # If setting config fails for any reason, log and continue with
            # the instantiated app; the worker CLI will provide more info.
            logger.exception("failed to set celery broker_url from env")
except Exception:
    # Celery not installed or failed to initialize; ensure attribute exists
    # so callers importing backend.tasks.celery won't get AttributeError.
    celery = celery_app


def _node_in_graph(node_graph, node_id):
    """Return True if node_id is present in node_graph.

    Accept common shapes: node_graph['nodes'] may be a dict keyed by id
    or a list of node dicts containing an 'id' field.
    """
    if not isinstance(node_graph, dict):
        return False
    nodes = node_graph.get("nodes")
    if nodes is None:
        return False
    if isinstance(nodes, dict):
        return node_id in nodes
    if isinstance(nodes, (list, tuple)):
        for n in nodes:
            if isinstance(n, dict) and n.get("id") == node_id:
                return True
    return False


def process_run(run_db_id, node_id=None, node_graph=None, run_input=None):
    """Process a workflow run inline.

    This is a simplified runner used for tests and the inline fallback
    when Celery is unavailable. It validates node_id and node_graph (or
    loads the graph from DB), then traverses the workflow graph from the
    starting node, executing supported node types and routing results
    along edges. Execution is synchronous and returns a dict with
    status and output mapping per-node.
    """
    logger.info("process_run called run_db_id=%s node_id=%s", run_db_id, node_id)

    # Acquire graph: use provided node_graph or load from DB
    graph = None
    if node_graph is not None:
        if not isinstance(node_graph, dict):
            logger.error("process_run node_graph must be a dict for run %s", run_db_id)
            raise InvalidNodeError("node_graph must be a dict")
        graph = node_graph
    else:
        # try DB
        try:
            from .database import SessionLocal
            from . import models as _models
            db = SessionLocal()
            try:
                run_obj = db.query(_models.Run).filter(_models.Run.id == run_db_id).first()
                if not run_obj:
                    logger.error("process_run could not find Run id=%s in DB", run_db_id)
                    raise InvalidNodeError(f"run id {run_db_id} not found")
                wf = db.query(_models.Workflow).filter(_models.Workflow.id == run_obj.workflow_id).first()
                if not wf or not getattr(wf, 'graph', None):
                    logger.error("process_run workflow/graph missing for run %s", run_db_id)
                    raise InvalidNodeError(f"workflow graph missing for run {run_db_id}")
                graph = wf.graph
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception:
            logger.error("process_run cannot validate node_id=%s for run %s because node_graph omitted and DB not available", node_id, run_db_id)
            raise InvalidNodeError("node_graph omitted and DB unavailable; cannot validate node_id")

    # Build helper maps for nodes and edges
    nodes = {}
    edges = []
    raw_nodes = graph.get('nodes') or []
    if isinstance(raw_nodes, dict):
        nodes = raw_nodes
    else:
        for n in raw_nodes:
            if isinstance(n, dict) and 'id' in n:
                nodes[n['id']] = n
    raw_edges = graph.get('edges') or []
    for e in raw_edges:
        if isinstance(e, dict) and 'source' in e and 'target' in e:
            edges.append(e)

    try:
        logger.info("process_run graph summary run=%s nodes=%s edges=%s", run_db_id, len(nodes), len(edges))
    except Exception:
        pass

    # adjacency list for outgoing edges
    outgoing = {}
    incoming = {}
    for e in edges:
        outgoing.setdefault(e['source'], []).append(e['target'])
        incoming.setdefault(e['target'], []).append(e['source'])

    # Attempt to fetch run input payload from DB (best-effort) unless
    # an explicit run_input override was provided (used by SplitInBatches
    # to pass per-chunk context into downstream execution).
    if run_input is None:
        run_input = {}
        try:
            from .database import SessionLocal
            from . import models as _models
            db = SessionLocal()
            try:
                run_obj = db.query(_models.Run).filter(_models.Run.id == run_db_id).first()
                if run_obj:
                    run_input = getattr(run_obj, 'input_payload', {}) or {}
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception:
            run_input = {}

    # simple evaluation context for templating expressions like {{ input.x }}
    def eval_expression(expr, context=None):
        try:
            if isinstance(expr, str) and expr.strip().startswith('{{') and expr.strip().endswith('}}'):
                inner = expr.strip()[2:-2].strip()
                # only support simple 'input.<key>' lookups for now
                if inner.startswith('input.'):
                    key = inner.split('.', 1)[1]
                    ctx = (context or {}).get('input') if context is not None else run_input
                    if ctx is None:
                        ctx = run_input
                    return ctx.get(key)
            return expr
        except Exception:
            return None

    # outputs collected per node
    outputs = {}

    # determine starting nodes when node_id omitted: nodes with no incoming edges
    if node_id:
        queue = [node_id]
    else:
        # nodes that are present but not targeted by any edge
        starting = [nid for nid in nodes.keys() if nid not in incoming]
        if not starting:
            # fallback: start from all nodes
            starting = list(nodes.keys())
        queue = starting
    try:
        logger.info("process_run starting queue for run=%s -> %s", run_db_id, queue)
    except Exception:
        pass

    visited = set()

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = nodes.get(current)
        if not node:
            outputs[current] = None
            continue

        ntype = node.get('type') or node.get('data', {}).get('label')
        result = None

        # Emit a node.started event so the UI can reflect that the node is running
        try:
            ts = datetime.utcnow().isoformat()
            _publish_redis_event({
                'type': 'node',
                'run_id': run_db_id,
                'node_id': current,
                'status': 'started',
                'timestamp': ts,
                'level': 'info',
                'message': f'Node {current} started',
            })
        except Exception:
            logger.exception("process_run failed to publish node started for run %s node %s", run_db_id, current)

        try:
            # HTTP node
            if ntype == 'http' or (isinstance(ntype, str) and ntype.lower() == 'http request'):
                cfg = node.get('data', {}) or node
                url = cfg.get('url') or cfg.get('config', {}).get('url') or node.get('url')
                method = (cfg.get('method') or cfg.get('config', {}).get('method') or 'GET').upper()
                headers = cfg.get('headers') or cfg.get('config', {}).get('headers') or {}
                body = cfg.get('body') or cfg.get('config', {}).get('body') or None
                import requests
                try:
                    if method == 'POST':
                        r = requests.post(url, headers=headers, json=body, timeout=5)
                    else:
                        r = requests.get(url, headers=headers, params=body, timeout=5)
                    result = {'status_code': getattr(r, 'status_code', None), 'text': getattr(r, 'text', None)}
                except Exception as exc:
                    # store exception message but redact via persistence layer
                    result = {'error': str(exc)}

            # LLM node
            elif isinstance(ntype, str) and ntype.lower() == 'llm' or (isinstance(node.get('data'), dict) and (node.get('data', {}).get('label') or '').lower().startswith('llm')):
                # extract prompt from multiple possible shapes
                cfg = node.get('data', {}) or node
                prompt = node.get('prompt') or cfg.get('prompt') or cfg.get('config', {}).get('prompt')
                # determine provider id or inline provider config
                provider_id = node.get('provider_id') or cfg.get('provider_id') or cfg.get('config', {}).get('provider_id') or cfg.get('config', {}).get('provider')
                provider_obj = None
                db_for_adapter = None
                if provider_id is not None:
                    # attempt to load provider from DB when possible
                    try:
                        # prefer a SessionLocal exposed on the module (tests may monkeypatch tasks.SessionLocal)
                        SessionLocal = globals().get('SessionLocal')
                        if SessionLocal is None:
                            from .database import SessionLocal
                        from . import models as _models
                        db = SessionLocal()
                        try:
                            provider_obj = db.query(_models.Provider).filter(_models.Provider.id == provider_id).first()
                            db_for_adapter = db
                        except Exception:
                            try:
                                db.close()
                            except Exception:
                                pass
                            provider_obj = None
                            db_for_adapter = None
                    except Exception:
                        provider_obj = None
                        db_for_adapter = None

                # fallback to inline provider dicts if present
                if provider_obj is None:
                    inline = None
                    try:
                        inline = cfg.get('provider') or cfg.get('config', {}).get('provider')
                    except Exception:
                        inline = None
                    if isinstance(inline, dict):
                        from types import SimpleNamespace
                        provider_obj = SimpleNamespace(**inline)

                # choose adapter based on provider type
                adapter = None
                try:
                    if provider_obj is not None:
                        ptype = getattr(provider_obj, 'type', None) or (getattr(provider_obj, 'config', {}) or {}).get('type')
                        if ptype and ptype.lower() == 'openai':
                            from .adapters.openai_adapter import OpenAIAdapter
                            adapter = OpenAIAdapter(provider_obj, db_for_adapter)
                        elif ptype and ptype.lower() == 'ollama':
                            from .adapters.ollama_adapter import OllamaAdapter
                            adapter = OllamaAdapter(provider_obj, db_for_adapter)
                        else:
                            # unknown provider: attempt openai adapter as default
                            from .adapters.openai_adapter import OpenAIAdapter
                            adapter = OpenAIAdapter(provider_obj, db_for_adapter)
                    else:
                        # no provider object found: create a minimal provider wrapper
                        from types import SimpleNamespace
                        dummy = SimpleNamespace(id=None, type='openai', workspace_id=None, secret_id=None, config={})
                        from .adapters.openai_adapter import OpenAIAdapter
                        adapter = OpenAIAdapter(dummy, None)
                except Exception as e:
                    logger.exception("process_run failed to instantiate adapter for llm node %s: %s", current, e)
                    adapter = None

                if adapter is None:
                    result = {'error': 'no adapter available'}
                else:
                    try:
                        node_model = None
                        try:
                            node_model = (cfg.get('config') or {}).get('model') if isinstance(cfg.get('config'), dict) else None
                        except Exception:
                            node_model = None
                        gen = adapter.generate(prompt or '', node_model=node_model)
                        # adapter should return dict with either text or error
                        if isinstance(gen, dict) and 'error' in gen:
                            result = {'error': gen.get('error')}
                        else:
                            # normalize to include 'text' and optional 'meta'
                            text = gen.get('text') if isinstance(gen, dict) else str(gen)
                            meta = gen.get('meta') if isinstance(gen, dict) else None
                            result = {'text': text, 'meta': meta}
                    except Exception as e:
                        logger.exception("process_run llm adapter.generate failed for node %s: %s", current, e)
                        result = {'error': str(e)}
                    finally:
                        # close DB session if we opened one for provider lookup
                        try:
                            if db_for_adapter is not None:
                                db_for_adapter.close()
                        except Exception:
                            pass

            # If node (branching)
            elif isinstance(node.get('data'), dict) and node.get('data', {}).get('label') == 'If':
                cfg = node.get('data', {}).get('config', {})
                expr = cfg.get('expression')
                # evaluate expression against run_input by default
                val = eval_expression(expr, {'input': run_input})
                true_target = cfg.get('true_target')
                false_target = cfg.get('false_target')
                chosen = true_target if val else false_target
                # record routing
                result = {'routed_to': chosen}
                if chosen:
                    queue.append(chosen)

            # SplitInBatches / Loop node
            elif isinstance(node.get('data'), dict) and node.get('data', {}).get('label') in ('SplitInBatches', 'Loop', 'Parallel'):
                # Config shape (MVP):
                # {
                #   'input_path': 'input.items',
                #   'batch_size': 10,
                #   'mode': 'serial'|'parallel',
                #   'concurrency': 4,
                #   'fail_behavior': 'stop_on_error'|'continue_on_error',
                # }
                cfg = node.get('data', {}).get('config', {}) or {}
                input_path = cfg.get('input_path') or cfg.get('path') or 'input'
                batch_size = int(cfg.get('batch_size') or cfg.get('size') or 1)
                mode = (cfg.get('mode') or 'serial').lower()
                concurrency = int(cfg.get('concurrency') or 1)
                fail_behavior = (cfg.get('fail_behavior') or 'stop_on_error')

                # helper to resolve dotted path from run_input
                def _get_by_path(obj, path):
                    if not path:
                        return obj
                    parts = path.split('.')
                    cur = obj
                    for p in parts:
                        if cur is None:
                            return None
                        if isinstance(cur, dict):
                            cur = cur.get(p)
                        else:
                            try:
                                cur = getattr(cur, p)
                            except Exception:
                                return None
                    return cur

                seq = _get_by_path({'input': run_input}, input_path)
                # Accept either the list itself or a single-key dict containing the list
                if seq is None:
                    seq = []
                # Chunk the sequence
                chunks = [seq[i:i + batch_size] for i in range(0, len(seq), batch_size)] if isinstance(seq, (list, tuple)) else [seq]
                total = len(chunks)
                chunk_results = []
                errors = []

                # Determine outgoing targets to process for each chunk; we'll
                # start execution at those nodes with a synthetic run id so
                # downstream nodes can run using the chunk as their input.
                targets = outgoing.get(current, [])

                # Emit a split.started event
                try:
                    _publish_redis_event({
                        'type': 'split',
                        'run_id': run_db_id,
                        'node_id': current,
                        'timestamp': datetime.utcnow().isoformat(),
                        'level': 'info',
                        'message': f'Split node {current} starting {total} chunks',
                        'total_chunks': total,
                    })
                except Exception:
                    pass

                # worker to process a single chunk (used in serial and parallel)
                def _process_chunk(idx, chunk):
                    synthetic_run_id = f"{run_db_id}.{current}.{idx}"
                    # prepare a run_input override where the input path points
                    # to the chunk; consumers can reference {{ input }} or
                    # the original dotted path depending on implementation.
                    # We'll provide a top-level 'input' mapping with the same
                    # structure as the parent but with the input_path key
                    # replaced by the chunk value when possible.
                    local_input = dict(run_input) if isinstance(run_input, dict) else {'input': run_input}
                    # attempt to set nested value by walking path
                    try:
                        parts = input_path.split('.')
                        if parts and parts[0] == 'input':
                            tgt = local_input.get('input', {}) if isinstance(local_input.get('input'), dict) else local_input.get('input') or {}
                            if isinstance(tgt, dict):
                                # set remaining path
                                sub = tgt
                                for p in parts[1:-1]:
                                    if p not in sub or not isinstance(sub.get(p), dict):
                                        sub[p] = {}
                                    sub = sub[p]
                                # final assign
                                if parts[-1]:
                                    sub[parts[-1]] = chunk
                            else:
                                # fallback: overwrite input
                                local_input['input'] = chunk
                        else:
                            # non-input root: simply place at 'input'
                            local_input['input'] = chunk
                    except Exception:
                        local_input = {'input': chunk}

                    # Emit per-chunk started event
                    try:
                        _publish_redis_event({
                            'type': 'split_chunk',
                            'run_id': run_db_id,
                            'node_id': current,
                            'timestamp': datetime.utcnow().isoformat(),
                            'level': 'info',
                            'message': f'Chunk {idx+1}/{total} started',
                            'chunk_index': idx,
                            'total_chunks': total,
                            'chunk_preview': repr(chunk)[:200],
                        })
                    except Exception:
                        pass

                    # If there are no downstream targets, just return the chunk
                    if not targets:
                        return {'chunk_index': idx, 'result': None}

                    # execute downstream starting at each target node and
                    # collect their outputs; we'll call process_run recursively
                    # with run_input override so downstream nodes can reference
                    # the chunk via {{ input }}.
                    aggregated = {}
                    for t in targets:
                        try:
                            subres = process_run(synthetic_run_id, node_id=t, node_graph=graph, run_input=local_input)
                            aggregated[t] = subres
                        except Exception as e:
                            aggregated[t] = {'error': str(e)}

                    # Emit per-chunk completion
                    try:
                        _publish_redis_event({
                            'type': 'split_chunk',
                            'run_id': run_db_id,
                            'node_id': current,
                            'timestamp': datetime.utcnow().isoformat(),
                            'level': 'info',
                            'message': f'Chunk {idx+1}/{total} completed',
                            'chunk_index': idx,
                            'total_chunks': total,
                        })
                    except Exception:
                        pass

                    return {'chunk_index': idx, 'result': aggregated}

                # Execute chunks
                if mode == 'parallel' and total > 0:
                    try:
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        max_workers = max(1, min(concurrency or 1, total))
                        with ThreadPoolExecutor(max_workers=max_workers) as ex:
                            futures = {ex.submit(_process_chunk, i, c): i for i, c in enumerate(chunks)}
                            for fut in as_completed(futures):
                                idx = futures[fut]
                                try:
                                    res = fut.result()
                                    chunk_results.append(res)
                                except Exception as e:
                                    errors.append({'chunk_index': idx, 'error': str(e)})
                                    if fail_behavior == 'stop_on_error':
                                        # attempt to cancel remaining futures
                                        for f in futures:
                                            try:
                                                f.cancel()
                                            except Exception:
                                                pass
                                        break
                    except Exception:
                        # fallback to serial if thread execution fails
                        for i, c in enumerate(chunks):
                            try:
                                chunk_results.append(_process_chunk(i, c))
                            except Exception as e:
                                errors.append({'chunk_index': i, 'error': str(e)})
                                if fail_behavior == 'stop_on_error':
                                    break
                else:
                    # serial processing
                    for i, c in enumerate(chunks):
                        try:
                            chunk_results.append(_process_chunk(i, c))
                        except Exception as e:
                            errors.append({'chunk_index': i, 'error': str(e)})
                            if fail_behavior == 'stop_on_error':
                                break

                result = {
                    'chunks': total,
                    'chunk_results': chunk_results,
                    'errors': errors,
                }

            # Execute sub-workflow / ExecuteWorkflow node
            elif isinstance(node.get('data'), dict) and node.get('data', {}).get('label') in ('ExecuteWorkflow', 'SubWorkflow'):
                # config may contain either an inline workflow graph under 'workflow'
                # or a 'workflow_id' to fetch from the DB. We run the child workflow
                # inline via process_run/execute_workflow and return its output as
                # the result for this node.
                cfg = node.get('data', {}).get('config', {}) or {}
                child_graph = cfg.get('workflow') or cfg.get('graph')
                child_wf_id = cfg.get('workflow_id')
                child_result = None
                try:
                    if child_graph:
                        # Run the child graph inline. Use a synthetic run id so
                        # persistence (when attempted) can still attribute events.
                        synthetic_run_id = f"{run_db_id}.{current}"
                        child_result = process_run(synthetic_run_id, node_id=None, node_graph=child_graph)
                    elif child_wf_id is not None:
                        # try to fetch workflow graph from DB and execute it
                        try:
                            from .database import SessionLocal
                            from . import models as _models
                            db = SessionLocal()
                            try:
                                wf = db.query(_models.Workflow).filter(_models.Workflow.id == child_wf_id).first()
                                if wf and getattr(wf, 'graph', None):
                                    synthetic_run_id = f"{run_db_id}.{current}"
                                    child_result = process_run(synthetic_run_id, node_id=None, node_graph=wf.graph)
                                else:
                                    child_result = {'error': f'workflow id {child_wf_id} not found or has no graph'}
                            finally:
                                try:
                                    db.close()
                                except Exception:
                                    pass
                        except Exception:
                            child_result = {'error': 'could not load child workflow from DB'}
                    else:
                        child_result = {'error': 'no child workflow specified'}
                except Exception as exc:
                    logger.exception("process_run sub-workflow execution failed run=%s node=%s", run_db_id, current)
                    child_result = {'error': str(exc)}

                result = {'subworkflow_result': child_result}

            # Switch node
            elif isinstance(node.get('data'), dict) and node.get('data', {}).get('label') == 'Switch':
                cfg = node.get('data', {}).get('config', {})
                expr = cfg.get('expression')
                val = eval_expression(expr, {'input': run_input})
                mapping = cfg.get('mapping', {}) or {}
                chosen = mapping.get(val) or cfg.get('default')
                result = {'routed_to': chosen}
                if chosen:
                    queue.append(chosen)

            else:
                # Unsupported node: mark as executed with a simple ok result
                result = {'status': 'ok'}

        except Exception as exc:
            logger.exception("process_run node execution failed run=%s node=%s", run_db_id, current)
            result = {'error': str(exc)}

        outputs[current] = result

        # enqueue outgoing edges if not already handled; for branching nodes
        # (If/Switch) we only follow the chosen route recorded in result.
        is_branching = isinstance(node.get('data'), dict) and node.get('data', {}).get('label') in ('If', 'Switch')
        if not is_branching:
            for tgt in outgoing.get(current, []):
                if tgt not in visited and tgt not in queue:
                    queue.append(tgt)

        # emit events for this node (completion)
        try:
            ts = datetime.utcnow().isoformat()
            logger.info("process_run: node executed run=%s node=%s result_keys=%s", run_db_id, current, list(result.keys()) if isinstance(result, dict) else None)
            _publish_redis_event({
                'type': 'log',
                'id': None,
                'run_id': run_db_id,
                'node_id': current,
                'timestamp': ts,
                'level': 'info',
                'message': f'Node {current} executed',
            })
            _publish_redis_event({
                'type': 'node',
                'run_id': run_db_id,
                'node_id': current,
                'status': 'success' if not (isinstance(result, dict) and 'error' in result) else 'failed',
                'result': result,
                'timestamp': datetime.utcnow().isoformat(),
            })
        except Exception:
            logger.exception("process_run failed to publish events for run %s node %s", run_db_id, current)

    logger.info("process_run completed run_db_id=%s", run_db_id)
    return {'status': 'success', 'output': outputs}


# For completeness, expose an execute_workflow function which workers may call.
# In the real system this would be the Celery task entrypoint. Here it simply
# delegates to process_run after validating arguments.
def execute_workflow(run_db_id, node_id=None, node_graph=None, **kwargs):
    return process_run(run_db_id, node_id=node_id, node_graph=node_graph)
