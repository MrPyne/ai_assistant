import logging
import os
from datetime import datetime

from celery import Celery
import requests

from .database import SessionLocal
from .models import Run, Workflow, RunLog, Provider
from .utils import redact_secrets
from .crypto import decrypt_value

from .adapters.openai_adapter import OpenAIAdapter
from .adapters.ollama_adapter import OllamaAdapter
try:
    from jinja2.sandbox import SandboxedEnvironment as JinjaEnv
except Exception:
    JinjaEnv = None

logger = logging.getLogger(__name__)

# Support both older env var names (CELERY_BROKER / CELERY_BACKEND) and the
# more explicit names used in .env/.env.example (CELERY_BROKER_URL,
# CELERY_RESULT_BACKEND). This makes Docker Compose and local env files
# interoperable.
CELERY_BROKER = os.getenv('CELERY_BROKER_URL') or os.getenv('CELERY_BROKER') or 'redis://localhost:6379/0'
CELERY_BACKEND = os.getenv('CELERY_RESULT_BACKEND') or os.getenv('CELERY_BACKEND') or 'redis://localhost:6379/1'

celery_app = Celery('backend.tasks', broker=CELERY_BROKER, backend=CELERY_BACKEND)

# Simple in-process metrics bag. This is intentionally lightweight and
# non-persistent; we'll replace or export these metrics in a follow-up
# (Prometheus / pushgateway etc.). Keys: runs_processed, runs_succeeded,
# runs_failed.
METRICS = {
    'runs_processed': 0,
    'runs_succeeded': 0,
    'runs_failed': 0,
}



@celery_app.task(bind=True, name='execute_workflow')
def execute_workflow(self, run_id):
    """Celery task wrapper that invokes process_run and implements a
    simple retry/backoff policy. Retries are performed via self.retry so
    Celery will re-enqueue the task. Configuration via env:
      - MAX_RUN_RETRIES (default 3)
      - RUN_RETRY_BACKOFF (seconds, default 5)
    """
    max_retries = int(os.getenv('MAX_RUN_RETRIES', '3'))
    base_backoff = int(os.getenv('RUN_RETRY_BACKOFF', '5'))

    # call the processor
    result = process_run(run_id)

    # update simple in-memory metrics and emit a structured-ish log line
    try:
        METRICS['runs_processed'] += 1
        if result.get('status') == 'success':
            METRICS['runs_succeeded'] += 1
        elif result.get('status') == 'failed':
            METRICS['runs_failed'] += 1
        logger.info(
            f"execute_workflow finished run_id={run_id} status={result.get('status')} attempts={result.get('attempts', 'n/a')}",
            extra={'metrics': METRICS.copy(), 'run_id': run_id, 'status': result.get('status')},
        )
    except Exception:
        logger.exception("Failed updating metrics for run %s", run_id)

    # if processing reported failure, decide whether to retry or mark as DLQ
    try:
        # reload run to get attempts count
        db = SessionLocal()
        run = db.query(Run).filter(Run.id == run_id).first()
        attempts = getattr(run, 'attempts', 0) if run else 0
    except Exception:
        attempts = 0
    finally:
        try:
            db.close()
        except Exception:
            pass

    if result.get('status') == 'failed':
        if attempts < max_retries:
            # schedule retry with exponential-ish backoff
            countdown = base_backoff * (2 ** (attempts - 1)) if attempts > 0 else base_backoff
            try:
                raise self.retry(countdown=countdown, max_retries=max_retries)
            except Exception:
                # if retry fails or maxed, just propagate
                raise
        else:
            # Exceeded max retries: mark run as permanently failed (DLQ)
            try:
                db = SessionLocal()
                run = db.query(Run).filter(Run.id == run_id).first()
                if run:
                    run.status = 'failed'
                    run.finished_at = datetime.utcnow()
                    db.add(run)
                    db.commit()
                    _write_log(db, run.id, None, 'error', f"Run marked failed after {attempts} attempts (DLQ)")
            except Exception:
                logger.exception("Failed to mark run %s as DLQ", run_id)
            finally:
                try:
                    db.close()
                except Exception:
                    pass

    return result


def _write_log(db, run_id, node_id, level, message):
    try:
        # redact before persisting to avoid accidental secret leaks
        safe_msg = redact_secrets(message)
        rl = RunLog(run_id=run_id, node_id=node_id, level=level, message=safe_msg)
        db.add(rl)
        db.commit()
    except Exception:
        logger.exception("Failed to write RunLog for run %s node %s", run_id, node_id)


