"""Real anomaly detectors for the problems SMEs actually lose money to (per Plan.md's
explicit ask + industry research: duplicate payments, invoice mismatches, missing
onboarding documents, unusual/near-duplicate transactions). These are algorithmic —
not keyword stubs — and back POST /v1/compliance/scan-documents.

Duplicate payment detection follows the "exact vs near-duplicate" pattern used by
real AP fraud tools: match on (supplier, amount, date-proximity) rather than only
exact invoice-number matches, since near-duplicates (typo'd invoice numbers, split
invoices, resubmissions) are the more common and expensive real-world pattern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional


@dataclass
class Transaction:
    id: str
    supplier: str
    amount: float
    date: datetime
    invoice_number: Optional[str] = None
    po_number: Optional[str] = None
    description: str = ""


@dataclass
class PurchaseOrder:
    po_number: str
    supplier: str
    amount: float
    line_items: List[Dict[str, Any]] = field(default_factory=list)


def _name_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def detect_duplicate_payments(
    transactions: List[Transaction],
    amount_tolerance_pct: float = 0.02,
    date_window_days: int = 10,
    supplier_similarity_threshold: float = 0.85,
) -> List[Dict[str, Any]]:
    """Pairwise near-duplicate scan: same-ish supplier, same-ish amount, close dates.
    O(n^2) is fine at SME transaction volumes (hundreds-low thousands per batch);
    for larger batches, pre-bucket by rounded amount before pairwise comparison."""
    findings = []
    n = len(transactions)
    for i in range(n):
        for j in range(i + 1, n):
            t1, t2 = transactions[i], transactions[j]
            if abs((t1.date - t2.date).days) > date_window_days:
                continue
            supplier_sim = _name_similarity(t1.supplier, t2.supplier)
            if supplier_sim < supplier_similarity_threshold:
                continue
            if t1.amount == 0:
                continue
            amount_diff_pct = abs(t1.amount - t2.amount) / max(abs(t1.amount), 1e-9)
            if amount_diff_pct > amount_tolerance_pct:
                continue

            exact = (
                t1.invoice_number and t2.invoice_number
                and t1.invoice_number.strip().lower() == t2.invoice_number.strip().lower()
            )
            findings.append({
                "type": "duplicate_payment",
                "severity": "critical" if exact else "high",
                "match_kind": "exact_invoice_match" if exact else "near_duplicate",
                "transaction_ids": [t1.id, t2.id],
                "supplier_similarity": round(supplier_sim, 3),
                "amount_diff_pct": round(amount_diff_pct, 4),
                "days_apart": abs((t1.date - t2.date).days),
                "amount": t1.amount,
                "supplier": t1.supplier,
                "finding": (
                    f"Possible duplicate payment: {t1.supplier} charged ₹{t1.amount:,.2f} "
                    f"twice within {abs((t1.date - t2.date).days)} day(s) "
                    f"({'identical invoice number' if exact else f'{round(supplier_sim*100)}% supplier name match'})."
                ),
            })
    return findings


def detect_invoice_po_mismatch(
    transactions: List[Transaction],
    purchase_orders: List[PurchaseOrder],
    amount_tolerance_pct: float = 0.03,
) -> List[Dict[str, Any]]:
    """Match invoices against POs by po_number; flag amount/supplier discrepancies."""
    po_index = {po.po_number.strip().lower(): po for po in purchase_orders if po.po_number}
    findings = []
    for t in transactions:
        if not t.po_number:
            continue
        po = po_index.get(t.po_number.strip().lower())
        if not po:
            findings.append({
                "type": "invoice_mismatch", "severity": "high",
                "transaction_id": t.id, "reason": "po_not_found",
                "finding": f"Invoice {t.invoice_number or t.id} references PO {t.po_number}, which was not found in records.",
            })
            continue

        amount_diff_pct = abs(t.amount - po.amount) / max(abs(po.amount), 1e-9)
        supplier_sim = _name_similarity(t.supplier, po.supplier)
        if amount_diff_pct > amount_tolerance_pct:
            findings.append({
                "type": "invoice_mismatch", "severity": "high" if amount_diff_pct > 0.15 else "medium",
                "transaction_id": t.id, "reason": "amount_mismatch",
                "invoiced_amount": t.amount, "po_amount": po.amount, "diff_pct": round(amount_diff_pct, 4),
                "finding": f"Invoice {t.invoice_number or t.id} amount ₹{t.amount:,.2f} differs from PO {po.po_number} amount ₹{po.amount:,.2f} by {round(amount_diff_pct*100,1)}%.",
            })
        if supplier_sim < 0.7:
            findings.append({
                "type": "invoice_mismatch", "severity": "critical",
                "transaction_id": t.id, "reason": "supplier_mismatch",
                "invoiced_supplier": t.supplier, "po_supplier": po.supplier,
                "finding": f"Invoice {t.invoice_number or t.id} supplier '{t.supplier}' does not match PO {po.po_number} supplier '{po.supplier}' — possible vendor impersonation.",
            })
    return findings


REQUIRED_ONBOARDING_DOCS = [
    "certificate_of_incorporation", "pan_card", "gst_registration",
    "bank_account_proof", "director_kyc", "board_resolution",
]


def detect_missing_documents(provided_docs: List[str], sector: Optional[str] = None) -> List[Dict[str, Any]]:
    """Flag missing mandatory onboarding documents (Plan.md's 'missing documents' anomaly)."""
    provided = {d.strip().lower().replace(" ", "_") for d in provided_docs}
    required = list(REQUIRED_ONBOARDING_DOCS)
    if sector and sector.lower() in ("nbfc", "financial services", "fintech"):
        required += ["rbi_registration", "net_owned_fund_certificate"]
    if sector and sector.lower() in ("import_export", "trading"):
        required += ["iec_certificate"]

    missing = [d for d in required if d not in provided]
    if not missing:
        return []
    return [{
        "type": "missing_documents", "severity": "high" if len(missing) > 2 else "medium",
        "missing": missing,
        "finding": f"{len(missing)} mandatory onboarding document(s) missing: {', '.join(d.replace('_', ' ').title() for d in missing)}.",
    }]


def detect_unusual_transaction_pattern(
    transactions: List[Transaction],
    historical_avg_amount: Optional[float] = None,
    historical_avg_monthly_count: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Flag transactions that deviate sharply from historical norms (z-score-lite)."""
    if not transactions:
        return []
    amounts = [t.amount for t in transactions]
    avg = historical_avg_amount if historical_avg_amount is not None else (sum(amounts) / len(amounts))
    findings = []
    for t in transactions:
        if avg > 0 and t.amount > avg * 5:
            findings.append({
                "type": "unusual_transaction", "severity": "high",
                "transaction_id": t.id, "amount": t.amount, "baseline_avg": round(avg, 2),
                "finding": f"Transaction of ₹{t.amount:,.2f} to {t.supplier} is {round(t.amount/avg,1)}x the baseline average (₹{avg:,.2f}).",
            })
    if historical_avg_monthly_count and len(transactions) > historical_avg_monthly_count * 3:
        findings.append({
            "type": "unusual_transaction", "severity": "medium",
            "finding": f"Transaction volume ({len(transactions)}) is {round(len(transactions)/historical_avg_monthly_count,1)}x the historical monthly average.",
        })
    return findings


def scan_all(
    transactions: List[Transaction],
    purchase_orders: Optional[List[PurchaseOrder]] = None,
    provided_docs: Optional[List[str]] = None,
    sector: Optional[str] = None,
) -> Dict[str, Any]:
    """Run every document/transaction anomaly detector and return a unified result,
    including which Stage-0 flag names each finding maps to (for feeding into the
    ml/pipeline anomaly scorer)."""
    dup = detect_duplicate_payments(transactions)
    mismatch = detect_invoice_po_mismatch(transactions, purchase_orders or [])
    missing = detect_missing_documents(provided_docs or [])
    unusual = detect_unusual_transaction_pattern(transactions)

    all_findings = dup + mismatch + missing + unusual
    flag_map = {
        "duplicate_payment": "structuring_pattern",
        "invoice_mismatch": "invoice_mismatch",
        "missing_documents": "shell_company_indicator",
        "unusual_transaction": "unusual_sector_activity",
    }
    mapped_flags = sorted({flag_map[f["type"]] for f in all_findings if f["type"] in flag_map})

    return {
        "total_findings": len(all_findings),
        "duplicate_payments": dup,
        "invoice_mismatches": mismatch,
        "missing_documents": missing,
        "unusual_transactions": unusual,
        "mapped_stage0_flags": mapped_flags,
        "requires_human_approval": any(f["severity"] == "critical" for f in all_findings),
    }
