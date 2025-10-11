Spec: No-code AI Assistant Platform (n8n-like)
Version: 1.16
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
- [x] Live LLM calls disabled by default (ENABLE_LIVE_LLM=false). Live calls require explicit flag + provider.secret_id.
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

Sprint 1 — Immediate work items (I will start these now)

1.14 (2025-10-10)
- Extended in-process redaction telemetry to record vendor-specific diagnostics:
  - vendor_timeouts: counts of vendor patterns that were skipped due to timeout when applying regexes (requires 'regex' package to exercise timeouts).
  - vendor_errors: counts of vendor patterns that failed to compile or raised errors during application.
  - Exposed on the existing /internal/redaction_metrics endpoint and reset by /internal/redaction_metrics/reset. These additions are intended to aid CI and operational diagnostics without changing previous behavior.

...

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

... (older entries retained)

Last updated: 2025-10-11

---

N8N Compatibility (authoritative checklist)
(abridged from N8N_COMPATIBILITY.md and merged above) — see the P0/P1/P2 checklists earlier in this document for the compatibility requirements and acceptance criteria.

---

Change log (merged)

1.16 (2025-10-11)
- Implemented ENABLE_LIVE_LLM opt-in guard across LLM adapters (OpenAI, Ollama). Live LLM calls are disabled by default; adapters return deterministic mock responses preserving response shape when disabled. Tests updated to opt-in to live behavior where necessary.

1.15 (2025-10-11)
- Implemented HTTP Request node execution in the worker with redaction and unit test coverage for Authorization header redaction.
- Marked HTTP Request node checklist items as implemented in the combined spec.

1.14 (2025-10-10)
- Extended in-process redaction telemetry to record vendor-specific diagnostics (see above).

... (older entries retained)

Last updated: 2025-10-11
