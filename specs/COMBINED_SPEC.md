Spec: No-code AI Assistant Platform (n8n-like)
Version: 1.15
Last updated: 2025-10-11
Maintainer: (fill in)

Purpose
- Provide a single reference checklist to guide development and acceptance testing.
- Be a living document: items can be added/removed; changes must include version update + date and changelog entry.

Project goal
- Build an n8n-compatible no-code workflow automation platform with LLM-enabled nodes.
- Deliver a visual workflow editor (drag-and-drop) with node types, credentials management, reliable execution, and a secure adapter model for connectors and LLMs.

---

High-level n8n compatibility checklist (P0/P1/P2)
- The following items define what "n8n parity" means for this project. Items marked P0 are required for MVP parity.

P0 — Core n8n parity (MVP)
- [x] Drag-and-drop workflow editor (react + react-flow) with node palette, node config panel, and ability to create connections. (Frontend MVP implemented)
- [x] Persist workflows (save / load /basic versioning) as graph JSON (POST/GET /api/workflows). (API wiring present; editor uses these endpoints)
- [x] Visual node types (minimum set): Trigger(Webhook), Action(HTTP Request), Action(LLM prompt), Transform (templating / JS), Set/Assign (store variables), Output(Log/Response). (Editor provides Webhook, HTTP, LLM and a raw JSON editor for transforms)
- [x] Webhook trigger endpoint for workflows (POST /api/webhook/{workflow_id}/{trigger_id}).
- [x] Manual run endpoint (POST /api/workflows/{workflow_id}/run).
- [x] Execution engine: worker that dequeues workflow runs, executes nodes in graph order, passes data between nodes, and persists run status and logs. (Worker skeleton + execution tasks implemented)
- [x] Run history UI and API (GET /api/runs, GET /api/runs/{id}, GET /api/runs/{id}/logs). (Frontend run list + logs viewer wired)
- [x] Credentials management UI/API (Secrets): create, update, delete secrets (workspace scoped) and reference secrets from nodes. Secrets MUST be encrypted at rest. (Secrets UI added to editor; backend encrypts secrets)
- [x] Provider model (connectors & LLM providers) with credential reference (provider.secret_id) — providers DO NOT store plaintext credentials.
- [x] Basic RBAC + workspace scoping (users, workspaces). Only workspace members can edit workflows or credentials in that workspace.
- [x] Safe JS/transform execution: provide a secure transform node (Jinja-like templating or sandboxed JS) for data transformations. (Editor exposes a raw JSON transform for MVP; secure sandboxing remains an implementation note)
- [x] Basic retry and error handling for nodes with configurable retry count; failed runs recorded with clear failure reason.
- [x] Basic logging with secret redaction; logs available in run history and streamed to the editor during execution (SSE or WebSocket stub acceptable for MVP).

P1 — Important features to match broader n8n UX
- [ ] Scheduler trigger (cron) nodes.
- [ ] Condition/If and Switch nodes for branching logic.
- [ ] Loop/Serial and Parallel nodes (SplitInBatches equivalent).
- [ ] Built-in connectors: Slack, GitHub, Google Sheets, Email (examples).
- [ ] Human-in-the-loop (wait for approval) node (UI for approving runs).
- [ ] Node testing UI (execute a single node with input sample).
- [ ] Loop/Serial and Parallel nodes (SplitInBatches equivalent).
- [ ] Export/import workflows (JSON) and basic version rollback.

P2 — Advanced / long-term
- [ ] Multi-tenant SaaS features, SSO, billing, rate limiting per workspace.
- [ ] Marketplace/plugin system to add node types.
- [ ] Advanced observability (Prometheus, Grafana), complex retry policies, and traceability integrations.

---

Non-functional & security requirements (applies to P0+)
- [ ] Secrets encrypted at rest (Fernet/KMS) and never logged in plaintext.
- [ ] Live LLM calls disabled by default (ENABLE_LIVE_LLM=false). Live calls require explicit flag + provider.secret_id.
 - [x] Live outbound HTTP disabled by default (LIVE_HTTP=false). Outbound HTTP from workers requires LIVE_HTTP=true to opt-in. Tests that exercise HTTP behavior should set LIVE_HTTP accordingly.
- [ ] Use strong password hashing (argon2 / bcrypt) and HTTPS in production.
- [ ] Sanitize and validate all node inputs and template execution to prevent injection.
- [ ] Audit logs for credential changes and run lifecycle events.
- [ ] KMS-ready design for secret rotation (design note: store key reference for KMS integration later).

---

Architecture & tech stack (confirmed)
- Frontend: React + TypeScript + react-flow for the editor; Material-UI or Tailwind (TBD).
- Backend: FastAPI (Python) with Pydantic for schemas.
- Execution/worker: Celery with Redis broker (workers run Python tasks that execute node graphs).
- Database: PostgreSQL for metadata; SQLite allowed for local tests.
- Object store: S3-compatible (MinIO for dev) for artifacts.
- LLM adapter layer: provider-agnostic adapter with OpenAI adapter implemented; adapters fetch credentials by secret_id.
- Secrets encryption: Fernet with SECRETS_KEY env variable (KMS-ready design).

