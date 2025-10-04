id: SPEC-001
title: Auth & core data model
status: in-progress
assignee: unassigned
priority: P0
estimate: 3d

tasks:
- [x] Add SQLAlchemy models for User, Workspace, Secret, Workflow, Run, RunLog
- [x] Configure DB engine and create tables on startup
- [x] Implement POST /api/auth/register
- [x] Implement POST /api/auth/login
- [ ] Add Alembic skeleton and migration files
- [ ] Add unit tests for auth endpoints
- [ ] Update spec file to mark items done and include links

notes:
- Uses bcrypt via passlib for password hashing
- JWT for authentication with simple SECRET_KEY env var
