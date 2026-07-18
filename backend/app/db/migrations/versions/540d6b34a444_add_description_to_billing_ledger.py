"""add description column to billing_ledger

Revision ID: 540d6b34a444
Revises: 540d6b34a443
Create Date: 2026-07-08 04:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '540d6b34a444'
down_revision: Union[str, None] = '540d6b34a443'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('billing_ledger', sa.Column('description', sa.String(), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('billing_ledger', 'description')
