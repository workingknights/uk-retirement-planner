from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import uuid
from typing import List

from models import SimulationParams
from engine import run_simulation

app = FastAPI(title="UK Retirement Planner API")

# Configure CORS for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Welcome to the UK Retirement Planner API"}

@app.post("/api/simulate")
def simulate(params: SimulationParams):
    result = run_simulation(params)
    return {"success": True, "data": result}

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")
os.makedirs(SCENARIOS_DIR, exist_ok=True)

class ScenarioSaveRequest(BaseModel):
    name: str
    data: SimulationParams

@app.get("/api/scenarios")
def list_scenarios():
    scenarios = []
    for filename in os.listdir(SCENARIOS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SCENARIOS_DIR, filename)
            try:
                stat = os.stat(filepath)
                with open(filepath, "r") as f:
                    content = json.load(f)
                    scenarios.append({
                        "id": content.get("id"),
                        "name": content.get("name"),
                        "last_modified": stat.st_mtime
                    })
            except Exception as e:
                pass
    
    # Sort by last modified descending
    scenarios.sort(key=lambda x: x["last_modified"], reverse=True)
    return {"success": True, "data": scenarios}

@app.post("/api/scenarios")
def save_scenario(req: ScenarioSaveRequest):
    # Check if a scenario with the same name already exists
    scenario_id = None
    for filename in os.listdir(SCENARIOS_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SCENARIOS_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    content = json.load(f)
                    if content.get("name") == req.name:
                        scenario_id = content.get("id")
                        break
            except Exception:
                pass
                
    if not scenario_id:
        scenario_id = str(uuid.uuid4())
        
    filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
    
    scenario_doc = {
        "id": scenario_id,
        "name": req.name,
        "data": req.data.model_dump()
    }
    
    with open(filepath, "w") as f:
        json.dump(scenario_doc, f, indent=2)
        
    return {"success": True, "data": {"id": scenario_id}}

@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Scenario not found")
        
    with open(filepath, "r") as f:
        content = json.load(f)
        
    return {"success": True, "data": content}

@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: str):
    filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
        return {"success": True}
    raise HTTPException(status_code=404, detail="Scenario not found")
