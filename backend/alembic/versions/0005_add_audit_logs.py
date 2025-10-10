"""add audit_logs table

Revision ID: 0005_add_audit_logs
Revises: 0004_add_webhooks_table
Create Date: 2025-10-09
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0005_add_audit_logs'
down_revision = '0004_add_webhooks_table'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('workspace_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('object_type', sa.String(), nullable=True),
        sa.Column('object_id', sa.Integer(), nullable=True),
        sa.Column('detail', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('audit_logs')
