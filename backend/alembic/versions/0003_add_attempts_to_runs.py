"""add attempts to runs

Revision ID: 0003_add_attempts_to_runs
Revises: 0002_add_user_role
Create Date: 2025-10-06
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_add_attempts_to_runs'
down_revision = '0002_add_user_role'
branch_labels = None
depends_on = None


def upgrade():
    # add attempts column to runs with default 0
    op.add_column('runs', sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('runs', 'attempts')
