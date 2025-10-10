import pytest
import asyncio
from fastapi.testclient import TestClient
from backend.app import app

# Skip entire module if FastAPI app doesn't expose route decorators (lightweight envs)
if not hasattr(app, 'get'):
    pytest.skip('FastAPI not available; skipping middleware tests', allow_module_level=True)

@app.get("/__test_redact_json")
async def _test_redact_json():
    # JSON response containing a variety of secret-like values
    return {
        "status": "ok",
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz012345",
        "nested": {"authorization": "Bearer secrettoken12345"},
        "normal": "this-should-stay"
    }

@app.get("/__test_redact_csv")
async def _test_redact_csv():
    # CSV/text response containing a secret-like string
    from fastapi.responses import StreamingResponse
    csv_str = "id,detail\n1,sk-abcdef0123456789abcdef0123456789abcdef\n"
    return StreamingResponse(iter([csv_str]), media_type="text/csv")


@app.get("/__test_redact_complex_json")
async def _test_redact_complex_json():
    # Deeply nested JSON with lists and dicts containing secret-like keys
    return {
        "ok": True,
        "level1": {
            "level2": [
                {"secret": "supersecretvalue"},
                {"info": "not-a-secret"}
            ],
            "auth_header": "Bearer tokentext123456"
        },
        "deep": {"list": ["keep-me", "sk-abcdef0123456789abcdef"]},
    }


@app.get("/__test_redact_stream_json")
async def _test_redact_stream_json():
    # Streaming JSON response where token is split across chunks
    from fastapi.responses import StreamingResponse

    async def gen():
        parts = [b'{"streamed": "', b'sk-abcdef0123456789', b'"}']
        for p in parts:
            await asyncio.sleep(0)
            yield p

    return StreamingResponse(gen(), media_type="application/json")


@app.get("/__test_redact_chunked_text")
async def _test_redact_chunked_text():
    # Chunked text/plain response where secret spans chunks
    from fastapi.responses import StreamingResponse

    async def gen():
        chunks = ["start-", "sk-abcde", "f0123456789", "-end"]
        for c in chunks:
            await asyncio.sleep(0)
            yield c.encode()

    return StreamingResponse(gen(), media_type="text/plain")


def test_middleware_redacts_json():
    client = TestClient(app)
    resp = client.get("/__test_redact_json")
    assert resp.status_code == 200
    j = resp.json()
    # api_key and nested.authorization should be redacted by middleware
    assert j.get("api_key") == "[REDACTED]"
    assert j.get("nested", {}).get("authorization") == "[REDACTED]"
    # ensure normal field is preserved
    assert j.get("normal") == "this-should-stay"


def test_middleware_redacts_csv():
    client = TestClient(app)
    resp = client.get("/__test_redact_csv")
    assert resp.status_code == 200
    text = resp.text
    # secret-like sk- string should be replaced
    assert "[REDACTED]" in text
    assert "sk-abcdef" not in text


def test_middleware_redacts_complex_json():
    client = TestClient(app)
    resp = client.get("/__test_redact_complex_json")
    assert resp.status_code == 200
    j = resp.json()
    # nested secret key should be redacted, other info preserved
    assert j.get('level1', {}).get('level2', [])[0].get('secret') == "[REDACTED]"
    assert j.get('level1', {}).get('level2', [])[1].get('info') == "not-a-secret"
    assert j.get('level1', {}).get('auth_header') == "[REDACTED]"
    assert j.get('deep', {}).get('list', [])[1] == "[REDACTED]"


def test_middleware_redacts_stream_json():
    client = TestClient(app)
    resp = client.get("/__test_redact_stream_json")
    assert resp.status_code == 200
    j = resp.json()
    assert j.get('streamed') == "[REDACTED]"


def test_middleware_redacts_chunked_text():
    client = TestClient(app)
    resp = client.get("/__test_redact_chunked_text")
    assert resp.status_code == 200
    text = resp.text
    assert "[REDACTED]" in text
    assert "sk-abcdef" not in text
