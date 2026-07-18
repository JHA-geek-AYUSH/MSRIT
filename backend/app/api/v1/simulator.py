"""Penalty Simulator — calculates regulatory fine exposure for 10 violation scenarios
as specified in Plan.md Section 8.

Each scenario has base_fine, per_day_fine, max_fine, imprisonment_months,
and aggravating factors. Calculation logic:

    total = base_fine + (days_since_breach × per_day_fine)
    total × aggravating_multiplier (1.0–3.0 based on repeat, volume, sector)
    capped at max_fine
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime, date

from app.core.security import current_user
import structlog

log = structlog.get_logger()
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════
# 10 Violation Scenarios (matching Plan.md Section 8)
# ═══════════════════════════════════════════════════════════════════
SCENARIOS = [
    {
        "id": "ctr_breach",
        "name": "Cash Transaction Reporting Failure",
        "rule_code": "AML-001",
        "rule_name": "Cash Transaction Reporting (CTR)",
        "description": "Failed to report a cash transaction exceeding ₹10 lakh to FIU-IND within 7 days.",
        "base_fine_inr": 100_000,
        "per_day_fine_inr": 10_000,
        "max_fine_inr": 1_000_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_volume", "concealment"],
        "references": ["PMLA Section 12", "FIU-IND Circular 2023-04"],
    },
    {
        "id": "str_failure",
        "name": "Suspicious Transaction Report Not Filed",
        "rule_code": "AML-003",
        "rule_name": "Suspicious Transaction Reporting (STR)",
        "description": "Failed to file STR with FIU-IND despite clear suspicious indicators within 7 working days.",
        "base_fine_inr": 500_000,
        "per_day_fine_inr": 25_000,
        "max_fine_inr": 5_000_000,
        "imprisonment_months": 7,
        "aggravating_factors": ["repeat_offence", "high_volume", "concealment", "tipping_off"],
        "references": ["PMLA Section 12", "PMLA Rules 2013, Rule 8"],
    },
    {
        "id": "kyc_non_compliance",
        "name": "KYC Documentation Incomplete",
        "rule_code": "KYC-002",
        "rule_name": "PEP Screening / Customer Due Diligence",
        "description": "Onboarding completed without required KYC documents — no PAN, Aadhaar, or address proof on record.",
        "base_fine_inr": 200_000,
        "per_day_fine_inr": 5_000,
        "max_fine_inr": 1_000_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_risk_customer"],
        "references": ["RBI KYC Master Direction 2016, Section 20-25"],
    },
    {
        "id": "gst_late_filing",
        "name": "GST Return Filed Late (>90 days)",
        "rule_code": "GST-001",
        "rule_name": "GST Return Filing Timeliness",
        "description": "GSTR-3B/GSTR-1 filed more than 90 days after due date. Late fee + interest applicable.",
        "base_fine_inr": 50_000,
        "per_day_fine_inr": 200,
        "max_fine_inr": 500_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_volume", "intentional_evasion"],
        "references": ["GST Act 2017, Section 37-39"],
    },
    {
        "id": "fema_violation",
        "name": "Unreported Foreign Remittance",
        "rule_code": "FEMA-001",
        "rule_name": "Unregistered Cross-Border Transfers",
        "description": "International remittance sent without proper purpose codes or RBI reporting.",
        "base_fine_inr": 300_000,
        "per_day_fine_inr": 5_000,
        "max_fine_inr": 3_000_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_value", "concealment"],
        "references": ["FEMA 1999, Section 5", "FEMA 1999, Section 13"],
    },
    {
        "id": "section_269st",
        "name": "Cash Receipt Above ₹2 Lakh (Section 269ST)",
        "rule_code": "IT-001",
        "rule_name": "Cash Transaction Limit (Section 269ST)",
        "description": "Received cash payment exceeding ₹2 lakh from a single person in a single day/transaction.",
        "base_fine_inr": 200_000,
        "per_day_fine_inr": 0,
        "max_fine_inr": 200_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_volume", "intentional_evasion"],
        "references": ["Income Tax Act 1961, Section 269ST", "Section 271DA"],
    },
    {
        "id": "structuring",
        "name": "Transaction Structuring (Smurfing)",
        "rule_code": "AML-002",
        "rule_name": "Structuring / Smurfing Detection",
        "description": "Multiple cash transactions just below ₹10 lakh threshold designed to evade CTR requirements.",
        "base_fine_inr": 1_000_000,
        "per_day_fine_inr": 50_000,
        "max_fine_inr": 10_000_000,
        "imprisonment_months": 84,
        "aggravating_factors": ["repeat_offence", "high_volume", "organized_network", "intentional_evasion"],
        "references": ["PMLA Section 3", "PMLA Section 4"],
    },
    {
        "id": "pep_undisclosed",
        "name": "Undisclosed PEP Director",
        "rule_code": "KYC-002",
        "rule_name": "PEP Screening",
        "description": "Politically Exposed Person onboarded as director without Enhanced Due Diligence (EDD).",
        "base_fine_inr": 500_000,
        "per_day_fine_inr": 10_000,
        "max_fine_inr": 5_000_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "high_risk_customer", "concealment"],
        "references": ["RBI KYC Master Direction 2016, Section 27", "FATF Recommendation 12"],
    },
    {
        "id": "beneficial_owner",
        "name": "Beneficial Ownership Non-Disclosure",
        "rule_code": "CORP-003",
        "rule_name": "Beneficial Ownership Register",
        "description": "Failed to maintain register of significant beneficial owners or file BEN-2 with ROC.",
        "base_fine_inr": 100_000,
        "per_day_fine_inr": 500,
        "max_fine_inr": 500_000,
        "imprisonment_months": 0,
        "aggravating_factors": ["repeat_offence", "concealment"],
        "references": ["Companies Act 2013, Section 90", "Beneficial Ownership Rules 2018"],
    },
    {
        "id": "shell_company",
        "name": "Shell Company Activity Detected",
        "rule_code": "AML-004",
        "rule_name": "Shell Company Indicators",
        "description": "Entity with high turnover, no employees, single director — classic shell company pattern.",
        "base_fine_inr": 2_000_000,
        "per_day_fine_inr": 100_000,
        "max_fine_inr": 50_000_000,
        "imprisonment_months": 84,
        "aggravating_factors": ["repeat_offence", "high_volume", "organized_network", "concealment", "money_laundering"],
        "references": ["PMLA Section 3", "PMLA Section 4"],
    },
]


class PenaltySimRequest(BaseModel):
    """Request to simulate a penalty for a specific violation scenario."""
    scenario_id: str = Field(..., description="Scenario ID (e.g. 'ctr_breach', 'structuring', 'shell_company')")
    days_since_breach: int = Field(default=30, ge=0, le=3650, description="Days since the breach occurred")
    aggravating_factors: List[str] = Field(default_factory=list, description="Active aggravating factors")
    transaction_volume: Optional[float] = Field(default=None, description="Monthly transaction volume (for volume-based multipliers)")
    sector_risk_score: Optional[float] = Field(default=None, ge=0, le=1.0, description="Sector risk score (0-1)")
    repeat_offence: bool = Field(default=False, description="Is this a repeat offence?")


class AggravatingDetail(BaseModel):
    factor: str
    multiplier: float
    reason: str


class PenaltySimResponse(BaseModel):
    scenario_id: str
    scenario_name: str
    rule_code: str
    rule_name: str
    description: str
    base_fine: int
    per_day_fine: int
    max_fine: int
    days_since_breach: int
    time_penalty: int
    aggravating_multiplier: float
    aggravating_details: List[AggravatingDetail]
    total_fine: int
    imprisonment_risk: bool
    imprisonment_months: int
    capped: bool
    verdict: str
    references: List[str]
    calculated_at: str


def _calculate_aggravating_multiplier(
    request: PenaltySimRequest,
    scenario: Dict[str, Any],
) -> tuple[float, List[AggravatingDetail]]:
    """Calculate total aggravating multiplier based on active factors.
    
    Base multiplier is 1.0. Each factor adds 0.2-0.5 based on severity.
    Maximum multiplier is 3.0.
    """
    multiplier = 1.0
    details: List[AggravatingDetail] = []

    factor_multipliers = {
        "repeat_offence": (0.5, "Repeat offence — 50% penalty enhancement"),
        "high_volume": (0.3, "High transaction volume — 30% penalty enhancement"),
        "high_value": (0.4, "High value involved — 40% penalty enhancement"),
        "concealment": (0.5, "Active concealment of breach — 50% penalty enhancement"),
        "intentional_evasion": (0.5, "Intentional tax/regulatory evasion — 50% penalty enhancement"),
        "high_risk_customer": (0.3, "High-risk customer profile — 30% penalty enhancement"),
        "organized_network": (0.5, "Organized network involvement — 50% penalty enhancement"),
        "tipping_off": (0.4, "Customer was tipped off about STR — 40% penalty enhancement"),
        "money_laundering": (0.5, "Proceeds of crime suspected — 50% penalty enhancement"),
    }

    # From request
    active_factors = set(request.aggravating_factors)

    if request.repeat_offence:
        active_factors.add("repeat_offence")

    # Additional factors from scenario defaults
    for factor in scenario.get("aggravating_factors", []):
        if factor in ("repeat_offence",) and request.repeat_offence:
            active_factors.add(factor)
        elif factor in ("high_volume",) and request.transaction_volume and request.transaction_volume > 500:
            active_factors.add(factor)
        elif factor not in ("repeat_offence",):
            active_factors.add(factor)

    for factor in active_factors:
        if factor in factor_multipliers:
            add, reason = factor_multipliers[factor]
            multiplier += add
            details.append(AggravatingDetail(factor=factor, multiplier=1.0 + add, reason=reason))

    # Sector risk boost
    if request.sector_risk_score and request.sector_risk_score > 0.7:
        sector_boost = (request.sector_risk_score - 0.7) * 0.5  # 0.1 max for high-risk sectors
        multiplier += sector_boost
        details.append(AggravatingDetail(
            factor="sector_risk",
            multiplier=1.0 + sector_boost,
            reason=f"High-risk sector ({request.sector_risk_score:.0%} risk score) — {sector_boost:.0%} enhancement",
        ))

    return min(3.0, multiplier), details


@router.get("/compliance/penalty-scenarios")
async def list_penalty_scenarios(user=Depends(current_user)):
    """List all 10 penalty violation scenarios with base parameters."""
    return {
        "total": len(SCENARIOS),
        "scenarios": [
            {
                "id": s["id"],
                "name": s["name"],
                "rule_code": s["rule_code"],
                "rule_name": s["rule_name"],
                "description": s["description"],
                "base_fine_inr": s["base_fine_inr"],
                "per_day_fine_inr": s["per_day_fine_inr"],
                "max_fine_inr": s["max_fine_inr"],
                "imprisonment_months": s["imprisonment_months"],
                "aggravating_factors": s["aggravating_factors"],
            }
            for s in SCENARIOS
        ],
    }


@router.post("/compliance/penalty-sim", response_model=PenaltySimResponse)
async def run_penalty_simulation(req: PenaltySimRequest, user=Depends(current_user)):
    """Run penalty simulation for a specific violation scenario.
    
    Calculation:
        1. base_fine
        2. + (days_since_breach × per_day_fine)
        3. × aggravating_multiplier (1.0–3.0 based on factors)
        4. capped at max_fine
    
    Returns total fine, imprisonment risk, and detailed breakdown.
    """
    scenario = next((s for s in SCENARIOS if s["id"] == req.scenario_id), None)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario '{req.scenario_id}' not found. Use GET /v1/compliance/penalty-scenarios to list all.")

    base_fine = scenario["base_fine_inr"]
    per_day_fine = scenario["per_day_fine_inr"]
    max_fine = scenario["max_fine_inr"]

    # Time component
    days = min(req.days_since_breach, 3650)  # Cap at 10 years
    time_penalty = days * per_day_fine

    # Aggravating factors
    agg_multiplier, agg_details = _calculate_aggravating_multiplier(req, scenario)

    # Total before cap
    total_before_cap = int((base_fine + time_penalty) * agg_multiplier)
    capped = total_before_cap > max_fine
    total_fine = min(max_fine, total_before_cap)

    # Verdict
    imprisonment = scenario["imprisonment_months"] > 0

    if total_fine == 0:
        verdict = "No penalty applicable."
    elif total_fine >= max_fine * 0.8:
        verdict = f"Maximum penalty applicable. Exposure: ₹{total_fine:,}. {'Imprisonment risk: ' + str(scenario['imprisonment_months']) + ' months.' if imprisonment else 'No imprisonment risk.'}"
    elif imprisonment:
        verdict = f"Significant penalty exposure: ₹{total_fine:,}. Imprisonment risk: {scenario['imprisonment_months']} months. Immediate legal counsel advised."
    elif total_fine > 500_000:
        verdict = f"High penalty exposure: ₹{total_fine:,}. Recommend voluntary disclosure and compounding."
    else:
        verdict = f"Moderate penalty exposure: ₹{total_fine:,}. Consider regularisation within 30 days."

    log.info("penalty_sim.complete", scenario=req.scenario_id, total=total_fine, capped=capped)

    return PenaltySimResponse(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        rule_code=scenario["rule_code"],
        rule_name=scenario["rule_name"],
        description=scenario["description"],
        base_fine=base_fine,
        per_day_fine=per_day_fine,
        max_fine=max_fine,
        days_since_breach=days,
        time_penalty=time_penalty,
        aggravating_multiplier=round(agg_multiplier, 2),
        aggravating_details=agg_details,
        total_fine=total_fine,
        imprisonment_risk=imprisonment,
        imprisonment_months=scenario["imprisonment_months"],
        capped=capped,
        verdict=verdict,
        references=scenario.get("references", []),
        calculated_at=datetime.utcnow().isoformat(),
    )


@router.post("/compliance/simulation-for-assessment")
async def simulate_for_assessment(
    scenario_id: str,
    assessment: Dict[str, Any],
    user=Depends(current_user),
):
    """Convenience endpoint: pass an assessment result + scenario to auto-calculate
    penalty based on assessment risk tier and sector."""
    from app.ml.risk_model_runner import extract_financial_features
    features = extract_financial_features(str(assessment))

    # Build a PenaltySimRequest from the assessment features
    req = PenaltySimRequest(
        scenario_id=scenario_id,
        days_since_breach=30,
        aggravating_factors=["high_volume"] if features.get("monthly_txn_volume", 0) > 500 else [],
        transaction_volume=features.get("monthly_txn_volume"),
        sector_risk_score=features.get("sector_risk_score"),
        repeat_offence=False,
    )
    return await run_penalty_simulation(req, user)
