"""
UK Retirement Planner — FastAPI Backend (Cloud Run)

Routes:
  GET  /api/me              — auth status
  POST /api/simulate         — run simulation engine
  GET  /api/scenarios        — list user's scenarios
  POST /api/scenarios        — save a scenario
  GET  /api/scenarios/{id}   — load a scenario
  DELETE /api/scenarios/{id} — delete a scenario
"""

import json
import time
import uuid
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from models import SimulationRequest, UserProfile
from engine import run_simulation
from auth import verify_token, get_user_email

from google.cloud import firestore

# ---------------------------------------------------------------------------
# App & Middleware
# ---------------------------------------------------------------------------
app = FastAPI(title="UK Retirement Planner API")

ALLOWED_ORIGINS = [
    "https://uk-retirement-planner.web.app",
    "https://uk-retirement-planner.firebaseapp.com",
    "http://localhost:5173",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Firestore client — uses Application Default Credentials on Cloud Run
db = firestore.Client()


# ---------------------------------------------------------------------------
# Auth Helper
# ---------------------------------------------------------------------------
def _get_user(request: Request) -> Optional[str]:
    """Extract and verify the Firebase ID token, return user email or None."""
    auth_header = request.headers.get("Authorization")
    decoded = verify_token(auth_header)
    return get_user_email(decoded)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/me")
async def me(request: Request):
    email = _get_user(request)
    if email:
        return {"authenticated": True, "email": email, "local": False}
    return {"authenticated": False, "email": None, "local": False}


@app.post("/api/simulate")
async def simulate(req: SimulationRequest):
    try:
        result = run_simulation(req)
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}")

@app.get("/api/profile")
async def get_profile(request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc = db.collection("users").document(email).get()
    if doc.exists:
        return {"success": True, "data": doc.to_dict()}
    return {"success": True, "data": UserProfile().dict()}

@app.post("/api/profile")
async def save_profile(request: Request, profile: UserProfile):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    db.collection("users").document(email).set(profile.dict())
    return {"success": True}

@app.get("/api/plans")
async def list_plans(request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        search_email = email.lower()
        docs = db.collection("plans").where("user_email", "==", search_email).stream()
        plans = []
        for doc in docs:
            d = doc.to_dict()
            plans.append({
                "id": doc.id,
                "name": d.get("name"),
                "last_modified": d.get("last_modified", 0),
                "scenarios": [s.get("name") for s in d.get("data", {}).get("scenarios", [])]
            })
        plans.sort(key=lambda x: x['last_modified'], reverse=True)
        return {"success": True, "data": plans}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/api/plans")
async def save_plan(request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    body = await request.json()
    plan_id = body.get("data", {}).get("id") or str(uuid.uuid4())
    doc = {
        "user_email": email,
        "name": body.get("name"),
        "data": body.get("data"),
        "last_modified": time.time(),
    }
    db.collection("plans").document(plan_id).set(doc)
    return {"success": True, "data": {"id": plan_id}}

@app.get("/api/plans/{plan_id}")
async def load_plan(plan_id: str, request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc = db.collection("plans").document(plan_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Plan not found")
    data = doc.to_dict()
    if data.get("user_email") != email:
        raise HTTPException(status_code=403, detail="Not your plan")
    return {"success": True, "data": data}

@app.delete("/api/plans/{plan_id}")
async def delete_plan(plan_id: str, request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")
    doc_ref = db.collection("plans").document(plan_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Plan not found")
    if doc.to_dict().get("user_email") != email:
        raise HTTPException(status_code=403, detail="Not your plan")
    doc_ref.delete()
    return {"success": True}


@app.get("/api/scenarios")
async def list_scenarios(request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        # Lowercase email to ensure matching (migration and auth casing can vary)
        search_email = email.lower()
        
        docs = (
            db.collection("scenarios")
            .where("user_email", "==", search_email)
            .stream()
        )

        scenarios = []
        for doc in docs:
            d = doc.to_dict()
            scenarios.append({
                "id": doc.id,
                "name": d.get("name"),
                "last_modified": d.get("last_modified", 0),
            })
        
        # Sort manually in Python to bypass Firestore composite index requirement
        scenarios.sort(key=lambda x: x['last_modified'], reverse=True)
        
        return {"success": True, "data": scenarios}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@app.post("/api/scenarios")
async def save_scenario(request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    body = await request.json()
    scenario_id = str(uuid.uuid4())
    doc = {
        "user_email": email,
        "name": body.get("name"),
        "data": body.get("data"),
        "last_modified": time.time(),
    }
    db.collection("scenarios").document(scenario_id).set(doc)
    return {"success": True, "data": {"id": scenario_id}}


@app.get("/api/scenarios/{scenario_id}")
async def load_scenario(scenario_id: str, request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc_ref = db.collection("scenarios").document(scenario_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Scenario not found")

    data = doc.to_dict()
    if data.get("user_email") != email:
        raise HTTPException(status_code=403, detail="Not your scenario")

    return {"success": True, "data": data}


@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str, request: Request):
    email = _get_user(request)
    if not email:
        raise HTTPException(status_code=401, detail="Not authenticated")

    doc_ref = db.collection("scenarios").document(scenario_id)
    doc = doc_ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Scenario not found")

    data = doc.to_dict()
    if data.get("user_email") != email:
        raise HTTPException(status_code=403, detail="Not your scenario")

    doc_ref.delete()
    return {"success": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
