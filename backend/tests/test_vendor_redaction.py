import os
from backend.utils import redact_secrets


def test_vendor_patterns_disabled_by_default():
    # Ensure vendor patterns are not applied unless env var is set
    s = "Here is a GitHub token ghp_123456789012345678901234567890123456 and a Slack token xoxb-abcdef123456"
    # Ensure env var not set
    os.environ.pop('REDACT_VENDOR_PATTERNS', None)
    out = redact_secrets(s)
    assert "ghp_123" in out
    assert "xoxb-abcdef" in out


def test_vendor_patterns_enabled():
    s = "Tokens: ghp_123456789012345678901234567890123456 and xoxp-abcdef123456 and sk_live_ABCDEF123456"
    os.environ['REDACT_VENDOR_PATTERNS'] = '1'
    try:
        out = redact_secrets(s)
        assert "ghp_" not in out
        assert "xoxp-" not in out
        assert "sk_live_" not in out
    finally:
        os.environ.pop('REDACT_VENDOR_PATTERNS', None)
