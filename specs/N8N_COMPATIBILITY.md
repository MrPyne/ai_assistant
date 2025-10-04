N8N Compatibility Checklist

Purpose
- Provide a concrete, testable checklist that defines what "n8n parity" means for this project. Each item includes priority (P0/P1/P2), acceptance criteria, and associated API/UI pieces.

How to use
- This file is authoritative for feature parity decisions. Add items as needed and mark status (todo/in-progress/done). Changes must be recorded in specs/README_SPEC.md changelog.

Summary of priorities
- P0: Required for MVP parity (developer-visible and user-facing core flows).
- P1: Important UX and feature parity improvements for broader adoption.
- P2: Advanced capabilities that differentiate or support enterprise use.

P0 — Core n8n parity (MVP)
- Visual editor (react-flow)
  - Acceptance: User can drag & drop nodes from a palette, connect nodes with edges, pan/zoom, multi-select, and save the graph.
  - API/UI: Frontend canvas, POST/GET /api/workflows, workflow version metadata.

- Persisted workflows + basic versioning
  - Acceptance: Saved workflows are stored as JSON graph and can be listed and loaded. Save creates a new version record.
  - API/UI: POST /api/workflows, GET /api/workflows, GET /api/workflows/{id}/versions

- Webhook trigger
  - Acceptance: Workflow with a Webhook node exposes a unique endpoint that can trigger a run. Example: POST /api/webhook/{workflow_id}/{trigger_id} responds 200 and enqueues run.
  - API/UI: Webhook management, test payload UI, run preview.

- Manual/Programmatic run
  - Acceptance: Can trigger runs via UI (Run now) and API (POST /api/workflows/{id}/run). Run is persisted and a run_id returned.
  - API/UI: POST /api/workflows/{id}/run, run modal in editor.

- Run history + per-node logs
  - Acceptance: Runs are listed with status (running/succeeded/failed). Each run shows per-node input/output and timestamps. Secrets must be redacted in logs.
  - API/UI: GET /api/runs, GET /api/runs/{id}, GET /api/runs/{id}/logs. Streaming (SSE/WebSocket) optional for live updates.

- Credentials/Secrets manager (workspace-scoped)
  - Acceptance: Users can create/store credentials (encrypted at rest) and reference them from node configs. Only workspace members see credentials.
  - API/UI: CRUD /api/secrets, secret selector in node config. Encryption via Fernet with env SECRETS_KEY.

- Provider/adapter model
  - Acceptance: Node types reference providers by id/secret_id; adapters fetch secret on runtime and do not persist plaintext credentials.
  - API/UI: Provider registry, adapter interface docs.

- HTTP Request node
  - Acceptance: Supports templated URL, headers, body; supports credentials for auth (Basic/OAuth/API Key). Responses are captured in node output.
  - API/UI: Node config schema, test-send button in node config.

- LLM node (adapter-enabled)
  - Acceptance: Node can run prompts through LLM adapter layer. Live LLM calls disabled by default; ENABLE_LIVE_LLM env var plus provider secret required for live calls. Mock mode supported for tests.
  - API/UI: LLM node config with provider selector, temperature, max_tokens, streaming opt.

- Transform/Function node (safe execution)
  - Acceptance: Provide templating (Jinja-like) or a safe JS sandbox for transforms. For MVP Jinja templating is acceptable.
  - API/UI: Transform node editor with test input.

- Basic retry and error handling
  - Acceptance: Nodes support configurable retry count and backoff. Permanent failures are marked in run and surfaced to UI.
  - API/UI: Retry config in node settings, run detail failure reason.

- RBAC + Workspace scoping
  - Acceptance: Users belong to workspaces; only workspace members can edit workflows/secrets. Basic role model (admin/editor/viewer) present.
  - API/UI: Workspace switcher, role management UI (minimal).

- Security & non-functional
  - Acceptance: Secrets encrypted; logs redacted; strong password hashing; live-LLM flag enforced.
  - API/UI: Admin/security page with toggles and audit logs.

P1 — Important UX parity
- Scheduler trigger (cron)
  - Acceptance: Cron-style schedule node that enqueues runs.
  - API/UI: Schedule editor and scheduler worker.

- If/Condition, Switch
  - Acceptance: Branching nodes with evaluation expressions.
  - API/UI: Condition editors and branch visualization.

- Looping / SplitInBatches
  - Acceptance: Batch processing node that splits input into chunks and processes them serially/parallel.

- Built-in connector examples (Slack, GitHub, Google Sheets)
  - Acceptance: Provide 1–3 example connectors to showcase provider model and OAuth flows.

- Node testing UI
  - Acceptance: Execute a single node in isolation with mocked inputs.

- Export/Import & version rollback
  - Acceptance: Export workflow JSON; import JSON to create a workflow. Ability to select prior version to restore.

P2 — Advanced features
- Marketplace/plugin system
- Enterprise-grade observability (Prometheus/Grafana)
- SSO/SSO integration, billing, rate-limiting
- Fine-grained audit and compliance features

Acceptance tests and QA
- E2E: Build a workflow with at least 3 nodes (Webhook -> HTTP -> Set) in editor, save it, trigger webhook, and assert run completes with logs showing node IO.
- Security: Run adapter & redaction tests to assert secrets never stored in plaintext in DB or logs.
- Interop: (Optional) Validate import of a simple n8n JSON export (best-effort compatibility).

Implementation notes and blockers
- JS sandboxing: Consider using a dedicated sandbox process or WASM-based sandbox for secure JS execution. MVP uses templating + limited filters.
- Live LLM cost control: enforce ENABLE_LIVE_LLM + provider presence and rate limits.
- Secrets rotation/KMS: design secret metadata to include key reference for KMS integration later.

Roadmap mapping
- Sprint 1: P0 core items (editor, webhook, run engine, run history, credentials).
- Sprint 2: P1 UX items (scheduler, condition nodes, connectors, import/export).
- Sprint 3+: P2 enterprise and marketplace features.

Status & tracking
- Track implementation status in project issues and update this file as items move to done.
