"""POST /v1/vendors/onboard — KYC/KYB vendor onboarding workflow.

Requirements: 4.1–4.6

Workflow:
  1. Accept vendor_name, vendor_gstin, vendor_pan, sector, documents (UploadFile list)
  2. Create VendorOnboardingCase record (kyc_status=in_review initially)
  3. Call OnboardingAgent.run() → missing_documents, pep_flags, ubo_issues
  4. If pep_flags non-empty → risk_tier=critical, create ApprovalRequest unconditionally
  5. Set kyc_status: escalated (pep_flags OR ubo_issues), in_review (missing docs only),
     approved (no flags, no issues, no missing docs)
  6. Append AuditTrailEntry on every status transition: vendor_case_created, kyc_status_set
  7. Persist all fields to vendor_onboarding_cases table; rollback on exception
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.onboarding_agent import OnboardingAgent
from app.core.security import get_db_user
from app.db.models import ApprovalRequest, AuditTrailEntry, VendorOnboardingCase
from app.db.session import get_db

log = structlog.get_logger()
router = APIRouter()


# ──────────────────────────────── Pydantic schemas ────────────────────────────


class VendorOnboardRequest(BaseModel):
    """Form-based request is handled via FastAPI Form/File params directly on the
    endpoint; this model is provided for documentation / downstream re-use."""

    vendor_name: str
    vendor_gstin: Optional[str] = None
    vendor_pan: Optional[str] = None
    sector: Optional[str] = None


class VendorOnboardResponse(BaseModel):
    case_id: str
    vendor_name: str
    kyc_status: str           # in_review | approved | escalated
    risk_tier: Optional[str]  # critical | high | medium | low | unknown | None
    missing_documents: List[str]
    pep_flags: List[str]
    ubo_issues: List[str]
    requires_approval: bool
    approval_id: Optional[str]


# ──────────────────────────────── Helpers ─────────────────────────────────────


def _safe_uuid(v: Any) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(v)) if v else None
    except Exception:
        return None


def _append_audit(
    db: AsyncSession,
    action: str,
    actor: str,
    entity_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditTrailEntry:
    """Create and add an AuditTrailEntry to the session (caller must commit)."""
    entry = AuditTrailEntry(
        action=action,
        actor=actor,
        entity_type="vendor_onboarding_case",
        entity_id=entity_id,
        timestamp=datetime.now(timezone.utc),
        metadata_=metadata or {},
    )
    db.add(entry)
    return entry


# ──────────────────────────────── Endpoint ────────────────────────────────────


@router.post("/vendors/onboard", response_model=VendorOnboardResponse)
async def onboard_vendor(
    vendor_name: str = Form(...),
    vendor_gstin: Optional[str] = Form(None),
    vendor_pan: Optional[str] = Form(None),
    sector: Optional[str] = Form(None),
    documents: List[UploadFile] = File(default=[]),
    user: Dict[str, Any] = Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> VendorOnboardResponse:
    """
    Onboard a new vendor with KYC/KYB checks.

    Steps:
      1. Create a VendorOnboardingCase with kyc_status='in_review'.
      2. Read uploaded document bytes and pass them to OnboardingAgent.
      3. Derive missing_documents, pep_flags, ubo_issues from agent helpers.
      4. Determine risk_tier and kyc_status based on findings.
      5. If pep_flags present: risk_tier=critical + create ApprovalRequest(status=pending).
      6. Write two AuditTrailEntry rows: vendor_case_created and kyc_status_set.
      7. Persist everything; rollback on any exception.
    """
    user_db_id = _safe_uuid(user.get("db_id") or user.get("id"))
    actor = user.get("email") or user.get("id") or "system"

    log.info("vendors.onboard.start", vendor_name=vendor_name, actor=actor)

    try:
        # ── Step 1: Create the case record (initial kyc_status=in_review) ────
        case = VendorOnboardingCase(
            user_id=user_db_id,
            vendor_name=vendor_name,
            vendor_gstin=vendor_gstin,
            vendor_pan=vendor_pan,
            sector=sector,
            kyc_status="in_review",
            risk_tier=None,
            missing_documents=[],
            pep_flags=[],
            ubo_issues=[],
            requires_approval=False,
            approval_id=None,
        )
        db.add(case)
        await db.flush()  # obtain case.id without committing yet
        case_id_str = str(case.id)

        # Audit: case created
        _append_audit(
            db,
            action="vendor_case_created",
            actor=actor,
            entity_id=case_id_str,
            metadata={
                "vendor_name": vendor_name,
                "vendor_gstin": vendor_gstin,
                "vendor_pan": vendor_pan,
                "sector": sector,
                "document_count": len(documents),
            },
        )

        # ── Step 2: Read document bytes and build matter_docs for agent ───────
        matter_docs: List[Dict[str, Any]] = []
        for upload in documents:
            try:
                content_bytes = await upload.read()
                content_text = content_bytes.decode("utf-8", errors="replace")
            except Exception as exc:
                log.warning(
                    "vendors.onboard.doc_read_error",
                    filename=upload.filename,
                    error=str(exc),
                )
                content_text = ""
            matter_docs.append(
                {
                    "filename": upload.filename,
                    "content_type": upload.content_type,
                    "content": content_text,
                }
            )

        # ── Step 3: Run OnboardingAgent ───────────────────────────────────────
        agent_query = (
            f"Vendor onboarding: {vendor_name}. "
            f"GSTIN: {vendor_gstin or 'N/A'}. "
            f"PAN: {vendor_pan or 'N/A'}. "
            f"Sector: {sector or 'N/A'}."
        )

        agent = OnboardingAgent()
        try:
            await agent.run(
                query=agent_query,
                packs=[],
                matter_docs=matter_docs,
            )
        except Exception as exc:
            log.error("vendors.onboard.agent_error", error=str(exc))

        # Extract structured findings directly from agent helper methods.
        # OnboardingAgent.run() returns an AgentOutput with only a reasoning
        # string; the structured lists are produced by the private helpers which
        # we call here to get machine-readable results.
        try:
            missing_documents: List[str] = agent._check_document_gaps(matter_docs)
            pep_flags: List[str] = agent._check_pep_sanctions(agent_query, matter_docs)
            ubo_issues: List[str] = agent._check_ubo(matter_docs)
        except Exception as exc:
            log.warning("vendors.onboard.agent_extraction_error", error=str(exc))
            missing_documents = []
            pep_flags = []
            ubo_issues = []

        # ── Step 4: Determine risk_tier ───────────────────────────────────────
        # pep_flags → critical (highest severity)
        # ubo_issues or missing_documents → high
        # clean → low
        if pep_flags:
            risk_tier: Optional[str] = "critical"
        elif ubo_issues or missing_documents:
            risk_tier = "high"
        else:
            risk_tier = "low"

        # ── Step 5: Determine kyc_status ──────────────────────────────────────
        # Spec: escalated if pep_flags OR ubo_issues;
        #       in_review if missing_documents only (no PEP / UBO);
        #       approved if no flags, no issues, no missing docs
        if pep_flags or ubo_issues:
            kyc_status = "escalated"
        elif missing_documents:
            kyc_status = "in_review"
        else:
            kyc_status = "approved"

        # ── Step 6a: ApprovalRequest if PEP flags present (unconditional) ─────
        approval_id: Optional[uuid.UUID] = None
        requires_approval = False

        if pep_flags:
            requires_approval = True
            approval = ApprovalRequest(
                requested_by_user_id=user_db_id,
                action_type="vendor_kyc_escalation",
                risk_level="critical",
                payload={
                    "case_id": case_id_str,
                    "vendor_name": vendor_name,
                    "pep_flags": pep_flags,
                    "ubo_issues": ubo_issues,
                },
                reason=(
                    f"Vendor '{vendor_name}' triggered PEP/sanctions flags: "
                    f"{', '.join(pep_flags)}. Manual KYC review required."
                ),
                status="pending",
            )
            db.add(approval)
            await db.flush()
            approval_id = approval.id

        # ── Step 6b: Persist findings to the case record ──────────────────────
        case.kyc_status = kyc_status
        case.risk_tier = risk_tier
        case.missing_documents = missing_documents
        case.pep_flags = pep_flags
        case.ubo_issues = ubo_issues
        case.requires_approval = requires_approval
        case.approval_id = approval_id

        # Audit: kyc_status set
        _append_audit(
            db,
            action="kyc_status_set",
            actor=actor,
            entity_id=case_id_str,
            metadata={
                "kyc_status": kyc_status,
                "risk_tier": risk_tier,
                "missing_documents": missing_documents,
                "pep_flags": pep_flags,
                "ubo_issues": ubo_issues,
                "requires_approval": requires_approval,
                "approval_id": str(approval_id) if approval_id else None,
            },
        )

        await db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        log.error("vendors.onboard.error", error=str(exc), vendor_name=vendor_name)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Vendor onboarding failed") from exc

    log.info(
        "vendors.onboard.complete",
        case_id=case_id_str,
        kyc_status=kyc_status,
        risk_tier=risk_tier,
        pep_flags=pep_flags,
    )

    return VendorOnboardResponse(
        case_id=case_id_str,
        vendor_name=vendor_name,
        kyc_status=kyc_status,
        risk_tier=risk_tier,
        missing_documents=missing_documents,
        pep_flags=pep_flags,
        ubo_issues=ubo_issues,
        requires_approval=requires_approval,
        approval_id=str(approval_id) if approval_id else None,
    )


@router.get("/vendors")
async def list_vendor_cases(
    kyc_status: Optional[str] = None,
    limit: int = 50,
    user: Dict[str, Any] = Depends(get_db_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """List vendor onboarding cases for the authenticated user, most recent first."""
    from sqlalchemy import select, desc

    user_db_id = _safe_uuid(user.get("db_id") or user.get("id"))
    stmt = select(VendorOnboardingCase).where(VendorOnboardingCase.user_id == user_db_id)
    if kyc_status:
        stmt = stmt.where(VendorOnboardingCase.kyc_status == kyc_status)
    stmt = stmt.order_by(desc(VendorOnboardingCase.created_at)).limit(limit)

    result = await db.execute(stmt)
    cases = result.scalars().all()

    return {
        "total": len(cases),
        "cases": [
            {
                "case_id": str(c.id),
                "vendor_name": c.vendor_name,
                "vendor_gstin": c.vendor_gstin,
                "sector": c.sector,
                "kyc_status": c.kyc_status,
                "risk_tier": c.risk_tier,
                "missing_documents": c.missing_documents,
                "pep_flags": c.pep_flags,
                "ubo_issues": c.ubo_issues,
                "requires_approval": c.requires_approval,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in cases
        ],
    }
