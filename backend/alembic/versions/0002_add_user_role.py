"""add user role

Revision ID: 0002_add_user_role
Revises: 0001_initial
Create Date: 2025-10-05
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_add_user_role'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade():
    # add role column to users with default 'user'
    op.add_column('users', sa.Column('role', sa.String(length=20), nullable=False, server_default=sa.text("'user'")))


def downgrade():
    op.drop_column('users', 'role')
