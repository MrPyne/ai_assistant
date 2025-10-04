Planned next steps (developer checklist)

1) Backend: GET /api/runs/{run_id}/logs
- Implement API to return redacted logs for a run. Ensure logs never include plaintext secrets.
- Add unit test asserting secrets are redacted.

2) Backend: Harden worker & adapters
- Enforce adapter interface only accepts secret_id and decrypts in memory.
- Ensure _write_log never writes decrypted secrets. Add tests.

3) Frontend: Editor scaffold
- Create React + TypeScript scaffold if missing, add react-flow, and implement node palette + canvas.
- Wire save/load to POST/GET /api/workflows.

4) Frontend: Run history & logs viewer
- Implement run list and run detail pages calling /api/runs and /api/runs/{id}/logs.

5) E2E test: webhook -> http -> set
- Test creating a workflow via API, triggering the webhook, and asserting run status and logs.

6) Security: Live LLM guardrails
- Enforce ENABLE_LIVE_LLM flag and provider.secret_id checks in LLM adapter runtime.

Notes
- Work in small commits and update specs/README_SPEC.md changelog for each milestone.
