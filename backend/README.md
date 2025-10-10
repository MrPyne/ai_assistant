Development

Start services via docker-compose (requires Docker):

  docker-compose up --build

Backend (FastAPI) will be available at http://localhost:8000

Environment variables
- DATABASE_URL: SQLAlchemy database url
- SECRET_KEY: JWT secret

Run tests:

  pytest -q

Redaction & telemetry configuration

The backend includes middleware and helpers to automatically redact secret-like
values from responses and logs. The redaction behaviour is conservative by
default but can be tuned via environment variables below.

- ENABLE_RESPONSE_REDACTION (default: 1)
  - If set to '0', 'false' or 'no' response redaction middleware is disabled.
  - When enabled the middleware will attempt to redact JSON and text/CSV
    responses to avoid leaking secrets in API responses.

- REDACT_MAX_BUFFER (default: 1048576)  # 1 MiB
  - Maximum number of bytes considered safe to buffer when attempting to
    parse and redact an application/json response. If the response body is
    larger than this or is streamed without an exposed .body the middleware
    will avoid buffering and will not attempt full JSON parsing.

- REDACT_LOOKBACK (default: 256)
  - Number of characters to keep as a sliding lookback buffer when streaming
    text responses. This helps detect secret tokens that are split across
    chunk boundaries while avoiding unbounded buffering of streaming bodies.
  - Increase this value (e.g., to 512) if your streaming chunks commonly split
    secret-like tokens across larger boundaries, but be mindful of memory
    usage for very large concurrent streams.

- REDACT_VENDOR_PATTERNS (default: disabled)
  - When enabled (set to '1', 'true', or 'yes') additional vendor-specific
    regexes are applied (GitHub, Slack, Stripe examples). These heuristics can
    increase false positives so they are opt-in.

- REDACT_VENDOR_REGEXES (default: unset)
  - Optional, user-provided additional regexes for redaction. Two formats are
    supported:
    1) JSON array of objects: e.g. [{"name":"mykey","pattern":"myregex"}, ...]
    2) Newline-separated list of `name:pattern` entries, e.g.:
       mykey:sk-[A-Za-z0-9_-]{8,}\nother:SEC_[A-F0-9]{32}
  - The middleware will attempt to parse this value; malformed input is
    ignored. Use this with care in CI/tests to add short-lived patterns.

- SECRETS_KEY (or SECRETS_KEY_FILE)
  - Key material (Fernet) used to encrypt secrets at rest. In local dev the
    repo uses a simple Fernet key. In production provide a secure key or a
    KMS-backed mechanism.

Redaction telemetry (admin-only)

The app exposes lightweight in-process telemetry intended to help tune and
unit-test redaction heuristics. This telemetry is intentionally minimal and
not intended as a production metrics export.

- GET /internal/redaction_metrics
  - Returns a JSON snapshot of in-memory counters: total 'count' of
    redactions and a 'patterns' map of pattern-name -> replacements.
  - Access restricted to users with role='admin'. Use the dev auth flows to
    create an admin user in tests/dev (registration accepts a 'role' field).

- POST /internal/redaction_metrics/reset
  - Resets the in-process telemetry counters to zero. Restricted to admin users.

Notes & best practices
- Secrets are encrypted at rest and endpoints that list secrets intentionally
  do not return plaintext values.
- The response redaction middleware prioritizes safety: it will not buffer
  arbitrarily large streaming responses to parse JSON and will fall back to
  streaming-safe redaction for text/CSV.
- Unit and integration tests in backend/tests include coverage for middleware
  redaction, vendor pattern toggles, and telemetry. Some tests are skipped in
  lightweight environments where FastAPI/TestClient aren't available.

Running tests locally
- Ensure test dependencies are installed (fastapi, starlette, httpx[testclient], pytest).
- Run from repo root:

  pytest -q backend/tests

If you see skips for middleware/tests, verify your environment has FastAPI and
its testclient installed.

Further documentation
- See specs/COMBINED_SPEC.md for the project spec, feature checklist, and
  priorities.
- For development tasks related to redaction heuristics see backend/utils.py
  and the middleware implementation in backend/app.py.