---

MVP prioritization & sprint plan (re-aligned to n8n parity)
- Sprint 1 (P0 core): Editor MVP + Workflows CRUD + Webhook trigger + Execution engine basic runner + Run history/logs + Credentials API + Webhook trigger sample workflow. (High priority)
- Sprint 2 (P1): Scheduler, Condition nodes, built-in connectors (one or two), node testing UI, export/import, versioning improvements.
- Sprint 3 (P2+): Marketplace, multi-tenant features, SSO, billing, advanced observability.

Sprint 1 — Immediate work items (I will start these now)
1) Update & stabilize spec (this file) and add a short n8n compatibility checklist — done (v1.7).
2) Frontend Editor MVP: ensure react-flow canvas + node palette + node config panels can create/save/load workflows using POST/GET /api/workflows. Wire run history and logs viewer to /api/runs endpoints. Provide provider/secret selectors in node config. (I will commit the frontend scaffold and incremental UI work in small steps.)
3) Backend hardening (in parallel, small focused tasks):
   - Harden worker redaction so decrypted secrets are never written to logs (adapter interface enforces secret_id only; adapters decrypt internally). Add unit tests.
   - Implement or improve GET /api/runs/{id}/logs to return redacted RunLog entries. Provide SSE/WebSocket stub for streaming logs; fallback to polling supported by UI.
   - Add server-side node config schema validation to reject invalid node configs on workflow save or run.
   - Add deeper Celery retry/backoff handling and DLQ marking for permanently failed runs.
4) Secure transform: implement Jinja-like templating sandbox for transforms (MVP: restrict to Jinja templates and safe filters; JS sandboxing deferred until secure embedding available).
5) Acceptance criteria & tests for Sprint 1: end-to-end tests that create a workflow (Webhook -> HTTP forward -> Set), trigger it via POST /api/webhook, and assert Run exists and logs are retrievable without any plaintext secrets.

Milestones & deliverables (short)
- Milestone 1 (this sprint): Editor MVP + Workflow save/load + Webhook run end-to-end (webhook -> run -> worker -> logs). Acceptance: user can build a simple HTTP-forward workflow in the editor and see a run complete with redacted logs.
- Milestone 2: Credentials UI + Provider wiring + LLM adapter live mode toggle. Acceptance: user can create a provider referencing a secret and run an LLM node in mock/live mode.
- Milestone 3: Control nodes (If/Condition, Loop), Scheduler. Acceptance: workflows with branching can be built and executed.

---

Implementation Checklist (merged)

This checklist is the single-source tracker for implemented work and remaining tasks required to reach feature parity with n8n. Use it to assign, mark progress, and run DoD verification for each feature.

Guidelines
- Tasks checked [x] are implemented (committed or verified in repo).
- Tasks unchecked [ ] are outstanding.
- Each feature includes: Purpose, Acceptance criteria (DoD), Estimate, and a granular checklist.

Project status summary
- Repo scaffold with FastAPI backend, Celery/Redis worker, React frontend (react-flow) — [x]
- Adapter skeletons & basic worker — [x]
- Frontend editor MVP exists (editor runtime unstable; add-node failing historically) — [x]
- Spec updated toward n8n parity — [x]

P0 (Must have)

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

Feature: Secrets (Credentials) UI & Backend
Purpose: Workspace-scoped secrets storage, selection in nodes, and secure resolution at runtime.
Estimate: 1 day
Acceptance criteria:
- Create/edit/delete secrets via UI.
- Designed so secret values are not returned by GET endpoints or shown in UI after save.
- Nodes can reference secrets; at runtime workers receive usable credentials without secrets exposed in logs or APIs.

Checklist:
 - [x] DB migration: create secrets table — DONE (TO_BE_FILLED)
 - [x] Backend APIs: POST/GET/PUT/DELETE /api/workspaces/:ws/secrets — DONE (TO_BE_FILLED)
 - [x] Encryption helpers (Fernet/KMS) and rotate strategy documented — DONE (TO_BE_FILLED)
 - [ ] UI: Secrets page and create/edit modal (masked input)
 - [x] Node config: credential selector lists workspace secrets (metadata only) — DONE (TO_BE_FILLED)
 - [x] Worker secret resolution flow (secure injection or server-forwarded secrets) — DONE (TO_BE_FILLED)
 - [ ] Audit logging for secret access
 - [x] Unit/integration tests to ensure no plaintext secret leakage — DONE (TO_BE_FILLED)

