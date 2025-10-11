"""add scheduler_entries table

Revision ID: 0006_add_scheduler_entries
Revises: 0005_add_audit_logs
Create Date: 2025-10-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0006_add_scheduler_entries'
down_revision = '0005_add_audit_logs'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scheduler_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('workspace_id', sa.Integer(), nullable=True),
        sa.Column('workflow_id', sa.Integer(), nullable=True),
        sa.Column('schedule', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('active', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('scheduler_entries')
