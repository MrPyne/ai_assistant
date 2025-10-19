from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import StreamingResponse

app = FastAPI()


# Try to register the application's route modules (backend/routes.register_all)
# If the project provides a richer `app_impl` that builds a runtime context we
# prefer that; otherwise fall back to a minimal in-memory context so the API
# endpoints (eg. /api/secrets) are available during local/dev runs and in the
# docker-compose setup used for debugging.
def _maybe_register_routes():
    try:
        print("STARTUP: attempting to register package routes")
        # Build a conservative ctx expected by backend/routes/api.register
        ctx = {}
        try:
            # DB SessionLocal if available
            from .database import SessionLocal
            ctx['SessionLocal'] = SessionLocal
        except Exception:
            ctx['SessionLocal'] = None

        try:
            # models module if present
            from . import models
            ctx['models'] = models
        except Exception:
            ctx['models'] = None

        # Default: assume no DB available unless an app_impl indicates otherwise
        ctx['_DB_AVAILABLE'] = False

        # Provide simple in-memory stores used by the api_routes fallback logic
        ctx['_users'] = {}
        ctx['_workspaces'] = {}
        ctx['_secrets'] = {}
        ctx['_providers'] = {}
        ctx['_workflows'] = {}
        ctx['_webhooks'] = {}
        ctx['_runs'] = {}
        ctx['_audit_logs'] = []
        ctx['_templates'] = None
        ctx['_next'] = {'secret': 1, 'provider': 1, 'workflow': 1, 'webhook': 1, 'run': 1}

        # Try to reuse helpers from an app_impl module when present
        appmod = None
        try:
            from . import app_impl as appmod
            # app_impl may export helpers and configured objects; copy if present
            for k in ('_user_from_token', '_add_audit', '_workspace_for_user', 'logger'):
                if hasattr(appmod, k):
                    ctx[k] = getattr(appmod, k)
        except Exception:
            # fallback: try to reuse test/dev stub which provides a simple
            # _user_from_token implementation used by tests and local runs
            appmod = None

        # If app_impl did not provide an auth helper, try app_stub next
        if not callable(ctx.get('_user_from_token')):
            try:
                from .app_stub import _user_from_token
                ctx['_user_from_token'] = _user_from_token
            except Exception:
                # last-resort stub that always returns None (unauthenticated)
                ctx['_user_from_token'] = lambda authorization=None: None

        # If app_impl exposed a SessionLocal or flagged DB available, prefer that
        try:
            if appmod is not None and hasattr(appmod, '_DB_AVAILABLE'):
                ctx['_DB_AVAILABLE'] = getattr(appmod, '_DB_AVAILABLE')
            if appmod is not None and hasattr(appmod, 'SessionLocal'):
                ctx['SessionLocal'] = getattr(appmod, 'SessionLocal')
            if appmod is not None and hasattr(appmod, 'models'):
                ctx['models'] = getattr(appmod, 'models')
        except Exception:
            pass

        # Delegate to the routes package to register endpoints
        try:
            from .routes import register_all
            register_all(app, ctx)
            print("STARTUP: registered package routes via backend.routes.register_all")
        except Exception as e:
            print("STARTUP: failed to register backend routes:", e)
    except Exception as e:
        print("STARTUP: route registration attempt failed:", e)


# Immediately attempt to register routes so they appear in app.routes
_maybe_register_routes()


@app.on_event("startup")
async def _startup_log_routes():
    # Print registered routes at startup to help diagnose 404s
    try:
        print("STARTUP: listing app.routes")
        for r in getattr(app, 'routes', []) or []:
            try:
                path = getattr(r, 'path', None)
                methods = getattr(r, 'methods', None)
                name = getattr(r, 'name', None)
                endpoint = getattr(r, 'endpoint', None)
                print(f"ROUTE: path={path!r} methods={methods!r} name={name!r} endpoint={endpoint!r}")
            except Exception as e:
                print("ROUTE inspect error:", e)
    except Exception as e:
        print("STARTUP route listing failed:", e)


