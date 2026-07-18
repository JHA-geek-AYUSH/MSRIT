from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import JSON, TIMESTAMP, BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clerk_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, default="lawyer")
    wallet_address: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    matters: Mapped[list["Matter"]] = relationship("Matter", back_populates="user")
    user_firms: Mapped[list["UserFirm"]] = relationship("UserFirm", back_populates="user")
    billing_account: Mapped[Optional["BillingAccount"]] = relationship("BillingAccount", back_populates="user", uselist=False)
    
    __table_args__ = (
        CheckConstraint(
            "role in ('lawyer','admin','paralegal','client','finance_analyst','compliance_officer','auditor','cfo','viewer')",
            name="users_role_chk",
        ),
    )


class Firm(Base):
    __tablename__ = "firms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    gstin: Mapped[Optional[str]] = mapped_column(String)  # GST Identification Number for Indian firms
    pan: Mapped[Optional[str]] = mapped_column(String)  # PAN for Indian firms
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String)
    state: Mapped[Optional[str]] = mapped_column(String)
    pincode: Mapped[Optional[str]] = mapped_column(String)
    phone: Mapped[Optional[str]] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user_firms: Mapped[list["UserFirm"]] = relationship("UserFirm", back_populates="firm")


class UserFirm(Base):
    __tablename__ = "user_firms"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    firm_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("firms.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String, default="member")
    joined_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="user_firms")
    firm: Mapped["Firm"] = relationship("Firm", back_populates="user_firms")
    
    __table_args__ = (
        CheckConstraint("role in ('owner', 'partner', 'associate', 'member', 'intern')", name="user_firms_role_chk"),
    )


class Authority(Base):
    __tablename__ = "authorities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    court: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    neutral_cite: Mapped[Optional[str]] = mapped_column(String)
    reporter_cite: Mapped[Optional[str]] = mapped_column(String)
    date: Mapped[Optional[datetime]] = mapped_column(Date)
    bench: Mapped[Optional[str]] = mapped_column(Text)
    url: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    hash_keccak256: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="authority")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    authority_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("authorities.id", ondelete="CASCADE"))
    para_from: Mapped[Optional[int]] = mapped_column(Integer)
    para_to: Mapped[Optional[int]] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[Optional[int]] = mapped_column(Integer)
    vector_id: Mapped[Optional[str]] = mapped_column(String)
    statute_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    has_citation: Mapped[bool] = mapped_column(Boolean, default=False)

    authority: Mapped[Optional[Authority]] = relationship("Authority", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_authority", "authority_id"),
        Index("idx_chunks_statutes", "statute_tags", postgresql_using="gin"),
    )


class Matter(Base):
    __tablename__ = "matters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="matters")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"))
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    filetype: Mapped[str] = mapped_column(String, nullable=False)
    size: Mapped[Optional[int]] = mapped_column(BigInteger)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    ocr_status: Mapped[str] = mapped_column(String, default="pending")
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class Query(Base):
    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("matters.id", ondelete="CASCADE"))
    message_encrypted: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # Encrypted user input
    message: Mapped[str] = mapped_column(Text, nullable=False)  # For backward compatibility, will be deprecated
    mode: Mapped[str] = mapped_column(String, nullable=False)
    filters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("mode in ('general','precedent','limitation','draft')", name="queries_mode_chk"),
    )

    @hybrid_property
    def decrypted_message(self) -> str:
        """Get decrypted message content"""
        if self.message_encrypted:
            from app.core.encryption import decrypt_user_input
            try:
                return decrypt_user_input(self.message_encrypted)
            except Exception:
                # Fallback to unencrypted message for migration period
                return self.message
        return self.message

    def encrypt_message(self, plaintext: str, user_id: str) -> None:
        """Encrypt and store message"""
        from app.core.encryption import encrypt_user_input
        self.message_encrypted = encrypt_user_input(plaintext, user_id)
        # Keep unencrypted for migration period
        self.message = plaintext


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"))
    answer_text: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric)
    retrieval_set_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class AgentVote(Base):
    __tablename__ = "agent_votes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"))
    agent: Mapped[str] = mapped_column(String, nullable=False)
    decision_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    aligned: Mapped[Optional[bool]] = mapped_column(Boolean)
    weights_before: Mapped[Optional[dict]] = mapped_column(JSON)
    weights_after: Mapped[Optional[dict]] = mapped_column(JSON)


