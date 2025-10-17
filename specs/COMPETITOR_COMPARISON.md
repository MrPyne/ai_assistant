Competitor Comparison Matrix

Purpose
- Provide a concise comparison of core features across competitors to help prioritize feature gaps and differentiation.

Competitors included
- n8n
- Zapier
- Make (Integromat)
- Node-RED
- Tray.io
- Workato

Matrix (high level)
- Triggers: Webhook, Schedule, Polling
- Nodes/Actions: HTTP, Code/Function, Built-in Apps (Slack, GitHub, Sheets), Email
- Credentials: UI for storing creds, OAuth flows
- Editor: Visual canvas, branching, loops, multi-select
- Versioning: Save versions, rollback
- Extensibility: Custom nodes/plugins
- Hosting: Self-host option, Cloud/SaaS
- Enterprise: SSO, RBAC, Billing
- Observability: Retry, DLQ, Metrics, Logs

Summary notes
- n8n: Strong open-source self-host story, feature-rich node library, visual editor, supports credentials and plugins. Lacks built-in advanced SaaS UX like Zapier.
- Zapier: Mature SaaS with app directory and multi-step workflows, strong UX and marketplace; no self-host option.
- Make: Visual flow builder with detailed execution trace and data mapping; strong for complex transformations.
- Node-RED: Low-level node system, strong IoT/embedded use cases; developer-focused.
- Tray.io / Workato: Enterprise-focused with powerful integrations and orchestration, paid offerings.

Competitive takeaways
- Prioritize: Visual editor parity, run history + step debugging, credentials manager, and a couple of high-impact connectors (GitHub, Slack) as P1.
- Differentiation: Tight LLM integration (LLM nodes + prompt templates + streaming) and strong secret handling plus self-hosting are differentiators.
- Marketplace: Important longer-term; early focus should be on first-class node UX and execution reliability.

Current implementation status (project -> feature mapping)
- Triggers
  - Webhook: Done (P0) — server webhook endpoint and editor support to build webhook-triggered workflows.
  - Scheduler (cron): Done (P1) — scheduler UI and backend retry/enqueue endpoint implemented; cron validation/timezone support remaining.
  - Polling trigger: Not implemented (P1/P2) — planned for connector implementations that require polling.

- Nodes/Actions
  - HTTP Request node: Done (P0) — action node available; live HTTP disabled by default (LIVE_HTTP opt-in).
  - LLM prompt node: Done (P0) — LLM adapter model in place (OpenAI/Ollama) with mock/live gating via backend/llm_utils.
  - Transform/templating node: Partial (P0) — raw JSON editor present; secure Jinja-like sandbox planned and partially supported.
  - Set/Assign/Output nodes: Done (P0) — basic set and logging nodes implemented.
  - Condition/If and Switch nodes: Not implemented (P1) — next recommended P1 feature; planning docs in COMBINED_SPEC.
  - Loop/Parallel (SplitInBatches): Not implemented (P1) — planned for future sprints.

- Credentials & Providers
  - Secrets UI/API: Done (P0) — secrets stored encrypted; backend uses Fernet; secrets not persisted in plaintext.
  - Provider model / adapters: Done (P0) — provider model present; adapters follow centralized is_live_llm_enabled guard for LLMs. Some adapters (OpenAI/Ollama) updated; others need migration.
  - OAuth flows (connectors): Not implemented (P1) — API-key style connectors supported first; OAuth planned per-connector.

- Editor & UX
  - Visual editor (react-flow): Done (P0) — drag-and-drop editor implemented.
  - Run history & logs viewer: Done (P0) — run list + logs wired; streaming via SSE/poll fallback present.
  - Run-logs UX improvements: In progress — immediate clear on run switch (done), node-running overlay added (done); spinner/loading state for logs and transitions are pending.
  - Node testing UI: Not implemented (P1) — UI modal for single-node testing planned.
  - Export/import & version rollback: Not implemented (P1) — basic save/load exists; richer versioning planned.

- Execution & Reliability
  - Execution engine & worker tasks: Done (P0) — Celery/Redis integration and fallback runner implemented; tasks and run persistence present.
  - Retry & DLQ: Partial (P0/P1) — basic retry support implemented; DLQ and advanced backoff policies require enhancement.
  - Redaction / secret safety: Done (P0) — log redaction utilities and a large suite of backend tests ensuring secrets are not leaked.

- Observability & Security
  - Audit logs: Partial — audit log model exists; API and export features present but full audit UX and filters may need work.
  - Metrics & monitoring: Partial — redaction metrics tracked; Prometheus/Grafana integration planned.
  - RBAC & workspaces: Done (P0) — workspace scoping and basic RBAC implemented.

Actionable next steps (prioritized)
1. Implement Condition/If and Switch nodes (P1) — highest-impact P1 item for branching workflows.
2. Add Node Testing UI (P1) — allow executing a single node with sample input to iterate quickly.
3. Ship a small set of high-value connectors (GitHub, Slack) using API-key flows; add OAuth later as needed (P1).
4. UX polish for run logs: add loading indicator for logs fetch, overlay transitions, and accessibility live regions (a11y) (low-effort, high-impact).
5. Improve SSE vs GET log race robustness: add server-stable event IDs and add integration tests for dedupe behavior (medium effort).
6. Add frontend tests that cover run-switching, SSE/poll dedupe, and node-running overlay behavior (P1).
7. Harden retry/DLQ behavior and add end-to-end tests for scheduler enqueuing and retry flows.

Next steps
- Map the prioritized items above to the sprint backlog and break into actionable issues (UI, API, worker, tests).
- If helpful, I can open PRs or draft individual task-specs for the top 3 items (Condition nodes, Node test modal, GitHub/Slack connectors).

