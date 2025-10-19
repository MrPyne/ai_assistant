from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse, Response

app = FastAPI()

@app.middleware("http")
async def redact_middleware(request: Request, call_next):
    res = await call_next(request)
    try:
        try:
            print("REDACT_MIDDLEWARE got response type:", type(res), "status:", getattr(res, "status_code", None))
        except Exception:
            pass
        # If the response is a streaming response (iterator/async iterator)
        # avoid attempting to read/drain it - return original response so
        # the streaming body is preserved. Detect common streaming indicators
        # conservatively (type name/module, attributes, known classes).
        try:
            t = type(res)
            tname = getattr(t, "__name__", "") or ""
            tmodule = getattr(t, "__module__", "") or ""
            lower_name = (tname + ' ' + tmodule).lower()
            # name/module based heuristic
            try:
                cls_repr = repr(res.__class__).lower()
            except Exception:
                cls_repr = ''
            if 'stream' in lower_name or 'stream' in cls_repr:
                try:
                    print("REDACT_MIDDLEWARE detected streaming type; skipping redaction:", tmodule + '.' + tname)
                except Exception:
                    pass
                return res
            # attribute-based heuristics
            if getattr(res, 'is_streaming', False) or getattr(res, 'background', None) is not None or hasattr(res, 'iterator') or hasattr(res, 'body_iterator'):
                try:
                    print("REDACT_MIDDLEWARE skipping redaction for streaming-like response")
                except Exception:
                    pass
                return res
            # lastly, isinstance check for public StreamingResponse
            try:
                if isinstance(res, StreamingResponse):
                    try:
                        print("REDACT_MIDDLEWARE skipping redaction for StreamingResponse")
                    except Exception:
                        pass
                    return res
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass
    return res


@app.get("/")
async def read_root():
    return {"hello": "world"}
