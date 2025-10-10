import os
from backend.utils import redact_secrets, get_redaction_metrics, reset_redaction_metrics


def test_vendor_regex_aggregate_budget_exceeded_records_metric():
    # Ensure we start from a clean slate
    reset_redaction_metrics()
    # Set total budget to 0ms so the first budget check will immediately
    # mark the aggregate budget as exceeded and short-circuit applying
    # vendor patterns.
    os.environ['REDACT_VENDOR_REGEX_TOTAL_TIMEOUT_MS'] = '0'
    # Provide several harmless patterns that would normally match; because
    # the aggregate budget is zero they should not be applied and we should
    # record an aggregate budget exceeded telemetry event.
    os.environ['REDACT_VENDOR_REGEXES'] = '[{"name":"p1","pattern":"FOO"}, {"name":"p2","pattern":"BAR"}]'
    try:
        s = 'FOO BAR BAZ'
        out = redact_secrets(s)
        # No patterns applied because budget was exceeded immediately
        assert out == s
        metrics = get_redaction_metrics()
        assert metrics.get('count', 0) == 0
        vbed = metrics.get('vendor_budget_exceeded', {})
        # The default key used by the implementation is 'aggregate'
        assert vbed.get('aggregate', 0) >= 1
    finally:
        os.environ.pop('REDACT_VENDOR_REGEX_TOTAL_TIMEOUT_MS', None)
        os.environ.pop('REDACT_VENDOR_REGEXES', None)
