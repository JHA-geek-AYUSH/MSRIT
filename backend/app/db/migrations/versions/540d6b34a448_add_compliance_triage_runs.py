"""add durable compliance triage runs

Revision ID: 540d6b34a448
Revises: 540d6b34a447
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "540d6b34a448"
down_revision: Union[str, None] = "540d6b34a447"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_triage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("redacted_description", sa.Text(), nullable=False),
        sa.Column("context_json", sa.JSON()),
        sa.Column("result_json", sa.JSON()),
        sa.Column("overall_rating", sa.String()),
        sa.Column("requires_str", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("requires_edd", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("idx_triage_runs_user_created", "compliance_triage_runs", ["user_id", "created_at"])
    op.create_index("idx_triage_runs_status", "compliance_triage_runs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_triage_runs_status", table_name="compliance_triage_runs")
    op.drop_index("idx_triage_runs_user_created", table_name="compliance_triage_runs")
    op.drop_table("compliance_triage_runs")