Feature: Webhook trigger + Test Runner
Purpose: Per-workflow webhook endpoints; incoming requests create runs and enqueue worker execution. UI test runner to exercise webhooks.
Estimate: 1–2 days
Acceptance criteria:
- Webhook endpoint is routable and triggers run creation with trigger_payload stored.
- Test button in UI sends payload and returns run id/response.

Checklist:
- [x] DB migration: webhooks table — DONE (2025-10-09, commit: 7d9f897)
- [x] Backend APIs: CRUD webhooks under /api/workflows/:workflow_id/webhooks — DONE (2025-10-09, commit: 7d9f897)
- [x] Public webhook route: /w/{workspace_id}/workflows/{workflow_id}/{path} — DONE (2025-10-09, commit: 7d9f897)
- [x] Implement run creation from incoming webhook and enqueue — DONE (2025-10-09, commit: 7d9f897)
- [ ] UI: Webhook trigger node and Test button
- [ ] Rate-limiting and optional auth token support
- [x] Unit/integration tests for webhook -> run flow — DONE (2025-10-09, commit: 7d9f897)

Feature: HTTP Request node execution
Purpose: Provide a general HTTP request node with templating and secret-based auth; mask secrets in logs and enforce outgoing connection safety.
Estimate: 1–2 days
Acceptance criteria:
- Node configured with URL and optional credential; worker executes request and response stored in run logs with sensitive fields masked.

Checklist:
- [x] Node schema for HTTP node and frontend config UI
- [x] Worker implementation: template evaluation (Jinja to be added), safe request with allowlist/denylist (basic safety applied), masking logic
- [x] Mask Authorization/Cookie headers and any secret references in stored logs
- [x] Unit tests with mock HTTP server to validate masking and behavior

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

P1 (Important)

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

P2 — Advanced / long-term

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
- [ ] Add sample dashboard queries documented

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
- [x] Implement secret scanning utility used in tests
- [x] Add tests scanning run logs and workflow exports for secret patterns
- [ ] Integrate into CI pipeline
- [x] Add unit test for aggregate vendor regex budget handling (ensures budget-exceeded telemetry recorded)

Note: Recent changes (2025-10-11)
- Implemented HTTP Request node execution in the worker with improved redaction:
  - Worker supports runtime execution of HTTP nodes (method, url, headers, body) and persists responses in run output.
  - Redaction: Authorization and Cookie headers are masked, and provider-referenced secrets (resolved at runtime, not persisted) are replaced with [REDACTED] in logs and outputs.
  - Unit test coverage added: backend/tests/test_http_node_redaction.py validates that Authorization headers are redacted from persisted RunLog entries even when the HTTP client raises an exception containing the header value.
  - Note: templating (Jinja) support for node fields will be added next; for now node values are used verbatim or resolved via provider secrets when configured.

1.14 (2025-10-10)
- Extended in-process redaction telemetry to record vendor-specific diagnostics:
  - vendor_timeouts: counts of vendor patterns that were skipped due to timeout when applying regexes (requires 'regex' package to exercise timeouts).
  - vendor_errors: counts of vendor patterns that failed to compile or raised errors during application.
  - Exposed on the existing /internal/redaction_metrics endpoint and reset by /internal/redaction_metrics/reset. These additions are intended to aid CI and operational diagnostics without changing previous behavior.

1.13 (2025-10-10)
- Hardened vendor-supplied redaction regex handling in backend/utils.py:
  - Added caching of compiled REDACT_VENDOR_REGEXES and thread-safe reload when env changes.
  - Added conservative safety limits: max number of vendor regexes (50) and max pattern length (1000).
  - Use optional 'regex' package when available to enable per-pattern timeouts; fall back to builtin 're' otherwise.
  - Introduced REDACT_VENDOR_REGEX_TIMEOUT_MS env var (per-pattern timeout, default 100 ms) to bound vendor regex execution.
  - Preserved previous behavior of silently ignoring malformed vendor patterns.
- Tests added/updated:
  - backend/tests/test_vendor_regexes.py: covers parsing formats and malformed inputs.
  - backend/tests/test_vendor_regex_timeouts.py: asserts pathological patterns are skipped quickly; test skips if 'regex' package not available in the environment.
  - backend/tests/test_vendor_regex_budget.py: new unit test that asserts aggregate vendor regex budget exceeding records telemetry and short-circuits pattern application.

... (previous changelog entries unchanged)

Last updated: 2025-10-11

---

N8N Compatibility (authoritative checklist)
(abridged from N8N_COMPATIBILITY.md and merged above) — see the P0/P1/P2 checklists earlier in this document for the compatibility requirements and acceptance criteria.

---

Change log (merged)

1.15 (2025-10-11)
- Implemented HTTP Request node execution in the worker with redaction and unit test coverage for Authorization header redaction.
- Marked HTTP Request node checklist items as implemented in the combined spec.

1.14 (2025-10-10)
- Extended in-process redaction telemetry to record vendor-specific diagnostics (see above).

... (older entries retained)