def _execute_node(db, run, node):
    node_id = node.get('id')
    ntype = node.get('type')
    _write_log(db, run.id, node_id, 'info', f"Executing node {node_id} type={ntype}")

    if ntype == 'llm':
        provider_id = node.get('provider_id')
        prompt = node.get('prompt', '')
        provider = None
        if provider_id:
            provider = db.query(Provider).filter(Provider.id == provider_id).first()
        if not provider:
            _write_log(db, run.id, node_id, 'warning', f"No provider configured for node {node_id}; returning mock response")
            return {'text': '[mock] no provider configured'}
        if provider.type == 'openai':
            adapter = OpenAIAdapter(provider, db=db)
            resp = adapter.generate(prompt)
            # redact obvious secrets before writing to logs
            _write_log(db, run.id, node_id, 'info', f"LLM response: {str(redact_secrets(resp))[:500]}")
            return resp
        elif provider.type == 'ollama':
            adapter = OllamaAdapter(provider, db=db)
            resp = adapter.generate(prompt)
            _write_log(db, run.id, node_id, 'info', f"LLM response: {str(redact_secrets(resp))[:500]}")
            return resp
        else:
            _write_log(db, run.id, node_id, 'warning', f"Unknown provider type: {provider.type}")
            return {'text': '[mock] unknown provider'}

    if ntype in ('http', 'http_request'):
        method = node.get('method', 'GET').upper()
        url = node.get('url')
        body = node.get('body')
        headers = node.get('headers') or {}
        # Render templated fields (safe sandboxed Jinja when available).
        # Templates have access to a minimal context: input (run.input_payload),
        # run (id, workflow_id) and a now timestamp. This keeps evaluation
        # deterministic and avoids exposing internals.
        def _safe_render(obj):
            if JinjaEnv is None:
                return obj
            env = JinjaEnv()
            ctx = {
                'input': getattr(run, 'input_payload', {}) or {},
                'run': {'id': run.id, 'workflow_id': run.workflow_id},
                'now': datetime.utcnow().isoformat(),
            }

            def _render_str(s):
                try:
                    if not isinstance(s, str):
                        return s
                    tpl = env.from_string(s)
                    return tpl.render(**ctx)
                except Exception:
                    # On template errors, fall back to the original value to
                    # avoid failing the whole run.
                    return s

            if isinstance(obj, str):
                return _render_str(obj)
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    out[k] = _safe_render(v)
                return out
            if isinstance(obj, list):
                return [_safe_render(v) for v in obj]
            return obj

        try:
            url = _safe_render(url)
            headers = _safe_render(headers) or {}
            body = _safe_render(body)
        except Exception:
            # rendering should be best-effort and non-fatal
            pass
        # Resolve any provider secret referenced by a Provider configured
        # on the node. This allows us to redact literal secret values that
        # may not be matched by generic regexes. Resolution is best-effort
        # and failures are non-fatal.
        known_secrets = []
        provider_id = node.get('provider_id') or node.get('provider')
        if provider_id and db is not None:
            try:
                prov = db.query(Provider).filter(Provider.id == provider_id).first()
                if prov and getattr(prov, 'secret_id', None):
                    from .models import Secret

                    s = db.query(Secret).filter(Secret.id == prov.secret_id, Secret.workspace_id == prov.workspace_id).first()
                    if s:
                        try:
                            val = decrypt_value(s.encrypted_value)
                            if val:
                                known_secrets.append(val)
                        except Exception:
                            # ignore decryption failures
                            pass
            except Exception:
                pass

        def _replace_known_secrets_in_str(s: str) -> str:
            if not s or not known_secrets:
                return s
            out = s
            for ks in known_secrets:
                try:
                    if ks and ks in out:
                        out = out.replace(ks, '[REDACTED]')
                except Exception:
                    continue
            return out

        def _replace_known_secrets(obj):
            # Recursively replace occurrences of known secrets in strings
            if isinstance(obj, str):
                return _replace_known_secrets_in_str(obj)
            if isinstance(obj, dict):
                return {k: _replace_known_secrets(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_replace_known_secrets(v) for v in obj]
            return obj
        try:
            if method == 'GET':
                r = requests.get(url, headers=headers, params=body, timeout=10)
            else:
                r = requests.post(url, headers=headers, json=body, timeout=10)
            # redact known secrets from logs
            info_msg = f"HTTP {method} {url} -> status {r.status_code}"
            info_msg = _replace_known_secrets_in_str(info_msg)
            _write_log(db, run.id, node_id, 'info', info_msg)
            try:
                data = r.json()
                return _replace_known_secrets(data)
            except Exception:
                return {'text': _replace_known_secrets(r.text)}
        except Exception as e:
            err = str(e)
            err = _replace_known_secrets_in_str(err)
            _write_log(db, run.id, node_id, 'error', f"HTTP request failed: {err}")
            return {'error': err}

    # default/mock
    _write_log(db, run.id, node_id, 'info', f"Node type {ntype} not implemented; returning mock")
    return {'text': f'[mock] node {node_id}'}


def _convert_elements_to_runtime_nodes(elements):
    """Convert a list of React Flow elements or runtime nodes into a
    consistent runtime node list that process_run understands.

    Accepts either:
      - runtime nodes: dicts with a 'type' key like 'http' or 'llm'
      - react-flow elements: dicts with 'data' and 'position' where
        data.label indicates the human-friendly node type and
        data.config holds node configuration.
    """
    runtime = []
    if not elements:
        return runtime

    for el in elements:
        # Already a runtime node
        if isinstance(el, dict) and el.get('type') in ('http', 'llm'):
            runtime.append(el)
            continue

        # React Flow node (has 'data')
        if isinstance(el, dict) and 'data' in el:
            data = el.get('data') or {}
            label = data.get('label', '').lower()
            cfg = data.get('config') or {}
            node_id = el.get('id')
            pos = el.get('position')

            if 'http' in label or 'http request' in label:
                n = {
                    'id': node_id,
                    'type': 'http',
                    'method': cfg.get('method', 'GET'),
                    'url': cfg.get('url'),
                    'headers': cfg.get('headers') or {},
                    'body': cfg.get('body'),
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'llm' in label or label.startswith('llm'):
                n = {
                    'id': node_id,
                    'type': 'llm',
                    'prompt': cfg.get('prompt', ''),
                    # provider id may be numeric or string; keep as-is
                    'provider_id': cfg.get('provider_id') or cfg.get('providerId') or cfg.get('provider'),
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            # fallback: include as mock node preserving id and raw config
            n = {'id': node_id, 'type': data.get('label') or 'unknown', 'config': cfg}
            if pos:
                n['position'] = pos
            runtime.append(n)
            continue

        # Unknown element shape, skip
    return runtime


def process_run(run_id):
    """Process a run by id: record logs and update status. This function is
    intentionally simple and defensive to avoid introducing indentation or
    syntax errors.
    """
    db = SessionLocal()
    try:
        run = db.query(Run).get(run_id)
        if not run:
            logger.error("Run not found: %s", run_id)
            return {"run_id": run_id, "status": "not_found"}

        # write start log
        msg = f"Starting run {run_id} at {datetime.utcnow().isoformat()}"
        _write_log(db, run.id, None, 'info', msg)

        # increment attempt counter (for basic retry/backoff tracking)
        try:
            run.attempts = (run.attempts or 0) + 1
            db.add(run)
            db.commit()
        except Exception:
            logger.exception("Failed to increment attempts for run %s", run_id)

        # load workflow and graph
        wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
        graph = wf.graph or {}
        nodes = None
        # graph may be stored in several shapes: a dict with 'nodes' (React Flow
        # or runtime nodes), or a plain list of nodes. Normalize both into a
        # runtime node list that _execute_node understands.
        if isinstance(graph, dict):
            raw_nodes = graph.get('nodes')
            nodes = _convert_elements_to_runtime_nodes(raw_nodes)
        elif isinstance(graph, list):
            nodes = _convert_elements_to_runtime_nodes(graph)
        else:
            nodes = None

        results = {}
        if nodes:
            for n in nodes:
                res = _execute_node(db, run, n)
                results[n.get('id')] = res
        else:
            _write_log(db, run.id, None, 'warning', 'No nodes defined in workflow graph; finishing')

        # finalize run (redact output before storing)
        run.status = 'success'
        run.finished_at = datetime.utcnow()
        try:
            run.output_payload = redact_secrets(results)
        except Exception:
            run.output_payload = None
        db.add(run)
        db.commit()

        _write_log(db, run.id, None, 'info', 'Run completed successfully')

        return {"run_id": run.id, "status": run.status, "output": run.output_payload}

    except Exception as e:
        logger.exception("Error processing run %s", run_id)
        # record error (redacted)
        err_msg = str(e)
        safe_err = redact_secrets(err_msg)
        try:
            rl = RunLog(run_id=run_id, level="error", message=safe_err)
            db.add(rl)
            db.commit()
        except Exception:
            logger.exception("Failed to write RunLog for run %s", run_id)
        return {"run_id": run_id, "status": "failed", "error": err_msg}
    finally:
        db.close()
