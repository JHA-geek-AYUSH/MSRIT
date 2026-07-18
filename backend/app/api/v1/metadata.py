from __future__ import annotations

from typing import List

from fastapi import APIRouter

router = APIRouter()


@router.get("/case-types", response_model=List[str])
async def get_case_types():
    return [
        "Contract Dispute",
        "Property Law",
        "Corporate Law",
        "Criminal Defense",
        "Family Law",
        "Intellectual Property",
        "Employment Law",
        "Constitutional Law",
        "Taxation",
        "Cyber Law"
    ]


@router.get("/jurisdictions", response_model=List[str])
async def get_jurisdictions():
    return [
        "Supreme Court of India",
        "Delhi High Court",
        "Bombay High Court",
        "Karnataka High Court",
        "Madras High Court",
        "Calcutta High Court",
        "Allahabad High Court",
        "Gujarat High Court",
        "Kerala High Court",
        "Punjab and Haryana High Court",
        "Other"
    ]
