"""add run_logs.event_id (nullable) and index

Revision ID: 0009_add_runlog_event_id
Revises: 0008_add_node_model_column
Create Date: 2025-10-18
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009_add_runlog_event_id"
down_revision = "0008_add_node_model_column"
branch_labels = None
depends_on = None


def upgrade():
    # Add nullable event_id column if it does not already exist.
    op.add_column("run_logs", sa.Column("event_id", sa.String(), nullable=True))
    # Create an index to speed lookups (non-unique, nullable)
    op.create_index("ix_run_logs_event_id", "run_logs", ["event_id"], unique=False)


def downgrade():
    op.drop_index("ix_run_logs_event_id", table_name="run_logs")
    op.drop_column("run_logs", "event_id")
