Changelog for Spec and Feature Additions

2025-10-18 - v1.22
- Promoted and documented the new Sub-workflows / ExecuteWorkflow node (basic inline & DB-backed invocation). Added acceptance criteria and follow-up items.
- Updated prioritization: moved sub-workflows to P1 and clarified P0/P1/P2 items driven by competitor analysis.
- Added recommended next steps and acceptance tests for re-run/replay, connector OAuth flows, and server-stable event IDs.

2025-10-18 - v1.23
- Backend: added deterministic server-side event_id generation for run events to reduce duplicate logs across SSE and polling. DB schema extended with RunLog.event_id (nullable). SSE stream and polling responses include event_id when present. Added Alembic revision 0009 to add the new column and index. Included a backfill script (scripts/backfill_runlog_event_ids.py) and rollout notes recommending a zero-downtime migration and optional backfill job.

2025-10-17 - v1.21
- Documented competitor gap analysis and prioritized roadmap items.

Older entries retained in COMBINED_SPEC.md history.
