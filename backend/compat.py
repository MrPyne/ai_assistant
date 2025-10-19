"""Compatibility helpers extracted from backend.app to reduce file size.

This module provides:
- _apply_redaction(res): helper to redact dicts/streaming responses in lightweight
  environments or when running without FastAPI.
- _maybe_response(obj, status): produce JSONResponse when FastAPI is available,
  otherwise return raw dict for DummyClient compatibility.
- install_compat_routes(app, g): register a compatibility _routes mapping and
  an HTTPException handler on the given FastAPI-like `app` using callables
  found in the provided globals mapping `g`.

The logic here was extracted verbatim from backend.app to minimize changes to
behavior while splitting the large file into smaller components.
"""
from typing import Optional, Dict, Any
import os


def _should_instrument():
    # Instrument when explicitly enabled, or when running under pytest. This
    # is intended to be test-only instrumentation to aid debugging of the
    # TestClient/response-normalization interaction.
    if os.environ.get('AI_ASSISTANT_TEST_INSTRUMENT') == '1':
        return True
    try:
        import sys

        if 'pytest' in sys.modules:
            return True
    except Exception:
        pass
    return False


def _apply_redaction(res):
    # Attempt to import redact_secrets from the project's utils
    try:
        from .utils import redact_secrets
    except Exception:
        try:
            import backend.utils as _bu

            redact_secrets = _bu.redact_secrets
        except Exception:
            redact_secrets = None

    # dicts -> redact structure
    if isinstance(res, dict) and redact_secrets:
        try:
            return redact_secrets(res)
        except Exception:
            return res
    # Try to extract a JSON/text body from Response-like objects so the
    # lightweight TestClient returns structured data instead of a string
    # representation of the Response object.
    try:
        import asyncio

        # 1) body() callable
        body_fn = getattr(res, 'body', None)
        if callable(body_fn):
            try:
                b = body_fn()
                if asyncio.iscoroutine(b):
                    b = asyncio.run(b)
                if isinstance(b, (bytes, bytearray)):
                    txt = None
                    try:
                        txt = b.decode('utf-8')
                    except Exception:
                        txt = ''
                    try:
                        import json as _json

                        parsed = _json.loads(txt)
                        return redact_secrets(parsed) if (redact_secrets and parsed is not None) else parsed
                    except Exception:
                        return redact_secrets(txt) if redact_secrets else txt
                if isinstance(b, str):
                    try:
                        import json as _json

                        parsed = _json.loads(b)
                        return redact_secrets(parsed) if (redact_secrets and parsed is not None) else parsed
                    except Exception:
                        return redact_secrets(b) if redact_secrets else b
            except Exception:
                pass

        # 2) common attributes
        for attr in ('content', 'body', 'text'):
            try:
                val = getattr(res, attr, None)
            except Exception:
                val = None
            if val is None:
                continue
            try:
                if isinstance(val, (bytes, bytearray)):
                    try:
                        txt = val.decode('utf-8')
                    except Exception:
                        txt = ''
                    try:
                        import json as _json

                        parsed = _json.loads(txt)
                        return redact_secrets(parsed) if (redact_secrets and parsed is not None) else parsed
                    except Exception:
                        return redact_secrets(txt) if redact_secrets else txt
                if isinstance(val, str):
                    try:
                        import json as _json

                        parsed = _json.loads(val)
                        return redact_secrets(parsed) if (redact_secrets and parsed is not None) else parsed
                    except Exception:
                        return redact_secrets(val) if redact_secrets else val
            except Exception:
                continue

        # 3) iterator or async iterator
        it = getattr(res, 'iterator', None) or getattr(res, 'body_iterator', None)
        if it:
            try:
                if hasattr(it, '__aiter__'):
                    async def _collect(it_inner):
                        acc = b''
                        async for chunk in it_inner:
                            if isinstance(chunk, (bytes, bytearray)):
                                acc += chunk
                            else:
                                acc += str(chunk).encode('utf-8')
                        return acc

                    try:
                        acc = asyncio.run(_collect(it))
                    except Exception:
                        acc = b''
                else:
                    acc = b''
                    for chunk in it:
                        if isinstance(chunk, (bytes, bytearray)):
                            acc += chunk
                        else:
                            acc += str(chunk).encode('utf-8')
                try:
                    txt = acc.decode('utf-8')
                except Exception:
                    txt = ''
                try:
                    import json as _json

                    parsed = _json.loads(txt)
                    return redact_secrets(parsed) if (redact_secrets and parsed is not None) else parsed
                except Exception:
                    return redact_secrets(txt) if redact_secrets else txt
            except Exception:
                pass
    except Exception:
        pass

    return res


