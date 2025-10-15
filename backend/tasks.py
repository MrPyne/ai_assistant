import logging
import os
import time
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
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except Exception:
    boto3 = None

try:
    from croniter import croniter
except Exception:
    croniter = None
import threading
from datetime import timedelta
try:
    from jinja2.sandbox import SandboxedEnvironment as JinjaEnv
except Exception:
    JinjaEnv = None

logger = logging.getLogger(__name__)

# Add task-level debug logger
task_logger = logging.getLogger('backend.tasks')

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
        # Try to publish to Redis so any SSE subscribers can get pushed events.
        try:
            try:
                import redis
                import json as _json
                import os as _os
            except Exception:
                redis = None
            if redis is not None:
                try:
                    REDIS_URL = _os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
                    rc = redis.from_url(REDIS_URL)
                    payload = {
                        'type': 'log',
                        'id': getattr(rl, 'id', None),
                        'run_id': run_id,
                        'node_id': node_id,
                        'timestamp': getattr(rl, 'timestamp', None).isoformat() if getattr(rl, 'timestamp', None) is not None else None,
                        'level': level,
                        'message': safe_msg,
                    }
                    try:
                        rc.publish(f"run:{run_id}:events", _json.dumps(payload))
                    except Exception:
                        # swallow redis publish errors
                        pass
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        logger.exception("Failed to write RunLog for run %s node %s", run_id, node_id)


