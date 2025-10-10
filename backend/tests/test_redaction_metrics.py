import pytest
from backend.utils import redact_secrets, get_redaction_metrics, reset_redaction_metrics


def test_metrics_increment_and_reset():
    reset_redaction_metrics()
    s = "sk-abcdefghijklmnop"
    out = redact_secrets(s)
    assert "[REDACTED]" in out
    metrics = get_redaction_metrics()
    assert metrics['count'] >= 1
    # pattern name used for sk- keys is 'openai_sk'
    assert 'openai_sk' in metrics['patterns']


def test_reset_clears_metrics():
    reset_redaction_metrics()
    metrics = get_redaction_metrics()
    assert metrics['count'] == 0
    assert metrics['patterns'] == {}
    # vendor diagnostic keys should be present and empty after reset
    assert metrics.get('vendor_timeouts', {}) == {}
    assert metrics.get('vendor_errors', {}) == {}
