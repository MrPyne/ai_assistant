import os
from backend.utils import redact_secrets, get_redaction_metrics, reset_redaction_metrics


def test_redact_vendor_regexes_json_array():
    # reset metrics
    reset_redaction_metrics()
    # JSON array format
    os.environ['REDACT_VENDOR_PATTERNS'] = '0'  # ensure vendor patterns default off
    os.environ['REDACT_VENDOR_REGEXES'] = '[{"name":"my_secret_pattern","pattern":"SEC_[A-F0-9]{6}"}]'
    try:
        s = "Here is a secret SEC_ABCDEF and something else SEC_123456"
        out = redact_secrets(s)
        # both occurrences should be redacted
        assert "SEC_ABCDEF" not in out
        assert "SEC_123456" not in out
        metrics = get_redaction_metrics()
        # ensure our named pattern was recorded at least once
        assert metrics['patterns'].get('my_secret_pattern', 0) >= 2
    finally:
        os.environ.pop('REDACT_VENDOR_REGEXES', None)
        os.environ.pop('REDACT_VENDOR_PATTERNS', None)


def test_redact_vendor_regexes_newline_format():
    reset_redaction_metrics()
    # newline-separated name:pattern entries
    os.environ['REDACT_VENDOR_REGEXES'] = 'custom1:SECX_[0-9]{4}\n# comment line\ncustom2:HELLO_[A-Z]{3}'
    try:
        s = "Values: SECX_1234 and HELLO_ABC and SECX_0000"
        out = redact_secrets(s)
        assert "SECX_1234" not in out
        assert "HELLO_ABC" not in out
        assert "SECX_0000" not in out
        metrics = get_redaction_metrics()
        assert metrics['patterns'].get('custom1', 0) >= 2
        assert metrics['patterns'].get('custom2', 0) >= 1
    finally:
        os.environ.pop('REDACT_VENDOR_REGEXES', None)


def test_redact_vendor_regexes_malformed_ignored():
    reset_redaction_metrics()
    # malformed JSON should be ignored and not raise
    os.environ['REDACT_VENDOR_REGEXES'] = 'not a json nor proper lines'
    try:
        s = "No patterns match here: ABC123"
        out = redact_secrets(s)
        # nothing changed
        assert out == s
        metrics = get_redaction_metrics()
        assert metrics['count'] == 0
    finally:
        os.environ.pop('REDACT_VENDOR_REGEXES', None)


def test_redact_vendor_regexes_malformed_records_error():
    reset_redaction_metrics()
    # Provide a JSON array with an invalid regex pattern to ensure we record
    # a vendor_errors telemetry entry instead of raising.
    os.environ['REDACT_VENDOR_REGEXES'] = '[{"name":"bad","pattern":"(unclosed"}]'
    try:
        s = "nothing to redact"
        out = redact_secrets(s)
        assert out == s
        metrics = get_redaction_metrics()
        # malformed pattern should have been skipped and recorded as an error
        ve = metrics.get('vendor_errors', {})
        assert ve.get('bad', 0) >= 1
    finally:
        os.environ.pop('REDACT_VENDOR_REGEXES', None)