class OnchainProof(Base):
    __tablename__ = "onchain_proofs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    merkle_root: Mapped[str] = mapped_column(String, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String, nullable=False)
    network: Mapped[str] = mapped_column(String, nullable=False)
    block_number: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class BillingAccount(Base):
    __tablename__ = "billing_accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    plan: Mapped[str] = mapped_column(String, default="starter")
    credits_balance: Mapped[int] = mapped_column(Integer, default=0)
    renews_at: Mapped[Optional[datetime]] = mapped_column(Date)
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="billing_account")


class BillingLedger(Base):
    __tablename__ = "billing_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    credits_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric)
    description: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class PIIRecord(Base):
    """Track PII detected and redacted in user inputs"""
    __tablename__ = "pii_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    query_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("queries.id", ondelete="CASCADE"))
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    pii_type: Mapped[str] = mapped_column(String, nullable=False)  # 'aadhaar', 'pan', 'email', etc.
    detection_confidence: Mapped[float] = mapped_column(Numeric, default=1.0)
    redacted_count: Mapped[int] = mapped_column(Integer, default=1)
    original_encrypted: Mapped[Optional[dict]] = mapped_column(JSON)  # Encrypted original PII for audit
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))  # For retention policy

    @hybrid_property
    def original_value(self) -> Optional[str]:
        """Get decrypted original PII value (audit use only)"""
        if self.original_encrypted:
            from app.core.encryption import decrypt_user_input
            try:
                return decrypt_user_input(self.original_encrypted)
            except Exception:
                return None
        return None

    def encrypt_original(self, original_value: str, user_id: str) -> None:
        """Encrypt and store original PII value for audit"""
        from app.core.encryption import encrypt_user_input
        self.original_encrypted = encrypt_user_input(original_value, f"pii:{user_id}")


class DataRetentionLog(Base):
    """Track data retention and deletion activities"""
    __tablename__ = "data_retention_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    retention_type: Mapped[str] = mapped_column(String, nullable=False)  # 'soft_delete', 'hard_delete', 'crypto_shred'
    table_name: Mapped[str] = mapped_column(String, nullable=False)
    record_id: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)  # 'retention_policy', 'user_request', 'compliance'
    retention_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    deleted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ComplianceAuditLog(Base):
    """Strict Audit Flow for human review of AI triage decisions"""
    __tablename__ = "compliance_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True)
    officer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    original_tier: Mapped[str] = mapped_column(String, nullable=False)
    overridden_tier: Mapped[Optional[str]] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # 'pending', 'approved', 'rejected', 'escalated'
    comments: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))
    
    # Relationships
    run: Mapped["Run"] = relationship("Run", backref="audit_log", uselist=False)
    officer: Mapped[Optional["User"]] = relationship("User")


# ═══════════════════════════════════════════════════════════════════════════
# FinTriage AI — Plan.md Section 12 tables
# ═══════════════════════════════════════════════════════════════════════════

class Entity(Base):
    """SME / business entity profile submitted for compliance triage."""
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    business_name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[Optional[str]] = mapped_column(String)
    incorporation_date: Mapped[Optional[datetime]] = mapped_column(Date)
    annual_turnover: Mapped[Optional[float]] = mapped_column(Numeric)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)
    director_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    assessments: Mapped[list["ComplianceAssessment"]] = relationship("ComplianceAssessment", back_populates="entity")


class ComplianceAssessment(Base):
    """One pipeline run (Stage 0-3) for an entity."""
    __tablename__ = "compliance_assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    monthly_txn_volume: Mapped[Optional[float]] = mapped_column(Numeric)
    avg_ticket_size: Mapped[Optional[float]] = mapped_column(Numeric)
    cash_ratio: Mapped[Optional[float]] = mapped_column(Numeric)
    cross_border_ratio: Mapped[Optional[float]] = mapped_column(Numeric)
    late_payment_rate: Mapped[Optional[float]] = mapped_column(Numeric)
    sector_risk_score: Mapped[Optional[float]] = mapped_column(Numeric)
    anomaly_risk_score: Mapped[Optional[float]] = mapped_column(Numeric)
    risk_tier: Mapped[Optional[str]] = mapped_column(String)
    risk_score: Mapped[Optional[float]] = mapped_column(Numeric)
    confidence_pct: Mapped[Optional[int]] = mapped_column(Integer)
    feature_importance: Mapped[Optional[dict]] = mapped_column(JSON)
    detected_flags: Mapped[Optional[list]] = mapped_column(JSON)
    total_penalty_exposure_inr: Mapped[Optional[float]] = mapped_column(Numeric)
    raw_features: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    entity: Mapped[Optional["Entity"]] = relationship("Entity", back_populates="assessments")
    findings: Mapped[list["ComplianceFinding"]] = relationship("ComplianceFinding", back_populates="assessment")


