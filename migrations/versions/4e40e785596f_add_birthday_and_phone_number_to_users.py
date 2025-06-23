"""Add birthday and phone_number to users

Revision ID: 4e40e785596f
Revises: e2f6a6263d46
Create Date: 2025-06-02 14:36:31.439012

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '4e40e785596f'
down_revision = 'e2f6a6263d46'
branch_labels = None
depends_on = None


def upgrade():
    # Add birthday column (nullable DATE field)
    op.add_column('users', sa.Column('birthday', sa.Date(), nullable=True))

    # Add phone_number column (nullable VARCHAR field)
    op.add_column(
        'users', sa.Column('phone_number', sa.String(length=20), nullable=True)
    )


def downgrade():
    # Remove the added columns
    op.drop_column('users', 'phone_number')
    op.drop_column('users', 'birthday')