@app.middleware("http")
async def redact_middleware(request: Request, call_next):
    try:
        print(f"REDACT_MIDDLEWARE start: {request.method} {request.url}")
        try:
            # Log routing hints from ASGI scope before forwarding the request
            scope = getattr(request, 'scope', {}) or {}
            ep = scope.get('endpoint')
            route = scope.get('route')
            print("REDACT_MIDDLEWARE scope.path:", scope.get('path'), "scope.root_path:", scope.get('root_path'))
            print("REDACT_MIDDLEWARE scope.endpoint:", ep, "scope.route:", route)
        except Exception as e:
            print("REDACT_MIDDLEWARE scope inspect error:", e)

        res = await call_next(request)
    except Exception as e:
        # If call_next itself raises, log and re-raise so FastAPI returns an error
        print("REDACT_MIDDLEWARE call_next error:", e)
        raise

    try:
        try:
            print("REDACT_MIDDLEWARE got response type:", type(res), "status:", getattr(res, "status_code", None))
        except Exception:
            pass

        # Log headers and key transport hints without consuming body
        try:
            hdrs = dict(res.headers) if hasattr(res, 'headers') else {}
            print("REDACT_MIDDLEWARE response headers:", hdrs)
        except Exception as e:
            print("REDACT_MIDDLEWARE headers error:", e)

        try:
            cl = hdrs.get('content-length') if isinstance(hdrs, dict) else None
            te = hdrs.get('transfer-encoding') if isinstance(hdrs, dict) else None
            mt = getattr(res, 'media_type', None)
            print("REDACT_MIDDLEWARE content-length:", cl, "transfer-encoding:", te, "media_type:", mt)
        except Exception:
            pass

        # Try to inspect a non-streamed .body attribute without forcing iteration
        try:
            body_attr = getattr(res, 'body', None)
            if body_attr is not None:
                b_preview = body_attr[:200] if isinstance(body_attr, (bytes, bytearray)) else str(body_attr)[:200]
                print("REDACT_MIDDLEWARE response.body preview:", b_preview)
            else:
                print("REDACT_MIDDLEWARE response.body: <None>")
        except Exception as e:
            print("REDACT_MIDDLEWARE response.body access error:", e)

        # Heuristics to detect streaming-like responses (avoid draining them)
        is_streaming = False
        try:
            t = type(res)
            tname = getattr(t, "__name__", "")
            tmodule = getattr(t, "__module__", "")
            lower_name = (tname + ' ' + tmodule).lower()
            cls_repr = ''
            try:
                cls_repr = repr(res.__class__).lower()
            except Exception:
                pass
            if 'stream' in lower_name or 'stream' in cls_repr:
                is_streaming = True
            if getattr(res, 'is_streaming', False) or getattr(res, 'background', None) is not None or hasattr(res, 'iterator') or hasattr(res, 'body_iterator'):
                is_streaming = True
            try:
                if isinstance(res, StreamingResponse):
                    is_streaming = True
            except Exception:
                pass
        except Exception:
            pass

        print("REDACT_MIDDLEWARE streaming_detected:", is_streaming)

        if is_streaming:
            try:
                it = getattr(res, 'iterator', None) or getattr(res, 'body_iterator', None)
                print("REDACT_MIDDLEWARE iterator attribute:", type(it), it)
            except Exception as e:
                print("REDACT_MIDDLEWARE iterator inspection error:", e)
            try:
                bg = getattr(res, 'background', None)
                print("REDACT_MIDDLEWARE background:", type(bg), bg)
            except Exception:
                pass
            print("REDACT_MIDDLEWARE skipping redaction for streaming-like response")
            return res

        # For non-streaming responses, attempt a safe preview
        try:
            content = None
            if hasattr(res, 'body') and getattr(res, 'body') is not None:
                content = res.body
            else:
                if hasattr(res, 'render'):
                    try:
                        content = await res.render()
                    except Exception as e:
                        print("REDACT_MIDDLEWARE render error:", e)
            if content is not None:
                preview = content[:200] if isinstance(content, (bytes, bytearray)) else str(content)[:200]
                print("REDACT_MIDDLEWARE redacted_type:", type(preview), "redacted_preview:", preview)
        except Exception as e:
            print("REDACT_MIDDLEWARE body read error:", e)
    except Exception as e:
        print("REDACT_MIDDLEWARE top-level error inspecting response:", e)
    return res



@app.get("/")
async def read_root():
    return {"hello": "world"}


@app.get("/__debug/routes")
async def _debug_routes():
    out = []
    try:
        for r in getattr(app, 'routes', []) or []:
            try:
                out.append({'path': getattr(r, 'path', None), 'methods': list(getattr(r, 'methods', []) or []), 'name': getattr(r, 'name', None)})
            except Exception:
                continue
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': 'failed to list routes', 'detail': str(e)})
    return JSONResponse(content=out)


@app.get("/__debug/echo")
async def _debug_echo(request: Request):
    try:
        scope = getattr(request, 'scope', {}) or {}
        hdrs = {k.decode(): v.decode() for k, v in scope.get('headers', [])}
        route = scope.get('route')
        endpoint = scope.get('endpoint')
        return JSONResponse(content={
            'path': scope.get('path'),
            'root_path': scope.get('root_path'),
            'method': scope.get('method'),
            'headers': hdrs,
            'route': repr(route),
            'endpoint': repr(endpoint),
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})
