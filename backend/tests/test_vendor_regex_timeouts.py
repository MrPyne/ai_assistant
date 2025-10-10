import os
import time
import pytest

from backend.utils import redact_secrets, get_redaction_metrics, reset_redaction_metrics


def test_vendor_regex_timeout_skips_pathological_pattern():
    # This test requires the 'regex' package to be installed; if it's not
    # available we skip the test. The production code falls back to 're'
    # which does not support timeouts, so skipping is appropriate here.
    try:
        import regex as _regex  # noqa: F401
    except Exception:
        pytest.skip("regex package not available; skipping timeout test")

    reset_redaction_metrics()
    # set a very small timeout so the pathological pattern triggers quickly
    os.environ["REDACT_VENDOR_REGEX_TIMEOUT_MS"] = "10"
    # pattern that causes catastrophic backtracking on long inputs
    os.environ["REDACT_VENDOR_REGEXES"] = '[{"name":"slow","pattern":"(a+)+$"}]'
    try:
        s = "a" * 2000 + "!"
        start = time.time()
        out = redact_secrets(s)
        elapsed = time.time() - start
        # function should return quickly (well under a second with timeout)
        assert elapsed < 1.0
        # pattern should not alter the non-matching input
        assert out == s
        metrics = get_redaction_metrics()
        # No successful redactions should have occurred
        assert metrics["count"] == 0
        # The pathological pattern should have been skipped due to timeout
        # and recorded in vendor_timeouts telemetry
        vt = metrics.get('vendor_timeouts', {})
        assert vt.get('slow', 0) >= 1
    finally:
        os.environ.pop("REDACT_VENDOR_REGEXES", None)
        os.environ.pop("REDACT_VENDOR_REGEX_TIMEOUT_MS", None)
