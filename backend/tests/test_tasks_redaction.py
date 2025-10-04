from backend.utils import redact_secrets


def test_redact_simple_api_key():
    data = {"api_key": "sk-ABCDEF123456"}
    out = redact_secrets(data)
    assert out["api_key"] == "[REDACTED]"


def test_redact_embedded_string():
    text = "user provided key sk-ABCDEF123456 and more"
    out = redact_secrets(text)
    assert "[REDACTED]" in out
