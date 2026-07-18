"""add fintriage tables: entities, compliance_assessments, compliance_findings,
penalty_simulations, audit_reports, fintriage_chat_messages

Revision ID: 540d6b34a446
Revises: 540d6b34a445
Create Date: 2026-07-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '540d6b34a446'
down_revision: Union[str, None] = '540d6b34a445'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('business_name', sa.Text(), nullable=False),
        sa.Column('sector', sa.String()),
        sa.Column('incorporation_date', sa.Date()),
        sa.Column('annual_turnover', sa.Numeric()),
        sa.Column('employee_count', sa.Integer()),
        sa.Column('director_count', sa.Integer()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'compliance_assessments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='CASCADE')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('monthly_txn_volume', sa.Numeric()),
        sa.Column('avg_ticket_size', sa.Numeric()),
        sa.Column('cash_ratio', sa.Numeric()),
        sa.Column('cross_border_ratio', sa.Numeric()),
        sa.Column('late_payment_rate', sa.Numeric()),
        sa.Column('sector_risk_score', sa.Numeric()),
        sa.Column('anomaly_risk_score', sa.Numeric()),
        sa.Column('risk_tier', sa.String()),
        sa.Column('risk_score', sa.Numeric()),
        sa.Column('confidence_pct', sa.Integer()),
        sa.Column('feature_importance', sa.JSON()),
        sa.Column('detected_flags', sa.JSON()),
        sa.Column('total_penalty_exposure_inr', sa.Numeric()),
        sa.Column('raw_features', sa.JSON()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_assessments_entity', 'compliance_assessments', ['entity_id'])
    op.create_index('idx_assessments_user', 'compliance_assessments', ['user_id'])

    op.create_table(
        'compliance_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('compliance_assessments.id', ondelete='CASCADE')),
        sa.Column('rule_code', sa.String(), nullable=False),
        sa.Column('gap_score', sa.Numeric()),
        sa.Column('cosine_similarity', sa.Numeric()),
        sa.Column('combined_score', sa.Numeric()),
        sa.Column('severity', sa.String()),
        sa.Column('warning_flags', sa.JSON()),
        sa.Column('plain_english_finding', sa.Text()),
        sa.Column('remediation_steps', sa.JSON()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_findings_assessment', 'compliance_findings', ['assessment_id'])

    op.create_table(
        'penalty_simulations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('compliance_assessments.id', ondelete='CASCADE')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('scenario_id', sa.String(), nullable=False),
        sa.Column('rule_code', sa.String()),
        sa.Column('days_since_breach', sa.Integer()),
        sa.Column('aggravating_factors', sa.JSON()),
        sa.Column('base_fine', sa.Numeric()),
        sa.Column('per_day_fine', sa.Numeric()),
        sa.Column('total_fine', sa.Numeric()),
        sa.Column('imprisonment_risk', sa.Boolean()),
        sa.Column('verdict', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'audit_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('compliance_assessments.id', ondelete='CASCADE')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('report_json', sa.JSON()),
        sa.Column('gemma_summary', sa.Text()),
        sa.Column('total_penalty_exposure', sa.Numeric()),
        sa.Column('urgency_tier', sa.String()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        'fintriage_chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('assessment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('compliance_assessments.id', ondelete='CASCADE')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE')),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tool_used', sa.String()),
        sa.Column('tool_result', sa.JSON()),
        sa.Column('confidence', sa.Numeric()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_fintriage_chat_user', 'fintriage_chat_messages', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_fintriage_chat_user', table_name='fintriage_chat_messages')
    op.drop_table('fintriage_chat_messages')
    op.drop_table('audit_reports')
    op.drop_table('penalty_simulations')
    op.drop_index('idx_findings_assessment', table_name='compliance_findings')
    op.drop_table('compliance_findings')
    op.drop_index('idx_assessments_user', table_name='compliance_assessments')
    op.drop_index('idx_assessments_entity', table_name='compliance_assessments')
    op.drop_table('compliance_assessments')
    op.drop_table('entities')
