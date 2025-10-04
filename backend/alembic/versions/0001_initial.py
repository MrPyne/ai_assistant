"""initial migration

Revision ID: 0001_initial
Revises: 
Create Date: 2025-10-03
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('email', sa.String, nullable=False, unique=True),
        sa.Column('hashed_password', sa.String, nullable=False),
        sa.Column('is_active', sa.Boolean, server_default=sa.sql.expression.true()),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'workspaces',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('owner_id', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'secrets',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id')),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('encrypted_value', sa.String, nullable=False),
        sa.Column('created_by', sa.Integer, sa.ForeignKey('users.id')),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'workflows',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id')),
        sa.Column('name', sa.String, nullable=False),
        sa.Column('description', sa.String, nullable=True),
        sa.Column('graph', sa.JSON, nullable=True),
        sa.Column('version', sa.Integer, server_default='1'),
        sa.Column('created_at', sa.DateTime, nullable=True),
        sa.Column('updated_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'providers',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('workspace_id', sa.Integer, sa.ForeignKey('workspaces.id')),
        sa.Column('secret_id', sa.Integer, sa.ForeignKey('secrets.id'), nullable=True),
        sa.Column('type', sa.String, nullable=False),
        sa.Column('config', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'runs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('workflow_id', sa.Integer, sa.ForeignKey('workflows.id')),
        sa.Column('status', sa.String, server_default='pending'),
        sa.Column('input_payload', sa.JSON, nullable=True),
        sa.Column('output_payload', sa.JSON, nullable=True),
        sa.Column('started_at', sa.DateTime, nullable=True),
        sa.Column('finished_at', sa.DateTime, nullable=True),
    )
    op.create_table(
        'run_logs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('run_id', sa.Integer, sa.ForeignKey('runs.id')),
        sa.Column('node_id', sa.String, nullable=True),
        sa.Column('timestamp', sa.DateTime, nullable=True),
        sa.Column('level', sa.String, nullable=True),
        sa.Column('message', sa.String, nullable=True),
    )


def downgrade():
    op.drop_table('run_logs')
    op.drop_table('runs')
    op.drop_table('workflows')
    op.drop_table('secrets')
    op.drop_table('workspaces')
    op.drop_table('users')