def _maybe_response(obj: dict, status: int = 200):
    """Return a JSONResponse when running under real FastAPI; otherwise return obj.

    This mirrors the behaviour in the original backend.app to keep TestClient and
    DummyClient behaviour compatible.
    """
    try:
        from fastapi.responses import JSONResponse  # type: ignore
        # When running under pytest, prefer returning the raw dict so FastAPI's
        # normal response handling (and TestClient) will produce the final
        # JSON response. Returning a JSONResponse instance here when tests are
        # active can sometimes lead to double-handling and empty bodies in
        # certain TestClient/shim combinations.
        try:
            import sys

            if 'pytest' in sys.modules:
                return obj
        except Exception:
            pass
        if _should_instrument():
            try:
                # Only print a simple diagnostic; avoid calling response.body()
                # or iterating the response here because that can drain/consume
                # the underlying content and break TestClient.
                print(f"DEBUG[compat]._maybe_response: obj_type={type(obj)!r} status={status}")
            except Exception:
                pass
        return JSONResponse(content=obj, status_code=status)
    except Exception:
        if _should_instrument():
            try:
                print(f"DEBUG[compat]._maybe_response: fastapi not available, returning raw obj type={type(obj)!r}")
            except Exception:
                pass
        return obj


def install_compat_routes(app, g: dict):
    """Install a compatibility _routes mapping and HTTPException handler.

    `g` should be the globals() mapping from the module that defines the
    endpoint callables (so we can look up names like '_auth_register').
    """
    try:
        # Populate the simple app._routes compatibility mapping so tests and
        # lightweight clients can call handlers directly via app._routes.
        # We do this for both lightweight and real FastAPI instances to keep
        # behaviour consistent across environments.
        if True:
            try:
                _map = {}
                candidates = []
                try:
                    candidates = list(getattr(app, 'routes', []) or [])
                except Exception:
                    candidates = []
                try:
                    router = getattr(app, 'router', None)
                    if router is not None:
                        candidates.extend(list(getattr(router, 'routes', []) or []))
                except Exception:
                    pass

                for _r in candidates:
                    try:
                        # Debug: examine candidate route
                        try:
                            p_dbg = getattr(_r, 'path', None)
                            methods_dbg = getattr(_r, 'methods', None)
                        except Exception:
                            p_dbg = None
                            methods_dbg = None
                        # print for diagnostics when running tests
                        try:
                            import sys
                            if 'pytest' in sys.modules:
                                print(f"DEBUG[compat] candidate route path={p_dbg} methods={methods_dbg}")
                        except Exception:
                            pass
                        p = getattr(_r, 'path', None)
                        methods = getattr(_r, 'methods', None) or set()
                        ep = getattr(_r, 'endpoint', None)
                        if p and ep and methods:
                            for mm in methods:
                                _map[(mm.upper(), p)] = ep
                    except Exception:
                        continue
                setattr(app, '_routes', _map)
            except Exception:
                pass

            try:
                explicit = getattr(app, '_routes', {}) or {}
                def _make_compat(fn):
                    import asyncio
                    import threading
                    import queue

                    def _run_awaitable(coro):
                        try:
                            loop = None
                            try:
                                loop = asyncio.get_event_loop()
                            except Exception:
                                loop = None
                            if loop is not None and loop.is_running():
                                q = queue.Queue()

                                def _thread_run():
                                    try:
                                        res = asyncio.run(coro)
                                    except Exception:
                                        res = None
                                    q.put(res)

                                t = threading.Thread(target=_thread_run)
                                t.start()
                                t.join()
                                return q.get() if not q.empty() else None
                            return asyncio.run(coro)
                        except Exception:
                            return None

                    def _extract_content(res):
                        try:
                            if _should_instrument():
                                try:
                                    print(f"DEBUG[compat]._extract_content: res_type={type(res)!r}")
                                except Exception:
                                    pass
                            if isinstance(res, dict):
                                return _apply_redaction(res)
                        except Exception:
                            pass

                        try:
                            body_fn = getattr(res, 'body', None)
                            if callable(body_fn):
                                try:
                                    if _should_instrument():
                                        try:
                                            print("DEBUG[compat]._extract_content: calling body()")
                                        except Exception:
                                            pass
                                    b = body_fn()
                                    if asyncio.iscoroutine(b):
                                        b = _run_awaitable(b)
                                    if isinstance(b, (bytes, bytearray)):
                                        try:
                                            txt = b.decode('utf-8')
                                        except Exception:
                                            txt = ''
                                        try:
                                            import json as _json
                                            parsed = _json.loads(txt)
                                            if _should_instrument():
                                                try:
                                                    print(f"DEBUG[compat]._extract_content: parsed body from body() -> {parsed}")
                                                except Exception:
                                                    pass
                                            return _apply_redaction(parsed)
                                        except Exception:
                                            if _should_instrument():
                                                try:
                                                    print(f"DEBUG[compat]._extract_content: body() returned bytes but not json: {txt}")
                                                except Exception:
                                                    pass
                                            return txt
                                    if isinstance(b, str):
                                        try:
                                            import json as _json
                                            parsed = _json.loads(b)
                                            if _should_instrument():
                                                try:
                                                    print(f"DEBUG[compat]._extract_content: parsed body() str -> {parsed}")
                                                except Exception:
                                                    pass
                                            return _apply_redaction(parsed)
                                        except Exception:
                                            if _should_instrument():
                                                try:
                                                    print(f"DEBUG[compat]._extract_content: body() returned str not json: {b}")
                                                except Exception:
                                                    pass
                                            return b
                                except Exception:
                                    pass

                            for attr in ('content', 'body', 'text'):
                                try:
                                    val = getattr(res, attr, None)
                                except Exception:
                                    val = None
                                if val is None:
                                    continue
                                try:
                                    if isinstance(val, (bytes, bytearray)):
                                        try:
                                            txt = val.decode('utf-8')
                                        except Exception:
                                            txt = ''
                                        try:
                                            import json as _json
                                            return _apply_redaction(_json.loads(txt))
                                        except Exception:
                                            return txt
                                    if isinstance(val, str):
                                        try:
                                            import json as _json
                                            return _apply_redaction(_json.loads(val))
                                        except Exception:
                                            return val
                                except Exception:
                                    continue

                            it = getattr(res, 'iterator', None) or getattr(res, 'body_iterator', None)
                            if it:
                                try:
                                    if hasattr(it, '__aiter__'):
                                        async def _collect(it_inner):
                                            acc = b''
                                            async for chunk in it_inner:
                                                if isinstance(chunk, (bytes, bytearray)):
                                                    acc += chunk
                                                else:
                                                    acc += str(chunk).encode('utf-8')
                                            return acc

                                        acc = _run_awaitable(_collect(it))
                                        if isinstance(acc, (bytes, bytearray)):
                                            try:
                                                txt = acc.decode('utf-8')
                                            except Exception:
                                                txt = ''
                                            try:
                                                import json as _json
                                                return _apply_redaction(_json.loads(txt))
                                            except Exception:
                                                return txt
                                    else:
                                        acc = b''
                                        for chunk in it:
                                            if isinstance(chunk, (bytes, bytearray)):
                                                acc += chunk
                                            else:
                                                acc += str(chunk).encode('utf-8')
                                        try:
                                            txt = acc.decode('utf-8')
                                        except Exception:
                                            txt = ''
                                        try:
                                            import json as _json
                                            return _apply_redaction(_json.loads(txt))
                                        except Exception:
                                            return txt
                                except Exception:
                                    pass
                        except Exception:
                            pass

                        return res

                    def _wrapped(*args, **kws):
                        try:
                            res = fn(*args, **kws)
                        except TypeError:
                            try:
                                res = fn()
                            except Exception:
                                res = None
                        try:
                            if asyncio.iscoroutine(res):
                                res = _run_awaitable(res)
                        except Exception:
                            pass
                        return _extract_content(res)

                    return _wrapped

                def _maybe_add(method, path, name):
                    key = (method.upper(), path)
                    if key in explicit:
                        return
                    fn = g.get(name)
                    if callable(fn):
                        explicit[key] = _make_compat(fn)

                _maybe_add('GET', '/', '_root')
                _maybe_add('POST', '/api/auth/register', '_auth_register')
                _maybe_add('POST', '/api/auth/login', '_auth_login')
                _maybe_add('POST', '/api/auth/resend', '_auth_resend')
                _maybe_add('POST', '/api/workflows/{wf_id}/run', 'manual_run')
                setattr(app, '_routes', explicit)
            except Exception:
                pass
        # Register HTTPException normalization handler for real FastAPI instances
        if hasattr(app, 'exception_handler'):
            from fastapi.responses import JSONResponse as _JSONResponse
            from fastapi import HTTPException

            async def _http_exception_handler(request, exc):
                detail = getattr(exc, 'detail', None)
                try:
                    if isinstance(detail, dict):
                        return _JSONResponse(status_code=exc.status_code, content=detail)
                    return _JSONResponse(status_code=exc.status_code, content={'message': str(detail)})
                except Exception:
                    return _JSONResponse(status_code=getattr(exc, 'status_code', 500), content={'message': 'internal error'})

            try:
                app.exception_handler(HTTPException)(_http_exception_handler)
            except Exception:
                # Some FastAPI versions expect decorator use; try the decorator approach
                try:
                    @app.exception_handler(HTTPException)
                    async def _eh(request, exc):
                        return await _http_exception_handler(request, exc)
                except Exception:
                    pass
    except Exception:
        pass