class ComplianceFinding(Base):
    """Per-rule finding from Stage 2+3 for a given assessment."""
    __tablename__ = "compliance_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_assessments.id", ondelete="CASCADE"))
    rule_code: Mapped[str] = mapped_column(String, nullable=False)
    gap_score: Mapped[Optional[float]] = mapped_column(Numeric)
    cosine_similarity: Mapped[Optional[float]] = mapped_column(Numeric)
    combined_score: Mapped[Optional[float]] = mapped_column(Numeric)
    severity: Mapped[Optional[str]] = mapped_column(String)
    warning_flags: Mapped[Optional[dict]] = mapped_column(JSON)
    plain_english_finding: Mapped[Optional[str]] = mapped_column(Text)
    remediation_steps: Mapped[Optional[list]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    assessment: Mapped[Optional["ComplianceAssessment"]] = relationship("ComplianceAssessment", back_populates="findings")


class PenaltySimulationRecord(Base):
    """Persisted penalty simulator runs (Plan.md Section 8)."""
    __tablename__ = "penalty_simulations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_assessments.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    scenario_id: Mapped[str] = mapped_column(String, nullable=False)
    rule_code: Mapped[Optional[str]] = mapped_column(String)
    days_since_breach: Mapped[Optional[int]] = mapped_column(Integer)
    aggravating_factors: Mapped[Optional[list]] = mapped_column(JSON)
    base_fine: Mapped[Optional[float]] = mapped_column(Numeric)
    per_day_fine: Mapped[Optional[float]] = mapped_column(Numeric)
    total_fine: Mapped[Optional[float]] = mapped_column(Numeric)
    imprisonment_risk: Mapped[Optional[bool]] = mapped_column(Boolean)
    verdict: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class AuditReportRecord(Base):
    """Generated compliance audit reports (Plan.md Section 10)."""
    __tablename__ = "audit_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_assessments.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    report_json: Mapped[Optional[dict]] = mapped_column(JSON)
    gemma_summary: Mapped[Optional[str]] = mapped_column(Text)
    total_penalty_exposure: Mapped[Optional[float]] = mapped_column(Numeric)
    urgency_tier: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class FinTriageChatMessage(Base):
    """Agent conversation history for the FinTriage 7-tool agent (Plan.md Section 7).
    Named distinctly from the legal-chat `queries`/`runs` tables used by /v1/chat."""
    __tablename__ = "fintriage_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_assessments.id", ondelete="CASCADE"))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String, nullable=False)  # 'user' | 'agent'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_used: Mapped[Optional[str]] = mapped_column(String)
    tool_result: Mapped[Optional[dict]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)


class ApprovalRequest(Base):
    """Human-in-the-loop gate for high-risk actions (Plan.md: "high-risk actions
    always require human approval") — connector writes, critical-severity findings
    being escalated, or auto-generated external notifications all land here first.
    Nothing in app/connectors executes until a request here is status='approved'."""
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requested_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    assessment_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("compliance_assessments.id", ondelete="CASCADE"))
    action_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. 'connector_write', 'escalate_to_regulator', 'notify_external'
    connector: Mapped[Optional[str]] = mapped_column(String)  # 'sap' | 'microsoft_graph' | 'local_db' | None
    risk_level: Mapped[str] = mapped_column(String, nullable=False, default="high")  # 'medium' | 'high' | 'critical'
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")  # 'pending' | 'approved' | 'rejected'
    reviewed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewer_comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))


class ComplianceTriageRun(Base):
    """Durable record of a Track 2 triage workflow.

    Only redacted input is retained here. Source documents remain in the document
    store, where retention and access controls can be applied independently.
    """
    __tablename__ = "compliance_triage_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running", index=True)
    redacted_description: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[Optional[dict]] = mapped_column(JSON)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    overall_rating: Mapped[Optional[str]] = mapped_column(String, index=True)
    requires_str: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_edd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))



