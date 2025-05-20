"""add is_optimized to user_trips

Revision ID: add_is_optimized_to_user_trips
Revises: 
Create Date: 2025-05-20 23:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_is_optimized_to_user_trips'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_optimized column with default value False
    op.add_column('user_trips', sa.Column('is_optimized', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    # Remove is_optimized column
    op.drop_column('user_trips', 'is_optimized') 