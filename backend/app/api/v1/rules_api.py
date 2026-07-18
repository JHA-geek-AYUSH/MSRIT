"""API endpoints for the compliance rules catalogue."""

from fastapi import APIRouter, Depends, HTTPException
from app.core.security import current_user
from app.ml.rules_db import (
    COMPLIANCE_RULES,
    get_rules_by_framework,
    get_rule_by_code,
    get_rules_by_severity,
    get_rules_summary,
)

router = APIRouter()


@router.get("/compliance/rules")
async def list_rules(
    user=Depends(current_user),
    framework: str | None = None,
    severity: str | None = None,
    limit: int = 40,
):
    """List compliance rules, optionally filtered by framework and/or severity.

    Frameworks: PMLA, RBI_KYC, GST, FEMA, INCOME_TAX, COMPANIES_ACT
    Severity: critical, high, medium, low
    """
    rules = COMPLIANCE_RULES

    if framework:
        rules = get_rules_by_framework(framework)
    if severity:
        rules = get_rules_by_severity(severity)

    return {
        "total": len(rules),
        "summary": get_rules_summary(),
        "rules": [
            {
                "id": r["id"],
                "code": r["code"],
                "name": r["name"],
                "framework": r["framework"],
                "description": r["description"],
                "severity": r["severity"],
                "max_penalty_inr": r.get("max_penalty_inr"),
                "imprisonment_risk": r.get("imprisonment_risk", False),
            }
            for r in rules[:limit]
        ],
    }


@router.get("/compliance/rules/{rule_code}")
async def get_rule_detail(rule_code: str, user=Depends(current_user)):
    """Get full detail for a single compliance rule by code (e.g. AML-001)."""
    rule = get_rule_by_code(rule_code.upper())
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule {rule_code} not found")
    return rule
