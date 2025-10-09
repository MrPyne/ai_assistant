"""Add webhooks table

Revision ID: 0004_add_webhooks_table
Revises: 0003_add_attempts_to_runs
Create Date: 2025-10-09
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_add_webhooks_table"
down_revision = "0003_add_attempts_to_runs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("workspace_id", sa.Integer, sa.ForeignKey("workspaces.id")),
        sa.Column("workflow_id", sa.Integer, sa.ForeignKey("workflows.id")),
        sa.Column("path", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("webhooks")
