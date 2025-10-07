Implementation Checklist — n8n parity project

Overview

This file is a single-source checklist to track implemented work and remaining tasks required to reach feature parity with n8n. Use it to assign, mark progress, and to run DoD verification for each feature.

Guidelines
- Tasks checked [x] are implemented (committed or verified in repo).
- Tasks unchecked [ ] are outstanding.
- Each feature includes: Purpose, Acceptance criteria (DoD), Estimate, and a granular checklist.

Project status summary
- Repo scaffold with FastAPI backend, Celery/Redis worker, React frontend (react-flow) — [x]
- Adapter skeletons & basic worker — [x]
- Frontend editor MVP exists (editor runtime unstable; add-node failing historically) — [x]
- Spec updated toward n8n parity — [x]

Legend
- P0: Highest priority (editor + core runtime features)
- P1: Important but after P0
- P2: Longer-term / operational

-----------------------------
P0 (Must have)
-----------------------------

Feature: Editor stabilization & Add Node
Purpose: Make the visual editor reliable and enable node additions, rendering, save/load.
Estimate: 0.5–1 day
Acceptance criteria:
- Clicking Add Node invokes handler and logs event.
- New node appears on canvas (nodes[] updated).
- No runtime console errors after adding nodes.
- Editor persists saved workflows via POST /api/workflows and loads them back.

Checklist:
- [x] Audit current editor wiring and locate add-node handler (frontend)
- [x] Migrate react-flow usage to controlled pattern (onNodesChange/onEdgesChange)
- [x] Implement addNode(type) handler that creates node and updates state
- [x] Add safe fallback node renderer for unknown node types
- [x] Wire save (POST /api/workflows) and load (GET /api/workflows/:id) to editor
- [x] Add unit tests for addNode handler
- [x] Manual test checklist and update README_SPEC

Notes: This is the immediate highest-priority task. Developer memory recommends starting here. The editor save/load wiring has been implemented and basic unit tests added; manual test checklist and README_SPEC have been updated (see specs/README_SPEC.md and specs/CHANGELOG.md for details).


Feature: Secrets (Credentials) UI & Backend
Purpose: Workspace-scoped secrets storage, selection in nodes, and secure resolution at runtime.
Estimate: 1 day
Acceptance criteria:
- Create/edit/delete secrets via UI.
- Designed so secret values are not returned by GET endpoints or shown in UI after save.
- Nodes can reference secrets; at runtime workers receive usable credentials without secrets exposed in logs or APIs.

Checklist:
- [ ] DB migration: create secrets table
- [ ] Backend APIs: POST/GET/PUT/DELETE /api/workspaces/:ws/secrets
- [ ] Encryption helpers (Fernet/KMS) and rotate strategy documented
- [ ] UI: Secrets page and create/edit modal (masked input)
- [ ] Node config: credential selector lists workspace secrets (metadata only)
- [ ] Worker secret resolution flow (secure injection or server-forwarded secrets)
- [ ] Audit logging for secret access
- [ ] Unit/integration tests to ensure no plaintext secret leakage


Feature: Webhook trigger + Test Runner
Purpose: Per-workflow webhook endpoints; incoming requests create runs and enqueue worker execution. UI test runner to exercise webhooks.
Estimate: 1–2 days
Acceptance criteria:
- Webhook endpoint is routable and triggers run creation with trigger_payload stored.
- Test button in UI sends payload and returns run id/response.

Checklist:
- [ ] DB migration: webhooks table
- [ ] Backend APIs: CRUD webhooks under /api/workspaces/:ws/workflows/:workflow_id/webhooks
- [ ] Public webhook route: /w/{workspace_id}/workflows/{workflow_id}/{path}
- [ ] Implement run creation from incoming webhook and enqueue
- [ ] UI: Webhook trigger node and Test button
- [ ] Rate-limiting and optional auth token support
- [ ] Unit/integration tests for webhook -> run flow


Feature: HTTP Request node execution
Purpose: Provide a general HTTP request node with templating and secret-based auth; mask secrets in logs and enforce outgoing connection safety.
Estimate: 1–2 days
Acceptance criteria:
- Node configured with URL and optional credential; worker executes request and response stored in run logs with sensitive fields masked.

Checklist:
- [ ] Node schema for HTTP node and frontend config UI
- [ ] Worker implementation: template evaluation, safe request with allowlist/denylist, masking logic
- [ ] Mask Authorization/Cookie headers and any secret references in stored logs
- [ ] Unit tests with mock HTTP server to validate masking and behavior


Feature: Run history & per-node logs UI
Purpose: Show run list for workflows and node-level inputs/outputs/errors for debugging.
Estimate: 1 day
Acceptance criteria:
- Runs created by triggers (webhook/scheduler/manual) are listed and each run’s node logs are viewable.

Checklist:
- [ ] DB migration: runs and run_node_logs (or JSONB retention plan)
- [ ] Backend APIs: GET /api/workflows/:id/runs, GET /api/runs/:run_id
- [ ] Frontend: Runs list and Run detail view with per-node log inspection
- [ ] Ensure sensitive data masked before persistence
- [ ] Tests: E2E for a sample webhook-triggered run

-----------------------------
P1 (Important)
-----------------------------

Feature: Function/Transform node (templating first)
Purpose: Allow users to transform payloads between nodes using safe templating (Jinja2-like) initially.
Estimate: 1–2 days
Acceptance criteria:
- Template transforms inputs and produces expected outputs; no secret access in templates.

Checklist:
- [ ] Node UI for template input and selectors
- [ ] Backend/worker templating evaluation engine (Jinja2 safe context)
- [ ] Unit tests for templating outputs
- [ ] Document limitations and opt-in JS sandbox plan


