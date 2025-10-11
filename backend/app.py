from fastapi import FastAPI, Request, Header, HTTPException
from typing import Optional, Dict, Any, List
from datetime import datetime

app = FastAPI()

# Simple in-memory run store used when a DB is not available.
_runs: Dict[int, Dict[str, Any]] = {}
_run_counter = 0

# Feature flag indicating whether a DB is present. Keep False to avoid
# external DB dependencies in tests unless a real DB is wired up.
_DB_AVAILABLE = False


def _user_from_token(token: Optional[str]) -> Optional[int]:
    """Very small helper that accepts any non-empty token as an authenticated user.
    Return None when unauthenticated.
    """
    if token:
        return 1
    return None


@app.post('/api/workflows/{wf_id}/run')
def manual_run(wf_id: int, request: Request, authorization: Optional[str] = Header(None)):
    """Schedule a manual run for workflow `wf_id`.
    Minimal implementation: create an in-memory run and return it queued.
    """
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    global _run_counter
    _run_counter += 1
    run_id = _run_counter
    _runs[run_id] = {
        'id': run_id,
        'workflow_id': wf_id,
        'status': 'queued',
        'created_by': user_id,
        'created_at': datetime.utcnow().isoformat(),
    }
    return {'run_id': run_id, 'status': 'queued'}


@app.get('/api/runs')
def list_runs(workflow_id: Optional[int] = None, limit: Optional[int] = 50, offset: Optional[int] = 0, authorization: Optional[str] = Header(None)):
    """List runs. Prefer DB-backed listing when available; otherwise use in-memory store.
    """
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    # If DB is available this implementation would query it. For now, use
    # the in-memory store so the endpoint works reliably in tests.
    try:
        runs: List[Dict[str, Any]] = []
        for rid, r in _runs.items():
            if workflow_id is None or r.get('workflow_id') == workflow_id:
                runs.append({'id': rid, 'workflow_id': r.get('workflow_id'), 'status': r.get('status'), 'created_at': r.get('created_at')})
        runs = sorted(runs, key=lambda x: x['id'], reverse=True)
        total = len(runs)
        paged = runs[offset: offset + limit]
        return {'items': paged, 'total': total, 'limit': limit, 'offset': offset}
    except Exception:
        return {'items': [], 'total': 0, 'limit': limit, 'offset': offset}


@app.get('/api/runs/{run_id}/logs')
def get_run_logs(run_id: int):
    """Return per-run logs. No authentication required for this minimal implementation.
    """
    try:
        # No persistent logs in this lightweight implementation.
        return {'logs': []}
    except Exception:
        return {'logs': []}


@app.get('/api/runs/{run_id}')
def get_run_detail(run_id: int, authorization: Optional[str] = Header(None)):
    user_id = _user_from_token(authorization)
    if not user_id:
        raise HTTPException(status_code=401)

    try:
        if _DB_AVAILABLE:
            try:
                db = SessionLocal()
                r = db.query(models.Run).filter(models.Run.id == run_id).first()
                if not r:
                    raise HTTPException(status_code=404, detail='run not found')
                out = {
                    'id': r.id,
                    'workflow_id': r.workflow_id,
                    'status': r.status,
                    'input_payload': r.input_payload,
                    'output_payload': r.output_payload,
                    'started_at': r.started_at,
                    'finished_at': r.finished_at,
                    'attempts': getattr(r, 'attempts', None),
                }
                # attach logs
                rows = db.query(models.RunLog).filter(models.RunLog.run_id == run_id).order_by(models.RunLog.timestamp.asc()).all()
                out_logs = []
                for rr in rows:
                    out_logs.append({'id': rr.id, 'run_id': rr.run_id, 'node_id': rr.node_id, 'timestamp': rr.timestamp.isoformat() if rr.timestamp is not None else None, 'level': rr.level, 'message': rr.message})
                out['logs'] = out_logs
                return out
            except HTTPException:
                raise
            except Exception:
                try:
                    db.rollback()
                except Exception:
                    pass
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        # fallback to in-memory run
        r = _runs.get(run_id)
        if not r:
            raise HTTPException(status_code=404, detail='run not found')
        out = {'id': run_id, 'workflow_id': r.get('workflow_id'), 'status': r.get('status'), 'input_payload': None, 'output_payload': None, 'started_at': None, 'finished_at': None, 'attempts': None, 'logs': []}
        return out
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail='internal error')