def _execute_node(db, run, node):
    node_id = node.get('id')
    ntype = node.get('type')
    _write_log(db, run.id, node_id, 'info', f"Executing node {node_id} type={ntype}")

    def _eval_expression(expr):
        """Evaluate a Jinja expression in a safe sandbox and return the
        rendered result. On error return None."""
        if not expr or JinjaEnv is None:
            return None
        try:
            env = JinjaEnv()
            ctx = {
                'input': getattr(run, 'input_payload', {}) or {},
                'run': {'id': run.id, 'workflow_id': run.workflow_id},
                'now': datetime.utcnow().isoformat(),
            }
            tpl = env.from_string(expr)
            return tpl.render(**ctx)
        except Exception:
            return None

    # Helper: resolve provider and its decrypted secret value (best-effort)
    def _resolve_provider_and_secret(provider_id):
        if not provider_id or db is None:
            task_logger.debug("_resolve_provider_and_secret: no provider_id or db; provider_id=%s", provider_id)
            return None, None
        prov = db.query(Provider).filter(Provider.id == provider_id).first()
        if not prov:
            task_logger.debug("_resolve_provider_and_secret: provider not found provider_id=%s", provider_id)
            return None, None
        secret_val = None
        try:
            if getattr(prov, 'secret_id', None):
                from .models import Secret

                s = db.query(Secret).filter(Secret.id == prov.secret_id, Secret.workspace_id == prov.workspace_id).first()
                if s:
                    try:
                        secret_val = decrypt_value(s.encrypted_value)
                        task_logger.debug("_resolve_provider_and_secret: decrypted secret for provider %s", provider_id)
                    except Exception as e:
                        task_logger.debug("_resolve_provider_and_secret: failed to decrypt secret for provider %s: %s", provider_id, e)
                        secret_val = None
        except Exception as e:
            task_logger.debug("_resolve_provider_and_secret: exception while resolving secret for provider %s: %s", provider_id, e)
            pass
        return prov, secret_val

    # SEND EMAIL
    if ntype in ('send_email', 'email', 'send email'):
        cfg = node.get('config') or node
        to = cfg.get('to')
        subject = cfg.get('subject') or cfg.get('title') or ''
        body = cfg.get('body') or cfg.get('text') or ''
        provider_id = cfg.get('provider_id') or cfg.get('provider')

        prov, secret_val = _resolve_provider_and_secret(provider_id)
        # Render templated fields
        try:
            if JinjaEnv is not None:
                env = JinjaEnv()
                ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                subject = env.from_string(subject).render(**ctx)
                body = env.from_string(body).render(**ctx)
        except Exception:
            pass

        # Try simple SMTP send (no external deps). Provider.type == 'smtp'
        try:
            import smtplib
            from email.message import EmailMessage

            host = None
            port = 25
            from_addr = None
            username = None
            password = None
            if prov:
                cfgp = prov.config or {}
                host = cfgp.get('host') or cfgp.get('smtp_host')
                port = cfgp.get('port') or cfgp.get('smtp_port') or port
                from_addr = cfgp.get('from') or cfgp.get('from_email')
            if secret_val:
                # secret may be JSON with user/password or a plain token or 'user:pass'
                try:
                    import json as _json

                    j = _json.loads(secret_val)
                    username = j.get('username') or j.get('user')
                    password = j.get('password')
                except Exception:
                    if ':' in secret_val:
                        username, password = secret_val.split(':', 1)
                    else:
                        password = secret_val

            if not host:
                _write_log(db, run.id, node_id, 'warning', 'No SMTP host configured for provider; skipping send')
                return {'status': 'skipped', 'reason': 'no_smtp_host'}

            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = from_addr or (username or 'no-reply@example.com')
            msg['To'] = to
            msg.set_content(body)

            smtp_port = int(port) if port else 25
            server = smtplib.SMTP(host, smtp_port, timeout=10)
            try:
                server.ehlo()
                if username and password:
                    server.starttls()
                    server.login(username, password)
                server.send_message(msg)
            finally:
                try:
                    server.quit()
                except Exception:
                    pass

            _write_log(db, run.id, node_id, 'info', f"Email sent to {to} via {prov.type if prov else 'smtp'}")
            return {'status': 'sent'}
        except Exception as e:
            _write_log(db, run.id, node_id, 'error', f"Email send failed: {str(e)}")
            return {'error': str(e)}

    # SLACK
    if ntype in ('slack', 'slack_message', 'slack message'):
        cfg = node.get('config') or node
        channel = cfg.get('channel') or cfg.get('to')
        text = cfg.get('text') or cfg.get('message') or ''
        blocks = cfg.get('blocks')
        provider_id = cfg.get('provider_id') or cfg.get('provider')

        prov, secret_val = _resolve_provider_and_secret(provider_id)
        try:
            if JinjaEnv is not None:
                env = JinjaEnv()
                ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                text = env.from_string(text).render(**ctx)
        except Exception:
            pass

        # If provider gives a webhook url in config use it; else if secret is a token use Slack API
        webhook = None
        if prov:
            webhook = (prov.config or {}).get('webhook_url')
        if webhook:
            try:
                r = requests.post(webhook, json={'text': text}, timeout=10)
                _write_log(db, run.id, node_id, 'info', f"Slack webhook posted -> status {r.status_code}")
                return {'status': 'posted', 'status_code': r.status_code}
            except Exception as e:
                _write_log(db, run.id, node_id, 'error', f"Slack webhook post failed: {e}")
                return {'error': str(e)}

        if secret_val:
            # secret_val may be the bearer token
            try:
                headers = {'Authorization': f"Bearer {secret_val}", 'Content-Type': 'application/json'}
                payload = {'channel': channel, 'text': text}
                if blocks:
                    payload['blocks'] = blocks
                r = requests.post('https://slack.com/api/chat.postMessage', json=payload, headers=headers, timeout=10)
                try:
                    data = r.json()
                except Exception:
                    data = {'status_code': r.status_code, 'text': r.text}
                _write_log(db, run.id, node_id, 'info', f"Slack API response: {str(redact_secrets(data))[:500]}")
                return data
            except Exception as e:
                _write_log(db, run.id, node_id, 'error', f"Slack API call failed: {e}")
                return {'error': str(e)}

        _write_log(db, run.id, node_id, 'warning', 'No Slack webhook or token configured; skipping')
        return {'status': 'skipped', 'reason': 'no_slack_configured'}

    # DB QUERY
    if ntype in ('db', 'db_query', 'db query', 'database'):
        cfg = node.get('config') or node
        query = cfg.get('query') or cfg.get('sql')
        provider_id = cfg.get('provider_id') or cfg.get('provider')

        prov, secret_val = _resolve_provider_and_secret(provider_id)
        # render query
        try:
            if JinjaEnv is not None and query:
                env = JinjaEnv()
                ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                query = env.from_string(query).render(**ctx)
        except Exception:
            pass

        if not query:
            _write_log(db, run.id, node_id, 'warning', 'No query provided')
            return {'error': 'no_query'}

        # Attempt to execute against postgres via psycopg2 if a DSN is available
        dsn = None
        if prov:
            dsn = (prov.config or {}).get('dsn') or (prov.config or {}).get('connection_string')
        if not dsn and secret_val:
            # secret may be a DSN string or JSON
            try:
                import json as _json

                j = _json.loads(secret_val)
                dsn = j.get('dsn') or j.get('connection_string')
            except Exception:
                # treat secret_val as DSN
                dsn = secret_val

        if not dsn:
            _write_log(db, run.id, node_id, 'warning', 'No DB connection configured; skipping')
            return {'status': 'skipped', 'reason': 'no_db_configured'}

        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            # Support parameterized queries via cfg.params (dict or list/tuple)
            params = cfg.get('params')
            try:
                if JinjaEnv is not None and params is not None:
                    # Render any templated string parameters
                    env = JinjaEnv()
                    ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                    if isinstance(params, dict):
                        params = {k: (env.from_string(v).render(**ctx) if isinstance(v, str) else v) for k, v in params.items()}
                    elif isinstance(params, list):
                        params = [(env.from_string(v).render(**ctx) if isinstance(v, str) else v) for v in params]
            except Exception:
                pass

            conn = psycopg2.connect(dsn)
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                if params is not None:
                    cur.execute(query, params)
                else:
                    cur.execute(query)
                if cur.description:
                    rows = cur.fetchall()
                    # convert Decimal etc. to serializable types if needed
                    result = [dict(r) for r in rows]
                else:
                    conn.commit()
                    result = {'rowcount': cur.rowcount}
                _write_log(db, run.id, node_id, 'info', f"DB query executed; rows: {len(result) if isinstance(result, list) else result}")
                return {'rows': result}
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        except Exception as e:
            _write_log(db, run.id, node_id, 'error', f"DB query failed: {e}")
            return {'error': str(e)}

    # S3 / FILE UPLOAD
    if ntype in ('s3', 's3_upload', 's3 upload', 'file_storage'):
        cfg = node.get('config') or node
        bucket = cfg.get('bucket')
        key = cfg.get('key')
        content = cfg.get('content') or cfg.get('body') or ''
        presigned = cfg.get('presigned_url')
        provider_id = cfg.get('provider_id') or cfg.get('provider')

        prov, secret_val = _resolve_provider_and_secret(provider_id)
        try:
            if JinjaEnv is not None:
                env = JinjaEnv()
                ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                key = env.from_string(key or '').render(**ctx)
                content = env.from_string(content or '').render(**ctx)
        except Exception:
            pass

        # Native S3 upload via boto3 if available and provider/secret contains creds
        # Priority: explicit presigned_url -> native boto3 upload -> provider upload_url_template -> skip
        if presigned:
            try:
                r = requests.put(presigned, data=content, timeout=20)
                _write_log(db, run.id, node_id, 'info', f"Uploaded to presigned URL -> status {r.status_code}")
                return {'status_code': r.status_code}
            except Exception as e:
                _write_log(db, run.id, node_id, 'error', f"Upload to presigned URL failed: {e}")
                return {'error': str(e)}

        # Try native boto3 upload when boto3 is available and we have bucket/key
        if boto3 is not None and bucket and key:
            # resolve credentials from provider config or secret
            aws_access_key = None
            aws_secret_key = None
            aws_session_token = None
            region = None
            if prov:
                pcfg = prov.config or {}
                region = pcfg.get('region') or pcfg.get('aws_region')
                # provider may include inline keys in config (not recommended)
                aws_access_key = pcfg.get('access_key') or pcfg.get('aws_access_key_id')
                aws_secret_key = pcfg.get('secret_key') or pcfg.get('aws_secret_access_key')
            if secret_val:
                try:
                    import json as _json

                    j = _json.loads(secret_val)
                    aws_access_key = aws_access_key or j.get('access_key') or j.get('aws_access_key_id')
                    aws_secret_key = aws_secret_key or j.get('secret_key') or j.get('aws_secret_access_key')
                    aws_session_token = j.get('session_token') or j.get('aws_session_token')
                    region = region or j.get('region') or j.get('aws_region')
                except Exception:
                    # treat secret_val as raw secret key if access key set in config
                    if aws_access_key and not aws_secret_key:
                        aws_secret_key = secret_val

            try:
                # build boto3 client with provided creds or rely on environment/instance profile
                client_kwargs = {}
                if aws_access_key and aws_secret_key:
                    client_kwargs['aws_access_key_id'] = aws_access_key
                    client_kwargs['aws_secret_access_key'] = aws_secret_key
                if aws_session_token:
                    client_kwargs['aws_session_token'] = aws_session_token
                if region:
                    client_kwargs['region_name'] = region

                s3 = boto3.client('s3', **client_kwargs) if client_kwargs else boto3.client('s3')
                # content may be a string; boto3 accepts bytes or file-like
                body = content.encode('utf-8') if isinstance(content, str) else content
                resp = s3.put_object(Bucket=bucket, Key=key, Body=body)
                _write_log(db, run.id, node_id, 'info', f"Uploaded to s3://{bucket}/{key}")
                # boto3 returns metadata in response dict; redact any obvious secrets
                return {'status_code': 200, 'response': redact_secrets(str(resp))}
            except (BotoCoreError, ClientError) as e:
                _write_log(db, run.id, node_id, 'error', f"S3 upload failed: {e}")
                return {'error': str(e)}
            except Exception as e:
                _write_log(db, run.id, node_id, 'error', f"S3 upload failed: {e}")
                return {'error': str(e)}

        # If provider.config contains an 'upload_url_template' allow rendering and use plain PUT
        upload_template = (prov.config or {}).get('upload_url_template') if prov is not None else None
        if upload_template:
            try:
                if JinjaEnv is not None:
                    env = JinjaEnv()
                    ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
                    url = env.from_string(upload_template).render(**ctx)
                else:
                    url = upload_template
                r = requests.put(url, data=content, timeout=20)
                _write_log(db, run.id, node_id, 'info', f"Uploaded to provider url -> status {r.status_code}")
                return {'status_code': r.status_code}
            except Exception as e:
                _write_log(db, run.id, node_id, 'error', f"S3 upload failed: {e}")
                return {'error': str(e)}

        _write_log(db, run.id, node_id, 'warning', 'No presigned URL, provider upload_url_template, or S3 credentials configured; skipping')
        return {'status': 'skipped', 'reason': 'no_upload_url_or_creds'}

    # TRANSFORM
    if ntype in ('transform', 'jinja_transform', 'template'):
        cfg = node.get('config') or node
        template = cfg.get('template') or cfg.get('script') or ''
        try:
            if JinjaEnv is None:
                _write_log(db, run.id, node_id, 'error', 'Jinja environment not available; cannot transform')
                return {'error': 'jinja_unavailable'}
            env = JinjaEnv()
            ctx = {'input': getattr(run, 'input_payload', {}) or {}, 'run': {'id': run.id}}
            tpl = env.from_string(template)
            out = tpl.render(**ctx)
            _write_log(db, run.id, node_id, 'info', f"Transform rendered output length {len(out) if out else 0}")
            return {'output': out}
        except Exception as e:
            _write_log(db, run.id, node_id, 'error', f"Transform failed: {e}")
            return {'error': str(e)}

    # WAIT / DELAY
    if ntype in ('wait', 'delay', 'wait_delay'):
        cfg = node.get('config') or node
        seconds = cfg.get('seconds') or cfg.get('delay_seconds') or cfg.get('duration') or 0
        try:
            sec = float(seconds)
        except Exception:
            sec = 0
        if sec <= 0:
            return {'status': 'skipped', 'reason': 'no_delay'}
        _write_log(db, run.id, node_id, 'info', f"Waiting for {sec} seconds")
        try:
            time.sleep(sec)
            return {'status': 'waited', 'seconds': sec}
        except Exception as e:
            _write_log(db, run.id, node_id, 'error', f"Wait failed: {e}")
            return {'error': str(e)}

    # Branching nodes: If/Condition and Switch
    if ntype in ('if', 'condition'):
        # config: expression (Jinja template), true_target, false_target, default_target
        cfg = node.get('config') or node
        expr = cfg.get('expression') or cfg.get('expr') or cfg.get('condition')
        rendered = _eval_expression(expr)
        choice = None
        try:
            # Jinja renders strings; interpret common boolean string values
            if isinstance(rendered, str):
                low = rendered.strip().lower()
                if low in ('', 'false', '0', 'none', 'null'):
                    choice = False
                else:
                    choice = True
            else:
                choice = bool(rendered)
        except Exception:
            choice = False

        # determine target
        target = cfg.get('true_target') if choice else cfg.get('false_target')
        if not target:
            target = cfg.get('default')
        _write_log(db, run.id, node_id, 'info', f"If node evaluated expression -> {rendered!r}, routed to {target}")
        return {'routed_to': target}

    if ntype == 'switch':
        # config: expression, mapping: {key: target}, default
        cfg = node.get('config') or node
        expr = cfg.get('expression') or cfg.get('expr')
        rendered = _eval_expression(expr)
        key = rendered
        # try to coerce numbers
        try:
            if isinstance(rendered, str) and rendered.isdigit():
                key = int(rendered)
        except Exception:
            pass
        mapping = cfg.get('mapping') or cfg.get('cases') or {}
        target = mapping.get(key)
        if target is None:
            # also try string keys
            target = mapping.get(str(key))
        if target is None:
            target = cfg.get('default')
        _write_log(db, run.id, node_id, 'info', f"Switch node evaluated -> {rendered!r}, routed to {target}")
        return {'routed_to': target}

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
            # By default, outbound HTTP is disabled unless LIVE_HTTP=true is
            # present in the environment. This is a safety measure for tests
            # and CI to avoid surprising external network calls. Tests that
            # need real HTTP behavior should explicitly set LIVE_HTTP=true
            # (see backend/tests/test_http_node_redaction.py).
            live_http = os.getenv('LIVE_HTTP', 'false').lower() == 'true'
            if not live_http:
                # Return a lightweight mock-like response object so the
                # rest of the code can continue to redact and log without
                # performing network IO.
                class _DummyResp:
                    def __init__(self):
                        self.status_code = 200
                        self.text = '[mock] http blocked by LIVE_HTTP'

                    def json(self):
                        raise ValueError('No JSON')

                r = _DummyResp()
            else:
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

    # LLM nodes
    try:
        ntype_lower = ntype.lower() if isinstance(ntype, str) else ''
    except Exception:
        ntype_lower = ''

    if ntype == 'llm' or 'llm' in ntype_lower:
        prompt = node.get('prompt') or (node.get('config') or {}).get('prompt') or ''
        provider_id = node.get('provider_id') or (node.get('config') or {}).get('provider_id') or (node.get('config') or {}).get('provider')
        prov = None
        task_logger.debug("LLM node invoked: node_id=%s provider_id=%s prompt_preview=%s", node.get('id'), provider_id, (prompt or '')[:80])
        try:
            if provider_id and db is not None:
                prov = db.query(Provider).filter(Provider.id == provider_id).first()
        except Exception:
            prov = None

        # Build a minimal provider-like object if none exists to allow adapters to operate
        try:
            from types import SimpleNamespace

            if prov is None:
                prov = SimpleNamespace(config={})
        except Exception:
            pass

        # choose adapter
        try:
            ptype = getattr(prov, 'type', '') or ''
            if isinstance(ptype, str) and 'ollama' in ptype.lower() or isinstance(ptype, str) and 'llama' in ptype.lower():
                adapter = OllamaAdapter(prov, db)
            else:
                adapter = OpenAIAdapter(prov, db)
            task_logger.debug("LLM node: using adapter %s for provider.type=%s provider_id=%s", adapter.__class__.__name__, getattr(prov, 'type', None), getattr(prov, 'id', None))
            res = adapter.generate(prompt)
            if isinstance(res, dict) and res.get('error'):
                _write_log(db, run.id, node_id, 'error', f"LLM generation failed: {res.get('error')}")
                return {'error': res.get('error')}
            # log a summary of the response
            txt = res.get('text') if isinstance(res, dict) else str(res)
            _write_log(db, run.id, node_id, 'info', f"LLM output: {txt}")
            task_logger.debug("LLM node result for node_id=%s: %s", node.get('id'), (txt or '')[:200])
            return res
        except Exception as e:
            _write_log(db, run.id, node_id, 'error', f"LLM node failed: {e}")
            return {'error': str(e)}

    # Cron / Timer trigger nodes
    if ntype_lower and ('cron' in ntype_lower or 'timer' in ntype_lower):
        # For manual runs, treat cron/timer nodes as a trigger that passes through.
        cfg = node.get('config') or {}
        msg = cfg.get('description') or cfg.get('schedule') or 'Cron trigger fired'
        _write_log(db, run.id, node_id, 'info', f"Cron trigger: {msg}")
        # expose the trigger config as the node result so downstream transforms can use it
        return {'status': 'triggered', 'config': cfg}

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
        if isinstance(el, dict) and el.get('type') in ('http', 'llm', 'send_email', 'slack', 'db', 's3', 'transform', 'wait'):
            runtime.append(el)
            continue

        # React Flow node (has 'data')
        if isinstance(el, dict) and 'data' in el:
            data = el.get('data') or {}
            label = (data.get('label') or '').lower()
            cfg = data.get('config') or {}
            node_id = el.get('id')
            pos = el.get('position')

            # map UI-friendly labels to runtime types
            if 'http' in label or 'http request' in label or 'http trigger' in label:
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

            # Cron / Timer trigger nodes created by the editor (label examples: "Cron Trigger", "timer")
            if 'cron' in label or 'timer' in label or label.startswith('cron trigger'):
                n = {
                    'id': node_id,
                    'type': 'cron_trigger',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'send' in label and 'email' in label or 'email' in label:
                n = {
                    'id': node_id,
                    'type': 'send_email',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'slack' in label:
                n = {
                    'id': node_id,
                    'type': 'slack',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'db' in label or 'database' in label or 'query' in label:
                n = {
                    'id': node_id,
                    'type': 'db',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 's3' in label or 'storage' in label or 'file' in label:
                n = {
                    'id': node_id,
                    'type': 's3',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'transform' in label or 'template' in label or 'jinja' in label:
                n = {
                    'id': node_id,
                    'type': 'transform',
                    'config': cfg,
                }
                if pos:
                    n['position'] = pos
                runtime.append(n)
                continue

            if 'wait' in label or 'delay' in label:
                n = {
                    'id': node_id,
                    'type': 'wait',
                    'config': cfg,
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
    """Top-level processor invoked by the Celery task wrapper or called
    directly in tests. Loads Run and Workflow, marks run as running,
    executes nodes in sequence via _execute_node and records result.
    This is intentionally simple: nodes are executed sequentially and
    failures mark the run failed. The function returns a result dict
    used by execute_workflow for retry decisions.
    """
    db = None
    try:
        db = SessionLocal()
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            logger.error("process_run: run %s not found", run_id)
            return {'status': 'failed', 'error': 'run_not_found'}

        run.attempts = (getattr(run, 'attempts', 0) or 0) + 1
        run.status = 'running'
        run.started_at = datetime.utcnow()
        db.add(run)
        db.commit()

        wf = db.query(Workflow).filter(Workflow.id == run.workflow_id).first()
        if not wf:
            _write_log(db, run.id, None, 'error', f"Workflow {run.workflow_id} not found")
            run.status = 'failed'
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            # publish terminal status to Redis
            try:
                try:
                    import redis as _redis
                    import os as _os
                    import json as _json
                except Exception:
                    _redis = None
                if _redis is not None:
                    try:
                        rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                        rc.publish(f"run:{run.id}:events", _json.dumps({'type': 'status', 'status': 'failed'}))
                    except Exception:
                        pass
            except Exception:
                pass
            return {'status': 'failed', 'error': 'workflow_not_found'}

        nodes = _convert_elements_to_runtime_nodes((wf.graph or {}).get('nodes') if wf.graph else [])
        outputs = {}
        try:
            for n in nodes:
                try:
                    res = _execute_node(db, run, n)
                    outputs[n.get('id')] = res
                    # Persist a structured node-level event so new SSE clients can
                    # learn node state from DB replay, and publish a node event to
                    # Redis so live subscribers update immediately.
                    try:
                        import json as _json
                        node_event = {
                            'type': 'node',
                            'node_id': n.get('id'),
                            'run_id': run.id,
                            'status': 'success' if not (isinstance(res, dict) and res.get('error')) else 'failed',
                            'result': res,
                        }
                        try:
                            # Persist as a RunLog row containing the JSON payload.
                            rl = RunLog(run_id=run.id, node_id=n.get('id'), level='info', message=_json.dumps(node_event))
                            db.add(rl)
                            db.commit()
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
                        # best-effort publish to Redis
                        try:
                            try:
                                import redis as _redis
                                import os as _os
                            except Exception:
                                _redis = None
                            if _redis is not None:
                                try:
                                    rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                                    rc.publish(f"run:{run.id}:events", _json.dumps(node_event))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        # node event persistence/publish is best-effort
                        pass
                    # if node returned error, mark run failed and stop
                    if isinstance(res, dict) and res.get('error'):
                        run.status = 'failed'
                        run.output_payload = outputs
                        run.finished_at = datetime.utcnow()
                        db.add(run)
                        db.commit()
                        # publish terminal status to Redis
                        try:
                            try:
                                import redis as _redis
                                import os as _os
                                import json as _json
                            except Exception:
                                _redis = None
                            if _redis is not None:
                                try:
                                    rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                                    rc.publish(f"run:{run.id}:events", _json.dumps({'type': 'status', 'status': 'failed'}))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        return {'status': 'failed', 'error': res.get('error'), 'attempts': run.attempts}
                except Exception as e:
                    # persist and publish node crash event
                    try:
                        import json as _json
                        node_event = {'type': 'node', 'node_id': n.get('id'), 'run_id': run.id, 'status': 'failed', 'error': str(e)}
                        try:
                            rl = RunLog(run_id=run.id, node_id=n.get('id'), level='error', message=_json.dumps(node_event))
                            db.add(rl)
                            db.commit()
                        except Exception:
                            try:
                                db.rollback()
                            except Exception:
                                pass
                        try:
                            try:
                                import redis as _redis
                                import os as _os
                            except Exception:
                                _redis = None
                            if _redis is not None:
                                try:
                                    rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                                    rc.publish(f"run:{run.id}:events", _json.dumps(node_event))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception:
                        pass
                    _write_log(db, run.id, n.get('id'), 'error', f"Node execution crashed: {e}")
                    run.status = 'failed'
                    run.output_payload = outputs
                    run.finished_at = datetime.utcnow()
                    db.add(run)
                    db.commit()
                    return {'status': 'failed', 'error': str(e), 'attempts': run.attempts}

            # success
            run.status = 'success'
            run.output_payload = outputs
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            # publish terminal status to Redis
            try:
                try:
                    import redis as _redis
                    import os as _os
                    import json as _json
                except Exception:
                    _redis = None
                if _redis is not None:
                    try:
                        rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                        rc.publish(f"run:{run.id}:events", _json.dumps({'type': 'status', 'status': 'success'}))
                    except Exception:
                        pass
            except Exception:
                pass
            return {'status': 'success', 'attempts': run.attempts}
        except Exception as e:
            logger.exception("process_run failed for %s", run_id)
            try:
                if db:
                    run = db.query(Run).filter(Run.id == run_id).first()
                    if run:
                        run.status = 'failed'
                        run.finished_at = datetime.utcnow()
                        db.add(run)
                        db.commit()
                        # publish terminal status to Redis
                        try:
                            try:
                                import redis as _redis
                                import os as _os
                                import json as _json
                            except Exception:
                                _redis = None
                            if _redis is not None:
                                try:
                                    rc = _redis.from_url(_os.getenv('REDIS_URL') or _os.getenv('CELERY_BROKER_URL') or 'redis://localhost:6379/0')
                                    rc.publish(f"run:{run.id}:events", _json.dumps({'type': 'status', 'status': 'failed'}))
                                except Exception:
                                    pass
                        except Exception:
                            pass
            except Exception:
                pass
        return {'status': 'failed', 'error': str(e)}
    finally:
        try:
            if db:
                db.close()
        except Exception:
            pass


# Scheduler background thread: periodically evaluate SchedulerEntry rows and
# enqueue runs for cron-style schedules. This is best-effort and non-blocking.
def _scheduler_loop():
    poll = int(os.getenv('SCHEDULER_POLL_SECONDS', '60'))
    enabled = os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true'
    if not enabled:
        logger.info('Scheduler disabled via ENABLE_SCHEDULER')
        return
    logger.info('Starting scheduler loop (poll=%s)', poll)
    while True:
        try:
            db = SessionLocal()
            entries = db.query(Provider).filter().first()  # dummy to ensure SessionLocal import used
            # load scheduler entries
            from .models import SchedulerEntry

            rows = db.query(SchedulerEntry).filter(SchedulerEntry.active == 1).all()
            now = datetime.utcnow()
            for s in rows:
                # if croniter not available skip
                if croniter is None:
                    continue
                last = s.last_run_at or s.created_at or (now - timedelta(days=1))
                try:
                    itr = croniter(s.schedule, last)
                    next_run = itr.get_next(datetime)
                except Exception:
                    # invalid cron expression or other error
                    continue
                if next_run <= now:
                    # enqueue a Run for this workflow
                    try:
                        new_run = Run(workflow_id=s.workflow_id, status='queued')
                        db.add(new_run)
                        db.commit()
                        db.refresh(new_run)
                        # update last_run_at
                        s.last_run_at = now
                        db.add(s)
                        db.commit()
                        try:
                            # prefer Celery enqueue
                            celery_app.send_task('execute_workflow', args=(new_run.id,))
                        except Exception:
                            # fallback: spawn a thread to process inline
                            threading.Thread(target=process_run, args=(new_run.id,)).start()
                    except Exception:
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        continue
            try:
                db.close()
            except Exception:
                pass
        except Exception:
            logger.exception('Scheduler loop iteration failed')
        time.sleep(poll)


# Start scheduler thread lazily if DB is available and croniter present.
try:
    # Only start scheduler when DB SessionLocal is a real callable
    if SessionLocal and croniter is not None and os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true':
        t = threading.Thread(target=_scheduler_loop, daemon=True)
        t.start()
except Exception:
    logger.exception('Failed to start scheduler thread')
