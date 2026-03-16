from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import json
import uuid
from typing import List

from models import SimulationParams
from engine import run_simulation
import traceback

app = FastAPI(title="UK Retirement Planner API")

# Configure CORS for frontend access
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173,http://localhost:5174,http://127.0.0.1:5174").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request, call_next):
    import time
    start_time = time.time()
    print(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        print(f"Request finished: {request.method} {request.url} - Status: {response.status_code} - Time: {process_time:.2f}s")
        return response
    except Exception as e:
        print(f"ERROR processing request: {e}")
        import traceback
        traceback.print_exc()
        raise

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Backend is alive"}

# Root endpoint removed to allow static files to serve the UI

@app.post("/api/simulate")
def simulate(params: SimulationParams):
    print(f"Simulating for: {params.people[0].name if params.people else 'unknown'}")
    result = run_simulation(params)
    return {"success": True, "data": result}

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "scenarios")
os.makedirs(SCENARIOS_DIR, exist_ok=True)

class ScenarioSaveRequest(BaseModel):
    name: str
    data: SimulationParams

@app.get("/api/scenarios")
async def list_scenarios(request: Request):
    # Cloudflare KV access pattern
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    
    if not kv:
        # Local development fallback (mocking KV behavior)
        scenarios = []
        if os.path.exists(SCENARIOS_DIR):
            for filename in os.listdir(SCENARIOS_DIR):
                if filename.endswith(".json"):
                    with open(os.path.join(SCENARIOS_DIR, filename), "r") as f:
                        content = json.load(f)
                        scenarios.append({
                            "id": content.get("id"),
                            "name": content.get("name"),
                            "last_modified": os.path.getmtime(os.path.join(SCENARIOS_DIR, filename))
                        })
        return {"success": True, "data": scenarios}

    # Real Cloudflare KV logic
    keys = await kv.list()
    scenarios = []
    for key in keys.keys:
        val = await kv.get(key.name)
        if val:
            content = json.loads(val)
            scenarios.append({
                "id": content.get("id"),
                "name": content.get("name"),
                "last_modified": content.get("last_modified", 0)
            })
    return {"success": True, "data": scenarios}

@app.post("/api/scenarios")
async def save_scenario(req: ScenarioSaveRequest, request: Request):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    import time
    
    scenario_id = str(uuid.uuid4())
    scenario_doc = {
        "id": scenario_id,
        "name": req.name,
        "data": req.data.model_dump(),
        "last_modified": time.time()
    }
    
    if kv:
        # Save to KV
        await kv.put(scenario_id, json.dumps(scenario_doc))
    else:
        # Local fallback
        filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
        with open(filepath, "w") as f:
            json.dump(scenario_doc, f, indent=2)
            
    return {"success": True, "data": {"id": scenario_id}}

@app.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str, request: Request):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    
    if kv:
        val = await kv.get(scenario_id)
        if not val:
            raise HTTPException(status_code=404, detail="Scenario not found")
        return {"success": True, "data": json.loads(val)}
    else:
        filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail="Scenario not found")
        with open(filepath, "r") as f:
            return {"success": True, "data": json.load(f)}

@app.delete("/api/scenarios/{scenario_id}")
async def delete_scenario(scenario_id: str, request: Request):
    kv = getattr(request.state, "env", {}).get("SCENARIOS_KV")
    
    if kv:
        await kv.delete(scenario_id)
        return {"success": True}
    else:
        filepath = os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return {"success": True}
        raise HTTPException(status_code=404, detail="Scenario not found")

# Serve frontend static files
# Search for 'dist' folder in current directory or parent
base_dir = os.path.dirname(__file__)
frontend_dist = os.path.join(base_dir, "dist")

print(f"Mounting static files from: {frontend_dist}")
if os.path.exists(frontend_dist):
    try:
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
        print("Static files mounted successfully")
    except Exception as e:
        import traceback
        print(f"ERROR mounting static files: {e}")
        traceback.print_exc()
else:
    print(f"CRITICAL: Static directory not found at {frontend_dist}")

print("--- BACKEND STARTUP SEQUENCE COMPLETE ---")
