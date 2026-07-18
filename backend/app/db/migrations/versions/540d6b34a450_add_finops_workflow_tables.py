"""add FinOps workflow tables: invoices, transaction_batches, vendor_onboarding_cases,
policy_documents, workflow_runs, audit_trail_entries

Revision ID: 540d6b34a450
Revises: 540d6b34a449
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "540d6b34a450"
down_revision: Union[str, None] = "540d6b34a449"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # approval_requests already exists (540d6b34a447) — invoices/batches/vendors/
    # workflow_runs all FK into it, so it must be created first (it is).

    op.create_table(
        "workflow_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("risk_tier", sa.String(20)),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "workflow_type IN ('invoice','transaction_batch','vendor_onboarding','policy_review','entity_assessment','full_triage')",
            name="workflow_runs_workflow_type_chk",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','awaiting_approval')",
            name="workflow_runs_status_chk",
        ),
        sa.CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="workflow_runs_risk_tier_chk",
        ),
    )
    op.create_index("idx_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index("idx_workflow_runs_status", "workflow_runs", ["status"])
    op.create_index("idx_workflow_runs_workflow_type", "workflow_runs", ["workflow_type"])

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_name", sa.String(255)),
        sa.Column("vendor_gstin", sa.String(20)),
        sa.Column("invoice_number", sa.String(100), nullable=False),
        sa.Column("invoice_date", sa.String(10)),
        sa.Column("amount_net", sa.Numeric(15, 2)),
        sa.Column("amount_gst", sa.Numeric(15, 2)),
        sa.Column("amount_total", sa.Numeric(15, 2)),
        sa.Column("po_number", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False, server_default="processing"),
        sa.Column("risk_tier", sa.String(20)),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("extraction_confidence", sa.Numeric(), nullable=False, server_default="0.0"),
        sa.Column("raw_extracted_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('processing','extracted','validated','risk_scored','approved','rejected')",
            name="invoices_status_chk",
        ),
        sa.CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="invoices_risk_tier_chk",
        ),
    )
    op.create_index("idx_invoices_user_id", "invoices", ["user_id"])
    op.create_index("idx_invoices_status", "invoices", ["status"])

    op.create_table(
        "transaction_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("total_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flagged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_tier", sa.String(20)),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("source IN ('manual','sap','excel','outlook','csv')", name="transaction_batches_source_chk"),
        sa.CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="transaction_batches_risk_tier_chk",
        ),
    )
    op.create_index("idx_transaction_batches_user_id", "transaction_batches", ["user_id"])

    op.create_table(
        "vendor_onboarding_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("vendor_gstin", sa.String(20)),
        sa.Column("vendor_pan", sa.String(10)),
        sa.Column("sector", sa.String(100)),
        sa.Column("kyc_status", sa.String(20), nullable=False, server_default="in_review"),
        sa.Column("risk_tier", sa.String(20)),
        sa.Column("missing_documents", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("pep_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("ubo_issues", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("approval_requests.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("kyc_status IN ('in_review','approved','escalated')", name="vendor_onboarding_cases_kyc_status_chk"),
        sa.CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="vendor_onboarding_cases_risk_tier_chk",
        ),
    )
    op.create_index("idx_vendor_onboarding_cases_user_id", "vendor_onboarding_cases", ["user_id"])
    op.create_index("idx_vendor_onboarding_cases_kyc_status", "vendor_onboarding_cases", ["kyc_status"])

    op.create_table(
        "policy_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), server_default="1.0"),
        sa.Column("effective_date", sa.String(10)),
        sa.Column("document_url", sa.String(500)),
        sa.Column("compliance_gaps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_policy_documents_user_id", "policy_documents", ["user_id"])

    op.create_table(
        "audit_trail_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False, server_default="system"),
        sa.Column("entity_type", sa.String(100)),
        sa.Column("entity_id", sa.String(255)),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id", ondelete="CASCADE")),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE")),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index("idx_audit_trail_entries_workflow_id", "audit_trail_entries", ["workflow_id"])
    op.create_index("idx_audit_trail_entries_invoice_id", "audit_trail_entries", ["invoice_id"])
    op.create_index("idx_audit_trail_entries_entity_id", "audit_trail_entries", ["entity_id"])
    op.create_index("idx_audit_trail_entries_timestamp", "audit_trail_entries", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_trail_entries")
    op.drop_table("policy_documents")
    op.drop_table("vendor_onboarding_cases")
    op.drop_table("transaction_batches")
    op.drop_table("invoices")
    op.drop_table("workflow_runs")
