import os
import json
import logging
from datetime import datetime
import uuid
import hashlib

logger = logging.getLogger(__name__)

from .utils import redact_secrets
from .llm_utils import is_live_llm_enabled


class InvalidNodeError(Exception):
    """Raised when a required node_id is missing or invalid for a run."""
    pass


def process_run(run_db_id, node_id=None, node_graph=None, run_input=None):
    """Original inline process_run implementation (migrated for compatibility).

    This function was moved from backend.tasks during a safe refactor. It's
    kept here to preserve behavior until handlers are fully extracted.
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

    # New: inspect nodes for llm-type presence and log a summary so we can
    # determine whether the workflow actually contains any LLM nodes.
    try:
        llm_nodes = []
        for nid, ndef in nodes.items():
            try:
                dtype = ndef.get('type') or (isinstance(ndef.get('data'), dict) and ndef.get('data', {}).get('label'))
            except Exception:
                dtype = None
            if isinstance(dtype, str) and dtype.lower() == 'llm':
                llm_nodes.append(nid)
            else:
                # also consider labels starting with 'llm'
                try:
                    lab = (ndef.get('data') or {}).get('label') if isinstance(ndef.get('data'), dict) else None
                    if isinstance(lab, str) and lab.lower().startswith('llm'):
                        llm_nodes.append(nid)
                except Exception:
                    pass
        logger.info("LLM NODE SUMMARY run=%s llm_node_count=%s llm_node_ids=%s", run_db_id, len(llm_nodes), llm_nodes)
    except Exception:
        logger.exception("process_run failed to compute llm node summary for run %s", run_db_id)

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
            from .events import _publish_redis_event
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

        # New: log node metadata to help diagnose missing LLM behavior
        try:
            lab = None
            try:
                lab = (node.get('data') or {}).get('label') if isinstance(node.get('data'), dict) else None
            except Exception:
                lab = None
            logger.info("NODE EXEC run=%s node=%s detected_type=%s label=%s outgoing_targets=%s", run_db_id, current, ntype, lab, outgoing.get(current))
        except Exception:
            pass

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

            # Slack / webhook node (special-cased for nicer errors / mocks)
            elif ntype == 'slack' or (isinstance(node.get('data'), dict) and (node.get('data', {}).get('label') or '').lower().startswith('slack')):
                cfg = node.get('data', {}) or node
                url = cfg.get('url') or cfg.get('config', {}).get('url') or node.get('url')
                message = cfg.get('text') or cfg.get('message') or cfg.get('body') or cfg.get('config', {}).get('text') if isinstance(cfg.get('config'), dict) else None
                if not url:
                    result = {'error': 'slack node missing url'}
                else:
                    live_http = os.environ.get('LIVE_HTTP', 'false').lower() == 'true'
                    if not live_http:
                        result = {'text': '[mock] slack blocked by LIVE_HTTP'}
                    else:
                        import requests
                        try:
                            payload = None
                            try:
                                # allow full JSON body override
                                payload = cfg.get('payload') or cfg.get('body') or {'text': message}
                            except Exception:
                                payload = {'text': message}
                            r = requests.post(url, json=payload, timeout=5)
                            result = {'status_code': getattr(r, 'status_code', None), 'text': getattr(r, 'text', None)}
                        except Exception as exc:
                            result = {'error': str(exc)}

            # Email node
            elif ntype == 'email' or (isinstance(node.get('data'), dict) and (node.get('data', {}).get('label') or '').lower().startswith('email')):
                cfg = node.get('data', {}) or node
                host = cfg.get('host') or cfg.get('smtp_host') or (cfg.get('config') or {}).get('host')
                to_addrs = cfg.get('to') or cfg.get('recipients') or (cfg.get('config') or {}).get('to')
                from_addr = cfg.get('from') or (cfg.get('config') or {}).get('from') or 'noreply@example.com'
                subject = cfg.get('subject') or (cfg.get('config') or {}).get('subject') or ''
                body_text = cfg.get('body') or cfg.get('text') or (cfg.get('config') or {}).get('body') or ''
                port = int(cfg.get('port') or (cfg.get('config') or {}).get('port') or 25)
                use_tls = bool(cfg.get('use_tls') or (cfg.get('config') or {}).get('use_tls'))
                username = cfg.get('username') or (cfg.get('config') or {}).get('username')
                password = cfg.get('password') or (cfg.get('config') or {}).get('password')
                if not to_addrs or not host:
                    result = {'error': 'email node missing host or recipients'}
                else:
                    live_smtp = os.environ.get('LIVE_SMTP', 'false').lower() == 'true'
                    if not live_smtp:
                        result = {'text': '[mock] email blocked by LIVE_SMTP'}
                    else:
                        try:
                            import smtplib
                            if isinstance(to_addrs, str):
                                tos = [t.strip() for t in to_addrs.split(',') if t.strip()]
                            else:
                                tos = list(to_addrs)
                            msg = f"Subject: {subject}\n\n{body_text}"
                            server = smtplib.SMTP(host, port, timeout=5)
                            try:
                                if use_tls:
                                    try:
                                        server.starttls()
                                    except Exception:
                                        pass
                                if username and password:
                                    try:
                                        server.login(username, password)
                                    except Exception:
                                        pass
                                server.sendmail(from_addr, tos, msg)
                                result = {'status': 'sent', 'to': tos}
                            finally:
                                try:
                                    server.quit()
                                except Exception:
                                    pass
                        except Exception as exc:
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
                    # Debug: log how we resolved the provider and global live-llm flag
                    try:
                        live_enabled = is_live_llm_enabled()
                    except Exception:
                        live_enabled = None
                    try:
                        prov_id = getattr(provider_obj, 'id', None) if provider_obj is not None else None
                        prov_type = getattr(provider_obj, 'type', None) or (getattr(provider_obj, 'config', {}) or {}).get('type') if provider_obj is not None else None
                        prov_secret = getattr(provider_obj, 'secret_id', None) if provider_obj is not None else None
                        prov_workspace = getattr(provider_obj, 'workspace_id', None) if provider_obj is not None else None
                        prov_config_keys = None
                        try:
                            cfg = getattr(provider_obj, 'config', None)
                            if isinstance(cfg, dict):
                                prov_config_keys = list(cfg.keys())
                        except Exception:
                            prov_config_keys = None
                        logger.info("LLM NODE provider resolution run=%s node=%s provider_id=%s provider_type=%s provider_secret_id=%s workspace_id=%s config_keys=%s live_enabled=%s", run_db_id, current, prov_id, prov_type, prov_secret, prov_workspace, prov_config_keys, live_enabled)
                    except Exception:
                        logger.exception("LLM NODE provider resolution logging failed for run %s node %s", run_db_id, current)

                    if provider_obj is not None:
                        ptype = getattr(provider_obj, 'type', None) or (getattr(provider_obj, 'config', {}) or {}).get('type')
                        if ptype and ptype.lower() == 'openai':
                            from .adapters.openai_adapter import OpenAIAdapter
                            # Log presence of common env keys (do NOT log values)
                            try:
                                openai_key_present = bool(os.environ.get('OPENAI_API_KEY'))
                            except Exception:
                                openai_key_present = None
                            logger.info("LLM NODE selecting OpenAIAdapter provider_type=%s openai_key_present=%s", ptype, openai_key_present)
                            adapter = OpenAIAdapter(provider_obj, db_for_adapter)
                        elif ptype and ptype.lower() == 'ollama':
                            from .adapters.ollama_adapter import OllamaAdapter
                            try:
                                ollama_host_present = bool(os.environ.get('OLLAMA_HOST') or os.environ.get('OLLAMA_URL'))
                            except Exception:
                                ollama_host_present = None
                            logger.info("LLM NODE selecting OllamaAdapter provider_type=%s ollama_host_present=%s", ptype, ollama_host_present)
                            adapter = OllamaAdapter(provider_obj, db_for_adapter)
                        else:
                            # unknown provider: attempt openai adapter as default
                            from .adapters.openai_adapter import OpenAIAdapter
                            logger.info("LLM NODE provider type unknown (%s) falling back to OpenAIAdapter", ptype)
                            adapter = OpenAIAdapter(provider_obj, db_for_adapter)
                    else:
                        # no provider object found: create a minimal provider wrapper
                        from types import SimpleNamespace
                        dummy = SimpleNamespace(id=None, type='openai', workspace_id=None, secret_id=None, config={})
                        from .adapters.openai_adapter import OpenAIAdapter
                        logger.info("LLM NODE no provider object; using dummy OpenAIAdapter (mock/static) live_enabled=%s", live_enabled)
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
                        # Debug: log adapter and prompt summary before generation
                        try:
                            adapter_name = adapter.__class__.__name__ if adapter is not None else None
                        except Exception:
                            adapter_name = None
                        try:
                            prompt_preview = (prompt[:200] + '...') if isinstance(prompt, str) and len(prompt) > 200 else prompt
                        except Exception:
                            prompt_preview = None
                        logger.info("LLM NODE invoking adapter=%s run=%s node=%s prompt_len=%s model=%s prompt_preview=%s", adapter_name, run_db_id, current, (len(prompt) if isinstance(prompt, str) else None), node_model, (prompt_preview[:100] + '...') if isinstance(prompt_preview, str) and len(prompt_preview) > 100 else prompt_preview)
                        gen = adapter.generate(prompt or '', node_model=node_model)
                        logger.info("LLM NODE adapter=%s generation returned type=%s", adapter_name, type(gen))
                        # adapter should return dict with either text or error
                        if isinstance(gen, dict) and 'error' in gen:
                            logger.warning("LLM NODE adapter returned error for run=%s node=%s error=%s", run_db_id, current, gen.get('error'))
                            result = {'error': gen.get('error')}
                        else:
                            # normalize to include 'text' and optional 'meta'
                            text = gen.get('text') if isinstance(gen, dict) else str(gen)
                            meta = gen.get('meta') if isinstance(gen, dict) else None
                            try:
                                logger.info("LLM NODE generation success run=%s node=%s text_len=%s", run_db_id, current, (len(text) if isinstance(text, str) else None))
                            except Exception:
                                pass
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
                    from .events import _publish_redis_event
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
                    # just access run_input directly
                    try:
                        override = run_input.copy() if isinstance(run_input, dict) else {'input': run_input}
                    except Exception:
                        override = {'input': run_input}
                    override['input'] = chunk
                    # Return a simple processed record for legacy shim
                    return {'idx': idx, 'status': 'processed', 'chunk': chunk}

                # process chunks serially (parallel mode not implemented in legacy shim)
                for i, ch in enumerate(chunks):
                    try:
                        res = _process_chunk(i, ch)
                        chunk_results.append(res)
                    except Exception as e:
                        errors.append(str(e))
                        if fail_behavior == 'stop_on_error':
                            break

                result = {'chunks': total, 'results': chunk_results, 'errors': errors}

            else:
                # Default: try to extract a direct output from node definition
                try:
                    result = node.get('output') or node.get('data', {}).get('output') or None
                except Exception:
                    result = None

            # persist output and publish finished event
            outputs[current] = result
            try:
                from .events import _publish_redis_event
                _publish_redis_event({
                    'type': 'node',
                    'run_id': run_db_id,
                    'node_id': current,
                    'status': 'finished',
                    'timestamp': datetime.utcnow().isoformat(),
                    'level': 'info',
                    'message': f'Node {current} finished',
                    'result': redact_secrets(result) if result is not None else None,
                })
            except Exception:
                pass

            # enqueue outgoing targets unless they were already enqueued inside node logic
            for tgt in outgoing.get(current, []) or []:
                if tgt not in visited and tgt not in queue:
                    queue.append(tgt)

        except Exception as exc:
            logger.exception("process_run failed executing node %s for run %s: %s", current, run_db_id, exc)
            outputs[current] = {'error': str(exc)}
            # continue to next node

    # end while
    try:
        logger.info("process_run completed run=%s visited=%s", run_db_id, list(visited))
    except Exception:
        pass

    return outputs
