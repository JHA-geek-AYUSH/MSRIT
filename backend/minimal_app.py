"""Minimal GemmaFinOS backend - works without all the complex dependencies."""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import json
from pathlib import Path

app = FastAPI(title="GemmaFinOS Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Simple in-memory storage
DATA_FILE = Path("gemmaFin_data.json")

def load_data():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"matters": [], "queries": [], "runs": []}

def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, default=str))

# Models
class MatterCreate(BaseModel):
    title: str
    language: str = "en"

class ChatRequest(BaseModel):
    matterId: str
    message: str
    mode: str = "general"
    filters: dict = {}

# Endpoints
@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/v1/matters")
async def get_matters():
    """Get all matters"""
    data = load_data()
    return {"data": data["matters"]}

@app.post("/v1/matters")
async def create_matter(req: MatterCreate):
    """Create a new matter"""
    data = load_data()
    matter = {
        "id": f"matter_{len(data['matters'])+1}",
        "title": req.title,
        "language": req.language,
        "created_at": "2025-01-01T00:00:00"
    }
    data["matters"].append(matter)
    save_data(data)
    return matter

@app.get("/v1/matters/{matter_id}")
async def get_matter(matter_id: str):
    """Get a specific matter"""
    data = load_data()
    for m in data["matters"]:
        if m["id"] == matter_id:
            return m
    raise HTTPException(status_code=404, detail="Matter not found")

@app.post("/v1/chat")
async def chat(req: ChatRequest):
    """Chat endpoint - compliance triage"""
    data = load_data()
    
    # Create a mock response
    run_id = f"run_{len(data['runs'])+1}"
    response = {
        "answer": f"Analysis of: {req.message[:100]}...\n\nThis is a mock response. The backend is working!",
        "citations": [],
        "runId": run_id,
        "merkleRoot": None,
        "confidence": 0.85
    }
    
    # Store the run
    data["runs"].append({
        "id": run_id,
        "matter_id": req.matterId,
        "message": req.message,
        "response": response
    })
    save_data(data)
    
    return response

@app.get("/v1/conversation/{matter_id}")
async def get_conversation(matter_id: str):
    """Get conversation history"""
    data = load_data()
    messages = []
    for run in data["runs"]:
        if run["matter_id"] == matter_id:
            messages.append({
                "role": "user",
                "content": run["message"],
                "timestamp": "2025-01-01T00:00:00"
            })
            messages.append({
                "role": "assistant",
                "content": run["response"]["answer"],
                "timestamp": "2025-01-01T00:00:00"
            })
    return {"messages": messages}

@app.post("/v1/compliance/triage")
async def compliance_triage(req: dict):
    """Compliance triage endpoint"""
    description = req.get("description", "")
    mode = req.get("mode", "full")
    
    return {
        "run_id": "compliance_run_1",
        "overall_rating": "medium",
        "domains": [
            {
                "name": "Transaction",
                "rating": "medium",
                "summary": f"Analysis of: {description[:100]}",
                "confidence": 0.75
            }
        ],
        "full_report": f"Compliance Report\n\nDescription: {description}\n\nThis is a mock report.",
        "recommendations": [
            "Review transaction patterns",
            "Conduct enhanced due diligence"
        ],
        "requires_str": False,
        "requires_edd": False
    }

@app.get("/v1/analytics/dashboard")
async def get_analytics():
    """Get analytics"""
    return {
        "recent_activity": {
            "queries_last_30_days": 5,
            "documents_uploaded": 2,
            "credits_spent": 50
        },
        "quick_stats": {
            "success_rate": 0.92,
            "total_matters": 3
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("[*] Starting GemmaFinOS Backend (Minimal)")
    print("[*] http://localhost:8000")
    print("[*] API docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
