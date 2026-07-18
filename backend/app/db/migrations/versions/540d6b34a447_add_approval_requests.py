"""add approval_requests table (human-in-the-loop gate for high-risk actions)

Revision ID: 540d6b34a447
Revises: 540d6b34a446
Create Date: 2026-07-11 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '540d6b34a447'
down_revision: Union[str, None] = '540d6b34a446'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'approval_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('requested_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('compliance_assessments.id', ondelete='CASCADE')),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('connector', sa.String()),
        sa.Column('risk_level', sa.String(), nullable=False, server_default='high'),
        sa.Column('payload', sa.JSON()),
        sa.Column('reason', sa.Text()),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('reviewed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('reviewer_comment', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column('reviewed_at', sa.TIMESTAMP(timezone=True)),
    )
    op.create_index('idx_approvals_status', 'approval_requests', ['status'])


def downgrade() -> None:
    op.drop_index('idx_approvals_status', table_name='approval_requests')
    op.drop_table('approval_requests')
