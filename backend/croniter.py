# Stub of croniter to avoid requiring the package during test runs.
# It provides a placeholder croniter() callable so `from croniter import croniter`
# succeeds. If scheduler functionality is used in tests, this will raise to
# indicate the real package is needed.

def croniter(expr, start_time=None):
    """Minimal stub: raises if actually invoked to make missing dependency
    explicit while allowing imports to succeed.
    """
    raise RuntimeError("croniter is not installed. Install the 'croniter' package to use scheduling functionality.")
