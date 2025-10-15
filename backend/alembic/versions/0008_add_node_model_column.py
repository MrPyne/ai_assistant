"""add node model column

Revision ID: 0008_add_node_model_column
Revises: 0007_add_provider_test_metadata
Create Date: 2025-10-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008_add_node_model_column"
down_revision = "0007_add_provider_test_metadata"
branch_labels = None
depends_on = None


def upgrade():
    """Add a nullable 'model' column to the providers table."""
    op.add_column("providers", sa.Column("model", sa.String(), nullable=True))


def downgrade():
    """Remove the 'model' column from the providers table."""
    op.drop_column("providers", "model")
