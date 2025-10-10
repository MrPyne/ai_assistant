import pytest
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
