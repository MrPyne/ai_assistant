"""add provider last_tested metadata

Revision ID: 0007_add_provider_test_metadata
Revises: 0006_add_scheduler_entries
Create Date: 2025-10-13
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0007_add_provider_test_metadata'
down_revision = '0006_add_scheduler_entries'
branch_labels = None
depends_on = None


def upgrade():
    # add columns to providers table
    op.add_column('providers', sa.Column('last_tested_at', sa.DateTime(), nullable=True))
    op.add_column('providers', sa.Column('last_tested_by', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('providers', 'last_tested_by')
    op.drop_column('providers', 'last_tested_at')