# ═══════════════════════════════════════════════════════════════════════════
# GemmaFin OS — FinOps Workflow Tables (Phase 4 DDL)
# ═══════════════════════════════════════════════════════════════════════════

class Invoice(Base):
    """Invoice processing workflow — tracks the full lifecycle from upload to approval."""
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255))
    vendor_gstin: Mapped[Optional[str]] = mapped_column(String(20))
    invoice_number: Mapped[str] = mapped_column(String(100), nullable=False)
    invoice_date: Mapped[Optional[str]] = mapped_column(String(10))  # YYYY-MM-DD
    amount_net: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    amount_gst: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    amount_total: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    po_number: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="processing")
    risk_tier: Mapped[Optional[str]] = mapped_column(String(20))
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    extraction_confidence: Mapped[float] = mapped_column(Numeric, nullable=False, default=0.0)
    raw_extracted_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('processing','extracted','validated','risk_scored','approved','rejected')",
            name="invoices_status_chk",
        ),
        CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="invoices_risk_tier_chk",
        ),
        Index("idx_invoices_user_id", "user_id"),
        Index("idx_invoices_status", "status"),
    )


class TransactionBatch(Base):
    """A batch of transactions ingested from any source (SAP, Excel, manual, etc.)."""
    __tablename__ = "transaction_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    total_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flagged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    risk_tier: Mapped[Optional[str]] = mapped_column(String(20))
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "source IN ('manual','sap','excel','outlook','csv')",
            name="transaction_batches_source_chk",
        ),
        CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="transaction_batches_risk_tier_chk",
        ),
        Index("idx_transaction_batches_user_id", "user_id"),
    )


class VendorOnboardingCase(Base):
    """KYC/KYB vendor onboarding case with PEP/UBO checks."""
    __tablename__ = "vendor_onboarding_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    vendor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vendor_gstin: Mapped[Optional[str]] = mapped_column(String(20))
    vendor_pan: Mapped[Optional[str]] = mapped_column(String(10))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    kyc_status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_review")
    risk_tier: Mapped[Optional[str]] = mapped_column(String(20))
    missing_documents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    pep_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    ubo_issues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        CheckConstraint(
            "kyc_status IN ('in_review','approved','escalated')",
            name="vendor_onboarding_cases_kyc_status_chk",
        ),
        CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="vendor_onboarding_cases_risk_tier_chk",
        ),
        Index("idx_vendor_onboarding_cases_user_id", "user_id"),
        Index("idx_vendor_onboarding_cases_kyc_status", "kyc_status"),
    )


class PolicyDocument(Base):
    """Policy documents with compliance gap analysis (AML, KYC, vendor, etc.)."""
    __tablename__ = "policy_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(50), default="1.0")
    effective_date: Mapped[Optional[str]] = mapped_column(String(10))  # YYYY-MM-DD
    document_url: Mapped[Optional[str]] = mapped_column(String(500))
    compliance_gaps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_policy_documents_user_id", "user_id"),
    )


class WorkflowRun(Base):
    """Unified workflow run tracker — one row per workflow execution regardless of type."""
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workflow_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    risk_tier: Mapped[Optional[str]] = mapped_column(String(20))
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "workflow_type IN ('invoice','transaction_batch','vendor_onboarding','policy_review','entity_assessment','full_triage')",
            name="workflow_runs_workflow_type_chk",
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','awaiting_approval')",
            name="workflow_runs_status_chk",
        ),
        CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('critical','high','medium','low','unknown')",
            name="workflow_runs_risk_tier_chk",
        ),
        Index("idx_workflow_runs_user_id", "user_id"),
        Index("idx_workflow_runs_status", "status"),
        Index("idx_workflow_runs_workflow_type", "workflow_type"),
    )


class AuditTrailEntry(Base):
    """Append-only audit trail — one row per action across all workflow types."""
    __tablename__ = "audit_trail_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    entity_type: Mapped[Optional[str]] = mapped_column(String(100))
    entity_id: Mapped[Optional[str]] = mapped_column(String(255))
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default="now()", nullable=False
    )
    # Python attr is metadata_ to avoid shadowing DeclarativeBase.metadata
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("idx_audit_trail_entries_workflow_id", "workflow_id"),
        Index("idx_audit_trail_entries_invoice_id", "invoice_id"),
        Index("idx_audit_trail_entries_entity_id", "entity_id"),
        Index("idx_audit_trail_entries_timestamp", "timestamp"),
    )