Feature: Scheduler trigger
Purpose: Cron-like trigger for scheduled runs.
Estimate: 1–2 days
Acceptance criteria:
- Cron/interval configured in node produces runs per schedule; runs persisted and visible.

Checklist:
- [ ] DB: scheduler_entries table
- [ ] Scheduler integration (Celery beat or APScheduler) and leader election if needed
- [ ] UI: Scheduler node config and next run preview
- [ ] Tests for schedule creation and execution

-----------------------------
P2 (Operational / Long-term)
-----------------------------

Feature: Retries / Backoff / DLQ
Purpose: Retry strategies for transient failures and dead-letter queue for persistent failures.
Estimate: 1–2 days
Acceptance criteria:
- Per-node retry policy honored; failures move to DLQ after configured retries.

Checklist:
- [ ] Add retry/backoff settings to node schema
- [ ] Worker logic to apply retry strategies (Celery retry integration)
- [ ] DLQ storage and admin view for failed runs
- [ ] Tests simulating transient failures

Feature: Observability — metrics & tracing
Purpose: Export Prometheus metrics and trace runs for observability.
Estimate: 1–3 days
Acceptance criteria:
- /metrics endpoint present and key counters/histograms exported.
- Trace id attached to runs and flows.

Checklist:
- [ ] Integrate prometheus_client and expose /metrics
- [ ] Instrument run creation/completion and node execution durations
- [ ] Add trace id propagation and basic OpenTelemetry support (optional)
- [ ] Dashboard sample queries documented

Feature: Versioning & Rollback
Purpose: Save and view workflow versions; revert to older snapshots.
Estimate: 1–2 days
Acceptance criteria:
- Version history available; rollback restores workflow to prior version.

Checklist:
- [ ] DB: workflows_versions table
- [ ] On-save, persist snapshot as new version (optionally diff)
- [ ] UI: Version history and rollback action
- [ ] Tests: save multiple versions and rollback

Feature: Plugin API / Marketplace (MVP)
Purpose: Let third-party node authors add nodes without core code deployments (MVP)
Estimate: 2–4 days
Acceptance criteria:
- Install a plugin and see new node in palette; plugin execution handled by adapter or sandbox.

Checklist:
- [ ] Plugin manifest schema and loader in frontend
- [ ] Backend registration mechanism for plugin adapters (simple dir or entrypoints)
- [ ] Security constraints and plugin review notes
- [ ] Tests installing a sample plugin that exposes a simple node

Feature: RBAC & Audit logs
Purpose: Role-based access control per workspace and audit logs of sensitive operations.
Estimate: 1–3 days
Acceptance criteria:
- Permissions enforced on endpoints; audit log entries created for mutating actions.

Checklist:
- [ ] Define roles (Owner, Admin, Editor, Viewer) and permission matrix
- [ ] Enforce via FastAPI dependencies/middleware
- [ ] Audit logs table and write points for create/update/delete actions
- [ ] Tests validating enforcement and audit trail

Feature: Secrets hardening & automated tests
Purpose: Ensure secrets never leak; add tests that fail if secrets appear in persisted outputs.
Estimate: 1 day (ongoing)
Acceptance criteria:
- CI includes secret-scan tests; secrets cannot be seen in run logs or exports.

Checklist:
- [ ] Implement secret scanning utility used in tests
- [ ] Add tests scanning run logs and workflow exports for secret patterns
- [ ] Integrate into CI pipeline

-----------------------------
Cross-cutting tasks
-----------------------------

- [x] OpenAPI / API documentation for all endpoints (basic FastAPI docs present)
- [ ] DB migrations for all tables listed above with rollback capability
- [x] Integration tests: webhook -> worker -> run -> UI (basic tests exist for run creation)
- [ ] E2E tests for editor (Cypress/Playwright) — optional but recommended
- [x] CI: linting, type-check, unit tests, secret-scan test (CI runs unit tests; secret-scan pending)
- [ ] Dev documentation: local dev setup for vite frontend and backend (include env var defaults)
- [ ] Security review report (post-implementation)

-----------------------------
Suggested sprint plan (high level)
-----------------------------
Sprint 0 (Day 0.5): repo sanity, CI basics, dev env sanity checks
Sprint 1 (1–2 days): Editor Add Node + save/load
Sprint 2 (2–3 days): Secrets UI + basic HTTP node wiring
Sprint 3 (2–3 days): Webhooks + run persistence
Sprint 4 (2–3 days): Run history UI + Function node + Scheduler
Sprint 5 (2–3 days): LLM Mock + retries + metrics
Sprint 6 (3–4 days): Versioning, plugins MVP, RBAC
Sprint 7 (2–3 days): Hardening, docs, tests, polish

-----------------------------
How to use this file
-----------------------------
- Mark tasks as complete as you merge code and verify acceptance criteria.
- Use each checklist block to create tickets in your tracker (Jira/Trello/GitHub issues).
- Keep README_SPEC.md and this file in sync; update when APIs or DB schemas change.

Completed next steps (automated updates):

- [x] (1) Implement GET /api/runs/{run_id}/logs and return a LogsResponse envelope (backend/app.py endpoint implemented and wired to schemas). Verified by backend tests.
- [x] (2) Harden worker redaction and add unit tests to ensure secrets are not persisted in RunLog entries (backend/tasks.py uses redact_secrets for structured messages; test added: backend/tests/test_write_log_redacts_dict_message.py).
- [x] (3) Scaffold/update frontend editor files and wire them to POST/GET /api/workflows — frontend editor save/load wiring implemented; basic editor unit tests added. Manual test checklist updated in this file and specs/README_SPEC.md.

Preferred default: proceed with small, focused commits for each remaining subtask so you can review changes incrementally. If you'd like a different order or want to postpone any item, tell me which.

Last updated: 2025-10-07
