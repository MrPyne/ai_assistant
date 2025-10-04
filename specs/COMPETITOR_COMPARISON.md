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

Next steps
- Map competitor features to product backlog with priorities (P0/P1/P2).
- Decide sample connectors for P1 implementation and prioritize OAuth flows vs API-key connectors.
