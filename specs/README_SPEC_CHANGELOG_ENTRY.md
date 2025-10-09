This file records the change made to README_SPEC.md in version 1.11.

Summary of change:
- Bumped README_SPEC.md version to 1.11 and last updated date.
- Documented addition of a backend integration test (backend/tests/test_http_exception_normalization.py) and the conftest import shim to improve pytest collection robustness when FastAPI/TestClient are not installed. The test is skipped in environments without FastAPI/TestClient; to run it in CI add FastAPI and httpx[testclient] to the test environment.

Rationale:
- The added integration test closes a coverage gap between unit tests and the real FastAPI/TestClient path, verifying the app's HTTPException normalization logic enforces the structured validation error contract.
- The conftest shim prevents pytest collection failures in lightweight environments and keeps the test deselected unless the real TestClient is present.

Files updated:
- specs/README_SPEC.md (version bump and detailed note in Change log)
- specs/CHANGELOG.md (added 1.11 entry)

Date: 2025-10-09
Author: automation
