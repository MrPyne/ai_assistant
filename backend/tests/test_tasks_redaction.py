from backend.utils import redact_secrets


def test_redact_simple_api_key():
    data = {"api_key": "sk-ABCDEF123456"}
    out = redact_secrets(data)
    assert out["api_key"] == "[REDACTED]"


def test_redact_embedded_string():
    text = "user provided key sk-ABCDEF123456 and more"
    out = redact_secrets(text)
    assert "[REDACTED]" in out


def test_redact_aws_and_bearer_and_key_equals():
    text = "aws=AKIAABCDEFGHIJKLMNOP and token=key=supersecretvalue123 and auth=Bearer abcdefghijklmnopqrstu"
    out = redact_secrets(text)
    # AWS key should be redacted
    assert "AKIAABCDEFGHIJKLMNOP" not in out
    # key= value should be redacted
    assert "supersecretvalue123" not in out
    # Bearer token should be redacted (case-insensitive)
    assert "abcdefghijklmnopqrstu" not in out
