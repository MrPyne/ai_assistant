+Title: Add Redis + Worker to docker-compose and implement run logs endpoint
+Status: todo
+Priority: P0
+Description:
+  - Add redis and worker services to docker-compose so Celery tasks can be processed in dev.
+  - Implement GET /api/runs/{run_id}/logs to return per-run logs (redacted).
+  - Ensure SECRETS_KEY is configurable via env and documented in README.
+
+Acceptance criteria:
+  - docker-compose up starts db, web, frontend, redis, and worker.
+  - GET /api/runs/{run_id}/logs returns run logs with secrets redacted.
+  - Spec updated to reflect redaction implemented.
+
