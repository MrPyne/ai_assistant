Changelog

1.5 (2025-10-04)
- Added N8N_COMPATIBILITY.md and COMPETITOR_COMPARISON.md
- Updated README_SPEC.md to v1.5 and clarified sprint priorities

1.4 (2025-10-04)
- Clarified parity checklist and sprint planning

1.3 (2025-10-04)
- Added initial competitor comparison and acceptance criteria

1.2 (2025-10-04)
- Re-aligned to n8n parity; sprint plans updated

1.1 (2025-10-04)
- Editor MVP implemented (frontend + basic wiring)

1.0 (2025-10-03)
- Initial spec created

1.6 (2025-10-05)
- Implemented redaction coverage for worker log writes and structured messages (unit tests added)

1.7 (2025-10-07)
- Added GET /api/runs/{run_id}/logs implementation and response envelope tests
- Hardened worker redaction and added unit tests ensuring secrets are not persisted in RunLog entries

1.8 (2025-10-07)
- Frontend editor save/load wiring finalized; editor unit tests added
- Updated README_SPEC.md and IMPLEMENTATION_CHECKLIST.md to reflect completed editor persistence work

1.9 (2025-10-09)
- Added server-side validation for workflow update to mirror create_workflow validation; added tests for update validation

1.10 (2025-10-09)
- Documented structured validation error contract

1.11 (2025-10-09)
- Added backend integration test to verify HTTPException normalization to the validation error contract and a conftest import shim to prevent test collection failures when FastAPI/TestClient are not installed. Test will be skipped unless FastAPI/TestClient are available in the environment; to run this test in CI, add backend test dependencies (fastapi, starlette, httpx[testclient]) to the CI job.
