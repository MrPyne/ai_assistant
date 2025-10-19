from fastapi import FastAPI, Request
from starlette.responses import StreamingResponse, Response

app = FastAPI()

async def redact_middleware(request: Request, call_next):
    print(f"REDACT_MIDDLEWARE start: {request.method} {request.url}")
    res = await call_next(request)
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
