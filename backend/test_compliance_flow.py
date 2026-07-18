#!/usr/bin/env python3
"""Quick test of compliance triage endpoint."""
import asyncio
import sys
sys.path.insert(0, '/d/gemmaFin_os/backend')

from app.agents.transaction_agent import TransactionAgent
from app.agents.onboarding_agent import OnboardingAgent
from app.agents.regulatory_agent import RegulatoryAgent
from app.agents.financial_risk_agent import FinancialRiskAgent
from app.agents.report_agent import ReportAgent

async def main():
    query = "Customer transferred ₹9.8L three times in 5 days to different accounts. No clear business purpose."
    
    print("Testing compliance agents...")
    print(f"Query: {query}\n")
    
    agents = {
        "transaction": TransactionAgent(),
        "onboarding": OnboardingAgent(),
        "regulatory": RegulatoryAgent(),
        "financial_risk": FinancialRiskAgent(),
    }
    
    results = {}
    for name, agent in agents.items():
        print(f"Running {name} agent...", end=" ", flush=True)
        try:
            output = await agent.run(query, [], [])
            results[name] = output
            print(f"✓ (confidence={output['confidence']:.2f})")
        except Exception as e:
            print(f"✗ ERROR: {str(e)[:80]}")
            return False
    
    print("\nGenerating report...")
    report_agent = ReportAgent()
    try:
        report_output = await report_agent.run(query, [], [], results)
        print(f"✓ Report generated (confidence={report_output['confidence']:.2f})")
    except Exception as e:
        print(f"✗ Report failed: {str(e)[:80]}")
        return False
    
    print("\n✓ All agents working!")
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
