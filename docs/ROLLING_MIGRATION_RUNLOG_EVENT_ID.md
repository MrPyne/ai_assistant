Rolling Migration & Backfill Plan for RunLog.event_id

Goal
- Add a nullable, indexed event_id column to run_logs and populate it for new events and optionally for historical rows.
- Keep the migration zero-downtime and safe for production; allow clients to continue working whether or not event_id is present.

High-level strategy
1. Schema migration (add column + index) — fast, additive, nullable.
2. Deploy application that writes event_id for new RunLog rows. New writes will populate the column.
3. Optional backfill job to compute event_id for historical rows. This can be run as a one-off background job with batching and resumability.
4. Monitor metrics and rollback plan.

Step-by-step

1) Create Alembic revision to add column + index
- Revision 0009_add_runlog_event_id already created in repo.
- This change is additive and nullable so it is safe to apply online.

2) Deploy migration
- Run alembic upgrade head via CI/CD or a migration job. Because the column is nullable and non-unique, the alter table should be fast on most clouds. The index creation may take time on very large tables — consider creating the index concurrently where supported (Postgres CREATE INDEX CONCURRENTLY) to avoid locking.
- If using Postgres and Alembic, you can modify the migration to use op.execute to run CREATE INDEX CONCURRENTLY within a transaction boundary workaround (Alembic will put migration in a transaction; use separate connection if needed).

3) Deploy app change
- The application code already computes event_id for persisted RunLog rows and sets the field on new writes. Deploy this code after the migration is applied.
- New RunLog rows will then have event_id populated automatically.

4) Optional backfill
- Backfill script (scripts/backfill_runlog_event_ids.py) is included. It is resumable and idempotent; it processes rows with NULL event_id in batches and writes deterministic ids.
- Run the script with --commit in a low-traffic maintenance window, or run in parallel with the app if desired. Use --batch-size to tune DB load.
- For large datasets consider a more robust approach: use a DB-side UPDATE where possible with a deterministic SQL expression, or run per-shard jobs.

5) Monitoring
- Monitor error budgets, DB load, and number of rows updated.
- Check SSE behavior: clients should receive SSE id: <event_id> for new events and API endpoints will include event_id when present.

6) Rollback
- Schema change is additive: to roll back, remove app change and drop column via another migration if necessary.
- Backfill is idempotent; if partial runs occurred, re-running will skip rows that already have event_id.

Notes and caveats
- UUID5 canonicalization must match the running code (the backfill script mirrors it). Do not change canonicalization later without coordinating a migration or versioning scheme for event ids.
- The canonicalization intentionally excludes the 'timestamp' field to remain stable across reruns and republished events. Maintaining this rule is required for determinism.
- The migration adds an index; ensure index creation strategy (concurrent vs in-transaction) matches your DB and downtime requirements.

SQL snippet for large Postgres tables (concurrent index creation)
- Example (run outside transactions):
    ALTER TABLE run_logs ADD COLUMN event_id VARCHAR NULL;
    CREATE INDEX CONCURRENTLY ix_run_logs_event_id ON run_logs (event_id);

Backfill considerations for very large tables
- Use batching based on primary key ranges.
- Use a job queue or kinesis to process rows in parallel while limiting DB connections and write locks.
- If you have replicas, consider doing backfill against a replica and then promote it, or perform throttled updates.

Contact
- For help coordinate with the platform/DB team and ensure you have backups and monitoring before running anything that updates many rows.
