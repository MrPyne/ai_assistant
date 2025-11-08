def install_wrappers(app):
    """Install wrapper decorators on FastAPI app to normalize responses.

    This encapsulates the logic that was previously inline in backend.app
    so the module remains smaller.
    """
    try:
        from fastapi.responses import JSONResponse
        from starlette.responses import StreamingResponse
    except Exception:
        JSONResponse = None
        StreamingResponse = None

    try:
        _orig_get = app.get
        _orig_post = app.post
        _orig_put = app.put
        _orig_delete = app.delete

        def _wrap_decorator(orig):
            def _dec(path, *args, **kwargs):
                def _inner(fn):
                    import asyncio

                    async def _wrapped(*a, **kw):
                        try:
                            res = fn(*a, **kw)
                            if asyncio.iscoroutine(res):
                                res = await res
                        except TypeError:
                            # handler may expect no args
                            try:
                                res = fn()
                                if asyncio.iscoroutine(res):
                                    res = await res
                            except Exception:
                                res = None

                        # Try to import redaction helper if available
                        try:
                            from backend.utils.redaction import redact_secrets
                        except Exception:
                            redact_secrets = None

                        try:
                            if isinstance(res, dict):
                                if redact_secrets:
                                    try:
                                        res2 = redact_secrets(res)
                                    except Exception:
                                        res2 = res
                                else:
                                    res2 = res
                                status = getattr(res, 'status_code', 200)
                                return JSONResponse(content=res2, status_code=status)

                            # streaming responses -> collect and redact
                            if StreamingResponse is not None and isinstance(res, StreamingResponse):
                                it = getattr(res, 'iterator', None) or getattr(res, 'body_iterator', None)
                                if it:
                                    acc = b''
                                    if hasattr(it, '__aiter__'):
                                        async for chunk in it:
                                            if isinstance(chunk, (bytes, bytearray)):
                                                acc += chunk
                                            else:
                                                acc += str(chunk).encode('utf-8')
                                    else:
                                        for chunk in it:
                                            if isinstance(chunk, (bytes, bytearray)):
                                                acc += chunk
                                            else:
                                                acc += str(chunk).encode('utf-8')
                                    try:
                                        txt = acc.decode('utf-8')
                                    except Exception:
                                        txt = acc.decode('latin-1', errors='ignore')
                                    # attempt JSON parse
                                    try:
                                        import json as _json

                                        parsed = _json.loads(txt)
                                        if redact_secrets:
                                            try:
                                                parsed = redact_secrets(parsed)
                                            except Exception:
                                                pass
                                        return JSONResponse(content=parsed, status_code=getattr(res, 'status_code', 200))
                                    except Exception:
                                        # text -> redact string
                                        if redact_secrets:
                                            try:
                                                red = redact_secrets(txt)
                                                if isinstance(red, str):
                                                    from starlette.responses import StreamingResponse as _SR
                                                    return _SR(iter([red.encode('utf-8')]), media_type=getattr(res, 'media_type', None))
                                            except Exception:
                                                pass
                                        from starlette.responses import StreamingResponse as _SR
                                        return _SR(iter([acc]), media_type=getattr(res, 'media_type', None))

                            return res
                        except Exception:
                            return res

                    # register with original decorator
                    return orig(path, *args, **kwargs)(_wrapped)

                return _inner

            return _dec

        app.get = _wrap_decorator(_orig_get)
        app.post = _wrap_decorator(_orig_post)
        app.put = _wrap_decorator(_orig_put)
        app.delete = _wrap_decorator(_orig_delete)
    except Exception:
        # Best-effort; if anything goes wrong, leave original app unchanged
        return
